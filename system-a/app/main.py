from __future__ import annotations
import copy,json,os,re,difflib,base64,mimetypes
from pathlib import Path
from urllib.parse import quote
from fastapi import FastAPI
from fastapi.responses import Response,JSONResponse
from pydantic import ValidationError
from .core import Store,Jobs,DomainError,ensure,uid,now,digest,canonical
from .settings import Settings
from .llm import LLM
from .http import install_http
from .story import StoryService,OPS,STRATEGIES,LEVELS,clean
from .models import ProbeSpec,CANDIDATE_SCHEMA
from .reading_export import export_reading
from .ideation import IdeationService,SCOPE as IDEATION_SCOPE
from .novel import NovelService
from .experience import ExperienceService
from .formats import FormatsService

ROOT=Path(__file__).resolve().parents[1]
def create_app(data_dir=None, shared=None):
 app=FastAPI(title='System A · Story Decision System',version='2.0.0')
 root=Path(data_dir or os.environ.get('STUDIO_DATA',ROOT/'data')).resolve();store=(shared or {}).get('store') or Store(root);settings=(shared or {}).get('settings') or Settings(root);jobs=(shared or {}).get('jobs') or Jobs(store);llm=LLM(store,settings);service=StoryService(store,settings,llm);experience=ExperienceService(store,'A');service.experiences=experience
 app.state.store=store;app.state.settings=settings;app.state.jobs=jobs;app.state.service=service;app.state.experience=experience
 install_http(app,store,settings,jobs,ROOT,'SYSTEM A')
 formats=FormatsService(service);service.formats=formats;app.state.formats=formats
 ideation=IdeationService(service)
 novel=NovelService(service)
 @app.post('/api/jobs/{identifier}/resume')
 def resume_text_job(identifier:str):
  old=jobs.get(identifier);ensure(old['state'] in ('cancelled','interrupted','failed'),'只能恢复已停止的任务','job_state',409)
  p=old['project'];kind=old['kind'];data={**old['data'],'operationId':'resume:'+identifier,'generationId':old['data'].get('generationId') or old['data'].get('operationId') or 'legacy:'+identifier}
  ensure(kind in ('advance','novel_analyze','novel_adapt','refine','script_format') or kind in OPS,'此任务请回到对应创作入口重试','manual_resume',409)
  action=(lambda progress,check:formats.propose(p,data,progress,check)) if kind=='script_format' else (lambda progress,check:novel.analyze_all(p,progress,check)) if kind=='novel_analyze' else (lambda progress,check:novel.propose(p,data,progress,check)) if kind=='novel_adapt' else (lambda progress,check:service.advance(p,data,progress,check)) if kind=='advance' else (lambda progress,check:service.generate(p,{**data,**({'op':'polish','candidateCount':1} if kind=='refine' else {'op':kind})},progress,check))
  return jobs.submit(p,kind,data,action,operation_id=data['operationId'])
 @app.get('/api/projects/{p}/scripts')
 def script_versions(p:str):return formats.list(p)
 @app.post('/api/projects/{p}/scripts/propose')
 def script_propose(p:str,data:dict):
  if str(data.get('instruction','')).strip():experience.record(p,{'text':data['instruction'],'source':'script_instruction','explicit':True,'conditions':{'presentationMode':data.get('mode',store.get(p).get('presentationMode','fast_drama'))},'anchor':{'type':'script_version','id':store.get(p).get('activeScriptVersionId'),'sceneIds':data.get('sceneIds',[])},'operationId':'feedback:'+(data.get('operationId') or digest(data))})
  return jobs.submit(p,'script_format',data,lambda progress,check:formats.propose(p,data,progress,check),operation_id=data.get('operationId'))
 @app.post('/api/projects/{p}/scripts/publish-current')
 def script_publish(p:str):return formats.publish_current(p)
 @app.post('/api/projects/{p}/scripts/{identifier}/adopt')
 def script_adopt(p:str,identifier:str,data:dict):return formats.adopt(p,identifier,data)
 @app.post('/api/projects/{p}/scripts/{identifier}/reject')
 def script_reject(p:str,identifier:str,data:dict):
  row=store.get(identifier);ensure(row['projectId']==p and row.get('status')=='proposed','只能拒绝本项目的待选剧本');row.update(status='rejected',reason=data.get('reason',''));store.put('script_version',row,p)
  if data.get('reason'):experience.record(p,{'text':data['reason'],'source':'script_rejection','explicit':False,'inferred':True,'conditions':{'presentationMode':row['mode']},'anchor':{'type':'script_version','id':identifier},'operationId':data.get('operationId') or 'reject:'+identifier})
  return row
 @app.get('/api/projects/{p}/scripts/compare')
 def script_compare(p:str,left:str,right:str):return formats.compare(p,left,right)
 @app.get('/api/projects/{p}/scripts/{identifier}/package')
 def script_package(p:str,identifier:str):return formats.export_package(p,identifier)
 @app.post('/api/novels')
 def create_novel(data:dict):return novel.create(data)
 @app.get('/api/projects/{p}/novel')
 def novel_source(p:str):return {**novel.get(p),'analysis':novel.analysis_status(p)}
 @app.put('/api/projects/{p}/novel')
 def update_novel_source(p:str,data:dict):return novel.update_source(p,data)
 @app.post('/api/projects/{p}/novel/analyze')
 def analyze_novel(p:str,data:dict):
  novel.get(p);return jobs.submit(p,'novel_analyze',data,lambda progress,check:novel.analyze_all(p,progress,check),operation_id=data.get('operationId'))
 @app.post('/api/projects/{p}/novel/propose')
 def novel_propose(p:str,data:dict):
  novel.get(p)
  return jobs.submit(p,'novel_adapt',data,lambda progress,check:novel.propose(p,data,progress,check),operation_id=data.get('operationId'))
 @app.post('/api/projects/{p}/novel/drafts/{identifier}/adopt')
 def novel_adopt(p:str,identifier:str):
  result=novel.adopt(p,identifier);experience.signal(p,{'kind':'novel_draft_adopted','targetId':identifier,'operationId':'adopt:'+identifier});return result
 @app.post('/api/projects/{p}/novel/drafts/{identifier}/reject')
 def novel_reject(p:str,identifier:str,data:dict):
  draft=store.get(identifier);ensure(draft['projectId']==p and draft['status']=='proposed','只能拒绝本项目待选稿');draft.update(status='rejected',reason=data.get('reason',''));saved=store.put('novel_draft',draft,p)
  if data.get('reason'):experience.record(p,{'text':data['reason'],'source':'novel_rejection','explicit':False,'inferred':True,'anchor':{'type':'novel_draft','id':identifier},'operationId':data.get('operationId') or 'reject:'+identifier})
  return saved
 @app.get('/api/brainstorms')
 def brainstorms():return {'batches':ideation.batches(),'jobs':jobs.list(IDEATION_SCOPE)}
 @app.post('/api/brainstorms')
 def brainstorm(data:dict):
  return jobs.submit(IDEATION_SCOPE,'brainstorm',data,lambda progress,check:ideation.generate(data,progress,check),operation_id=data.get('operationId'))
 @app.post('/api/brainstorms/{batch_id}/ideas/{idea_id}/adopt')
 def adopt_idea(batch_id:str,idea_id:str):return ideation.adopt(batch_id,idea_id)
 @app.exception_handler(ValidationError)
 async def validation(request,e):return JSONResponse({'error':'数据校验失败','code':'validation','details':json.loads(e.json())},422)
 @app.get('/api/projects')
 def projects():return [p for p in store.list(kind='project') if p.get('workspace','A' if p.get('canon') is not None else 'B')=='A']
 @app.post('/api/projects')
 def create(data:dict):return service.create(data)
 @app.get('/api/projects/{p}')
 def get(p:str):return {**service.get(p),'scriptVersions':formats.list(p),'changeRequests':[row for row in store.list(kind='change_request') if row.get('sourceProjectId')==p and row.get('status')=='pending'],'workflow':service.next_step(p)}
 @app.get('/api/projects/{p}/workflow')
 def workflow(p:str):return service.next_step(p)
 @app.post('/api/projects/{p}/advance')
 def advance(p:str,data:dict):
  service.get(p)
  data={**data,'generationId':data.get('generationId') or data.get('operationId') or uid('generation')}
  return jobs.submit(p,'advance',data,lambda progress,check:service.advance(p,data,progress,check),operation_id=data.get('operationId'))
 @app.post('/api/projects/{p}/refine')
 def refine(p:str,data:dict):
  ensure(isinstance(data.get('instruction'),str) and data['instruction'].strip(),'请描述本次精修方向')
  node=store.get(data.get('nodeId',''));ensure(node['projectId']==p,'节点不属于项目')
  data={**data,'generationId':data.get('generationId') or data.get('operationId') or uid('generation')}
  experience.record(p,{'text':data['instruction'],'source':'refine_instruction','explicit':True,'anchor':{'type':'node','id':node['id']},'operationId':'feedback:'+data['generationId']})
  task={**data,'op':'polish','nodeId':node['id'],'candidateCount':1}
  return jobs.submit(p,'refine',data,lambda progress,check:service.generate(p,task,progress,check),operation_id=data.get('operationId'))
 @app.put('/api/projects/{p}')
 def update(p:str,data:dict):return service.update_project(p,data)
 @app.post('/api/projects/{p}/generate')
 def generate(p:str,data:dict):
  data={**data,'generationId':data.get('generationId') or data.get('operationId') or uid('generation')}
  ensure(data.get('op','vary') in OPS,'未知操作');return jobs.submit(p,data.get('op','vary'),data,lambda progress,check:service.generate(p,data,progress,check),operation_id=data.get('operationId'))
 @app.post('/api/projects/{p}/plan')
 def plan(p:str,data:dict):return service.plan(p,data)
 @app.post('/api/projects/{p}/structure')
 def structure(p:str,data:dict):return service.structural(p,data)
 @app.post('/api/projects/{p}/candidates/{id}/adopt')
 def adopt(p:str,id:str,data:dict|None=None):
  result=service.adopt(p,id,approve_proposals=bool((data or {}).get('approveProposals')));experience.signal(p,{'kind':'candidate_adopted','targetId':id,'operationId':'adopt:'+id});return result
 @app.post('/api/projects/{p}/candidates/{id}/reject')
 def reject(p:str,id:str,data:dict):
  result=service.reject(p,id,data.get('reason',''))
  return result
 @app.get('/api/projects/{p}/candidates/{id}/diff')
 def candidate_diff(p:str,id:str,other:str|None=None):
  c=store.get(id);ensure(c['projectId']==p,'候选不属于项目');base=store.get(other)['items'] if other else ([{'contract':store.get(c['targetId'])['contract'],'body':store.get(c['targetId'])['body']}] if c['targetId'] else [])
  return {'diff':'\n'.join(difflib.unified_diff(json.dumps(base,ensure_ascii=False,indent=2).splitlines(),json.dumps(c['items'],ensure_ascii=False,indent=2).splitlines(),fromfile='基线',tofile=c['title'],lineterm=''))}
 @app.post('/api/projects/{p}/candidates/merge')
 def merge(p:str,data:dict):
  ids=data.get('candidateIds',[]);ensure(len(ids)==2,'合成需要两个候选');cs=[store.get(i) for i in ids];ensure(all(c['projectId']==p for c in cs),'跨项目候选不可合成')
  task={'op':'merge','nodeId':cs[0]['targetId'],'instruction':data.get('instruction','以 A 为基底，采用 B 的结局逻辑重新生成；不要拼接。'),'references':[{'title':c['title'],'items':c['items']} for c in cs]}
  return jobs.submit(p,'merge',task,lambda progress,check:service.generate(p,task,progress,check))
 @app.get('/api/projects/{p}/nodes/{id}/revisions')
 def revisions(p:str,id:str):return service.revisions(p,id)
 @app.post('/api/projects/{p}/nodes/{id}/restore')
 def restore(p:str,id:str,data:dict):return service.restore(p,id,data['revisionId'])
 @app.post('/api/projects/{p}/undo')
 def undo(p:str):
  history=store.history(p);undone={o.get('undoOf') for o in history if o['op']=='undo'}
  last=next((o for o in history if o['op'] in ('adopt','delete','reorder','lock','unlock','restore') and o['id'] not in undone and isinstance(o.get('after'),list)),None)
  ensure(last is not None,'没有可撤销的节点操作')
  with store.transaction() as conn:
   before={n['id']:n for n in last.get('before',[])}
   for after in last['after']:
    current=store.get(after['id'],conn);ensure(current['currentRevision']==after['currentRevision'],'该操作之后节点已再次修改，请使用节点版本历史','version_conflict',409)
    ensure(current['status']!='locked' or last['op']=='lock','锁定节点须显式解锁','locked',409)
   for after in last['after']:
    current=store.get(after['id'],conn);old=before.get(after['id']);restored=copy.deepcopy(old or current)
    if not old:restored['status']='archived'
    out=service.revise(p,restored,current,'undo',conn=conn);service.propagate(p,current,out,conn)
   store.audit(p,'undo',last['scope'],{'undoOf':last['id']},conn)
  return {'ok':True,'undoOf':last['id']}
 @app.put('/api/projects/{p}/canon')
 def canon(p:str,data:dict):return service.update_canon(p,data)
 @app.post('/api/projects/{p}/patches/{id}')
 def patch(p:str,id:str,data:dict):return service.patch(p,id,bool(data.get('approve')))
 @app.get('/api/projects/{p}/readthrough')
 def readthrough(p:str):store.audit(p,'readthrough',[],{});return service.readthrough(p)
 @app.post('/api/projects/{p}/scan')
 def scan(p:str,data:dict):return jobs.submit(p,'scan',data,lambda progress,check:service.scan(p,bool(data.get('semantic')),check))
 @app.get('/api/projects/{p}/knowledge')
 def knowledge(p:str):return service.knowledge(p)
 @app.post('/api/projects/{p}/edges')
 def edge(p:str,data:dict):return service.add_edge(p,data)
 @app.put('/api/projects/{p}/edges/{id}')
 def edge_update(p:str,id:str,data:dict):
  with store.transaction() as c:
   e=store.get(id,c);ensure(e['projectId']==p,'边不属于项目')
   status=data.get('status',e['status']);ensure(status in ('open','progressing','paid','orphan'),'伏笔状态无效');old=copy.deepcopy(e);e['status']=status
   store.put('edge',e,p,conn=c);store.audit(p,'edge_update',[id],{'beforeEdge':old,'afterEdge':e},c)
  return e
 @app.post('/api/projects/{p}/probe')
 def probe(p:str,data:dict):return jobs.submit(p,'probe',data,lambda progress,check:service.probe(p,data['batchId'],progress,check))
 @app.put('/api/projects/{p}/probe-specs')
 def specs(p:str,data:dict):
  values=data.get('specs',[]);ensure(values,'规格不能为空')
  for s in values:
   ProbeSpec.model_validate(s);ensure(not re.search(r'第\s*\d+\s*场',s['sceneSelector']),'选择器不能指定场次位置');s={**s,'id':s.get('id',uid('probespec')),'projectId':p,'registeredAt':now()};store.put('probe_spec',s,p)
  store.audit(p,'probe_specs_update',[],{'specs':values});return service.probe_specs(p)
 @app.post('/api/projects/{p}/experiments')
 def experiment(p:str,data:dict):
  ensure(data.get('outlineChoice') and data.get('probeChoice'),'须记录两次选择');obj={**data,'id':uid('experiment'),'projectId':p,'switched':data['outlineChoice']!=data['probeChoice'],'createdAt':now()};store.put('experiment',obj,p);return obj
 @app.post('/api/projects/{p}/experiments/blind')
 def blind_experiment(p:str,data:dict):
  import secrets
  batch=store.get(data['batchId']);ensure(batch['projectId']==p,'候选批次不属于项目');cs=[c for c in store.list(p,'candidate') if c['batchId']==batch['id'] and c.get('visible')];ids=[c['id'] for c in cs];ensure(data.get('outlineChoice') in ids and data.get('reason'),'先记录大纲选择与理由')
  order=secrets.SystemRandom().sample(ids,len(ids));experiment={'id':uid('experiment'),'projectId':p,'batchId':batch['id'],'outlineChoice':data['outlineChoice'],'reason':data['reason'],'blindOrder':order,'status':'awaiting_probe','createdAt':now()};store.put('experiment',experiment,p)
  def work(progress,check):
   spikes=service.probe(p,batch['id'],progress,check);by={x['candidateId']:x for x in spikes};cards=[]
   for i,cid in enumerate(order):
    spike=by[cid];cards.append({'label':'样戏 '+str(i+1),'index':i,'script':spike['script'],'signals':spike['signals'],'imageUrl':spike.get('imageUrl')})
   experiment['status']='awaiting_choice';store.put('experiment',experiment,p);return {'experimentId':experiment['id'],'cards':cards}
  return jobs.submit(p,'blind_probe',{'experimentId':experiment['id']},work)
 @app.post('/api/projects/{p}/experiments/{id}/choose')
 def finish_experiment(p:str,id:str,data:dict):
  exp=store.get(id);ensure(exp['projectId']==p and exp.get('status')=='awaiting_choice','实验已结束或不属于项目');index=int(data['index']);ensure(0<=index<len(exp['blindOrder']),'样戏序号无效');exp.update(probeChoice=exp['blindOrder'][index],switched=exp['outlineChoice']!=exp['blindOrder'][index],status='completed',completedAt=now());store.put('experiment',exp,p);store.audit(p,'blind_choice',[],{'experimentId':id,'switched':exp['switched']});return {'switched':exp['switched'],'outlineChoice':exp['outlineChoice'],'probeChoice':exp['probeChoice']}
 @app.get('/api/projects/{p}/experiments')
 def experiments(p:str):
  rows=[x for x in store.list(p,'experiment') if 'switched' in x];rate=sum(x['switched'] for x in rows)/len(rows) if rows else None
  return {'rows':rows,'switchRate':rate,'decision':None if rate is None or .2<=rate<=.4 else 'revert-first' if rate<.2 else 'probe-first','note':'20%–40%（含边界）原文未判定，不自动做决策。'}
 @app.post('/api/projects/{p}/branches')
 def branch(p:str,data:dict):return service.branch(p,data.get('title',''))
 @app.get('/api/projects/{p}/branches/{id}/compare')
 def compare(p:str,id:str):return service.compare_branch(p,id)
 @app.post('/api/projects/{p}/branches/{id}/adopt')
 def adopt_branch(p:str,id:str):return service.adopt_branch(p,id)
 @app.post('/api/projects/{p}/branches/{id}/abandon')
 def abandon_branch(p:str,id:str):return service.adopt_branch(p,id,True)
 @app.get('/api/projects/{p}/metrics')
 def metrics(p:str):return service.metrics(p)
 @app.post('/api/projects/{p}/intent')
 def intent(p:str,data:dict):
  instruction=data.get('instruction','');ensure(instruction,'请输入指令');node=data.get('nodeId')
  guessed='rewrite'
  for word,op in [('紧张','escalate'),('压缩','compress'),('扩展','expand'),('对白','fill'),('风格','restyle'),('反转','twist'),('伏笔','add_setup'),('删除','delete')]:
   if word in instruction:guessed=op;break
  out=llm.json(p,'intent','将用户请求解析为有限操作，禁止执行。JSON {"op":"operation","nodeId":"selected id","instruction":"original instruction"}。合法操作：'+','.join(OPS|{'delete','reorder','lock','unlock'})+'. 无法确定位置时仍保留当前选中节点，不猜节点ID。',{'instruction':instruction,'selected':node,'nodes':[{'id':n['id'],'title':n['title']} for n in service.nodes(p)]},demo={'op':guessed,'nodeId':node,'instruction':instruction})
  ensure(out.get('op') in OPS|{'delete','reorder','lock','unlock'},'指令解析到不支持的操作');return {**out,'plan':service.plan(p,out)}
 @app.post('/api/projects/{p}/voice-audit')
 def voice(p:str):
  def work(progress,check):
   by={}
   for n in service.nodes(p):
    if n['level'] not in ('script','scene') or n['status']=='archived':continue
    for d in n.get('body',{}).get('dialogue',[]):by.setdefault(d.get('character','未标注'),[]).append({'nodeId':n['id'],'text':d.get('text','')})
   out=llm.json(p,'validator','跨场按角色审计语言区分度。不要生成或拼接台词。输出 JSON {"characters":[{"id":"","patterns":[],"risks":[],"evidence":[]}]}。只能指出有原句证据的问题。',{'dialogueByCharacter':by,'canon':store.get(p)['canon']},demo={'characters':[{'id':id,'patterns':['演示审计，未调用模型'],'risks':[],'evidence':d[:2]} for id,d in by.items()]},check=check)
   store.audit(p,'voice_audit',[],{'result':out});return out
  return jobs.submit(p,'voice_audit',{},work)
 @app.post('/api/projects/{p}/seed-vision')
 def seed_vision(p:str,data:dict):
  file=store.get(data['fileId']);ensure(file['projectId']==p and file['filename'].lower().endswith(('.jpg','.jpeg','.png','.webp')),'请选择本项目图片')
  def work(progress,check):
   path=Path(file['path']);out=llm.json(p,'vision','分析创作种子图片。分离可见观察与叙事联想，不把猜测当事实。返回 JSON {"observations":[],"motifs":[],"directions":[]}。不要修改正式设定。','提取构图、人物外观、空间、情绪和潜在张力。',demo={'observations':['演示模式不识别实际图片'],'motifs':[],'directions':[]},images=[{'mime':mimetypes.guess_type(path.name)[0] or 'image/png','data':base64.b64encode(path.read_bytes()).decode()}],check=check)
   obj={**out,'id':uid('observation'),'projectId':p,'fileId':file['id']};store.put('observation',obj,p);return obj
  return jobs.submit(p,'seed_vision',data,work)
 @app.get('/api/projects/{p}/experiences')
 def experiences(p:str):return experience.list(p)
 @app.post('/api/projects/{p}/feedback')
 def feedback(p:str,data:dict):return experience.record(p,data)
 @app.post('/api/projects/{p}/experiences/{identifier}/confirm')
 def confirm_experience(p:str,identifier:str,data:dict):return experience.confirm(p,identifier,data)
 @app.put('/api/projects/{p}/experiences/{identifier}')
 def update_experience(p:str,identifier:str,data:dict):return experience.update(p,identifier,data)
 @app.post('/api/projects/{p}/experiences/{identifier}/validate')
 def validate_experience(p:str,identifier:str,data:dict):return experience.validate(p,identifier,data)
 @app.get('/api/projects/{p}/experience-pack')
 def export_experience_pack(p:str):return experience.export_pack(p)
 @app.post('/api/projects/{p}/experience-pack/import')
 def import_experience_pack(p:str,data:dict):return experience.import_pack(p,data)
 @app.get('/api/projects/{p}/export/{format}')
 def export(p:str,format:str):
  if format=='html':
   body=export_reading(service.get(p),'A')
   return Response(body,media_type='text/html',headers={'Content-Disposition':"attachment; filename*=UTF-8''"+quote(store.get(p)['title']+'-阅读版.html')})
  ensure(format in ('md','json','fdx','fountain','scene-export'),'导出格式不支持');body,mime,ext=service.export(p,format)
  return Response(body,media_type=mime,headers={'Content-Disposition':"attachment; filename*=UTF-8''"+quote(store.get(p)['title']+ext)})
 @app.get('/api/schemas')
 def schemas():return {'candidate':CANDIDATE_SCHEMA,'strategies':STRATEGIES,'levels':LEVELS}
 return app

app=None if os.environ.get('STUDIO_EMBEDDED')=='1' else create_app()
