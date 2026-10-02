"""Layered media gates. Missing detector weights are UNKNOWN, never PASS."""
from __future__ import annotations
import base64,json,math,mimetypes,shutil,subprocess,tempfile,re
from pathlib import Path
import httpx
from PIL import Image,ImageStat
from .core import ensure,uid,now,DomainError

class Gates:
 def __init__(self,store,settings,llm):self.s=store;self.settings=settings;self.llm=llm
 def probe(self,path):
  cfg=self.settings.read();exe=cfg.get('ffprobe') or shutil.which('ffprobe')
  if not exe:
   from .assembly import get_ffmpeg
   ff=get_ffmpeg(cfg)
   raw=subprocess.run([ff,'-hide_banner','-i',str(path)],capture_output=True,text=True,errors='replace',timeout=30).stderr
   streams=[]
   for line in raw.splitlines():
    if 'Stream #' not in line:continue
    if 'Video:' in line:
     dims=re.search(r'(?<![0-9])(\d{2,5})x(\d{2,5})(?![0-9])',line)
     if dims:streams.append({'codec_type':'video','width':int(dims[1]),'height':int(dims[2])})
    elif 'Audio:' in line:streams.append({'codec_type':'audio'})
    elif 'Subtitle:' in line:streams.append({'codec_type':'subtitle'})
   match=re.search(r'Duration:\s*(\d+):(\d+):(\d+(?:\.\d+)?)',raw)
   duration=float(match[1])*3600+float(match[2])*60+float(match[3]) if match else 0
   ensure(streams,'FFmpeg 无法读取媒体轨道','media_invalid',422)
   return {'streams':streams,'format':{'duration':str(duration)},'probeMethod':'ffmpeg-stderr-fallback'}
  result=subprocess.run([exe,'-v','error','-show_format','-show_streams','-of','json',str(path)],capture_output=True,text=True,timeout=30)
  if result.returncode:raise DomainError('FFprobe 无法读取媒体：'+result.stderr[-800:],'media_invalid',422)
  return json.loads(result.stdout)
 def inspect(self,p,render,shot=None,check=lambda:None):
  file=self.s.get(render['fileId']);path=Path(file['path']);cfg=self.settings.read();checks=[];images=[];sampled_frames=[];probe=None
  def add(stage,name,state,message,**details):checks.append({'stage':stage,'name':name,'state':state,'message':message,'details':details})
  check()
  if render['kind']=='keyframe':
   try:
    im=Image.open(path);im.verify();im=Image.open(path).convert('RGB');w,h=im.size;images=[im.copy()]
    add(1,'decode','pass','图像可解码',width=w,height=h)
    sd=ImageStat.Stat(im.resize((128,128))).stddev;add(1,'blank_frame','fail' if max(sd)<2 else 'pass','空白/单色画面检测',deviation=sd)
   except Exception as e:add(1,'decode','fail','无法解码图片：'+str(e));w=h=0
  else:
   try:
    probe=self.probe(path)
    if not probe:add(1,'video_probe','unknown','未找到 ffprobe，请安装 FFmpeg 或在设置中指定路径');w=h=0
    else:
     video=next((x for x in probe['streams'] if x['codec_type']=='video'),None);ensure(video,'媒体没有视频轨');w=int(video['width']);h=int(video['height']);duration=float(probe['format'].get('duration',0));add(1,'decode','pass','视频可解码',width=w,height=h,duration=duration)
     if shot:
      delta=abs(duration-shot['duration']);add(1,'duration','pass' if delta<=max(.25,shot['duration']*.08) else 'review','实际时长与镜头计划比较',planned=shot['duration'],actual=duration)
     from .assembly import get_ffmpeg
     exe=get_ffmpeg(cfg)
     if exe and duration>0:
      interval=render.get('proposedInterval') if isinstance(render.get('proposedInterval'),dict) else None
      start=max(0,float((interval or {}).get('in',0)));end=min(duration,float((interval or {}).get('out',duration)))
      if not start<end:start,end=0,duration
      last=max(start,end-min(.04,max(.01,(end-start)/20)));count=min(5,max(2,int(math.ceil(end-start))+1));times=[]
      for i in range(count):
       value=start+(last-start)*i/max(1,count-1)
       if not times or abs(value-times[-1])>.005:times.append(value)
      with tempfile.TemporaryDirectory() as d:
       for index,timestamp in enumerate(times):
        target=Path(d)/(f'{index:03d}.png')
        subprocess.run([exe,'-y','-v','error','-ss',f'{timestamp:.6f}','-i',str(path),'-frames:v','1','-vf','scale=480:-1',str(target)],capture_output=True,timeout=30)
        if target.is_file():
         images.append(Image.open(target).convert('RGB').copy());sampled_frames.append({'index':len(images)-1,'time':round(timestamp,3),'method':'ffmpeg_frame_extract'})
      add(1,'sampled_frames','pass' if images else 'unknown','已抽取多个真实时间点供审查' if images else '未能抽取审查帧',timepoints=[x['time'] for x in sampled_frames],interval={'in':start,'out':end})
      if len(images)>1:
       means=[sum(ImageStat.Stat(x.resize((64,64))).mean)/3 for x in images];diffs=[abs(a-b) for a,b in zip(means,means[1:])];add(1,'flicker','review' if max(diffs)>65 else 'pass','亮度突跳初筛；不等价于时序一致性证明',largestJump=round(max(diffs),2))
   except Exception as e:add(1,'decode','fail','视频读取失败：'+str(e));w=h=0
  if shot and w and h:
   project=self.s.get(p);style=self.s.get(project['styleId']);a,b=map(float,style['aspectRatio'].split(':'));relative=abs(w/h-a/b)/(a/b)
   add(1,'aspect','pass' if relative<.03 else 'review','画幅与风格包比较',expected=style['aspectRatio'],actual=f'{w}:{h}')
  # OpenCV is optional. Face presence is not an identity comparison.
  try:
   import cv2,numpy as np
   cascade=cv2.CascadeClassifier(cv2.data.haarcascades+'haarcascade_frontalface_default.xml')
   counts=[]
   for im in images[:4]:counts.append(len(cascade.detectMultiScale(cv2.cvtColor(np.array(im),cv2.COLOR_RGB2GRAY),1.1,4)))
   if counts:add(1,'face_count','review','正脸检测仅作初筛，遮挡/侧脸需要人工确认',counts=counts)
  except ImportError:add(1,'face_count','unknown','可选 OpenCV 未安装；未执行人脸数量初筛')
  completed=set()
  # Plugins return checks; the protocol can serve embedding, hand/face/OCR and optical flow models.
  for plugin in cfg.get('gatePlugins',[]):
   check()
   if not plugin.get('enabled') or any(x['state']=='fail' for x in checks):continue
   try:
    with path.open('rb') as f:
     with httpx.Client(timeout=float(plugin.get('timeout',90)),trust_env=False) as client:
      response=client.post(plugin['url'],files={'media':(path.name,f)},data={'context':json.dumps({'shot':shot,'kind':render['kind'],'projectId':p},ensure_ascii=False)},headers={'Authorization':'Bearer '+plugin['apiKey']} if plugin.get('apiKey') else {})
    response.raise_for_status();result=response.json()
    for item in result['checks']:
     ensure(item['state'] in ('pass','fail','review','unknown'),'检测器返回了未知状态');name=item['name'];completed.add(name);add(int(item.get('stage',2)),name,item['state'],item.get('message',''),**item.get('details',{}))
   except Exception as e:add(2,plugin.get('name','detector'),'unknown','检测器不可用：'+str(e)[:300])
  for name,label in [('identity','角色相似度 embedding'),('anatomy','手/脸形变专用模型'),('text','文字崩坏')]:
   if name not in completed:add(1 if name=='identity' else 2,name,'unknown',label+' 未配置，需要人工审核')
  if render['kind']=='clip' and 'temporal_identity' not in completed:add(2,'temporal_identity','unknown','时序身份/运动方向专用检测器未配置，需要人工审核')
  if render['kind']=='clip' and shot and (shot.get('dialogueIds') or shot.get('dialogueText')) and 'dialogue_audio' not in completed:
   has_audio=bool(probe and any(x.get('codec_type')=='audio' for x in probe.get('streams',[])))
   add(2,'dialogue_audio','unknown','检测到音轨，但未配置对白转写/听检；须单独核对实际台词' if has_audio else '未检测到音轨；若本次视频包含对白，须人工确认交付方式',hasAudio=has_audio,expectedDialogue=shot.get('dialogueText') or shot.get('dialogueIds'))
  payload=(shot or {}).get('informationPayload',[])
  visioncfg=self.settings.model('vision')
  if not any(x['state']=='fail' for x in checks) and images and payload and visioncfg['provider']!='demo' and visioncfg.get('model') and visioncfg.get('baseUrl') and self.s.get(p).get('workflowVersion',1)<4:
   import io
   encoded=[]
   for image in images[:6]:
    frame=image.copy();buffer=io.BytesIO();frame.thumbnail((1024,1024));frame.save(buffer,format='JPEG',quality=85);encoded.append({'mime':'image/jpeg','data':base64.b64encode(buffer.getvalue()).decode()})
   try:
    result=self.llm.json(p,'vision','按提供的多个真实时间点，只验证镜头必须承载的信息。不评价故事美学。每条信息返回 yes/no/uncertain、观察到的 timepoint 和简短可见证据。没有看到就 uncertain，禁止推测。JSON {"checks":[{"payload":"","answer":"yes|no|uncertain","timepoint":0,"evidence":""}]}。',{'informationPayload':payload,'sampledTimepoints':[x['time'] for x in sampled_frames]},images=encoded,check=check)
    for item in result.get('checks',[]):add(3,'payload','pass' if item['answer']=='yes' else 'fail' if item['answer']=='no' else 'review',item.get('payload',''),timepoint=item.get('timepoint'),evidence=item.get('evidence',''))
   except Exception as e:add(3,'payload','unknown','VLM 检查未完成：'+str(e)[:300])
  elif payload:add(3,'payload','unknown','信息交付与剧情承接请查看连续情节审片' if self.s.get(p).get('workflowVersion',1)>=4 else '未配置真实 VLM，信息承载须人工确认')
  status='rejected' if any(c['state']=='fail' for c in checks) else 'review' if any(c['state'] in ('unknown','review') for c in checks) else 'passed'
  obj={'id':uid('gate'),'projectId':p,'renderId':render['id'],'status':status,'passed':status=='passed','checks':checks,'createdAt':now(),'mediaProbe':probe,'sampledFrames':sampled_frames,'automatic':True};self.s.put('gate_report',obj,p)
  render=self.s.get(render['id']);render['gateReportId']=obj['id'];render['gateStatus']=status;self.s.put('render',render,p);self.s.audit(p,'media_gate',[render['id']],{'status':status,'checks':len(checks)})
  return obj
