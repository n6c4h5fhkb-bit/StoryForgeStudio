"""Trusted renderer CLI. Reads one TaskSpec; emits normalized RunResult.
Providers: manual (refuses), demo (labelled test cards), Dreamina CLI,
OpenAI-compatible images, generic HTTP job API, ComfyUI API workflow, or uploaded
media via the application.
No LLM is used here. No arbitrary shell commands are executed.
"""
from __future__ import annotations
import base64,copy,hashlib,json,mimetypes,os,re,shutil,subprocess,sys,time,urllib.parse
from pathlib import Path
import httpx
from PIL import Image,ImageDraw

DREAMINA_IMAGE_EXTENSIONS={'.png','.jpg','.jpeg','.webp'}
DREAMINA_VIDEO_EXTENSIONS={'.mp4','.mov','.webm'}

class RemoteStateUnknown(RuntimeError):pass

def at(obj,path,default=None):
 for part in path.split('.'):
  try:obj=obj[int(part)] if isinstance(obj,list) else obj[part]
  except (KeyError,IndexError,TypeError,ValueError):return default
 return obj

def template(value,variables):
 if isinstance(value,dict):return {k:template(v,variables) for k,v in value.items()}
 if isinstance(value,list):return [template(v,variables) for v in value]
 if not isinstance(value,str):return value
 if value.startswith('{{') and value.endswith('}}') and value.count('{{')==1:return variables.get(value[2:-2],value)
 for k,v in variables.items():
  if not isinstance(v,(dict,list)):value=value.replace('{{'+k+'}}',str(v))
 return value

def ffmpeg(cfg):
 if cfg.get('ffmpeg'):return cfg['ffmpeg']
 p=shutil.which('ffmpeg')
 if p:return p
 import imageio_ffmpeg;return imageio_ffmpeg.get_ffmpeg_exe()

def download(client,url,dest,max_bytes=1024**3):
 if not url.startswith(('http://','https://')):raise ValueError('返回的媒体 URL 协议不受支持')
 # Provider URLs may legitimately point to LAN ComfyUI. This app is localhost-only.
 with client.stream('GET',url,follow_redirects=True) as r:
  r.raise_for_status();total=0
  with dest.open('wb') as f:
   for chunk in r.iter_bytes():
    total+=len(chunk)
    if total>max_bytes:raise ValueError('远端媒体超过下载上限')
    f.write(chunk)

def json_output(stdout):
 candidates=[stdout.strip(),*[line.strip() for line in stdout.splitlines()[::-1]]]
 for candidate in candidates:
  if not candidate or candidate[0] not in '[{':continue
  try:return json.loads(candidate)
  except json.JSONDecodeError:continue
 return {'raw':stdout[-4000:]}

def deep_value(value,names):
 if isinstance(value,dict):
  for key,item in value.items():
   if key.lower() in names and item not in (None,''):return item
  for item in value.values():
   found=deep_value(item,names)
   if found not in (None,''):return found
 if isinstance(value,list):
  for item in value:
   found=deep_value(item,names)
   if found not in (None,''):return found
 return None

def dreamina_ratio(width,height,video=False):
 supported=['1:1','3:4','16:9','4:3','9:16','21:9'] if video else ['21:9','16:9','3:2','4:3','1:1','3:4','2:3','9:16']
 actual=float(width)/float(height)
 ratios={value:float(value.split(':')[0])/float(value.split(':')[1]) for value in supported}
 result=min(ratios,key=lambda value:abs(ratios[value]-actual))
 if abs(ratios[result]-actual)>.03:raise ValueError('画幅无法映射到 Dreamina 支持的比例，请调整作品画幅')
 return result

def dreamina_command(cfg):
 requested=cfg.get('command') or 'dreamina';exe=shutil.which(requested)
 if not exe and Path(str(requested)).is_file():exe=str(Path(str(requested)).resolve())
 if not exe:raise ValueError('未找到 dreamina CLI；请先安装并完成登录')
 return exe

