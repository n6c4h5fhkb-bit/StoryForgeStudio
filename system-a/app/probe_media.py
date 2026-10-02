from __future__ import annotations
import json,subprocess,sys,time,os,signal
from pathlib import Path
from .core import ensure,uid,now,digest,DomainError

def render_probe(service,p,spike,check):
 cfg=service.settings.read();media=cfg['media'];ensure(media['provider']!='manual','关键帧探针未配置图像服务；在设置的图像页配置，或使用 Script 探针','configuration_required',409)
 # This image is explicitly non-canonical. It never becomes a Scene/asset.
 prompt='Single cinematic still frame illustrating this scene. No montage, no text.\n'+spike['script'];project=service.s.get(p);seed=int(digest(spike['candidateId'])[:8],16)
 freeze='\n'.join(e.get('freezeString','') for e in project['canon']['entities'] if e.get('freezeString'));prompt=freeze+'\n'+prompt
 if media['provider']!='demo':ensure(media.get('priceConfigured'),'请先配置探针图片单价')
 estimate=0 if media['provider']=='demo' else float(media.get('imageCost',0));spent=sum(float(r.get('cost',0)) for r in service.s.list(p,'run'));ensure(spent+estimate<=cfg['budget']['project'],'探针预算不足')
 taskid=uid('probe_media');work=service.s.root/'media'/p/'probes'/taskid;work.mkdir(parents=True,exist_ok=True);task={'taskId':taskid,'workdir':str(work.resolve()),'inputs':{'prompt':prompt,'kind':'keyframe','media':media,'seed':seed,'width':640,'height':360,'referencePaths':[]}}
 taskfile=work/'task.json';taskfile.write_text(json.dumps(task,ensure_ascii=False),encoding='utf-8');tool=Path(__file__).resolve().parents[1]/'tools'/'probe_render.py';start=time.monotonic()
 log=work/'render.log'
 with log.open('wb') as f:
  proc=subprocess.Popen([sys.executable,str(tool),str(taskfile)],stdout=f,stderr=f)
  try:
   while proc.poll() is None:
    check();ensure(time.monotonic()-start<float(media.get('timeout',900)),'探针图像超时','timeout',408);time.sleep(.1)
   result=json.loads((work/'report.json').read_text(encoding='utf-8'));ensure(result['status']=='ok','探针图像生成失败','render_failed',502,result)
  except BaseException:proc.kill();proc.wait();raise
  finally:
   task['inputs']['media']=service.settings._redact(media);taskfile.write_text(json.dumps(task,ensure_ascii=False),encoding='utf-8')
 path=Path(result['artifacts'][0]['path']).resolve();ensure(path.is_relative_to(work),'探针产物越界');file={'id':uid('file'),'projectId':p,'path':str(path),'filename':path.name,'url':'/media/'+str(path.relative_to(service.s.root/'media')).replace('\\','/'),'size':path.stat().st_size,'createdAt':now()};service.s.put('file',file,p)
 service.s.put('run',{'id':uid('run'),'projectId':p,'role':'probe_image','provider':media['provider'],'status':'succeeded','cost':estimate,'costKnown':True,'wallTime':time.monotonic()-start,'createdAt':now(),'nonCanonical':True},p)
 return {'imageFileId':file['id'],'imageUrl':file['url'],'imageDemo':media['provider']=='demo'}
