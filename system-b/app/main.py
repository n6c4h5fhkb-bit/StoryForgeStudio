from __future__ import annotations
import copy,json,os,shutil,csv,io,zipfile,math,re
from pathlib import Path
from urllib.parse import quote
from fastapi import FastAPI
from fastapi.responses import JSONResponse,Response,FileResponse
from pydantic import ValidationError
from .core import Store,Jobs,ensure,uid,now,digest,DomainError
from .settings import Settings
from .llm import LLM
from .http import install_http
from .production import ProductionService,KINDS
from .runner import RunnerRegistry
from .gates import Gates
from .assembly import Assembly
from .cinema import PRESETS,PROFILE,COMPILER_VERSION
from .models import SceneDirection,ShotContract,TaskSpec,RunResult
from .reading_export import export_reading
from studio.directing_methods import METHOD_VERSION
from .experience import ExperienceService
from .sequence_review import review_sequence

ROOT=Path(__file__).resolve().parents[1]
def create_app(data_dir=None, shared=None):
 app=FastAPI(title='System B · Audiovisual Director',version='2.0.0');root=Path(data_dir or os.environ.get('STUDIO_DATA',ROOT/'data')).resolve();s=(shared or {}).get('store') or Store(root);settings=(shared or {}).get('settings') or Settings(root);jobs=(shared or {}).get('jobs') or Jobs(s);llm=LLM(s,settings);runners=RunnerRegistry(s,settings,ROOT);b=ProductionService(s,settings,llm,runners,ROOT);b.gates=Gates(s,settings,llm);b.assembler=Assembly(b);experience=ExperienceService(s,'B');b.experiences=experience
 app.state.store=s;app.state.settings=settings;app.state.jobs=jobs;app.state.service=b;app.state.runners=runners;app.state.experience=experience
 install_http(app,s,settings,jobs,ROOT,'SYSTEM B')
 @app.post('/api/jobs/{identifier}/resume')
 def resume_text_job(identifier:str):
  old=jobs.get(identifier);ensure(old['state'] in ('cancelled','interrupted','failed'),'只能恢复已停止任务','job_state',409)
  p=old['project'];kind=old['kind'];data={**old['data'],'operationId':'resume:'+identifier}
  ensure(kind in ('advance','sequence_review','refine','propose_B0','propose_B1','propose_B2','propose_B3','propose_B4'),'媒体任务请重新预览本次费用后执行','manual_resume',409)
  action=(lambda progress,check:review_sequence(b,p,data['sceneId'],progress,check,task_id=data.get('taskId'))) if kind=='sequence_review' else (lambda progress,check:b.advance(p,data,progress,check)) if kind=='advance' else (lambda progress,check:b.propose(p,'B4' if kind=='refine' else kind[-2:],data,progress,check))
  return jobs.submit(p,kind,data,action,operation_id=data['operationId'])
 @app.exception_handler(ValidationError)
 async def validation(request,e):return JSONResponse({'error':'字段校验失败','code':'validation','details':json.loads(e.json())},422)
 @app.get('/api/projects')
 def projects():return [p for p in s.list(kind='project') if p.get('workspace','B' if p.get('styleId') else 'A')=='B']
 @app.post('/api/projects')
 def create(data:dict):return b.create(data)
 @app.get('/api/projects/{p}')
 def project(p:str):
  obj=b.get(p);obj['assetOptions']=s.list(p,'asset_option');obj['runners']=runners.profiles();obj['workflow']=b.next_step(p);return obj
 @app.get('/api/projects/{p}/workflow')
 def workflow(p:str,sceneId:str|None=None):return b.next_step(p,sceneId)
 @app.post('/api/projects/{p}/shooting/propose')
 def shooting_propose(p:str,data:dict):return jobs.submit(p,'shooting',data,lambda progress,check:b.propose_shooting(p,data,progress,check),operation_id=data.get('operationId'))
 @app.post('/api/projects/{p}/shooting/{identifier}/adopt')
 def shooting_adopt(p:str,identifier:str,data:dict|None=None):
  result=b.adopt_shooting(p,identifier,data or {});experience.signal(p,{'kind':'shooting_script_adopted','targetId':identifier,'operationId':'adopt:'+identifier});return result
 @app.get('/api/projects/{p}/shooting/{identifier}/adoption-preview')
 def shooting_adoption_preview(p:str,identifier:str):return b.shooting_adoption_plan(p,identifier)
 @app.post('/api/projects/{p}/shooting/{identifier}/reject')
 def shooting_reject(p:str,identifier:str,data:dict):
  row=s.get(identifier);ensure(row['projectId']==p and row['status']=='proposed','只能拒绝本项目待选稿');row.update(status='rejected',reason=data.get('reason',''));saved=s.put('shooting_script',row,p)
  if data.get('reason'):experience.record(p,{'text':data['reason'],'source':'shooting_rejection','explicit':False,'inferred':True,'anchor':{'type':'shooting_script','id':identifier},'operationId':data.get('operationId') or 'reject:'+identifier})
  return saved
 @app.post('/api/projects/{p}/import-script-package/preview')
 def script_import_preview(p:str,data:dict):return b.script_import_plan(p,data)
 @app.post('/api/projects/{p}/import-script-package')
 def script_import(p:str,data:dict):return b.import_script_package(p,data.get('package',data),plan_hash=data.get('planHash'))
 @app.post('/api/projects/{p}/change-requests')
 def request_story_change(p:str,data:dict):return b.create_change_request(p,data)
 @app.post('/api/projects/{p}/scenes/{identifier}/sequence-review')
 def sequence_review(p:str,identifier:str,data:dict):
  data={**data,'sceneId':identifier};return jobs.submit(p,'sequence_review',data,lambda progress,check:review_sequence(b,p,identifier,progress,check,task_id=data.get('taskId')),operation_id=data.get('operationId'))
 @app.post('/api/projects/{p}/generation-tasks/{identifier}/adopt')
 def adopt_clip_group(p:str,identifier:str,data:dict):
  data={**data,'taskId':identifier};return jobs.submit(p,'adopt_clips',data,lambda progress,check:b.adopt_clip_group(p,identifier,data,progress,check),operation_id=data.get('operationId'))
 @app.post('/api/projects/{p}/generation-tasks')
 def generation_tasks(p:str,data:dict):return b.plan_generation_tasks(p,data)
 @app.post('/api/projects/{p}/generation-tasks/dry-run')
 def generation_task_cost(p:str,data:dict):return b.generation_dry_run(p,data)
 @app.post('/api/projects/{p}/generation-tasks/execute')
 def generation_task_execute(p:str,data:dict):return jobs.submit(p,'generation_units',data,lambda progress,check:b.execute_generation_tasks(p,data,progress,check),operation_id=data.get('operationId'))
 @app.post('/api/projects/{p}/generation-tasks/{identifier}/import')
 def generation_task_import(p:str,identifier:str,data:dict):return b.attach_generation_task(p,identifier,data)
 @app.post('/api/projects/{p}/assets/{identifier}/review-reference')
 def review_reference(p:str,identifier:str,data:dict):return b.review_reference(p,identifier,data)
 @app.post('/api/projects/{p}/advance')
 def advance(p:str,data:dict):
  b.get(p)
  return jobs.submit(p,'advance',data,lambda progress,check:b.advance(p,data,progress,check),operation_id=data.get('operationId'))
 @app.post('/api/projects/{p}/refine')
 def refine(p:str,data:dict):
  ensure(isinstance(data.get('instruction'),str) and data['instruction'].strip(),'请描述本次精修方向')
  ensure(isinstance(data.get('shotIds'),list) and data['shotIds'],'请先选择要修改的镜头')
  scene=s.get(data.get('sceneId',''));ensure(scene['projectId']==p,'场景不属于项目')
  experience.record(p,{'text':data['instruction'],'source':'refine_instruction','explicit':True,'anchor':{'type':'shots','id':data['shotIds'][0] if len(data['shotIds'])==1 else scene['id'],'shotIds':data['shotIds']},'operationId':'feedback:'+(data.get('operationId') or digest(data))})
  return jobs.submit(p,'refine',data,lambda progress,check:b.propose(p,'B4',data,progress,check),operation_id=data.get('operationId'))
 @app.put('/api/projects/{p}')
 def update(p:str,data:dict):
  pr=s.get(p)
  if 'presentationMode' in data:
   ensure(data['presentationMode'] in ('cinema','series','fast_drama'),'呈现方向无效')
   ensure(not b.active_shooting(p) or data['presentationMode']==pr.get('presentationMode'),'呈现方向请在 A 比较，采用后建立对应制作分支','story_workspace_required',409)
  if 'keySceneChoices' in data:
   choices=data['keySceneChoices'];known={scene['id'] for scene in b.list_active(p,'scene')}
   ensure(isinstance(choices,dict) and set(choices)<=known and all(isinstance(roles,list) and roles and all(role in ('opening','character_introduction','reveal_or_twist','climax','complex_staging','user_selected') for role in roles) for roles in choices.values()),'关键场次选择无效','key_scene',422)
  for key in ('title','source','sourceType','genre','targetDuration','rendererProfile','constraints','curves','assemblyDraft','presentationMode','keySceneChoices'):
   if key in data:pr[key]=data[key]
  target=pr.get('targetDuration');ensure(target is None or isinstance(target,(int,float)) and not isinstance(target,bool) and math.isfinite(target) and target>0,'目标时长必须为空或正数');pr.pop('budget',None);s.put('project',pr,p,expected=data.get('_version'));s.audit(p,'project_settings',[],{'fields':list(data)});return b.get(p)
 @app.post('/api/projects/{p}/propose/{stage}')
 def propose(p:str,stage:str,data:dict):
  ensure(stage in ('B0','B1','B2','B3','B4'),'阶段非法');return jobs.submit(p,'propose_'+stage,data,lambda progress,check:b.propose(p,stage,data,progress,check),operation_id=data.get('operationId'))
 @app.post('/api/projects/{p}/proposals/{id}/adopt')
 def adopt(p:str,id:str,data:dict|None=None):
  result=b.adopt_proposal(p,id,data or {});experience.signal(p,{'kind':'proposal_adopted','targetId':id,'operationId':'adopt:'+id});return result
 @app.get('/api/projects/{p}/proposals/{id}/adoption-preview')
 def proposal_adoption_preview(p:str,id:str):
  row=s.get(id);ensure(row['projectId']==p,'提案不属于项目');return b.director_adoption_plan(p,id) if row.get('workflowVersion',0)>=2 else {'proposalId':id,'planHash':digest({'id':id,'version':row.get('_version')})}
 @app.post('/api/projects/{p}/proposals/{id}/reject')
 def reject(p:str,id:str,data:dict):
  obj=s.get(id);ensure(obj['projectId']==p,'提案不属于项目');obj['status']='rejected';obj['rejectReason']=data.get('reason','');saved=s.put('proposal',obj,p);s.audit(p,'proposal_rejected',[id],data)
  if data.get('reason'):experience.record(p,{'text':data['reason'],'source':'proposal_rejection','explicit':False,'inferred':True,'anchor':{'type':'proposal','id':id},'operationId':data.get('operationId') or 'reject:'+id})
  return saved
 @app.put('/api/projects/{p}/proposals/{id}')
 def edit_proposal(p:str,id:str,data:dict):
  obj=s.get(id);ensure(obj['projectId']==p and obj['status']=='proposed','只能编辑未采纳提案');ensure(obj.get('workflowVersion')!=2,'新版导演稿请通过局部精修重新复核','review_required',409);obj['payload']=data['payload'];obj['humanEdited']=True;s.put('proposal',obj,p);s.audit(p,'proposal_edited',[id],{'fields':list(data)});return obj
 @app.post('/api/projects/{p}/objects/{kind}/plan')
 def change_plan(p:str,kind:str,data:dict):return b.change_plan(p,kind,data.get('object',data))
 @app.post('/api/projects/{p}/objects/{kind}')
 def save_object(p:str,kind:str,data:dict):return b.save(p,kind,data.get('object',data),data.get('planHash'))
 @app.get('/api/projects/{p}/objects/{kind}/{id}/revisions')
 def object_revisions(p:str,kind:str,id:str):
  obj=s.get(id);ensure(obj['projectId']==p,'对象不属于项目');return [r for r in s.list(p,'revision') if r.get('objectId')==id and r.get('kind')==kind]
 @app.post('/api/projects/{p}/objects/{kind}/{id}/restore')
 def object_restore(p:str,kind:str,id:str,data:dict):
  revision=s.get(data['revisionId']);current=s.get(id);ensure(revision['projectId']==p and revision['objectId']==id,'版本不属于该对象');restored={**revision['after'],'_version':current['_version']};return b.save(p,kind,restored,data.get('planHash'))
 @app.post('/api/projects/{p}/objects/{kind}/{id}/finalize')
 def finalize(p:str,kind:str,id:str,data:dict):return b.finalize(p,kind,id,data.get('expectedVersion'))
 @app.post('/api/projects/{p}/objects/{kind}/{id}/unlock')
 def unlock(p:str,kind:str,id:str,data:dict):
  ensure(data.get('confirmed'),'解锁需要确认');obj=s.get(id);ensure(obj['projectId']==p,'对象不属于项目');obj['status']='accepted';s.put(kind,obj,p);s.audit(p,'unlock_'+kind,[id],{'reason':data.get('reason','人工解锁')});return obj
 @app.post('/api/projects/{p}/objects/{kind}/{id}/archive')
 def archive(p:str,kind:str,id:str,data:dict):
  ensure(data.get('confirmed'),'归档需要确认');obj=s.get(id);ensure(obj['projectId']==p and obj['status']!='locked','锁定对象不能归档');obj['status']='archived';return b.save(p,kind,obj,data.get('planHash'))
 @app.post('/api/projects/{p}/objects/{kind}/{id}/resolve')
 def resolve(p:str,kind:str,id:str,data:dict):
  ensure(data.get('reason'),'仲裁必须说明理由');obj=s.get(id);ensure(obj['projectId']==p,'对象不属于项目');obj['freshness']='clean';obj['freshnessNotes']=[];obj['resolutionReason']=data['reason'];s.put(kind,obj,p);s.audit(p,'human_arbitration',[id],data);return obj
 @app.get('/api/projects/{p}/scenes/{id}/validate')
 def validate_scene(p:str,id:str):return b.validate_scene(p,id)
 @app.get('/api/projects/{p}/scenes/{id}/manifest')
 def manifest(p:str,id:str):return b.manifest(p,id)
 @app.post('/api/projects/{p}/assets/generate')
 def asset_gen(p:str,data:dict):return jobs.submit(p,'asset_render',data,lambda progress,check:b.asset_render(p,data,progress,check),operation_id=data.get('operationId'))
 @app.post('/api/projects/{p}/assets/dry-run')
 def asset_dry_run(p:str,data:dict):return b.asset_dry_run(p,data)
 @app.post('/api/projects/{p}/assets/options/{id}/accept')
 def asset_accept(p:str,id:str):return b.accept_asset_option(p,id)
 @app.post('/api/projects/{p}/assets/{id}/reference')
 def asset_reference(p:str,id:str,data:dict):
  asset=s.get(id);f=s.get(data['fileId']);ensure(asset['projectId']==p and f['projectId']==p,'资产与文件须属于本项目');variant=s.get(data.get('variantId') or asset['defaultVariantId']);variant['referenceFileId']=f['id'];return b.save(p,'variant',variant,data.get('planHash'))
 @app.post('/api/projects/{p}/render/preview')
 def preview(p:str,data:dict):
  request=b.render_request(p,data);return {'prompt':request['compiled'],'renderKey':request['key'],'references':request['refs'],'profile':request['profile'],'seed':request['seed']}
 @app.post('/api/projects/{p}/render/dry-run')
 def dry_run(p:str,data:dict):return b.dry_run(p,data)
 @app.post('/api/projects/{p}/render/execute')
 def render(p:str,data:dict):return jobs.submit(p,'render',data,lambda progress,check:b.render(p,data,progress,check))
 @app.post('/api/projects/{p}/render/retry-plan')
 def retry_plan(p:str,data:dict):return b.retry_plan(p,data)
 @app.post('/api/projects/{p}/render/import')
 def import_render(p:str,data:dict):return b.attach_render(p,data)
 @app.post('/api/projects/{p}/renders/{id}/review')
 def review(p:str,id:str,data:dict):return b.select_render(p,id,data)
 @app.get('/api/projects/{p}/renders/{id}/adoption-preview')
 def adoption_preview(p:str,id:str):
  render=s.get(id);ensure(render['projectId']==p and render['kind']=='clip','视频不属于项目');shot=s.get(render['shotId']);file=s.get(render['fileId']);probe=b.gates.probe(file['path']);manifest=b.event_manifest(p,shot) if shot.get('eventId') else {}
  return {'duration':float(probe['format'].get('duration',0)),'expectedEndState':{r['entityId']:manifest['end'][r['entityId']] for r in manifest.get('resolved',[])},'referenceIssues':manifest.get('missing',[])}
 @app.post('/api/projects/{p}/renders/{id}/gate')
 def gate(p:str,id:str):
  r=s.get(id);ensure(r['projectId']==p,'素材不属于项目');shot=s.get(r['shotId']) if r.get('shotId') else None;return jobs.submit(p,'media_gate',{},lambda progress,check:b.gates.inspect(p,r,shot,check))
 @app.post('/api/projects/{p}/renders/shortlist')
 def shortlist(p:str,data:dict):
  ids=data.get('renderIds',[]);ensure(0<len(ids)<=3,'每轮最多保留 3 份候选');rows=[s.get(id) for id in ids];ensure(len({r['shotId'] for r in rows})==1 and all(r['projectId']==p for r in rows),'短名单须属于同一镜头')
  with s.transaction() as c:
   for r in s.list(p,'render',c):
    if r['shotId']==rows[0]['shotId'] and r['kind']==rows[0]['kind']:r['shortlisted']=r['id'] in ids;s.put('render',r,p,conn=c)
  s.audit(p,'shortlist',[r['id'] for r in rows],{'sourceCount':data.get('sourceCount'),'humanReview':True});return rows
 @app.post('/api/projects/{p}/circuit/reset')
 def reset(p:str,data:dict):
  ensure(data.get('reason'),'熔断复位请说明已处理的原因');pr=s.get(p);pr.setdefault('circuit',{})[data['sceneId']]=0;s.put('project',pr,p);s.audit(p,'circuit_reset',[data['sceneId']],data);return pr
 @app.post('/api/projects/{p}/assembly/plan')
 def assembly_plan(p:str,data:dict):return b.assembler.plan(p,data)
 @app.post('/api/projects/{p}/assembly/run')
 def assembly_run(p:str,data:dict):return jobs.submit(p,'assembly',data,lambda progress,check:b.assembler.run(p,data,progress,check))
 @app.post('/api/projects/{p}/assemblies/{id}/accept')
 def accept_assembly(p:str,id:str,data:dict):
  ensure(data.get('confirmed'),'最终成片必须人工验收');obj=s.get(id);ensure(obj['projectId']==p,'成片不属于项目');obj['status']='accepted';obj['acceptance']={'at':now(),'notes':data.get('notes','')};s.put('assembly',obj,p);s.audit(p,'film_accepted',[id],data);return obj
 @app.post('/api/projects/{p}/import-scene-export')
 def import_a(p:str,data:dict):return b.import_scene_export(p,data)
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
  obj=b.get(p);title=obj['project']['title']
  if format=='storyboard.html':content=export_reading(obj,'B',s);mime='text/html';ext='-分镜阅读版.html'
  elif format=='json':content=json.dumps({'format':'system-b-v1',**obj},ensure_ascii=False,indent=2);mime='application/json';ext='.json'
  elif format=='shots.csv':
   out=io.StringIO();writer=csv.writer(out);writer.writerow(['镜头ID','场次','镜号','景别','机位','焦段','运镜','时长','动作','必传信息','资产变体','表演过程','摄影机触发条件','切点','切镜依据'])
   for shot in obj['shots']:
    if shot['status']=='archived':continue
    writer.writerow([shot['id'],shot['sceneId'],shot['order']+1,shot['shotSize'],shot['angle'],shot['lens'],shot['movement']['type'],shot['duration'],shot.get('actionLine',''),'；'.join(shot['informationPayload']),';'.join(shot['assetVariants']),json.dumps(shot.get('performanceBeats',[]),ensure_ascii=False),json.dumps(shot.get('cameraCue',{}),ensure_ascii=False),shot.get('cutPoint',{}).get('cue',''),shot.get('cutPoint',{}).get('reason','')])
   content='\ufeff'+out.getvalue();mime='text/csv';ext='-分镜.csv'
  elif format=='prompts':
   rows=[]
   for shot in b.ordered_shots(p,[row for row in b.list_active(p,'shot') if s.get(row['sceneId'])['status']!='archived']):
    from .cinema import compile_prompt
    manifest=b.event_manifest(p,shot) if shot.get('eventId') else b.manifest(p,shot['sceneId'])
    rows.append({'shotId':shot['id'],'sceneId':shot['sceneId'],'eventId':shot.get('eventId'),'presentationId':shot.get('presentationId'),**compile_prompt(b.with_dialogue(p,shot),manifest,b.style(p),b.renderer_profile(p))})
   content=json.dumps({'compilerVersion':COMPILER_VERSION,'shots':rows},ensure_ascii=False,indent=2);mime='application/json';ext='-prompts.json'
  elif format=='producibility':
   content=json.dumps({'format':'ProducibilityReport','source':'system-b','projectId':p,'reports':[{'sourceSceneId':x.get('externalSceneId'), 'sceneId':x['id'],'risks':b.manifest(p,x['id'])['risky'],'issues':[shot['producibilityRisk'] for shot in b.list_active(p,'shot') if shot['sceneId']==x['id'] and shot['producibilityRisk']['score']>=.5]} for x in b.list_active(p,'scene')]},ensure_ascii=False,indent=2);mime='application/json';ext='-可生成性报告.json'
  elif format=='production-package':
   ordered=b.ordered_shots(p,[row for row in b.list_active(p,'shot') if s.get(row['sceneId'])['status']!='archived'])
   selected=[row for row in obj['renders'] if row.get('selected') and row.get('freshness')!='broken']
   adopted_files=[];missing=[]
   for row in selected:
    file=s.get(row['fileId'],required=False)
    if not file or not Path(file['path']).is_file():missing.append({'type':'render','id':row['id'],'fileId':row.get('fileId')});continue
    if row.get('kind')=='clip' and not (row.get('adoption') or {}).get('interval'):missing.append({'type':'adoption_interval','renderId':row['id'],'shotId':row['shotId']})
    adopted_files.append({'role':'adopted_'+row['kind'],'renderId':row['id'],'shotId':row['shotId'],'fileId':file['id'],'filename':file['filename'],'path':file['path'],'sha256':file['sha256'],'adoption':row.get('adoption')})
   used_variants={identifier for shot in ordered for identifier in shot.get('assetVariants',[])};used_masters={v['masterId'] for v in obj['variants'] if v['id'] in used_variants};used_variants|={m.get('defaultVariantId') for m in obj['masters'] if m['id'] in used_masters and m.get('defaultVariantId')}
   for variant in [row for row in obj['variants'] if row['id'] in used_variants]:
    file=s.get(variant.get('referenceFileId',''),required=False)
    if file and Path(file['path']).is_file():adopted_files.append({'role':'asset_reference','assetId':variant['masterId'],'variantId':variant['id'],'fileId':file['id'],'filename':file['filename'],'path':file['path'],'sha256':file['sha256'],'controlBindings':(variant.get('visualReview') or {}).get('controlBindings',{})})
    elif variant.get('requiresImage'):missing.append({'type':'asset_reference','assetId':variant['masterId'],'variantId':variant['id']})
   for shot in ordered:
    try:missing.extend({'type':'shot_reference','shotId':shot['id'],**item} for item in (b.event_manifest(p,shot) if shot.get('eventId') else b.manifest(p,shot['sceneId']))['missing'])
    except DomainError as error:missing.append({'type':'shot_reference','shotId':shot['id'],'code':error.code,'reason':str(error)})
   packaged={};used=set()
   for index,row in enumerate(adopted_files,1):
    source=Path(row['path']);key=row['sha256']
    if key not in packaged:
     base=re.sub(r'[^0-9A-Za-z._-]+','_',source.name) or ('file_'+str(index)+source.suffix);name=f"media/{len(packaged)+1:03d}_{base}"
     while name in used:name=f"media/{len(packaged)+1:03d}_{digest(str(source))[:8]}_{base}"
     used.add(name);packaged[key]=name
    row['packagePath']=packaged[key]
   active=b.active_shooting(p);manifest={'format':'ProductionPackage-v1','schemaVersion':1,'project':{k:obj['project'].get(k) for k in ('id','title','presentationMode','genre','estimatedDuration','activeScriptId','sourceScriptVersionId','activeShootingId')},'versionFingerprint':digest({'project':obj['project'].get('_version'),'shooting':active.get('id') if active else None,'shots':[(x['id'],x.get('_version'),x.get('contractHash')) for x in ordered],'media':[(x['renderId'],x['sha256'],x.get('adoption')) for x in adopted_files if x['role'].startswith('adopted_')]}),'shootingScript':active,'scenes':b.list_active(p,'scene'),'shots':ordered,'assets':[{k:m.get(k) for k in ('id','name','kind','freezeString','identityHash','defaultVariantId','status')} for m in obj['masters'] if m.get('status')!='archived'],'assetVariants':[{k:v.get(k) for k in ('id','masterId','name','claims','embedded','roles','identityHash','referenceFileId','visualReview')} for v in obj['variants'] if v['id'] in used_variants],'media':[{k:v for k,v in row.items() if k!='path'} for row in adopted_files],'missing':missing,'versions':{'compilerVersion':COMPILER_VERSION,'projectVersion':obj['project'].get('_version'),'experienceSnapshot':experience.guidance(p,{'stage':'production_package'})},'createdAt':now()}
   manifest['directions']=b.list_active(p,'direction')
   manifest['versions']['methodVersion']=METHOD_VERSION
   manifest['versionFingerprint']=digest({'base':manifest['versionFingerprint'],'directions':[(d['id'],d.get('_version'),d.get('directingPlan')) for d in manifest['directions']]})
   memory=io.BytesIO()
   with zipfile.ZipFile(memory,'w',zipfile.ZIP_DEFLATED) as archive:
    archive.writestr('production-package.json',json.dumps(manifest,ensure_ascii=False,indent=2))
    archive.writestr('storyboard.html',export_reading(obj,'B',s))
    archive.writestr('README.txt','制作包包含采用拍摄版、镜头顺序、素材对应、真实文件、视频采用区间、末态观察及版本指纹。\n剪辑时只使用 production-package.json 中 media 的 adoption.interval；缺失项列在 missing。\n对白、声音提示和镜头动作位于 shots 与 shootingScript。')
    written=set()
    for row in adopted_files:
     if row['packagePath'] in written:continue
     written.add(row['packagePath']);archive.write(Path(row['path']),row['packagePath'])
   content=memory.getvalue();mime='application/zip';ext='-制作包.zip'
  else:raise DomainError('导出格式不支持')
  return Response(content,media_type=mime,headers={'Content-Disposition':"attachment; filename*=UTF-8''"+quote(title+ext)})
 @app.get('/api/runners')
 def profiles():return {'profiles':runners.profiles(),'routing':settings.read(True)['routing'],'qualification':{id:runners.qualified(p) for id,p in runners.profiles().items()}}
 @app.post('/api/runners/{id}/qualify')
 def qualify(id:str,data:dict):
  ensure(data.get('confirmed'),'Runner 验收会执行真实 CLI，需要确认');ensure(id in runners.profiles(),'未知 Runner')
  from .qualification import Qualification
  return jobs.submit(data.get('projectId'),'runner_qualification',{'runner':id},lambda progress,check:Qualification(runners).run(id,progress,check))
 @app.get('/api/runners/{id}/qualification')
 def qualifications(id:str):return s.get('qualification_'+id,required=False)
 @app.get('/api/projects/{p}/runner-runs')
 def runner_runs(p:str):return s.list(p,'runner_run')
 @app.post('/api/projects/{p}/runner-runs/{identifier}/recover')
 def recover_runner_run(p:str,identifier:str,data:dict):
  s.get(p);return jobs.submit(p,'media_recovery',{'runnerRunId':identifier},lambda progress,check:b.recover_remote(p,identifier,progress,check),operation_id=data.get('operationId') or 'recover:'+identifier)
 @app.post('/api/projects/{p}/curator/{id}')
 def curator(p:str,id:str,data:dict):
  obj=s.get(id);ensure(obj['projectId']==p,'条目不属于项目');obj['status']=data.get('status','reviewed');obj['note']=data.get('note','');s.put('curator_item',obj,p);s.audit(p,'curator_review',[id],data);return obj
 @app.get('/api/schemas')
 def schemas():return {'presets':PRESETS,'rendererProfile':PROFILE,'direction':SceneDirection.model_json_schema(),'shot':ShotContract.model_json_schema(),'task':TaskSpec.model_json_schema(),'result':RunResult.model_json_schema()}
 return app
app=None if os.environ.get('STUDIO_EMBEDDED')=='1' else create_app()