def dreamina_run(args,out,timeout):
 result=subprocess.run(args,cwd=out,capture_output=True,text=True,encoding='utf-8',errors='replace',timeout=timeout,shell=False)
 payload=json_output(result.stdout)
 if result.returncode and not deep_value(payload,{'submit_id','submitid','status','gen_status','genstatus'}):
  raise RuntimeError('Dreamina CLI 执行失败：'+(result.stderr or result.stdout)[-2000:])
 return payload,result

def dreamina_help_evidence(exe,subcommand,required):
 result=subprocess.run([exe,subcommand,'-h'],capture_output=True,text=True,encoding='utf-8',errors='replace',timeout=30,shell=False)
 output=(result.stdout or '')+'\n'+(result.stderr or '')
 if result.returncode:raise RuntimeError('无法读取 Dreamina 当前能力说明：'+output[-1200:])
 for label,value in required.items():
  if value and str(value) not in output:raise ValueError(f'Dreamina 当前 {subcommand} 帮助未声明支持 {label}={value}；请刷新配置')
 return {'subcommand':subcommand,'helpSha256':hashlib.sha256(output.encode('utf-8')).hexdigest(),'checkedAt':time.time(),'required':required}

def dreamina_remote(out,submit_id,status,response,capability=None,submission_attempted=True):
 record={'provider':'dreamina','submitId':str(submit_id) if submit_id not in (None,'') else None,'status':status or 'unknown','lastResponse':response,'submissionAttempted':submission_attempted,'updatedAt':time.time()}
 if capability:record['capabilityEvidence']=capability
 (out/'provider-submit.json').write_text(json.dumps(record,ensure_ascii=False,indent=2),encoding='utf-8')
 return record

def dreamina_file(out,kind,before):
 extensions=DREAMINA_VIDEO_EXTENSIONS if kind=='clip' else DREAMINA_IMAGE_EXTENSIONS
 files=[path for path in out.rglob('*') if path.is_file() and path.suffix.lower() in extensions and str(path.resolve()) not in before]
 return max(files,key=lambda path:path.stat().st_mtime) if files else None

