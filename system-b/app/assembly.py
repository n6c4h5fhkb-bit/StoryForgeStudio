"""Real FFmpeg assembly: normalized clips, optional still animatic, audio buses,
subtitles and inspectable edit decisions. No generation is hidden here."""
from __future__ import annotations
import json,math,shutil,subprocess,time
from pathlib import Path
from .core import ensure,uid,now,DomainError,digest
from .cinema import render_dimensions

class Assembly:
 def __init__(self,service):self.b=service;self.s=service.s;self.settings=service.settings
 def ffmpeg(self):
  exe=self.settings.read().get('ffmpeg') or shutil.which('ffmpeg')
  if not exe:
   import imageio_ffmpeg
   exe=imageio_ffmpeg.get_ffmpeg_exe()
  ensure(exe,'需要 FFmpeg');return exe
 def command(self,args,check,logfile):
  with open(logfile,'ab') as log:
   log.write(('\n$ '+' '.join(map(str,args))+'\n').encode('utf-8'));log.flush()
   proc=subprocess.Popen(list(map(str,args)),stdout=log,stderr=log)
   start=time.monotonic()
   try:
    while proc.poll() is None:
     check();ensure(time.monotonic()-start<1800,'剪辑命令超过 30 分钟','timeout',408);time.sleep(.15)
   except BaseException:
    proc.kill();proc.wait();raise
   ensure(proc.returncode==0,'FFmpeg 执行失败，见剪辑日志','ffmpeg_failed',422,{'log':str(logfile),'tail':Path(logfile).read_text(errors='replace')[-3000:]})
 def plan(self,p,data):
  b=self.b;scenes=sorted(b.list_active(p,'scene'),key=lambda x:x['order']);shotorder={x['id']:i for i,x in enumerate(scenes)};shots=sorted([shot for shot in b.list_active(p,'shot') if shot['sceneId'] in shotorder],key=lambda x:(shotorder[x['sceneId']],x['order']));selected=data.get('shotIds')
  if selected:shots=[s for s in shots if s['id'] in selected]
  shots=b.ordered_shots(p,shots)
  ensure(shots,'没有可装配的镜头');allrenders=b.list_active(p,'render');entries=[];warnings=[];cursor=0
  for shot in shots:
   rs=[r for r in allrenders if r.get('shotId')==shot['id'] and r.get('selected')]
   clip=next((r for r in reversed(rs) if r['kind']=='clip'),None)
   if not clip and data.get('allowAnimatic'):clip=next((r for r in reversed(rs) if r['kind']=='keyframe'),None)
   ensure(clip,'有镜头未终选视频；静帧预演需要显式开启 allowAnimatic','assembly_missing',409,{'shotId':shot['id']})
   if clip['freshness']=='broken':warnings.append({'shotId':shot['id'],'code':'broken_media','message':'采用的素材已受上游变化影响'})
   f=self.s.get(clip['fileId']);ensure(Path(f['path']).is_file(),'采用媒体文件丢失')
   adoption=clip.get('adoption');duration=adoption['interval']['out']-adoption['interval']['in'] if adoption else shot['duration']
   if shot.get('eventId') and clip['kind']=='clip':ensure(adoption,'先记录实际采用区间与末态再剪辑','adopted_interval',409)
   if adoption:
    import hashlib
    ensure(hashlib.sha256(Path(f['path']).read_bytes()).hexdigest()==adoption['fileHash'],'采用的视频文件已被替换，请重新审片','stale_media',409)
   entries.append({'shotId':shot['id'],'sceneId':shot['sceneId'],'renderId':clip['id'],'fileId':f['id'],'path':f['path'],'kind':clip['kind'],'sourceIn':adoption['interval']['in'] if adoption else 0,'adoptionHash':digest(adoption) if adoption else None,'start':round(cursor,3),'duration':duration,'end':round(cursor+duration,3),'hook':shot.get('hook',False),'actionLine':shot.get('actionLine','')});cursor+=duration
  style=b.style(p);asl=cursor/len(entries)
  if not style['aslRange'][0]<=asl<=style['aslRange'][1]:warnings.append({'code':'asl','message':'实际 ASL 超出风格包区间','actual':asl,'expected':style['aslRange'],'returnTo':'B4'})
  target=self.s.get(p)['targetDuration']
  if target is not None and abs(cursor-target)>max(1,target*.05):warnings.append({'code':'total_duration','message':'全片时长与目标不同','actual':cursor,'target':target,'returnTo':'B1'})
  if style.get('preset')=='vertical' and self.s.get(p).get('workflowVersion',1)<2:
   hooks=[e['start'] for e in entries if e['hook']]
   if not hooks or hooks[0]>3:warnings.append({'code':'opening_hook','message':'未标注首 3 秒钩子；请人工确认','returnTo':'B4'})
   if hooks and max([b-a for a,b in zip([0]+hooks,hooks+[cursor])])>30:warnings.append({'code':'hook_spacing','message':'钩子间隔超过 30 秒','returnTo':'B4'})
  audio=[]
  for track in data.get('audio',[]):
   f=self.s.get(track['fileId']);ensure(f['projectId']==p,'音频不属于项目');ensure(float(track.get('start',0))>=0 and 0<=float(track.get('gain',1))<=5,'音频起点或增益非法');audio.append({**track,'path':f['path']})
  value={'entries':entries,'warnings':warnings,'duration':round(cursor,3),'asl':round(asl,3),'audio':audio,'subtitles':data.get('subtitles',[]),'keepOriginalAudio':bool(data.get('keepOriginalAudio',False)),'allowAnimatic':bool(data.get('allowAnimatic',False)),'silence':data.get('silence',[]),'width':render_dimensions(style['aspectRatio'],data.get('quality','final'))[0],'height':render_dimensions(style['aspectRatio'],data.get('quality','final'))[1],'fps':int(data.get('fps',24)),'transitions':b.list_active(p,'transition')}
  ensure(value['fps'] in (24,25,30,60),'帧率不支持');value['planHash']=digest(value);return value
 def run(self,p,data,progress,check):
  plan=self.plan(p,data);ensure(data.get('planHash')==plan['planHash'],'先预览剪辑计划，再确认执行','confirmation_required',409,plan)
  if plan['warnings']:ensure(data.get('acknowledgeWarnings'), '剪辑计划含警告，请确认或返回上游调整','assembly_warning',409,plan['warnings'])
  id=uid('assembly');work=self.s.root/'media'/p/'assemblies'/id;work.mkdir(parents=True,exist_ok=True);log=work/'ffmpeg.log';ff=self.ffmpeg();w,h,fps=plan['width'],plan['height'],plan['fps'];normalized=[];count=len(plan['entries']);cursor=0
  for i,e in enumerate(plan['entries']):
   check();progress((i+.2)/(count+2)*.85,f'规范化镜头 {i+1}/{count}');out=work/f'{i:04d}.mp4';vf=f'scale={w}:{h}:force_original_aspect_ratio=decrease,pad={w}:{h}:(ow-iw)/2:(oh-ih)/2,setsar=1,fps={fps},format=yuv420p'
   args=[ff,'-y','-v','warning']
   if e['kind']=='keyframe':args+=['-loop','1','-i',e['path']]
   else:args+=['-ss',str(e.get('sourceIn',0)),'-i',e['path']];vf+=f',tpad=stop_mode=clone:stop_duration={e["duration"]}'
   args+=['-f','lavfi','-i','anullsrc=channel_layout=stereo:sample_rate=48000','-t',str(e['duration']),'-vf',vf,'-map','0:v:0']
   # Always normalize audio. Original audio is optional and retained only if a real track exists.
   has_audio=False
   if plan['keepOriginalAudio'] and e['kind']=='clip':
    try:has_audio=any(s['codec_type']=='audio' for s in self.b.gates.probe(e['path'])['streams'])
    except Exception:pass
   args+=['-map','0:a:0' if has_audio else '1:a:0','-af','apad','-c:v','libx264','-preset','veryfast','-crf','20','-c:a','aac','-ar','48000','-ac','2','-threads','2',str(out)];self.command(args,check,log);normalized.append(out)
  # cut/match-cut continuity is supplied by the shot designs. Sound bridges use timed audio tracks.
  listing=work/'concat.txt';listing.write_text('\n'.join("file '"+str(x).replace('\\','/').replace("'","'\\''")+"'" for x in normalized),encoding='utf-8');rough=work/'picture.mp4';self.command([ff,'-y','-v','warning','-f','concat','-safe','0','-i',listing,'-c','copy',rough],check,log)
  progress(.87,'混合对白、音乐与音效');audio=plan['audio'];mixed=work/'mixed.mp4';args=[ff,'-y','-v','warning','-i',str(rough)]
  for t in audio:args+=['-i',t['path']]
  filters=['[0:a]apad[a0]'];labels=['[a0]']
  for i,t in enumerate(audio,1):
   start=float(t.get('start',0));offset=float(t.get('offset',0));duration=float(t.get('duration',max(.05,plan['duration']-start)));delay=int(start*1000);gain=float(t.get('gain',1));fi=float(t.get('fadeIn',0));fo=float(t.get('fadeOut',0));chain=f'[{i}:a]atrim=start={offset}:duration={duration},asetpts=PTS-STARTPTS,volume={gain}'
   if fi:chain+=f',afade=t=in:st=0:d={min(fi,duration)}'
   if fo:chain+=f',afade=t=out:st={max(0,duration-fo)}:d={min(fo,duration)}'
   chain+=f',adelay={delay}|{delay}[a{i}]';filters.append(chain);labels.append(f'[a{i}]')
  filters.append(''.join(labels)+f'amix=inputs={len(labels)}:duration=longest:normalize=0[mix]');last='mix'
  for i,silence in enumerate(plan['silence']):
   a,b=float(silence['start']),float(silence['end']);ensure(0<=a<b<=plan['duration'],'静默区间无效');name=f'silent{i}';filters.append(f'[{last}]volume=enable=\'between(t,{a},{b})\':volume=0[{name}]');last=name
  filters.append(f'[{last}]alimiter=limit=0.95,atrim=duration={plan["duration"]}[finalaudio]');filterfile=work/'audio.filter';filterfile.write_text(';\n'.join(filters),encoding='utf-8')
  args+=['-filter_complex_script',str(filterfile),'-map','0:v:0','-map','[finalaudio]','-c:v','copy','-c:a','aac','-b:a','192k','-t',str(plan['duration']),str(mixed)];self.command(args,check,log)
  output=work/'film.mp4';subs=plan['subtitles']
  if subs:
   def stamp(n):
    ensure(float(n)>=0,'字幕时间非法');ms=round(float(n)*1000);hh,ms=divmod(ms,3600000);mm,ms=divmod(ms,60000);ss,ms=divmod(ms,1000);return f'{hh:02}:{mm:02}:{ss:02},{ms:03}'
   lines=[]
   for i,s in enumerate(subs,1):
    ensure(0<=float(s['start'])<float(s['end'])<=plan['duration']+.1,'字幕时间超出全片');lines+=[str(i),stamp(s['start'])+' --> '+stamp(s['end']),str(s['text']).replace('\r',''),'']
   srt=work/'subtitles.srt';srt.write_text('\n'.join(lines),encoding='utf-8');(work/'subtitles.vtt').write_text('WEBVTT\n\n'+'\n'.join(line.replace(',', '.') if ' --> ' in line else line for line in lines),encoding='utf-8');self.command([ff,'-y','-v','warning','-i',mixed,'-i',srt,'-map','0','-map','1:0','-c','copy','-c:s','mov_text','-metadata:s:s:0','language=zho','-movflags','+faststart',output],check,log)
  else:self.command([ff,'-y','-v','warning','-i',mixed,'-c','copy','-movflags','+faststart',output],check,log)
  (work/'edit-decision-list.json').write_text(json.dumps(plan,ensure_ascii=False,indent=2),encoding='utf-8')
  edl=self.b.register_file(p,work/'edit-decision-list.json');subtitle=self.b.register_file(p,work/'subtitles.srt') if subs else None;file=self.b.register_file(p,output);obj={'id':id,'projectId':p,'fileId':file['id'],'url':file['url'],'status':'draft','freshness':'clean','plan':plan,'createdAt':now(),'acceptance':None,'edlFile':edl,'subtitleFile':subtitle,'webVttFile':self.b.register_file(p,work/'subtitles.vtt') if subs else None,'hasConfiguredAudio':bool(audio),'isAnimatic':any(e['kind']=='keyframe' for e in plan['entries'])};self.s.put('assembly',obj,p);self.s.audit(p,'assembly_complete',[id],{'fileId':file['id'],'duration':plan['duration'],'humanAcceptanceRequired':True});progress(1,'成片已输出，等待人工验收');return obj

def get_ffmpeg(cfg):
 exe=cfg.get('ffmpeg') or shutil.which('ffmpeg')
 if not exe:
  import imageio_ffmpeg
  exe=imageio_ffmpeg.get_ffmpeg_exe()
 return exe
