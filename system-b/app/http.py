from __future__ import annotations
import asyncio,json,os,re,shutil,sys,tempfile,zipfile
from pathlib import Path
from urllib.parse import urlparse
from fastapi import FastAPI,Request,UploadFile,File
from fastapi.responses import JSONResponse,FileResponse,StreamingResponse,HTMLResponse
from fastapi.staticfiles import StaticFiles
from .core import DomainError,ensure,uid,safe_path,now,digest

def install_http(app,store,settings,jobs,root,title):
 @app.exception_handler(DomainError)
 async def domain_error(request,e):return JSONResponse({'error':str(e),'code':e.code,'details':e.details},status_code=e.status)
 @app.middleware('http')
 async def local_guard(request,call_next):
  host=request.headers.get('host','').split(':')[0]
  if host not in ('127.0.0.1','localhost','testserver','[','::1'):
   return JSONResponse({'error':'仅允许本机访问。远程部署须配置认证反向代理。'},403)
  origin=request.headers.get('origin')
  if origin and urlparse(origin).netloc!=request.headers.get('host'):
   return JSONResponse({'error':'跨来源请求被拒绝'},403)
  if request.method not in ('GET','HEAD','OPTIONS') and request.url.path.startswith('/api/') and request.headers.get('x-studio-client')!='local-ui':
   return JSONResponse({'error':'缺少本地客户端请求标记'},403)
  response=await call_next(request)
  response.headers['X-Content-Type-Options']='nosniff';response.headers['Referrer-Policy']='no-referrer'
  response.headers['Content-Security-Policy']="default-src 'self'; script-src 'self'; style-src 'self' 'unsafe-inline'; img-src 'self' data: blob:; media-src 'self' blob:; connect-src 'self'; frame-ancestors 'none'"
  return response
 @app.get('/api/health')
 def health():return {'ok':True,'system':title,'version':'1.0.0','python':sys.version.split()[0],'mode':settings.read()['llm']['provider'],'ffmpeg':bool(shutil.which('ffmpeg') or settings.read().get('ffmpeg'))}
 @app.get('/api/settings')
 def get_settings():return settings.read(True)
 @app.put('/api/settings')
 def save_settings(value:dict):return settings.save(value)
 @app.get('/api/codex/status')
 def codex_status(role:str=''):
  from .codex_cli import status
  return status(settings.model(role) if role else settings.read()['llm'])
 @app.get('/api/projects/{id}/codex-sessions')
 def codex_sessions(id:str):
  from .codex_cli import CodexSessions
  return CodexSessions(store).summaries(id)
 @app.post('/api/projects/{id}/codex-sessions/{session}/reset')
 def reset_codex_session(id:str,session:str):
  from .codex_cli import CodexSessions
  return CodexSessions(store).reset(id,session)
 @app.get('/api/jobs')
 def list_jobs(project:str|None=None):return jobs.list(project)
 @app.get('/api/jobs/{id}')
 def get_job(id:str):return jobs.get(id)
 @app.post('/api/jobs/{id}/cancel')
 def cancel_job(id:str):return jobs.cancel(id)
 @app.get('/api/events')
 async def events(request:Request,since:int=0,project:str|None=None):
  async def stream():
   nonlocal since
   try:since=max(since,int(request.headers.get('last-event-id','0')))
   except ValueError:pass
   while not await request.is_disconnected():
    for event in store.events(since,project):
     since=event['seq'];yield f'id: {since}\nevent: update\ndata: '+json.dumps(event,ensure_ascii=False)+'\n\n'
    yield ': keepalive\n\n';await asyncio.sleep(1)
  return StreamingResponse(stream(),media_type='text/event-stream',headers={'Cache-Control':'no-cache','X-Accel-Buffering':'no'})
 @app.get('/api/projects/{id}/history')
 def history(id:str):return store.history(id)
 @app.get('/api/projects/{id}/runs')
 def runs(id:str):return store.list(id,'run')
 @app.post('/api/projects/{id}/upload')
 async def upload(id:str,file:UploadFile=File(...)):
  store.get(id);ext=Path(file.filename or '').suffix.lower()
  ensure(ext in ('.png','.jpg','.jpeg','.webp','.mp4','.mov','.webm','.wav','.mp3','.m4a','.ogg','.txt','.md','.json','.srt','.fountain'), '不支持的文件格式')
  name=uid('file')+ext;folder=store.root/'media'/id;folder.mkdir(parents=True,exist_ok=True);path=folder/name;size=0
  try:
   with path.open('wb') as f:
    while chunk:=await file.read(1024*1024):
     size+=len(chunk);ensure(size<=1024**3,'文件超过 1GB 上限','file_too_large',413);f.write(chunk)
  except:path.unlink(missing_ok=True);raise
  obj={'id':uid('assetfile'),'projectId':id,'filename':file.filename,'relative':str(path.relative_to(store.root)).replace('\\','/'),'path':str(path.resolve()),'url':'/media/'+id+'/'+name,'size':size,'createdAt':now()}
  store.put('file',obj,id);store.audit(id,'upload',[obj['id']],{'filename':file.filename});return obj
 @app.get('/api/projects/{id}/files')
 def files(id:str):return store.list(id,'file')
 @app.get('/api/projects/{id}/backup')
 def backup(id:str):
  project=store.get(id);folder=store.root/'exports';folder.mkdir(exist_ok=True);path=folder/(id+'.zip')
  with store.connect() as c:
   docs=[{'kind':r['kind'],'value':json.loads(r['data'])} for r in c.execute('SELECT kind,data FROM documents WHERE project=?',(id,))]
  with zipfile.ZipFile(path,'w',zipfile.ZIP_DEFLATED) as z:
   z.writestr('project.json',json.dumps({'format':'studio-project-v2','system':title,'sourceRoot':str(store.root.resolve()),'project':project,'documents':docs,'operations':store.history(id)},ensure_ascii=False,indent=2))
   media=(store.root/'media'/id).resolve()
   for item in store.list(id,'file'):
    f=Path(item['path']).resolve()
    candidates=[Path(base).resolve()/id for base in getattr(store,'media_roots',[store.root/'media'])]
    source=next((base for base in candidates if f.is_relative_to(base)),None)
    if f.is_file() and source:z.write(f,'media/'+str(f.relative_to(source)))
  return FileResponse(path,filename=project.get('title',id)+'-backup.zip')
 @app.post('/api/backups/restore')
 async def restore_backup(file:UploadFile=File(...)):
  # Portable project archive: new IDs, no runner credentials, no cache replay,
  # no executable extraction. The original project is never overwritten.
  import copy,io
  payload=await file.read(1024**3+1);ensure(len(payload)<=1024**3,'备份超过 1GB')
  try:z=zipfile.ZipFile(io.BytesIO(payload));manifest=json.loads(z.read('project.json'))
  except Exception:raise DomainError('无法读取项目备份')
  ensure(manifest.get('format')=='studio-project-v2' and manifest.get('system')==title,'备份不属于当前系统或版本不受支持')
  ensure(sum(i.file_size for i in z.infolist())<=2*1024**3,'解压后文件超过 2GB')
  docs=manifest['documents'];ensure(isinstance(docs,list) and len(docs)<100000,'备份对象数量非法')
  original=manifest['project']['id'];new=uid('a' if title.endswith('A') else 'b')
  ids={x['value']['id']:uid(x['kind']) for x in docs};ids[original]=new
  excluded={'runner_run','reservation','curator_item','run','qualification','experiment','llm_hold','codex_session'}
  files={x['value']['id']:x['value'] for x in docs if x['kind']=='file'};path_map={};url_map={};relative_map={}
  for fid,f in files.items():
   oldpath=Path(f['path']);oldrel=str(f.get('relative','')).replace('\\','/')
   prefix='media/'+original+'/'
   ensure(oldrel.startswith(prefix),'备份中的素材路径不合法')
   relative=oldrel[len(prefix):];arc='media/'+relative
   dest=safe_path(store.root/'media'/new,relative)
   ensure(dest.suffix.lower() in ('.png','.jpg','.jpeg','.webp','.mp4','.mov','.webm','.wav','.mp3','.m4a','.ogg','.txt','.md','.json','.srt','.fountain','.fdx'), '备份含不允许的素材类型')
   if arc in z.namelist():
    dest.parent.mkdir(parents=True,exist_ok=True)
    with z.open(arc) as src,dest.open('wb') as dst:shutil.copyfileobj(src,dst)
   path_map[str(oldpath)]=str(dest.resolve());url_map[f.get('url','')]=' /media/'.strip()+new+'/'+relative
   relative_map[oldrel]='media/'+new+'/'+relative
  def remap(v):
   if isinstance(v,dict):return {ids.get(k,k):remap(x) for k,x in v.items() if k!='_version'}
   if isinstance(v,list):return [remap(x) for x in v]
   if isinstance(v,str):return ids.get(v,path_map.get(v,url_map.get(v,relative_map.get(v,v))))
   return v
  with store.transaction() as c:
   for row in docs:
    kind=row['kind']
    if kind in excluded:continue
    val=remap(row['value']);val['projectId']=new
    if kind=='project':val['title']=val.get('title','项目')+' · 恢复副本';val.pop('branchOf',None)
    if kind=='candidate':val['status']='archived';val['visible']=False
    if kind in ('render','asset_option'):val['restoredFromBackup']=True
    if kind=='branch':val['status']='abandoned'
    store.put(kind,val,new,conn=c)
   # Retain original audit as read-only provenance, not re-executed commands.
   store.put('backup_provenance',{'id':uid('backup_history'),'projectId':new,'sourceProjectId':original,'operations':manifest.get('operations',[]),'restoredAt':now()},new,conn=c)
   store.audit(new,'restore_backup',[],{'sourceProjectId':original,'sourceSystem':title},c)
  return {'projectId':new,'title':store.get(new).get('title')}
 @app.post('/api/projects/{id}/comments')
 def comment(id:str,data:dict):
  ensure(str(data.get('text','')).strip(),'批注不能为空');obj={**data,'id':uid('comment'),'projectId':id,'createdAt':now()};store.put('comment',obj,id);return obj
 @app.get('/api/projects/{id}/comments')
 def comments(id:str):return store.list(id,'comment')
 @app.get('/')
 def index(request:Request):
  prefix=request.scope.get('root_path','')
  html=(root/'static'/'index.html').read_text(encoding='utf-8')
  html=html.replace('/static/',prefix+'/static/')
  html=html.replace('</body>','<script type="module" src="'+prefix+'/static/workspaces.js"></script></body>')
  return HTMLResponse(html)
 (store.root/'media').mkdir(exist_ok=True)
 @app.get('/media/{relative:path}')
 def media_file(relative:str):
  candidates=[safe_path(Path(base),relative) for base in getattr(store,'media_roots',[store.root/'media'])]
  files=store.list(kind='file')
  allowed=next((item for item in files if Path(item['path']).resolve() in candidates and Path(item['path']).is_file()),None)
  ensure(allowed,'素材不存在或未公开','not_found',404)
  return FileResponse(Path(allowed['path']),filename=None)
 @app.get('/api/files/{fileid}/download')
 def download(fileid:str):
  f=store.get(fileid);ensure('path' in f and 'url' in f,'不是公开附件');path=Path(f['path']).resolve();ensure(any(path.is_relative_to(Path(base).resolve()) for base in getattr(store,'media_roots',[store.root/'media'])) and path.is_file(),'附件不可用', 'not_found',404)
  return FileResponse(path,filename=f.get('filename',path.name))
 app.mount('/static',StaticFiles(directory=root/'static'),name='static')