def dreamina(task,out):
 i=task['inputs'];cfg=i['media'];kind=i.get('kind','keyframe');exe=dreamina_command(cfg);session=int(cfg.get('session',0));submit_id=i.get('resumeSubmitId')
 before={str(path.resolve()) for path in out.rglob('*') if path.is_file()};deadline=time.monotonic()+float(cfg.get('timeout',900));last={};capability=None
 if not submit_id:
  if kind=='clip':
   model=cfg.get('videoModel') or cfg.get('model') or 'seedance2.0fast';resolution=cfg.get('videoResolution','720p');duration=float(i.get('duration',0));rounded=round(duration)
   maximum=30 if model=='seedance2.5' else 15
   if abs(duration-rounded)>.001 or not 4<=rounded<=maximum:raise ValueError(f'Dreamina 当前模型视频时长必须是 4–{maximum} 的整数秒；请在生成单元中合并镜头或调整单元时长')
   allowed={'seedance2.5':('480p','720p','1080p'),'seedance2.0_vip':('720p','1080p','4k')}.get(model,('720p',))
   if resolution not in allowed:raise ValueError('Dreamina 当前模型不支持分辨率 '+str(resolution))
   images=list(i.get('referencePaths',[]));videos=[i['referenceVideoPath']] if i.get('referenceVideoPath') else []
   if not images and not videos:raise ValueError('Seedance 2.0 全能参考至少需要一张参考图或一个参考视频')
   image_limit,video_limit,total_limit=(30,10,50) if model=='seedance2.5' else (9,3,12)
   if len(images)>image_limit or len(videos)>video_limit or len(images)+len(videos)>total_limit:raise ValueError(f'Dreamina 参考输入超过当前模型上限（图片 {image_limit}、视频 {video_limit}、总数 {total_limit}）')
   args=[exe,'multimodal2video',*sum((['--image',path] for path in images),[]),*sum((['--video',path] for path in videos),[]),'--prompt',i['prompt'],'--duration',str(rounded),'--ratio',dreamina_ratio(i.get('width',640),i.get('height',360),True),'--video_resolution',resolution,'--model_version',model,'--session',str(session),'--poll','0']
   capability=dreamina_help_evidence(exe,'multimodal2video',{'model_version':model,'video_resolution':resolution,'ratio':dreamina_ratio(i.get('width',640),i.get('height',360),True)})
  else:
   model=cfg.get('imageModel') or cfg.get('model') or '5.0';resolution=cfg.get('imageResolution','2k');refs=list(i.get('referencePaths',[]))
   if len(refs)>10:raise ValueError('Dreamina 单次生图最多使用 10 张参考图')
   if refs and model in ('3.0','3.1'):raise ValueError('Dreamina image2image 当前不支持 3.0/3.1，请使用 4.0 以上模型')
   args=[exe,'image2image' if refs else 'text2image']
   if refs:args += sum((['--images',path] for path in refs),[])
   args += ['--prompt',i['prompt'],'--ratio',dreamina_ratio(i.get('width',640),i.get('height',360)),'--resolution_type',resolution,'--model_version',model,'--generate_num','1','--session',str(session),'--poll','0']
   capability=dreamina_help_evidence(exe,'image2image' if refs else 'text2image',{'model_version':model,'resolution_type':resolution,'ratio':dreamina_ratio(i.get('width',640),i.get('height',360))})
  dreamina_remote(out,None,'submitting',{'command':capability['subcommand']},capability,False)
  last,result=dreamina_run(args,out,min(120,max(30,float(cfg.get('submitTimeout',120)))))
  submit_id=deep_value(last,{'submit_id','submitid','task_id','taskid'})
  immediate_status=str(deep_value(last,{'gen_status','genstatus','status'}) or '').lower()
  if not submit_id:
   file=dreamina_file(out,kind,before)
   if file and immediate_status in ('success','succeeded','completed','done'):return file,{'provider':'dreamina','submitId':None,'status':'success','lastResponse':last,'capabilityEvidence':capability,'submissionAttempted':True}
   dreamina_remote(out,None,'state_unknown',last,capability,True)
   raise RemoteStateUnknown('Dreamina 返回结果中缺少 submit_id，无法安全判断是否已经提交；请先在任务记录中人工核对，禁止直接重提')
  dreamina_remote(out,submit_id,immediate_status,last,capability,True)
 successes={'success','succeeded','completed','done'};failures={'failed','failure','error','cancelled','canceled'}
 while time.monotonic()<deadline:
  last,result=dreamina_run([exe,'query_result','--submit_id',str(submit_id),'--download_dir',str(out.resolve())],out,min(120,max(30,float(cfg.get('queryTimeout',120)))))
  status=str(deep_value(last,{'gen_status','genstatus','status','state'}) or '').lower();remote=dreamina_remote(out,submit_id,status,last,capability,True);file=dreamina_file(out,kind,before)
  if status in successes:
   if not file:raise RemoteStateUnknown('Dreamina 报告成功但未下载到媒体文件；保留 submit_id='+str(submit_id)+'，请只重试下载')
   return file,remote
  if status in failures:raise RuntimeError('Dreamina 远端任务失败：'+json.dumps(last,ensure_ascii=False)[:2000])
  if file:return file,{**remote,'status':'success'}
  time.sleep(float(cfg.get('pollSeconds',3)))
 raise TimeoutError('Dreamina 生成仍在进行；已保留 submit_id='+str(submit_id)+'，请使用恢复功能查询原任务，不要重新提交')

def demo(task,out):
 i=task['inputs'];w=int(i.get('width',640));h=int(i.get('height',360));im=Image.new('RGB',(w,h),(24,31,43));d=ImageDraw.Draw(im)
 # Explicit test card; not presented as an AI-generated story frame.
 d.rectangle((w*.08,h*.12,w*.92,h*.86),outline=(93,116,141),width=3);d.line((w*.08,h*.64,w*.92,h*.64),fill=(93,116,141),width=2)
 d.text((w*.12,h*.22),'SYSTEM B / PIPELINE TEST CARD',fill=(220,226,231));d.text((w*.12,h*.34),'NOT AI-GENERATED FOOTAGE',fill=(239,185,82));d.text((w*.12,h*.48),'SEED '+str(i.get('seed',0)),fill=(220,226,231))
 image=out/'test-card.png';im.save(image)
 if i.get('kind')=='clip':
  dest=out/'test-clip.mp4';subprocess.run([ffmpeg(i),'-y','-loop','1','-i',str(image),'-f','lavfi','-i','anullsrc=r=48000:cl=stereo','-t',str(i.get('duration',2)),'-vf','format=yuv420p','-r','24','-c:v','libx264','-preset','ultrafast','-c:a','aac','-shortest',str(dest)],check=True,capture_output=True);return dest
 return image

def openai_image(task,out,client):
 i=task['inputs'];cfg=i['media'];base=cfg['baseUrl'].rstrip('/');headers={'Authorization':'Bearer '+cfg['apiKey']};kind=i.get('kind','keyframe')
 if kind=='clip':return generic(task,out,client)
 body={'model':cfg['model'],'prompt':i['prompt'],'n':1,'size':cfg.get('size','1024x1024')};body.update(cfg.get('extraBody',{}))
 refs=i.get('referencePaths',[])
 if refs and not cfg.get('useEdits',False):raise ValueError('存在参考图，必须启用 useEdits 或切换到支持参考图的接口')
 if refs and cfg.get('useEdits',False):
  handles=[open(p,'rb') for p in refs]
  try:r=client.post(base+'/images/edits',headers=headers,data={k:str(v) for k,v in body.items()},files=[('image[]',(Path(p).name,h,mimetypes.guess_type(p)[0] or 'image/png')) for p,h in zip(refs,handles)])
  finally:
   for h in handles:h.close()
 else:r=client.post(base+'/images/generations',headers=headers,json=body)
 r.raise_for_status();data=r.json()['data'][0];dest=out/'image.png'
 if data.get('b64_json'):dest.write_bytes(base64.b64decode(data['b64_json']))
 elif data.get('url'):download(client,data['url'],dest)
 else:raise ValueError('图像接口缺少 b64_json 或 url')
 return dest

def generic(task,out,client):
 i=task['inputs'];cfg=i['media'];g=cfg.get('generic',{});kind=i.get('kind','keyframe');spec=g.get('video' if kind=='clip' else 'image',g)
 if not spec.get('createPath'):raise ValueError('未配置通用渲染 API 的 createPath/bodyTemplate/resultPath')
 refs=[]
 for p in i.get('referencePaths',[]):refs.append('data:'+(mimetypes.guess_type(p)[0] or 'image/png')+';base64,'+base64.b64encode(Path(p).read_bytes()).decode())
 variables={'prompt':i['prompt'],'negativePrompt':i.get('negativePrompt',''),'seed':i.get('seed',0),'width':i.get('width',640),'height':i.get('height',360),'duration':i.get('duration',2),'model':cfg.get('model',''),'references':refs,'firstFrame':refs[0] if refs else '', 'referenceVideo':i.get('referenceVideoUrl','')}
 if i.get('referenceVideoPath'):
  video_path=Path(i['referenceVideoPath']);variables['referenceVideo']='data:'+(mimetypes.guess_type(video_path.name)[0] or 'video/mp4')+';base64,'+base64.b64encode(video_path.read_bytes()).decode()
 # For APIs requiring upload URLs, configure multipart upload rather than sending local paths.
 upload=spec.get('uploadPath')
 if upload:
  urls=[]
  for p in i.get('referencePaths',[]):
   with open(p,'rb') as f:r=client.post(cfg['baseUrl'].rstrip('/')+upload,headers={'Authorization':'Bearer '+cfg.get('apiKey','')},files={'file':(Path(p).name,f)})
   r.raise_for_status();urls.append(at(r.json(),spec.get('uploadResultPath','url')))
  variables.update(references=urls,firstFrame=urls[0] if urls else '')
  if i.get('referenceVideoPath'):
   p=i['referenceVideoPath']
   with open(p,'rb') as f:r=client.post(cfg['baseUrl'].rstrip('/')+upload,headers={'Authorization':'Bearer '+cfg.get('apiKey','')},files={'file':(Path(p).name,f)})
   r.raise_for_status();variables['referenceVideo']=at(r.json(),spec.get('uploadResultPath','url'))
 body_source=json.dumps(spec.get('bodyTemplate',{}))
 if i.get('referenceVideoPath') and '{{referenceVideo}}' not in body_source:raise ValueError('视频强依赖未映射：bodyTemplate 必须引用 {{referenceVideo}}')
 if refs and not any(x in body_source for x in ('{{references}}','{{firstFrame}}')):raise ValueError('参考图未映射：bodyTemplate 必须引用 {{references}} 或 {{firstFrame}}')
 headers={'Authorization':'Bearer '+cfg.get('apiKey',''),**cfg.get('headers',{})};base=cfg['baseUrl'].rstrip('/');body=template(spec.get('bodyTemplate',{'prompt':'{{prompt}}','model':'{{model}}','seed':'{{seed}}'}),variables)
 r=client.post(base+spec['createPath'],headers=headers,json=body);r.raise_for_status();result=r.json();jobid=at(result,spec.get('jobIdPath','id'))
 (out/'provider-submit.json').write_text(json.dumps(result,ensure_ascii=False),encoding='utf-8')
 if spec.get('pollPath'):
  deadline=time.monotonic()+float(cfg.get('timeout',900));status=''
  while time.monotonic()<deadline:
   path=spec['pollPath'].replace('{id}',str(jobid));r=client.get(base+path,headers=headers);r.raise_for_status();result=r.json();status=at(result,spec.get('statusPath','status'))
   if status in spec.get('successStatuses',['succeeded','completed','done']):break
   if status in spec.get('failureStatuses',['failed','cancelled','error']):raise RuntimeError('远端任务失败：'+json.dumps(result,ensure_ascii=False)[:2000])
   time.sleep(float(cfg.get('pollSeconds',3)))
  else:raise TimeoutError('远端生成超时；provider-submit.json 保留任务 ID，不要盲目重新提交')
 dest=out/('clip.mp4' if kind=='clip' else 'image.png');value=at(result,spec.get('resultPath','url'))
 if not value:raise ValueError('渲染 API 未返回 configured resultPath：'+json.dumps(result)[:1000])
 if spec.get('resultEncoding')=='base64':dest.write_bytes(base64.b64decode(value))
 else:download(client,str(value),dest)
 return dest

def comfy(task,out,client):
 i=task['inputs'];cfg=i['media'];base=cfg.get('baseUrl','http://127.0.0.1:8188').rstrip('/');workflow=copy.deepcopy(cfg.get('workflow'))
 if not workflow:raise ValueError('请在 media.workflow 配置 ComfyUI API 格式工作流')
 variables={'prompt':i['prompt'],'negativePrompt':i.get('negativePrompt',''),'seed':i.get('seed',0),'width':i.get('width',640),'height':i.get('height',360),'duration':i.get('duration',2)}
 for j,p in enumerate(i.get('referencePaths',[])):
  with open(p,'rb') as f:r=client.post(base+'/upload/image',files={'image':(Path(p).name,f)},data={'overwrite':'true'})
  r.raise_for_status();d=r.json();variables['reference'+str(j)]=(d.get('subfolder','')+'/' if d.get('subfolder') else '')+d['name']
 workflow=template(workflow,variables);r=client.post(base+'/prompt',json={'prompt':workflow,'client_id':task['taskId']});r.raise_for_status();submitted=r.json()
 (out/'provider-submit.json').write_text(json.dumps(submitted),encoding='utf-8');pid=submitted['prompt_id'];deadline=time.monotonic()+float(cfg.get('timeout',900))
 while time.monotonic()<deadline:
  r=client.get(base+'/history/'+pid);r.raise_for_status();record=r.json().get(pid)
  if record:
   if record.get('status',{}).get('status_str')=='error':raise RuntimeError('ComfyUI 工作流报错：'+json.dumps(record)[:1000])
   found=[]
   for output in record.get('outputs',{}).values():
    for field in ('images','gifs','videos'):
     found+=output.get(field,[])
   if found:
    f=found[0];url=base+'/view?'+urllib.parse.urlencode({k:f[k] for k in ('filename','subfolder','type') if k in f});dest=out/Path(f['filename']).name;download(client,url,dest);return dest
  time.sleep(float(cfg.get('pollSeconds',2)))
 raise TimeoutError('ComfyUI 生成超时，保留远端 prompt_id，需核对后重试')

def main():
 path=Path(sys.argv[1]);task=json.loads(path.read_text(encoding='utf-8'));out=Path(task['workdir']);start=time.monotonic();i=task['inputs'];cfg=i.get('media',{});provider=cfg.get('provider','manual')
 try:
  if provider=='manual':raise ValueError('当前为手动素材模式，请上传关键帧/片段，或在设置中配置渲染服务')
  remote=None
  with httpx.Client(timeout=float(cfg.get('timeout',900))) as client:
   if provider=='demo':file=demo(task,out)
   elif provider=='dreamina':file,remote=dreamina(task,out)
   elif provider=='openai':file=openai_image(task,out,client)
   elif provider=='generic':file=generic(task,out,client)
   elif provider=='comfyui':file=comfy(task,out,client)
   else:raise ValueError('未知媒体 provider：'+provider)
  cost=0 if provider=='demo' else float(cfg.get('imageCost',0) if i.get('kind')!='clip' else cfg.get('videoCostPerSecond',0)*i.get('duration',1))
  result={'status':'ok','artifacts':[{'path':str(file.resolve()),'kind':i.get('kind'),'mime':mimetypes.guess_type(file.name)[0] or 'application/octet-stream'}],
   'report':{'actions':['compiled_prompt_received','provider:'+provider,'artifact_saved'],'actualPrompt':i['prompt'],'notes':'测试素材，非 AI 生成画面' if provider=='demo' else ''},'usage':{'cost':cost,'costKnown':provider=='demo' or cfg.get('priceConfigured',False),'wallTime':time.monotonic()-start,'turns':1},'runner':{}}
  if remote:result['remote']=remote
 except Exception as e:
  cls='timeout' if isinstance(e,(TimeoutError,httpx.TimeoutException)) else 'state_unknown' if isinstance(e,RemoteStateUnknown) else 'configuration' if isinstance(e,ValueError) else 'provider'
  result={'status':'timeout' if cls=='timeout' else 'failed','artifacts':[],'report':{'actions':['provider:'+provider],'failureClass':cls,'notes':str(e)},'usage':{'wallTime':time.monotonic()-start,'turns':1},'runner':{}}
  submit=out/'provider-submit.json'
  if submit.exists():
   try:result['remote']=json.loads(submit.read_text(encoding='utf-8'))
   except (OSError,json.JSONDecodeError):pass
 (out/'report.json').write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf-8');print(json.dumps(result,ensure_ascii=False),flush=True)
 # Failure still returns normalized report; the parent checks status, not just exit code.
if __name__=='__main__':main()
