from __future__ import annotations
import copy,json,math,os,re,shutil,hashlib,mimetypes,subprocess
from pathlib import Path
from .core import Store,DomainError,ensure,uid,now,digest,canonical,safe_path
from .models import SceneDirection,ShotContract,SkeletonOutput
from .cinema import PRESETS,PROFILE,COMPILER_VERSION,shot_count,allocate_durations,resolve_manifest,complete_shots,validate_shots,compile_prompt,render_key,strong_order,render_dimensions,shot_design
from .workflow import ProposalWorkflow
from .script_input import ScriptInputWorkflow
from .shooting import ShootingWorkflow
from .story_contract import normalize_document, stable_blocks, validate_shot_coverage
from studio.directing_methods import without_explanations, validate_directing_fields

KINDS=('scene','style','master','variant','asset_state','direction','shot','transition','link','render','proposal','foreshadow','assembly','gate_report','reservation','curator_item','shooting_script','adopted_script','generation_task','sequence_review','change_request')

def scrub(d):return {k:v for k,v in d.items() if k!='_version'}
def identity(kind,obj):
 fields={'style':['aslRange','shotCountRange','shotCountMode','aspectRatio'],'master':['identity','freezeString','identityHash'],'variant':['masterId','deltaString','referenceFileId','claims','identityHash','embedded','roles'],'direction':['dramaticFunction','informationPayload','tensionType','emotion','coverage','blocking','lighting','palette','sound','targetDuration','transitionIn','transitionOut']}
 return {k:obj.get(k) for k in fields.get(kind,list(obj)) if k not in ('_version','freshness','freshnessNotes','status','id','projectId')}

def scene_export_text(body,canon):
 """Preserve authored block order; action/dialogue are legacy alternatives."""
 names={e['id']:e.get('name',e['id']) for e in canon.get('characters',[]) if e.get('id')}
 def dialogue(line):
  who=line.get('character',line.get('speaker',''));name=names.get(who,who)
  aside=str(line.get('parenthetical','')).strip();prefix=str(name)+('（'+aside.strip('()（）')+'）' if aside else '')
  return (prefix+'：' if prefix else '')+str(line.get('text',''))
 blocks=body.get('blocks') or [];parts=[]
 if body.get('sceneHeading') and not any(b.get('type')=='scene_heading' for b in blocks):parts.append(str(body['sceneHeading']))
 if blocks:
  for block in blocks:
   text=dialogue(block) if block.get('type')=='dialogue' else str(block.get('text',''))
   if text:parts.append(text)
 else:
  if body.get('action'):parts.append(str(body['action']))
  parts.extend(dialogue(line) for line in body.get('dialogue',[]))
 return '\n\n'.join(parts)

def direction_demo(scene,style):
 return {'dramaticFunction':'用可见行动推进本场信息','informationPayload':scene.get('informationPayload',[]),'tensionType':scene.get('tensionType','mystery'),
 'emotion':{'entry':2,'turn':5,'exit':7},'coverage':{'master':'主体与出口在同一画面','emptyShots':False},
 'blocking':{'axisGroup':'axis_'+scene['id'],'positions':{aid:{'x':-1 if i%2==0 else 1,'y':0} for i,aid in enumerate(scene.get('characters',[]))},'description':'动作围绕主体与门口发生'},
 'lighting':{'keyDirection':45,'ratio':style.get('lightingRatio',4),'motivation':'场内窗光或实景灯'},'palette':style.get('palette','冷灰'),'sound':{'ambience':'场景底噪','musicIn':None,'musicOut':None,'silence':[]},'targetDuration':scene.get('targetDuration',20),'transitionIn':None,'transitionOut':None}

class ProductionService(ScriptInputWorkflow,ShootingWorkflow,ProposalWorkflow):
 def __init__(self,store,settings,llm,runners,root):self.s=store;self.settings=settings;self.llm=llm;self.runners=runners;self.root=root;self.gates=None;self.assembler=None
 def create(self,data):
  target=data.get('targetDuration')
  ensure(target is None or (isinstance(target,(int,float)) and not isinstance(target,bool) and math.isfinite(target) and target>0),'目标时长必须为空或正数')
  title=str(data.get('title','未命名视听项目'))[:100];source=str(data.get('source',''));p={'id':uid('b'),'workspace':'B','title':title,'source':source,'sourceType':data.get('sourceType','script'),'createdAt':now(),'currency':'USD','stage':'B0','targetDuration':target,'timingMode':'content' if target is None else 'target','styleId':'','status':'active','circuit':{},'constraints':data.get('constraints',[])}
  key=data.get('preset','vertical');ensure(key in PRESETS,'风格档无效');style={'id':uid('style'),'projectId':p['id'],**copy.deepcopy(PRESETS[key]),'preset':key,'palette':'低饱和冷灰','texture':'写实、自然光','lightingRatio':4,'promptPrefix':'cinematic live-action, natural motivated light','negativePrompt':'deformed anatomy, inconsistent identity, watermark','status':'draft','freshness':'clean','freshnessNotes':[],'compilerVersion':COMPILER_VERSION}
  style['aspectRatio']=data.get('aspectRatio',style['aspectRatio']);ensure(style['aspectRatio'] in ('9:16','16:9','2.39:1','1:1'),'请选择有效画幅')
  style['shotCountMode']='content' if target is None else 'fixed'
  p['styleId']=style['id']
  p.update(workflowVersion=data.get('workflowVersion',4),presentationMode=data.get('presentationMode','fast_drama'))
  if p['workflowVersion']>=2:style['shotCountMode']='content'
  with self.s.transaction() as c:self.s.put('project',p,p['id'],conn=c);self.s.put('style',style,p['id'],conn=c);self.s.audit(p['id'],'create_project',[],{'preset':key},c)
  return self.get(p['id'])
 def get(self,p):
  project=self.s.get(p);out={'project':project}
  for kind in KINDS:out[kind+'s']=self.s.list(p,kind)
  out['scenes']=sorted(out.pop('scenes',[]),key=lambda x:x['order']);out['shots']=sorted(out['shots'],key=lambda x:(next((i for i,s in enumerate(out['scenes']) if s['id']==x['sceneId']),0),x['order']))
  out['style']=self.s.get(project['styleId']);out['files']=self.s.list(p,'file');out['cost']=self.cost(p);out['manifests']=[self.manifest(p,s['id']) for s in out['scenes'] if s['status']!='archived'];return out
 def list_active(self,p,kind,conn=None):return [x for x in self.s.list(p,kind,conn) if x.get('status')!='archived']
 def style(self,p):return self.s.get(self.s.get(p)['styleId'])
 def require_production_ready(self,p,shot):
  scene=self.s.get(shot['sceneId']);project=self.s.get(p)
  ensure(shot.get('freshness')!='broken' and scene.get('status')!='archived','镜头设计已失效或场次已归档，先采用当前有效分镜','stale_shot',409)
  ensure(not shot.get('reviewRequired') and not any(d.get('reviewRequired') for d in self.list_active(p,'direction') if d['sceneId']==scene['id']),'本场剧本意图或拍法说明已更新，先复核导演方案；已有媒体保留','director_review_required',409)
  pending=[r for r in self.s.list(p,'change_request') if r.get('status')=='pending' and r.get('sourceScriptVersionId')==project.get('sourceScriptVersionId') and (not r.get('sceneIds') or scene.get('shootingSceneId') in r['sceneIds'])]
  ensure(not pending,'本场有待 A 处理的情节修改，先选择正式剧本或已有有效拍法','story_change_required',409,[r['id'] for r in pending])
 def shot_media_signature(self,p,shot,kind):
  """Compare actual compiled input, independent of directing explanations."""
  manifest=self.event_manifest(p,shot) if shot.get('eventId') else self.manifest(p,shot['sceneId'])
  compiled=compile_prompt(self.with_dialogue(p,copy.deepcopy(shot)),manifest,self.style(p),self.renderer_profile(p,kind),kind=kind)
  return digest({'prompt':compiled['imagePrompt' if kind=='keyframe' else 'videoPrompt'],'negative':compiled['negativePrompt'],
                 'references':compiled['referenceFileIds'],'seed':compiled['seed']})
 def manifest(self,p,sceneid):
  scene=self.s.get(sceneid);ensure(scene['projectId']==p,'场次不属于项目')
  return resolve_manifest(scene,self.list_active(p,'master'),self.list_active(p,'variant'),self.list_active(p,'asset_state'),self.list_active(p,'scene'))
 def cost(self,p):
  rs=self.s.list(p,'reservation');modelCost=sum(float(x.get('cost',0)) for x in self.s.list(p,'run'));return {'modelCost':modelCost,'spent':round(modelCost+sum(r.get('actual',r['estimate']) for r in rs if r['status'] in ('spent','unknown')),4),'reserved':round(sum(r['estimate'] for r in rs if r['status']=='reserved'),4),'unknown':sum(r['status']=='unknown' for r in rs)}
 def save(self,p,kind,data,plan_hash=None):
  ensure(kind in KINDS and kind not in ('render','reservation','shooting_script','adopted_script','generation_task','sequence_review'),'此对象不能直接写入');data=copy.deepcopy(data);old=self.s.get(data.get('id',''),required=False);ensure(old is None or old['projectId']==p,'对象不属于项目')
  if kind=='proposal':
    ensure(self.s.get(p).get('workflowVersion',1)<2 and (old or {}).get('workflowVersion',0)<2 and data.get('workflowVersion',0)<2,'新版导演稿请通过局部精修重新复核','review_required',409)
  data['id']=data.get('id') or uid(kind);data['projectId']=p;data.setdefault('status','draft');data.setdefault('freshness','clean');data.setdefault('freshnessNotes',[])
  if kind=='scene' and old and old.get('shootingScriptId'):
   ensure(all(data.get(k)==old.get(k) for k in ('body','sourceText','presentation','shootingHash','shootingScriptId','shootingSceneId')),'拍摄正文请通过转换与复核生成新版本','shooting_revision_required',409)
  if kind=='style':
   ensure(0<data['aslRange'][0]<=data['aslRange'][1] and 1<=data['shotCountRange'][0]<=data['shotCountRange'][1],'风格时长或数量范围无效')
   ensure(data['aspectRatio'] in ('9:16','16:9','2.39:1','1:1'),'不支持的画幅')
  if kind=='master':
   ensure(data.get('freezeString','').strip(),'角色/场景/道具必须有冻结描述串');ensure(data.get('kind') in ('character','location','prop'),'资产种类无效');data.setdefault('seed',int(hashlib.sha256(data['id'].encode()).hexdigest()[:8],16));data.setdefault('identity',{'description':data['freezeString']})
   if data.get('sourceEntityId'):data['identityHash']=digest({'identity':data['identity'],'freezeString':data['freezeString']}) if old and (old.get('identity')!=data['identity'] or old.get('freezeString')!=data['freezeString']) else data.get('identityHash')
  if kind=='variant':
   master=self.s.get(data['masterId']);ensure(master['projectId']==p,'变体主资产不属于项目');data.setdefault('deltaString','');data.setdefault('requiresImage',False)
   if old and old.get('referenceFileId')!=data.get('referenceFileId'):data.pop('visualReview',None)
  if kind=='asset_state':
   sceneids={s['id'] for s in self.list_active(p,'scene')};ensure(data['validFrom'] in sceneids and (not data.get('validUntil') or data['validUntil'] in sceneids),'时间轴引用未知场次')
   master=self.s.get(data['assetId']);variant=self.s.get(data['variantId']);ensure(master['projectId']==p and variant['masterId']==master['id'],'资产状态与变体不匹配')
  if kind=='scene':
   duration=data.get('targetDuration');ensure(data.get('title') and (duration is None or isinstance(duration,(int,float)) and not isinstance(duration,bool) and math.isfinite(duration) and duration>0),'场次必须有名称，已规划时长必须为正数');data.setdefault('targetDuration',None);data.setdefault('characters',[]);data.setdefault('props',[]);data.setdefault('informationPayload',[]);data.setdefault('order',len(self.list_active(p,'scene')));data.setdefault('sourceText','')
   data['bodyHash']=digest(data.get('presentation') or data['sourceText']);data['contractHash']=digest(data['informationPayload']);data.setdefault('canonHash',digest([]))
  if kind=='transition':
   ensure(data['fromScene']!=data['toScene'],'转场两端不能相同')
   for id in (data['fromScene'],data['toScene']):ensure(self.s.get(id)['projectId']==p,'转场引用跨项目')
   ensure(data['type'] in ('cut','match_cut','graphic_match','motion_match','sound_bridge','color_shift','camera_continuation'),'转场类型无效')
  if kind=='foreshadow':
   data['setupSceneId']=data.get('setupSceneId',data.get('setupScene'));data['payoffSceneId']=data.get('payoffSceneId',data.get('payoffScene'))
   ensure(self.s.get(data['assetId'])['projectId']==p,'伏笔资产跨项目');ensure(self.s.get(data['variantId'])['masterId']==data['assetId'],'伏笔变体不属于资产')
   for sid in (data.get('setupSceneId'),data.get('payoffSceneId')):
    if sid:ensure(self.s.get(sid)['projectId']==p,'伏笔场次跨项目')
   for phase in ('setup','payoff'):
    delivery=data.get(phase+'Delivery')
    if delivery is not None:ensure(isinstance(delivery,dict) and delivery.get('channel') in ('visual','sound','dialogue','action'),'伏笔交付方式无效','foreshadow_delivery',422)
  if kind=='direction':SceneDirection.model_validate(data)
  if kind=='shot':ShotContract.model_validate(data)
  if kind in ('shot','direction'):
   scene=self.s.get(data['sceneId'])
   if scene.get('shootingScriptId'):
    creative=self.creative_inputs(p,scene)
    try:validate_directing_fields(data if kind=='direction' else {},[data] if kind=='shot' else [],creative['scene'],creative['events'],creative['entities'])
    except ValueError as error:raise DomainError(str(error),'directing_fields',422)
  if kind=='link':
   ensure(data['type'] in ('cut','match_cut','frame_chain','extension','ref_video'),'衔接类型无效');a,b=self.s.get(data['from']),self.s.get(data['to']);ensure(a['projectId']==p and b['projectId']==p and a['id']!=b['id'],'衔接端点无效')
   strong_order(self.list_active(p,'shot'),[x for x in self.list_active(p,'link') if x['id']!=data['id']]+[data])
  changed=old and digest(identity(kind,old))!=digest(identity(kind,data))
  plan=self.change_plan(p,kind,data) if old or kind in ('asset_state','link','transition') else None
  if old and old['status']=='locked':
   ensure(plan_hash==plan['planHash'],'修改已定稿对象前必须预览影响并二次确认','confirmation_required',409,plan)
   data['status']='draft' if changed and kind in ('style','master') else old['status']
  with self.s.transaction() as c:
   if old and plan and plan.get('reviewOnly'):data['reviewRequired']=True
   result=self.s.put(kind,data,p,expected=data.get('_version'),conn=c)
   if plan:self.apply_impact(p,plan,c)
   rev={'id':uid('rev'),'projectId':p,'kind':kind,'objectId':data['id'],'before':scrub(old) if old else None,'after':scrub(result),'createdAt':now()};self.s.put('revision',rev,p,conn=c);self.s.audit(p,'save_'+kind,[data['id']],{'revisionId':rev['id'],'identityChanged':bool(changed),'impact':plan},c)
   if kind=='master' and not old:
    var={'id':uid('variant'),'projectId':p,'masterId':data['id'],'name':'基准','deltaString':'','requiresImage':False,'referenceFileId':None,'status':'accepted','freshness':'clean','freshnessNotes':[]}
    self.s.put('variant',var,p,conn=c);result['defaultVariantId']=var['id'];result=self.s.put('master',result,p,conn=c)
  return result
 def change_plan(self,p,kind,new):
  new=copy.deepcopy(new)
  if kind=='master' and new.get('sourceEntityId'):
   previous=self.s.get(new['id'],required=False)
   if previous and (previous.get('identity')!=new.get('identity') or previous.get('freezeString')!=new.get('freezeString')):new['identityHash']=digest({'identity':new['identity'],'freezeString':new['freezeString']})
  old=self.s.get(new['id'],required=False) or {**new,'_version':0};changed=digest(identity(kind,old))!=digest(identity(kind,new));items=[];masters=self.list_active(p,'master');variants=self.list_active(p,'variant');shots=self.list_active(p,'shot');renders=self.list_active(p,'render');dirs=self.list_active(p,'direction');trans=self.list_active(p,'transition');links=self.list_active(p,'link')
  def add(objects,freshness='broken'):
   for o in objects:
    found=next(k for k,group in [('shot',shots),('render',renders),('direction',dirs),('transition',trans),('variant',variants)] if any(x['id']==o['id'] for x in group))
    items.append({'id':o['id'],'kind':found,'freshness':freshness,'pinned':o.get('pinned',False)})
  cost='low'
  if kind=='style':
   if changed:add(dirs);add(shots);add(renders);cost='avalanche'
   else:cost='future_only'
  elif kind=='master':
   if changed:
    affected=[v for v in variants if v['masterId']==old['id']];ids={v['id'] for v in affected};add(affected);add([r for r in renders if ids.intersection(r.get('assetVariants',[]))]);cost='avalanche'
   else:cost='future_only'
  elif kind=='variant':add([r for r in renders if old['id'] in r.get('assetVariants',[])]);cost='medium'
  elif kind=='direction':
   if without_explanations(identity(kind,new))!=without_explanations(identity(kind,old)):
    ss=[s for s in shots if s['sceneId']==old['sceneId']];ids={s['id'] for s in ss};add(ss);add([r for r in renders if r.get('shotId') in ids]);add([t for t in trans if old['sceneId'] in (t['fromScene'],t['toScene'])],'opportunity');cost='high'
   else:cost='review_only'
  elif kind=='shot':
   media_kinds=[kind_name for kind_name in ('keyframe','clip') if self.shot_media_signature(p,old,kind_name)!=self.shot_media_signature(p,new,kind_name)]
   if media_kinds:
    ids={old['id']};queue=[old['id']]
    while queue:
     identifier=queue.pop(0)
     for l in links:
      if l['from']==identifier and l['type'] in ('frame_chain','extension','ref_video') and l['to'] not in ids:ids.add(l['to']);queue.append(l['to'])
    add([s for s in shots if s['id'] in ids and s['id']!=old['id']]);add([r for r in renders if r.get('shotId') in ids and (r.get('shotId')!=old['id'] or r.get('kind') in media_kinds)]);cost='medium'
   else:cost='review_only'
  elif kind=='scene':
   sceneids={old['id']};add([d for d in dirs if d['sceneId'] in sceneids]);add([sh for sh in shots if sh['sceneId'] in sceneids]);ids={sh['id'] for sh in shots if sh['sceneId'] in sceneids};add([r for r in renders if r.get('shotId') in ids]);cost='high'
  elif kind=='asset_state':
   ids={old.get('assetId'),new.get('assetId')};vs={v['id'] for v in variants if v['masterId'] in ids};add([r for r in renders if vs.intersection(r.get('assetVariants',[]))]);cost='medium'
  elif kind=='link':
   targets={old.get('to'),new.get('to')};add([r for r in renders if r.get('shotId') in targets and r.get('kind','clip')=='clip']);cost='medium'
  elif kind=='transition':
   for sceneid,last in ((old['fromScene'],True),(old['toScene'],False)):
    ss=sorted([s for s in shots if s['sceneId']==sceneid],key=lambda x:x['order'])
    if ss:add([ss[-1] if last else ss[0]])
  items=self.expanded_impact(p,items);dedup={i['id']:i for i in items};estimate=sum(float(r.get('costEstimate',0)) for r in renders if r['id'] in dedup)
  return {'kind':kind,'id':old['id'],'identityChanged':bool(changed),'costLevel':cost,'reviewOnly':cost=='review_only','mediaChanged':bool(items),'items':items,'estimatedRegenerationCost':round(estimate,4),'pinnedConflicts':sum(x['pinned'] for x in items),'planHash':digest({'kind':kind,'oldVersion':old['_version'],'new':identity(kind,new),'items':items,'newAll':scrub(new)})}
 def expanded_impact(self,p,entries,c=None):
  # Pixel dependencies follow strong media links transitively, even when the
  # originating edit was a master identity, variant file, or scene revision.
  renders=self.s.list(p,'render',c);items={item['id']:item for item in entries}
  affected={item['id'] for item in entries if item['kind']=='shot' and item['freshness']=='broken'} | {r['shotId'] for r in renders if r['id'] in items and items[r['id']]['freshness']=='broken' and r.get('shotId')}
  queue=list(affected);links=self.list_active(p,'link',c)
  while queue:
   parent=queue.pop(0)
   for link in links:
    if link['from']==parent and link['type'] in ('frame_chain','extension','ref_video') and link['to'] not in affected:affected.add(link['to']);queue.append(link['to'])
  for row in renders:
   if row.get('shotId') in affected and row.get('kind','clip')=='clip':items[row['id']]={'id':row['id'],'kind':'render','freshness':'broken'}
  for task in self.s.list(p,'generation_task',c):
   if affected.intersection(task['shotIds']):items[task['id']]={'id':task['id'],'kind':'generation_task','freshness':'broken'}
  return list(items.values())
 def apply_impact(self,p,plan,c):
  if not plan:return
  for item in self.expanded_impact(p,plan['items'],c):
   obj=self.s.get(item['id'],c);obj['freshness']=item['freshness'];obj.setdefault('freshnessNotes',[]).append({'source':plan['id'],'message':'上游 '+plan['kind']+' 已变化','at':now()});self.s.put(item['kind'],obj,p,conn=c)
 def finalize(self,p,kind,id,expected=None):
  ensure(kind in ('style','master','direction','scene','shot'),'对象不支持定稿')
  with self.s.transaction() as c:
   obj=self.s.get(id,c);ensure(obj['projectId']==p,'对象不属于项目')
   if kind=='master':ensure(obj.get('freezeString'),'主资产缺少冻结描述串')
   if kind=='shot':
    check=self.validate_scene(p,obj['sceneId']);ensure(check['passed'],'连续性校验未通过','validation_failed',409,check)
   obj['status']='locked';obj['freshness']='clean';obj['freshnessNotes']=[];out=self.s.put(kind,obj,p,expected,conn=c);self.s.audit(p,'finalize_'+kind,[id],{'version':out['_version'],'humanGate':True},c)
  return out
 def propose(self,p,stage,data,progress=lambda *_:None,check=lambda:None):
  if self.s.get(p).get('workflowVersion',1)>=2:
   if stage in ('B0','B1'):return self.propose_shooting(p,data,progress,check)
   if stage=='B2':return self.prepare_event_assets(p,data['sceneId'])
   if stage in ('B3','B4'):return self.propose_director(p,data,progress,check)
  ensure(stage in ('B0','B1','B2','B3','B4'),'此阶段不使用 LLM 生成');readset=self.proposal_read_set(p,stage,data.get('sceneId'));project=self.s.get(p);style=self.style(p);scenes=self.list_active(p,'scene');scene=self.s.get(data['sceneId']) if data.get('sceneId') else None
  if scene:ensure(scene['projectId']==p,'场次不属于项目')
  if stage in ('B3','B4'):ensure(style['status']=='locked','请先人工定稿风格包，再生成导演方案或分镜','style_gate',409);ensure(scene,'请选择场次')
  if stage in ('B3','B4'):
   handling=scene.get('narrativeHandling',{})
   unresolved=[k for k,v in handling.items() if isinstance(v,dict) and v.get('needed') and not v.get('decision')]
   ensure(not unresolved,'小说特殊呈现尚未由人决定，请先在 B0 处理','narrative_gate',409,unresolved)
  base={'sourceHash':digest(project['source']),'styleVersion':style['_version'],'sceneVersion':scene['_version'] if scene else None,'sceneId':scene['id'] if scene else None,'readSet':readset}
  required=set(scene.get('characters',[])+scene.get('props',[])+([scene['locationId']] if scene.get('locationId') else [])) if scene else set()
  context_assets=[a for a in self.list_active(p,'master') if stage not in ('B3','B4') or a['id'] in required]
  experience=self.experiences.guidance(p,{'stage':stage,'presentationMode':project.get('presentationMode'),'sceneId':scene['id'] if scene else None}) if hasattr(self,'experiences') else {'revisionHash':digest([]),'lessons':[]}
  context={'stable':{'system':'System B 视听导演系统，只改呈现，不改故事','style':{k:v for k,v in style.items() if k not in ('_version','freshnessNotes')},'constraints':project['constraints'],'experience':experience},'semiStable':{'curves':[c for c in project.get('curves',[]) if not scene or c.get('sceneId')==scene['id']],'assets':[{k:a.get(k) for k in ('id','name','kind','freezeString')} for a in context_assets]},'variable':{'scene':scene,'instruction':data.get('instruction','')}}
  if data.get('newCandidate'):context['variable']['candidateNonce']=uid('candidate')
  schema=None
  if stage=='B0':
   system='将小说/剧本归一化为场次。只改呈现，不改人物目标、因果、结果。输出 JSON {scenes:[{title,sourceText,location,timeOfDay,characterNames:[],informationPayload:[],tensionType:suspense|surprise|mystery,narrativeHandling:{innerMonologue:{needed:boolean,options:[],decision:null},summary:{needed:boolean,options:[],decision:null},pov:{options:[],decision:null}},flatness:{informationGain:0到5,visualizability:0到5,emotionDelta:0到5,conflictPressure:0到5},suggestedAdaptations:[]}]}。内心独白和概述必须列显式处理选项，不替人决策。此阶段只理解和拆分故事，不安排秒数，不压缩剧情以适配时长。'
   context['variable'].update(source=project['source'],sourceType=project['sourceType'])
   if project.get('targetDuration') is not None:
    context['variable']['targetDuration']=project['targetDuration'];system+=' 用户另有明确时长要求时，补充各场 targetDuration，合计等于该要求。'
   segments=[s.strip() for s in re.split(r'\n\s*\n|(?=第[一二三四五六七八九十\d]+场)',project['source']) if s.strip()] or ['等待导入原稿']
   duration=project['targetDuration']/len(segments) if project.get('targetDuration') is not None else None
   demo={'scenes':[{'title':'场次 '+str(i+1),'sourceText':s,'location':'待确认地点','timeOfDay':'夜','characterNames':['主角'],'informationPayload':[s[:90]],'tensionType':'mystery','targetDuration':duration,
    'narrativeHandling':{'innerMonologue':{'needed':project['sourceType']=='novel','options':['外化为行为/道具/环境','VO','对白','删除'],'decision':None},'summary':{'needed':False,'options':['蒙太奇','单镜象征','展开场景','删除'],'decision':None},'pov':{'options':['限知跟随','全知','主观镜头'],'decision':None}},
    'flatness':{'informationGain':3,'visualizability':3,'emotionDelta':2,'conflictPressure':3},'suggestedAdaptations':['加入具体动作线','让空间承载信息']} for i,s in enumerate(segments)]}
  elif stage=='B1':
   ensure(scenes,'先生成并采纳场次表');system='为场次表制定视听改编，不改故事事实与结局。输出 JSON {adaptations:[{sceneId,strategy,presentation}],curves:[{sceneId,entry,turn,exit,targetDuration}],transitions:[{fromScene,toScene,type,requirement:{fromShotSpec:{shotSize,angle},toShotSpec:{shotSize,angle}}}]}。type 只用 cut/match_cut/graphic_match/motion_match/sound_bridge/color_shift/camera_continuation。转场两端成对约束。';context['variable']['scenes']=scenes
   system+=' 在改编呈现确定后，按实际对白朗读、动作和情绪停顿估算每场 targetDuration（正秒数），并给 timingReason。必须覆盖每一场，不套用固定全片时长、不均分、不为风格建议镜数删改故事；最终时长由各场累加，供用户在此阶段选择或调整。'
   demo={'adaptations':[{'sceneId':s['id'],'strategy':'动作承载信息','presentation':s['sourceText']} for s in scenes], 'curves':[{'sceneId':s['id'],'entry':2,'turn':5,'exit':7,'targetDuration':s.get('targetDuration') or max(6,round(len(re.sub(r'\s+','',s['sourceText']))/4.5+3,1)),'timingReason':'离线演示：按文本量加动作停顿粗估，真实创作由模型结合对白和表演估算。'} for s in scenes], 'transitions':[{'fromScene':a['id'],'toScene':b['id'],'type':'cut','requirement':{'fromShotSpec':{},'toShotSpec':{}}} for a,b in zip(scenes,scenes[1:])]}
  elif stage=='B2':
   ensure(scenes,'先采纳场次表');targets=[scene] if scene else scenes;context['variable']['scenes']=targets
   system='从场次抽取可复用视觉资产。返回 JSON {assets:[{key,name,kind:character|location|prop,freezeString,identity:{face,hair,body,wardrobe},requiresImage:boolean}],assignments:[{sceneId,characters:[key],location:key,props:[key]}]}。复用 existing asset 的 id 作为 key，不能改其冻结串。冻结串具体稳定，不包含临时光天气。角色脸/发型/标志性服装、伏笔道具、反复出现物都要参考图。不要生图，不要写 prompt。'
   names=list(dict.fromkeys(n for s in targets for n in s.get('characterNames',['主角'])));locations=list(dict.fromkeys(s.get('location','场景') for s in targets));assets=[]
   existing=self.list_active(p,'master')
   for kind,items in [('character',names),('location',locations)]:
    for name in items:
     old=next((a for a in existing if a['name']==name and a['kind']==kind),None);key=old['id'] if old else kind+'_'+digest(name)[:8]
     assets.append({'key':key,'name':name,'kind':kind,'freezeString':old['freezeString'] if old else (name+'，普通日常装束，稳定面容与发型' if kind=='character' else name+'，固定门窗与家具位置，真实空间'),'identity':old.get('identity',{}) if old else {'description':name},'requiresImage':True})
   lookup={a['name']:a['key'] for a in assets};demo={'assets':assets,'assignments':[{'sceneId':s['id'],'characters':[lookup[n] for n in s.get('characterNames',['主角'])],'location':lookup[s.get('location','场景')],'props':[]} for s in targets]}
  elif stage=='B3':
   ensure(scene.get('targetDuration') and scene['targetDuration']>0,'先在改编与节奏阶段确认本场时长','timing_required',409)
   system='逐场设计导演方案，不改变故事。返回 SceneDirection JSON。必须含 dramaticFunction/informationPayload/tensionType/emotion{entry,turn,exit}/coverage{master,emptyShots}/blocking{description,positions:{角色id:{x,y}},axisGroup}/lighting{keyDirection:角度数值,ratio:数值,motivation}/palette/sound{ambience,musicIn,musicOut,silence:[]}/targetDuration/transitionIn/transitionOut。suspense 给观众独知信息；mystery 避免提前清晰揭示；surprise 平淡前置后切换节奏。用场次给定目标时长。';schema=SceneDirection.model_json_schema();context['variable']['manifest']=self.manifest(p,scene['id']);demo=direction_demo(scene,style)
   context['variable']['transitions']=[t for t in self.list_active(p,'transition') if scene['id'] in (t['fromScene'],t['toScene'])]
  else:
   direction=next((d for d in self.list_active(p,'direction') if d['sceneId']==scene['id']),None);ensure(direction and direction['status'] in ('accepted','locked') and direction['freshness']!='broken','先生成并采纳该场有效导演方案','direction_required',409)
   n=shot_count(direction['targetDuration'],style);base['directionId']=direction['id'];base['directionVersion']=direction['_version'];context['variable'].update(direction=direction,manifest=self.manifest(p,scene['id']),exactCount=n,transitions=[t for t in self.list_active(p,'transition') if scene['id'] in (t['fromScene'],t['toScene'])])
   system='生成镜头骨架，场级一次批量。只输出 JSON {shots:[ShotSkeleton]}。必须 exactly exactCount 颗镜头。不要输出 duration/assetVariants/lighting/axisGroup/screenPosition/eyeline/risk，这些由程序算。字段 shotSize(ELS/LS/MS/MCU/CU/ECU),angle(eye/low/high/overhead/pov/shoulder),lens,movement{type,speed,startFraming,endFraming},actionLine,isEmpty,subjects[资产ID],informationPayload[],emotionWeight(0.25-4,越高节奏越快),cameraSide(positive/negative/axis),explicitCrossing,framing。同轴线不无故换侧。景别和机位为信息服务，禁止平均切镜，遵从转场两端与 tensionType。人物冻结设定不改。'
   schema=SkeletonOutput.model_json_schema();sizes=style['shotSizePreference']+['CU','MS','MCU'];information=scene.get('informationPayload') or ['行动推进'];demo={'shots':[{'shotSize':sizes[i%len(sizes)],'angle':'eye' if i%3 else 'shoulder','lens':50,'movement':{'type':'push' if i%3 else 'static','speed':'slow','startFraming':'主体偏画面左侧','endFraming':'保持空间可读'},'actionLine':scene.get('presentation',scene['sourceText'])[:120]+f'；以第{i+1}个动作推进信息。','isEmpty':False,'subjects':scene.get('characters',[]),'informationPayload':[information[i%len(information)]],'emotionWeight':1+.15*(i%3),'cameraSide':'positive','explicitCrossing':False,'framing':{}} for i in range(n)]}
   existing=sorted([s for s in self.list_active(p,'shot') if s['sceneId']==scene['id']],key=lambda s:s['order'])
   if data.get('shotIds'):ensure(set(data['shotIds'])<={s['id'] for s in existing},'局部修改引用了其他场次或已归档镜头','invalid_patch',422)
   if existing:
    selected=set(data.get('shotIds') or [s['id'] for s in existing if s['status']!='locked']);targets=[s for s in existing if s['id'] in selected]
    ensure(targets and all(s['status']!='locked' for s in targets),'锁定镜头不会被自动改写；请先选择可修改镜头','locked',409)
    base['shotIds']=[s['id'] for s in targets];base['mode']='patch';n=len(targets);context['variable'].update(exactCount=n,targetShotIds=base['shotIds'],existingShots=existing)
    system+=' 这是局部精修：只返回 targetShotIds 指定的镜头，每项必须含原 shotId，禁止新增、删除或改写其他镜头。保留邻接镜、已锁定镜和本段时长预算；未要求改变的创意保持原样。'
    demo={'shots':[{**{k:s.get(k) for k in ('shotSize','angle','lens','movement','actionLine','isEmpty','subjects','informationPayload','framing')},'shotId':s['id'],'emotionWeight':1,'cameraSide':s['continuity'].get('cameraSide','positive'),'explicitCrossing':s['continuity'].get('explicitCrossing',False)} for s in targets]}
  role={'B0':'normalizer','B1':'treatment','B2':'assets','B3':'direction','B4':'shots'}[stage]
  rejected=[q for q in self.s.list(p,'proposal') if q['stage']==stage and q.get('sceneId')==(scene['id'] if scene else None) and q['status']=='rejected' and q.get('base',{}).get('readSet')==readset]
  if rejected:
   context['variable']['revisionFeedback']=[{'rejectionId':q['id'],'reason':q.get('rejectReason','用户未采用此方案，请给出不同且更符合目标的方案'),'previousCandidate':q['payload']} for q in rejected[-2:]]
   system+=' 用户已经拒绝 revisionFeedback 中的候选。理解具体原因，仅在本次目标范围内改进；不要原样重复被拒方案。'
  budget=int(self.settings.model(role).get('contextCharacters',32000));ensure(len(canonical(context))<=budget,'场级上下文超过预算，缩小目标范围或提高 contextCharacters','context_budget',422)
  ensure(readset==self.proposal_read_set(p,stage,data.get('sceneId')),'准备提案时依赖已变化，请重试','base_changed',409)
  # Canonical JSON is for identity; explicit ordered blocks are for prefix reuse.
  prompt_context='\n'.join(label+'\n'+canonical(context[key]) for label,key in (('STABLE','stable'),('SCENE ASSETS','semiStable'),('CURRENT REQUEST','variable')))
  config=self.settings.model(role);request_digest=digest({'role':role,'system':system,'context':prompt_context,'model':{k:config.get(k) for k in ('provider','baseUrl','model','format','temperature','maxTokens','extraBody')}})
  previous=next((q for q in reversed(self.s.list(p,'proposal')) if q.get('requestDigest')==request_digest and q['status']=='proposed' and q.get('base',{}).get('readSet')==readset),None)
  if previous:progress(1,'已复用当前待选提案');return previous
  progress(.15,'模型正在生成 '+stage+' 候选')
  out=self.llm.json(p,role,system,context if config["provider"]=="codex_cli" else prompt_context,schema,demo=demo,cache=True,check=check,session_scope="legacy:"+stage+":"+(scene["id"] if scene else "project"))
  if stage=='B0' and project.get('targetDuration') is None:
   for row in out.get('scenes',[]):row['targetDuration']=None
  if stage=='B1':
   curves=out.get('curves',[]);ensure(len(curves)==len(scenes) and {r.get('sceneId') for r in curves}=={s['id'] for s in scenes},'节奏方案必须覆盖所有场次且不重复','schema_validation',422)
   ensure(all(isinstance(r.get('targetDuration'),(int,float)) and not isinstance(r['targetDuration'],bool) and math.isfinite(r['targetDuration']) and r['targetDuration']>0 for r in curves),'节奏方案缺少有效时长','schema_validation',422)
  if stage=='B3':out['targetDuration']=scene['targetDuration']
  if stage=='B4':ensure(len(out['shots'])==n,'模型生成的镜头数与代码预算不符；请重生成','shot_count',422)
  obj={'id':uid('proposal'),'projectId':p,'stage':stage,'sceneId':scene['id'] if scene else None,'payload':out,'base':base,'requestDigest':request_digest,'status':'proposed','createdAt':now(),'demo':self.settings.model(role)['provider']=='demo'}
  with self.s.transaction() as c:
   previous=next((q for q in reversed(self.s.list(p,'proposal',c)) if q.get('requestDigest')==request_digest and q['status']=='proposed' and q.get('base',{}).get('readSet')==readset),None)
   if previous:obj=previous
   else:self.s.put('proposal',obj,p,conn=c);self.s.audit(p,'propose_'+stage,[scene['id']] if scene else [],{'proposalId':obj['id'],'contextDigest':digest(context)},c)
  if hasattr(self,'experiences'):self.experiences.applied(p,{'type':'legacy_proposal','stage':stage,'sceneId':scene['id'] if scene else None,'proposalId':obj['id']},experience,obj['id'])
  progress(1,'已生成提案，等待人工采纳');return obj
 def adopt_proposal(self,p,id,data=None):
  proposal=self.s.get(id);ensure(proposal['projectId']==p,'提案不属于项目')
  if proposal.get('workflowVersion',0)>=2:return self.adopt_director(p,id,data)
  if proposal['status']=='adopted':return {'ids':proposal['adoptedIds'],'idempotent':True}
  ensure(proposal['status']=='proposed','提案已拒绝');stage=proposal['stage'];project=self.s.get(p);base=proposal['base'];style=self.style(p)
  if base.get('readSet') is None:
   ensure(base['sourceHash']==digest(project['source']),'原稿已变化，请重新生成','base_changed',409)
   if stage in ('B1','B3','B4'):ensure(style['_version']==base['styleVersion'],'风格已变化，请重新生成','base_changed',409)
   if base.get('sceneId'):ensure(self.s.get(base['sceneId'])['_version']==base['sceneVersion'],'场次已变化，请重新生成','base_changed',409)
  payload=proposal['payload'];created=[]
  if stage=='B0':
   for row in payload.get('scenes',[]):ensure(row.get('title') and row.get('sourceText') and isinstance(row.get('informationPayload'),list) and (row.get('targetDuration') is None or isinstance(row['targetDuration'],(int,float)) and not isinstance(row['targetDuration'],bool) and math.isfinite(row['targetDuration']) and row['targetDuration']>0),'场次提案缺少必要字段','schema_validation',422)
  if stage=='B2':
   for row in payload.get('assets',[]):ensure(row.get('key') and row.get('name') and row.get('freezeString') and row.get('kind') in ('character','location','prop'),'资产提案字段不完整','schema_validation',422)

  with self.s.transaction() as c:
   project=self.s.get(p,c);style=self.s.get(project['styleId'],c)
   current_proposal=self.s.get(id,c);ensure(current_proposal['status']=='proposed','提案已经处理','version_conflict',409)
   ensure(current_proposal['_version']==proposal['_version'],'提案已被编辑，请重新预览后采纳','version_conflict',409)
   if base.get('readSet') is not None:ensure(base['readSet']==self.proposal_read_set(p,stage,proposal.get('sceneId'),c),'提案依据的剧本、资产或相邻约束已变化，请重新生成或局部精修','base_changed',409)
   if base.get('readSet') is None:
    ensure(base['sourceHash']==digest(project['source']),'原稿已变化，请重新生成','base_changed',409)
    if stage in ('B1','B3','B4'):ensure(self.s.get(project['styleId'],c)['_version']==base['styleVersion'],'风格已变化，请重新生成','base_changed',409)
    if base.get('sceneId'):ensure(self.s.get(base['sceneId'],c)['_version']==base['sceneVersion'],'场次已变化，请重新生成','base_changed',409)
   if stage=='B0':
    ensure(not self.list_active(p,'scene',c),'已有场次，重新归一化将改变全片；请新建项目或逐场改编','ingest_exists',409)
    ensure(payload.get('scenes'),'没有归一化场次')
    for i,s in enumerate(payload['scenes']):
     flat=s.get('flatness',{});flags=[k for k in ('informationGain','visualizability','emotionDelta','conflictPressure') if float(flat.get(k,0))<2]
     scene={**s,'targetDuration':s.get('targetDuration') if project.get('targetDuration') is not None else None,'id':uid('scene'),'projectId':p,'order':i,'source':{'type':project['sourceType'],'ref':'project.source'},'characters':[],'props':[],'locationId':None,'flat':bool(flags),'flatFlags':flags,'status':'accepted','freshness':'clean','freshnessNotes':[],'contractHash':digest(s.get('informationPayload',[])),'bodyHash':digest(s.get('sourceText','')),'canonHash':digest([])}
     self.s.put('scene',scene,p,conn=c);created.append(scene['id'])
   elif stage=='B1':
    project['curves']=payload.get('curves',[]);project['estimatedDuration']=sum(float(r['targetDuration']) for r in project['curves']);self.s.put('project',project,p,conn=c)
    for a in payload.get('adaptations',[]):
     scene=self.s.get(a['sceneId'],c);ensure(scene['projectId']==p,'改编引用了未知场次');ensure(scene['status']!='locked','场次已锁定，不能自动改呈现','locked',409)
     changed=scene.get('presentation',scene.get('sourceText'))!=a['presentation'];scene['presentation']=a['presentation'];scene['presentationFreshness']='clean';scene['presentationSourceHash']=scene.get('sourceHashes',{}).get('bodyHash',scene.get('bodyHash'));scene['bodyHash']=digest(a['presentation'])
     if changed:self.apply_impact(p,self.change_plan(p,'scene',scene),c)
     scene['adaptationStrategy']=a['strategy'];self.s.put('scene',scene,p,conn=c)
    for curve in payload.get('curves',[]):
     scene=self.s.get(curve['sceneId'],c);ensure(scene['projectId']==p,'节奏曲线引用跨项目');duration=float(curve['targetDuration']);ensure(duration>0,'场次时长必须为正数')
     if scene['targetDuration']!=duration:self.apply_impact(p,self.change_plan(p,'scene',{**scene,'targetDuration':duration}),c)
     scene['targetDuration']=duration;self.s.put('scene',scene,p,conn=c)
    for previous in self.list_active(p,'transition',c):
     ensure(previous['status']!='locked','已有锁定转场，不能整体替换','locked',409);previous['status']='archived';self.s.put('transition',previous,p,conn=c)
    for t in payload.get('transitions',[]):
     obj={**t,'id':uid('transition'),'projectId':p,'status':'accepted','freshness':'clean','freshnessNotes':[]};self.s.put('transition',obj,p,conn=c);created.append(obj['id'])
   elif stage=='B2':
    mapping={};known=self.list_active(p,'master',c)
    for a in payload.get('assets',[]):
     existing=next((x for x in known if x['id']==a['key'] or (x['name']==a['name'] and x['kind']==a['kind'])),None)
     if existing:mapping[a['key']]=existing['id'];continue
     aid=uid('master');vid=uid('variant');master={'id':aid,'projectId':p,'name':a['name'],'kind':a['kind'],'freezeString':a['freezeString'],'identity':a.get('identity',{'description':a['freezeString']}),'seed':int(digest(aid)[:8],16),'defaultVariantId':vid,'referenceFileId':None,'status':'draft','freshness':'clean','freshnessNotes':[]}
     variant={'id':vid,'projectId':p,'masterId':aid,'name':'基准','deltaString':'','requiresImage':a.get('requiresImage',True),'referenceFileId':None,'status':'accepted','freshness':'clean','freshnessNotes':[]}
     self.s.put('master',master,p,conn=c);self.s.put('variant',variant,p,conn=c);created+=[aid,vid];mapping[a['key']]=aid
    for assignment in payload.get('assignments',[]):
     scene=self.s.get(assignment['sceneId'],c);ensure(scene['projectId']==p,'资产分配引用未知场次');before={k:scene.get(k) for k in ('characters','props','locationId')};scene['characters']=[mapping.get(x,x) for x in assignment['characters']];scene['props']=[mapping.get(x,x) for x in assignment.get('props',[])];scene['locationId']=mapping.get(assignment.get('location'),assignment.get('location'));scene['assetsPlanned']=True
     if before!={k:scene.get(k) for k in before}:self.apply_impact(p,self.change_plan(p,'scene',scene),c)
     self.s.put('scene',scene,p,conn=c)
   elif stage=='B3':
    SceneDirection.model_validate(payload);old=next((d for d in self.list_active(p,'direction',c) if d['sceneId']==proposal['sceneId']),None)
    if old:ensure(old['status']!='locked','导演方案已锁定，先显式解锁或修改','locked',409)
    obj={**payload,'id':old['id'] if old else uid('direction'),'projectId':p,'sceneId':proposal['sceneId'],'status':'accepted','freshness':'clean','freshnessNotes':[]}
    if old:self.apply_impact(p,self.change_plan(p,'direction',obj),c)
    self.s.put('direction',obj,p,conn=c);created.append(obj['id'])
   else:
    direction=self.s.get(base['directionId'],c)
    if base.get('readSet') is None:ensure(direction['_version']==base['directionVersion'],'导演方案版本已变化','base_changed',409)
    scene=self.s.get(proposal['sceneId'],c);manifest=self.manifest(p,scene['id'])
    oldshots=sorted([x for x in self.list_active(p,'shot',c) if x['sceneId']==scene['id']],key=lambda s:s['order']);oldmap={s['id']:s for s in oldshots};targetids=base.get('shotIds')
    skeletons=copy.deepcopy(payload['shots']);patch_direction=copy.deepcopy(direction)
    if oldshots:
     ensure(targetids and len(skeletons)==len(targetids),'已有分镜仅支持基于当前版本的局部候选，请重新生成','base_changed',409)
     ensure(set(targetids)<=set(oldmap) and all(oldmap[sid]['status']!='locked' for sid in targetids),'目标镜头已锁定或替换','locked',409)
     supplied=[s.get('shotId') for s in skeletons]
     if any(supplied):
      ensure(len(set(supplied))==len(targetids) and set(supplied)==set(targetids),'局部候选必须逐一匹配目标 shotId','invalid_patch',422);byid={s['shotId']:s for s in skeletons};skeletons=[byid[sid] for sid in targetids]
     patch_direction['targetDuration']=sum(oldmap[sid]['duration'] for sid in targetids)
    shots=complete_shots(skeletons,patch_direction,scene,manifest,style)
    for i,shot in enumerate(shots):
     if targetids:
      original=oldmap[targetids[i]]
      for field,value in original.items():
       if field not in shot:shot[field]=copy.deepcopy(value)
      shot.update(id=original['id'],order=original['order'],duration=original['duration'])
     shot['status']='accepted';shot['contractHash']=digest(shot_design(shot));shot['bodyHash']=digest(shot['actionLine']);ShotContract.model_validate(shot)
    merged={s['id']:s for s in oldshots};merged.update({s['id']:s for s in shots});report=validate_shots(list(merged.values()),direction,style,self.list_active(p,'transition',c),self.list_active(p,'foreshadow',c),self.list_active(p,'variant',c));ensure(report['passed'],'局部候选与保留镜头未通过连续性约束，需修改提案或导演方案','validation_failed',409,report)
    changed=[s for s in shots if s['id'] not in oldmap or shot_design(s)!=shot_design(oldmap[s['id']]) or oldmap[s['id']]['freshness']=='broken']
    for shot in changed:
     if shot['id'] in oldmap:self.apply_impact(p,self.change_plan(p,'shot',shot),c)
    for shot in changed:self.s.put('shot',shot,p,conn=c)
    created.extend(s['id'] for s in shots);proposal['changedIds']=[s['id'] for s in changed];proposal['preservedIds']=[s['id'] for s in oldshots if s['id'] not in proposal['changedIds']]
   proposal['status']='adopted';proposal['adoptedIds']=created;self.s.put('proposal',proposal,p,conn=c)
   for sibling in self.s.list(p,'proposal',c):
    if sibling['id']!=id and sibling['status']=='proposed' and sibling['stage']==stage and sibling.get('sceneId')==proposal.get('sceneId') and sibling.get('base',{}).get('readSet')==base.get('readSet'):
     sibling['status']='superseded';sibling['selectedProposalId']=id;self.s.put('proposal',sibling,p,conn=c)
   project=self.s.get(p,c);project['stage']=stage;self.s.put('project',project,p,conn=c);self.s.audit(p,'adopt_'+stage,created,{'proposalId':id,'humanGate':True},c)
  return {'ids':created}
 def validate_scene(self,p,sceneid):
  direction=next((d for d in self.list_active(p,'direction') if d['sceneId']==sceneid),None);ensure(direction,'缺少导演方案')
  shots=[s for s in self.list_active(p,'shot') if s['sceneId']==sceneid];report=validate_shots(shots,direction,self.style(p),self.list_active(p,'transition'),self.list_active(p,'foreshadow'),self.list_active(p,'variant'))
  scene=self.s.get(sceneid)
  if scene.get('shootingScriptId'):
   try:validate_shot_coverage(shots,self.active_shooting(p)['payload'],scene['shootingSceneId'])
   except DomainError as e:report['passed']=False;report['issues'].append({'code':e.code,'message':str(e),'severity':'error','details':e.details})
   try:
    creative=self.creative_inputs(p,scene);validate_directing_fields(direction,shots,creative['scene'],creative['events'],creative['entities'])
   except ValueError as e:report['passed']=False;report['issues'].append({'code':'directing_fields','message':str(e),'severity':'error'})
  return report
 def renderer_profile(self,p,kind="keyframe"):
  project=self.s.get(p);profile=copy.deepcopy(PROFILE);profile.update(project.get('rendererProfile',{}));cfg=self.settings.media(kind)
  profile['providerIdentity']={k:cfg.get(k) for k in ('provider','baseUrl','model','imageModel','videoModel','imageResolution','videoResolution','size','extraBody','generic','workflow','useEdits')}
  # Explicit declared support; never invent capabilities for a provider.
  if cfg.get('capabilities'):profile['capabilities'].update(cfg['capabilities'])
  if cfg.get('provider')=='dreamina':
   if kind=='clip':
    model=cfg.get('videoModel','seedance2.0fast');limit=30 if model=='seedance2.5' else 15;images=30 if model=='seedance2.5' else 9;videos=10 if model=='seedance2.5' else 3
    profile['maxSeconds']=min(profile.get('maxSeconds',limit),limit);profile['maxImages']=min(profile.get('maxImages',images),images);profile['maxVideos']=min(profile.get('maxVideos',videos),videos)
    profile['capabilities'].update(referenceImage=True,referenceVideo=True,audio=False)
   else:
    profile['maxImages']=min(profile.get('maxImages',10),10);profile['capabilities']['referenceImage']=True
  if hasattr(self,'experiences'):
   guidance=self.experiences.guidance(p,{'stage':'media','kind':kind,'presentationMode':project.get('presentationMode'),'model':cfg.get('model')})
   production=[x for x in guidance['lessons'] if x.get('category') in ('production','preference')]
   profile['experienceRevision']=digest(production);profile['experienceIds']=[x['id'] for x in production]
   profile['productionGuidance']=[x['action'] for x in production if x.get('action')]
   if profile['productionGuidance']:profile['prefix']='\n'.join([profile.get('prefix',''),*profile['productionGuidance']]).strip()
  return profile
 def render_request(self,p,data):
  shot=self.s.get(data['shotId']);ensure(shot['projectId']==p,'镜头不属于项目');style=self.style(p);kind=data.get('kind','keyframe');quality=data.get('quality','proxy');ensure(kind in ('keyframe','clip'),'渲染种类无效');ensure(quality in ('proxy','final'),'质量档无效');ensure(shot['freshness']!='broken','镜头设计已失效，先修复 B4','broken_block',409)
  self.require_production_ready(p,shot)
  ensure(style['status']=='locked','风格包未定稿','style_gate',409)
  ensure(self.s.get(shot['sceneId'])['status']!='archived','该镜头所属拍摄场次已归档','stale_shooting',409)
  if quality=='final':
   acceptedProxy=next((x for x in self.s.list(p,'render') if x.get('shotId')==shot['id'] and x['kind']==kind and x.get('selected') and x['freshness']!='broken'),None)
   ensure(acceptedProxy,'先确认本镜同类低清代理物，再投入正式生成','proxy_gate',409)
  manifest=self.event_manifest(p,shot) if shot.get('eventId') else self.manifest(p,shot['sceneId'])
  if shot.get('eventId') and kind=='keyframe':
   visible_refs=[r for r in manifest['resolved'] if r.get('role')!='end_state'];required={r['variantId'] for r in visible_refs};manifest={**manifest,'resolved':visible_refs,'missing':[r for r in manifest['missing'] if r.get('variantId') in required or not r.get('variantId')]}
  if not shot.get('eventId'):
   wanted=set(shot.get('assetVariants',[]));manifest={**manifest,'resolved':[r for r in manifest['resolved'] if r['variantId'] in wanted],'missing':[r for r in manifest['missing'] if r.get('variantId') in wanted or not r.get('variantId')]}
  ensure(not manifest['missing'],'本镜所需素材尚未就绪，请处理定位的问题','asset_missing',409,manifest['missing'])
  for r in manifest['resolved']:ensure(self.s.get(r['assetId'])['status']=='locked','主资产未人工定稿','asset_gate',409,{'assetId':r['assetId']})
  validation=self.validate_scene(p,shot['sceneId']);ensure(validation['passed'],'本场分镜校验未通过','validation_failed',409,validation)
  profile=self.renderer_profile(p,kind)
  if data.get('repairRuleId'):
   rule=next((r for r in self.settings.read().get('promptRepairRules',[]) if r.get('id')==data['repairRuleId']),None);ensure(rule,'修正规则已不存在');profile['negativeSuffix']=profile.get('negativeSuffix','')+' '+rule['negativeSuffix'];profile['repairRuleId']=data['repairRuleId']
  compiled=compile_prompt(self.with_dialogue(p,shot),manifest,style,profile,kind=kind);cfg=self.settings.media(kind);links=[l for l in self.list_active(p,'link') if l['to']==shot['id'] and l['type'] in ('frame_chain','extension','ref_video')];refs=[];referencePaths=[];refVideo=None;bound=[]
  if cfg.get('provider')=='dreamina' and kind=='clip':
   duration=float(shot.get('duration',0));maximum=30 if cfg.get('videoModel')=='seedance2.5' else 15;ensure(abs(duration-round(duration))<.001 and 4<=round(duration)<=maximum,f'Dreamina 当前模型单次视频需为 4–{maximum} 整数秒；短镜请先组合成生成单元','duration_limit',422)
  for fileid in compiled['referenceFileIds']:
   f=self.s.get(fileid);ensure(Path(f['path']).is_file(),'资产参考图不存在');referencePaths.append(f['path']);refs.append({'id':fileid,'sha256':hashlib.sha256(Path(f['path']).read_bytes()).hexdigest()})
  if kind=='clip':
   own=next((r for r in reversed(self.s.list(p,'render')) if r.get('shotId')==shot['id'] and r['kind']=='keyframe' and r.get('selected') and r['freshness']!='broken'),None)
   ensure(own,'请先终选本镜关键帧，再生成视频','keyframe_gate',409)
   f=self.s.get(own['fileId']);referencePaths.insert(0,f['path']);refs.append({'keyframe':own['id'],'sha256':hashlib.sha256(Path(f['path']).read_bytes()).hexdigest()})
   for link in links:
    cap={'frame_chain':'firstFrame','extension':'extension','ref_video':'referenceVideo'}[link['type']];ensure(profile['capabilities'].get(cap),f'当前 RendererProfile 未声明支持 {cap}','unsupported_capability',409)
    prev=next((r for r in reversed(self.s.list(p,'render')) if r.get('shotId')==link['from'] and r['kind']=='clip' and r.get('selected') and r['freshness']!='broken'),None)
    ensure(prev,'强依赖上游片段尚未验收','dependency_waiting',409,link)
    f=self.s.get(prev['fileId']);file_hash=hashlib.sha256(Path(f['path']).read_bytes()).hexdigest();adoption=prev.get('adoption')
    if shot.get('eventId'):
     ensure(adoption and adoption['fileHash']==file_hash and adoption.get('observedEndState'),'强承接需要上游实际采用区间及末态观察记录','end_evidence_required',409,{'renderId':prev['id']})
     current=manifest['start']
     relevant={r['entityId'] for r in manifest['resolved']}
     ensure(all(eid in adoption['observedEndState'] and all(adoption['observedEndState'][eid].get(k)==v for k,v in current[eid].items()) for eid in relevant),'上游实际末态与本镜起态不一致；请选择切镜或修订承接','observed_state_mismatch',409,{'renderId':prev['id'],'requiredEntities':sorted(relevant)})
    bound.append({'linkId':link['id'],'type':link['type'],'renderId':prev['id'],'path':f['path'],'adoption':adoption});refs.append({'upstream':prev['id'],'type':link['type'],'sha256':file_hash,'adoptionHash':self.adoption_signature(adoption) if adoption else None})
    if link['type'] in ('extension','ref_video'):refVideo=f['path']
  seed=int(data.get('seed',compiled['seed']));variants=[{'id':r['variantId'],'version':self.s.get(r['variantId'])['_version']} for r in manifest['resolved']]
  key=render_key(shot,variants,style,profile,seed,quality,kind,refs,compiled=compiled);width,height=render_dimensions(style['aspectRatio'],quality)
  if cfg.get('provider')=='openai' and kind=='keyframe' and referencePaths:ensure(cfg.get('useEdits',False),'已有角色参考图；请启用图像编辑接口 useEdits，不能静默丢弃参考图','reference_support_required',409)
  return {'key':key,'shot':shot,'manifest':manifest,'style':style,'profile':profile,'compiled':compiled,'kind':kind,'quality':quality,'seed':seed,'width':width,'height':height,'referencePaths':referencePaths,'referenceVideoPath':refVideo,'bound':bound,'refs':refs}
 def dry_run(self,p,data):
  ids=data.get('shotIds') or ([data['shotId']] if data.get('shotId') else []);ensure(ids,'请选择镜头');requests=[];blocked=[];cfg=self.settings.media(data.get('kind','keyframe'));cost=0;seconds=0;miss=0
  for id in ids:
   try:
    req=self.render_request(p,{**data,'shotId':id});hit=self.s.cached(req['key']);runner_id=self.runners.route({'role':'operator','stage':'B5','task':'video_render' if req['kind']=='clip' else 'image_render'},data.get('runner'));runner_profile=self.runners.profiles()[runner_id];execution_cost=0 if hit else float(runner_profile['limits'].get('costPerRunEstimate',0));estimate=0 if hit or cfg['provider']=='demo' else float(cfg.get('imageCost',0)) if req['kind']=='keyframe' else float(cfg.get('videoCostPerSecond',0))*req['shot']['duration']
    estimate+=execution_cost
    if not hit:
     ensure(runner_profile.get('enabled'),'所选 Runner 尚未启用','runner_disabled',409)
     ensure(self.runners.qualified(runner_profile),'所选 Runner 尚未通过当前配置对应的验收','runner_unqualified',409)
    requests.append({'runnerId':runner_id,'runnerProfileHash':digest(runner_profile),'runnerEstimatedCost':execution_cost,'shotId':id,'renderKey':req['key'],'cacheHit':bool(hit),'cost':estimate,'duration':req['shot']['duration'],'kind':req['kind'],'quality':req['quality'],'seed':req['seed']});cost+=estimate;seconds+=req['shot']['duration'] if req['kind']=='clip' and not hit else 0;miss+=not bool(hit)
   except DomainError as e:blocked.append({'shotId':id,'error':str(e),'code':e.code,'details':e.details})
  known=cfg['provider']=='demo' or cfg.get('priceConfigured',False)
  if not known and miss:blocked.append({'error':'填写媒体单价后才能准确预览本次费用','code':'price_required'})
  value={'requests':requests,'blocked':blocked,'newRenders':miss,'videoSeconds':round(seconds,2),'estimatedCost':round(cost,4),'currency':self.s.get(p)['currency'],'costKnown':known,'runner':data.get('runner') or '按路由','configHash':digest(self.renderer_profile(p,data.get('kind','keyframe')))}
  value['planHash']=digest(value);return value
 def reserve(self,p,taskid,estimate):
  with self.s.transaction() as c:
   self.s.get(p,c);ensure(math.isfinite(estimate) and estimate>=0,'费用估算必须为非负有限数')
   obj={'id':taskid,'projectId':p,'estimate':estimate,'status':'reserved','createdAt':now()};self.s.put('reservation',obj,p,conn=c)
 def finish_reservation(self,p,id,result):
  with self.s.transaction() as c:
   r=self.s.get(id,c);r['status']='spent' if result['status']=='ok' else 'unknown';r['actual']=0 if result.get('cacheHit') else result.get('usage',{}).get('cost',r['estimate']);self.s.put('reservation',r,p,conn=c)
 def render(self,p,data,progress=lambda *_:None,check=lambda:None):
  plan=self.dry_run(p,data);ensure(plan['planHash']==data.get('planHash'),'批量生成前须确认最新 dry-run','plan_required',409,plan);ensure(not plan['blocked'],'生成被闸口阻止','render_blocked',409,plan['blocked'])
  ids=[r['shotId'] for r in plan['requests']];shotmap={s['id']:s for s in self.list_active(p,'shot')};ordered=strong_order([shotmap[i] for i in ids],self.list_active(p,'link'));results=[]
  for index,id in enumerate(ordered):
   check();r=self.render_request(p,{**data,'shotId':id});expected=next(x for x in plan['requests'] if x['shotId']==id);ensure(r['key']==expected['renderKey'],'生成过程中设计或参考媒体已变化，停止以避免使用旧计划','base_changed',409)
   cached=self.s.cached(r['key'])
   existing=next((x for x in self.s.list(p,'render') if x.get('shotId')==id and x.get('renderKey')==r['key'] and x.get('actualKey')==(cached or {}).get('actualKey') and x['freshness']!='broken'),None)
   if cached and existing:
    results.append({**existing,'cacheHit':True});self.s.audit(p,'render_cache_hit',[existing['id']],{'renderKey':r['key'],'modelsCalled':0});progress((index+1)/len(ids),'已复用有效素材与门禁记录');continue
   project=self.s.get(p);circuit=project.get('circuit',{}).get(r['shot']['sceneId'],0);ensure(circuit<self.settings.read()['failureCircuit'],'整场连续失败已熔断，检查原因并手动复位','circuit_open',409)
   taskid=uid('task');work=self.s.root/'media'/p/'renders'/taskid;work.mkdir(parents=True,exist_ok=True);cfg=self.settings.read();cfg['media']=self.settings.media(r['kind']);refs=[]
   # Copy only explicitly authorized inputs into the isolated per-task directory.
   for j,path in enumerate(r['referencePaths']):
    dest=work/('ref-'+str(j)+Path(path).suffix);shutil.copy2(path,dest);refs.append(str(dest.resolve()))
   video=None
   if r['referenceVideoPath']:
    selected_bound=next((x for x in r['bound'] if x['path']==r['referenceVideoPath']),None)
    dest=work/'reference-video.mp4'
    if selected_bound and selected_bound.get('adoption'):
     from .assembly import get_ffmpeg
     interval=selected_bound['adoption']['interval'];subprocess.run([get_ffmpeg(cfg),'-y','-v','error','-ss',str(interval['in']),'-i',r['referenceVideoPath'],'-t',str(interval['out']-interval['in']),'-c:v','libx264','-c:a','aac',str(dest)],check=True,capture_output=True,timeout=60)
    else:shutil.copy2(r['referenceVideoPath'],dest)
    video=str(dest.resolve())
   for bound in r['bound']:
    if bound['type']=='frame_chain':
     from .assembly import get_ffmpeg
     dest=work/'upstream-adopted-end.png';seek=['-ss',str(bound['adoption']['endFrameTime'])] if bound.get('adoption') else ['-sseof','-0.08'];cmd=[get_ffmpeg(cfg),'-y',*seek,'-i',bound['path'],'-frames:v','1',str(dest)];subprocess.run(cmd,check=True,capture_output=True,timeout=30);refs.insert(0,str(dest))
   prompt=r['compiled']['imagePrompt' if r['kind']=='keyframe' else 'videoPrompt'];inputs={'prompt':prompt,'negativePrompt':r['compiled']['negativePrompt'],'freezeStrings':[x['freezeString'] for x in r['manifest']['resolved'] if x['variantId'] in r['shot']['assetVariants']],
    'seed':r['seed'],'width':r['width'],'height':r['height'],'duration':r['shot']['duration'],'kind':r['kind'],'quality':r['quality'],'referencePaths':refs,'referenceVideoPath':video,'media':cfg['media'],'ffmpeg':cfg.get('ffmpeg',''),'recoveryRequest':{'mode':'shot','shotId':id,'kind':r['kind'],'quality':r['quality'],'seed':r['seed']}}
   task={'taskId':taskid,'renderKey':r['key'],'role':'operator','stage':'B5','task':'video_render' if r['kind']=='clip' else 'image_render','objective':'执行已编译渲染任务。冻结串不得改写；只在白名单内调用渲染工具；报告实际使用的 prompt 和产物。',
    'inputs':inputs,'tools':['render','read_task','write_report'],'workdir':str(work.resolve()),'acceptance':{'minBytes':64,'extensions':['.mp4','.webm','.mov'] if r['kind']=='clip' else ['.png','.jpg','.jpeg','.webp']},'limits':{'maxTurns':12,'timeout':cfg['media'].get('timeout',900),'budget':0},'reportSchema':{}}
   cachehit=self.s.cached(r['key'])
   if not cachehit:self.reserve(p,taskid,expected['cost'])
   try:result=self.runners.execute(p,task,data.get('runner'),check)
   except Exception:
    if not cachehit:self.finish_reservation(p,taskid,{'status':'failed'})
    raise
   if not cachehit:self.finish_reservation(p,taskid,result)
   if result['status']!='ok':
    project=self.s.get(p);project.setdefault('circuit',{})[r['shot']['sceneId']]=circuit+1;self.s.put('project',project,p)
    raise DomainError('渲染失败：'+result.get('report',{}).get('notes',result['status']),'render_failed',502,result)
   art=result['artifacts'][0];file=self.register_file(p,Path(art['path']),r['kind']);obj={'id':uid('render'),'projectId':p,'shotId':id,'kind':r['kind'],'quality':r['quality'],'renderKey':r['key'],'actualKey':result.get('actualKey',r['key']),
    'fileId':file['id'],'url':file['url'],'assetVariants':r['shot']['assetVariants'],'seed':r['seed'],'pinned':False,'selected':False,'status':'draft','freshness':'clean','freshnessNotes':[],'boundReferences':r['refs'],'cacheHit':bool(result.get('cacheHit')),'runner':result.get('runner',{}),'costEstimate':expected['cost'],'demo':cfg['media']['provider']=='demo','createdAt':now()}
   existing=next((x for x in self.s.list(p,'render') if x.get('shotId')==id and x.get('renderKey')==r['key'] and x.get('actualKey')==obj['actualKey'] and x['freshness']!='broken'),None)
   if existing:obj=existing
   else:self.s.put('render',obj,p)
   if self.gates and not existing:obj['gate']=self.gates.inspect(p,obj,r['shot']);obj['gateReportId']=obj['gate']['id'];obj['gateStatus']=obj['gate']['status'];self.s.put('render',obj,p)
   project=self.s.get(p);project.setdefault('circuit',{})[r['shot']['sceneId']]=0;self.s.put('project',project,p);results.append(obj);progress((index+1)/len(ids),'已完成 '+str(index+1)+'/'+str(len(ids))+'；等待人工终选')
  return results
 def register_file(self,p,path,kind=None):
  path=path.resolve();ensure(path.is_relative_to((self.s.root/'media'/p).resolve()),'产物不在项目媒体目录','path_escape',403)
  obj={'id':uid('file'),'projectId':p,'filename':path.name,'path':str(path),'relative':str(path.relative_to(self.s.root)).replace('\\','/'),'url':'/media/'+str(path.relative_to(self.s.root/'media')).replace('\\','/'),'size':path.stat().st_size,'sha256':hashlib.sha256(path.read_bytes()).hexdigest(),'kind':kind,'createdAt':now()};self.s.put('file',obj,p);return obj
 def attach_render(self,p,data):
  shot=self.s.get(data['shotId']);file=self.s.get(data['fileId']);ensure(shot['projectId']==p and file['projectId']==p,'镜头与文件须属于本项目');kind=data.get('kind','keyframe');ensure(kind in ('keyframe','clip'),'素材类型无效')
  obj={'id':uid('render'),'projectId':p,'shotId':shot['id'],'kind':kind,'quality':data.get('quality','final'),'renderKey':'import:'+digest({'shot':shot['id'],'file':file['id']}),'actualKey':None,'fileId':file['id'],'url':file['url'],'assetVariants':shot['assetVariants'],'seed':None,'pinned':False,'selected':False,'status':'draft','freshness':'clean','freshnessNotes':[],'demo':False,'createdAt':now(),'imported':True,'costEstimate':0,'proposedInterval':data.get('proposedInterval')}
  self.s.put('render',obj,p)
  if self.gates:obj['gate']=self.gates.inspect(p,obj,shot);obj['gateReportId']=obj['gate']['id'];obj['gateStatus']=obj['gate']['status'];self.s.put('render',obj,p)
  self.s.audit(p,'import_render',[obj['id']],{'fileId':file['id']});return obj
 def select_render(self,p,id,data):
  initial=self.s.get(id);ensure(initial['projectId']==p,'素材不属于项目')
  adoption=self.observed_adoption(p,initial,data) if data.get('selected') and initial['kind']=='clip' and (self.s.get(initial['shotId']).get('eventId') or data.get('adoptedInterval')) else None
  with self.s.transaction() as c:
   r=self.s.get(id,c);ensure(r['projectId']==p,'素材不属于项目')
   if data.get('selected'):
    ensure(r['freshness']!='broken' or data.get('arbitrationReason'),'失效素材需先仲裁才能终选','pinned_conflict',409)
    gate=r.get('gate',{});ensure(gate.get('status')=='passed' or data.get('humanReview'),'自动门禁未完全通过，需要人工复核并记录理由','review_required',409,gate)
    ensure(gate.get('status')=='passed' or data.get('reason'),'请填写人工复核理由')
    previous=[x for x in self.s.list(p,'render',c) if x.get('shotId')==r['shotId'] and x['kind']==r['kind'] and x.get('selected') and x['id']!=id]
    for other in previous:
     ensure(not other.get('pinned') or data.get('replacePinned'),'当前终选素材已 Pin，需显式允许切换；原素材不会删除','pinned',409)
     other['selected']=False;self.s.put('render',other,p,conn=c)
    adoption_changed=adoption is not None and self.adoption_signature(adoption)!=self.adoption_signature(r.get('adoption'))
    if adoption:r['adoption']=adoption
    r['selected']=True;r['status']='accepted';r['review']={'reason':data.get('reason','自动门禁通过后人工终选'),'at':now()}
    # Any newly selected upstream media invalidates bound successors, not unrelated cuts.
    if previous or adoption_changed:
     affected={r['shotId']};queue=[r['shotId']];links=self.s.list(p,'link',c)
     while queue:
      parent=queue.pop(0)
      for link in links:
       if link['from']==parent and link['type'] in ('frame_chain','extension','ref_video') and link['to'] not in affected:affected.add(link['to']);queue.append(link['to'])
     for downstream in self.s.list(p,'render',c):
      if downstream.get('shotId') in affected-{r['shotId']} and downstream.get('kind','clip')=='clip':downstream['freshness']='broken';downstream.setdefault('freshnessNotes',[]).append({'source':id,'message':'已采用的强依赖上游媒体发生改变'});self.s.put('render',downstream,p,conn=c)
     if r['kind']=='keyframe':
      for downstream in self.s.list(p,'render',c):
       if downstream.get('shotId')==r['shotId'] and downstream['kind']=='clip':downstream['freshness']='broken';self.s.put('render',downstream,p,conn=c)
     for task in self.s.list(p,'generation_task',c):
      if affected.intersection(task['shotIds']):task['freshness']='broken';self.s.put('generation_task',task,p,conn=c)
   if 'pinned' in data:r['pinned']=bool(data['pinned'])
   if data.get('arbitrationReason'):r['freshness']='clean';r['freshnessNotes']=[];r['arbitrationReason']=data['arbitrationReason']
   self.s.put('render',r,p,conn=c);self.s.audit(p,'render_review',[id],{'selected':r['selected'],'pinned':r['pinned'],'reason':data.get('reason'),'arbitrationReason':data.get('arbitrationReason')},c)
  return r
 def import_scene_export(self,p,data):
  if data.get('format')=='ScriptPackage-v1':return self.import_script_package(p,data,plan_hash=data.get('planHash'))
  if data.get('schemaVersion') in (3,4) or self.s.get(p).get('workflowVersion',1)>=2:return self.import_story_version(p,data)
  ensure(data.get('format')=='SceneExport-v1','不是受支持的 SceneExport-v1 文件');created=[]
  with self.s.transaction() as c:
   for i,e in enumerate(data.get('scenes',[])):
    old=next((s for s in self.s.list(p,'scene',c) if s.get('externalSceneId')==e['sceneId']),None)
    body=e['body'];narrative=e.get('narrativeContext',{});directives=e.get('directives',{});canon=e.get('canonSlice',{});tension=e.get('tensionType','mystery');motifs=e.get('visualMotifs',[])
    hashes={'contractHash':e.get('contractHash',digest(e.get('contract',{}))),'bodyHash':e.get('bodyHash',digest(body)),'canonHash':e.get('canonHash',digest(canon)),'narrativeHash':e.get('narrativeHash',digest(narrative)),'directivesHash':e.get('directivesHash',digest({'directives':directives,'tensionType':tension,'visualMotifs':motifs}))}
    order=e.get('order',old['order'] if old else i);mode=None
    if old:
     before={'narrativeHash':digest(old.get('narrativeContext',{})),'directivesHash':digest({'directives':old.get('directives',{}),'tensionType':old.get('tensionType','mystery'),'visualMotifs':old.get('visualMotifs',[])}),**old,**old.get('sourceHashes',{})}
     changes={k for k,value in hashes.items() if before.get(k)!=value}
     if not changes and order==old['order']:continue
     design=bool(changes.intersection({'contractHash','narrativeHash','directivesHash'})) or order!=old['order'];canon_changed='canonHash' in changes
     mode='broken' if design else 'restage' if canon_changed else 'opportunity'
     for direction in self.s.list(p,'direction',c):
      if direction['sceneId']==old['id']:
       direction['freshness']='broken' if design else 'opportunity';direction.setdefault('freshnessNotes',[]).append({'source':e['sceneId'],'message':'上游剧本的 '+', '.join(sorted(changes))+' 已更新','at':now()});self.s.put('direction',direction,p,conn=c)
     affected=set()
     for shot in self.s.list(p,'shot',c):
       if shot['sceneId']==old['id']:
        if mode!='restage':shot['freshness']=mode;self.s.put('shot',shot,p,conn=c)
        affected.add(shot['id'])
     queue=list(affected)
     while queue:
      parent=queue.pop(0)
      for link in self.list_active(p,'link',c):
       if link['from']==parent and link['type'] in ('frame_chain','extension','ref_video') and link['to'] not in affected:affected.add(link['to']);queue.append(link['to'])
     for r in self.s.list(p,'render',c):
      if r.get('shotId') in affected:r['freshness']='opportunity' if mode=='opportunity' else 'broken';self.s.put('render',r,p,conn=c)
    information=list(e.get('contract',{}).get('informationPayload',e.get('contract',{}).get('reveals',[])))
    for beat in body.get('beats',[]):
     if isinstance(beat,dict):information.extend(beat.get('informationPayload',[]))
    scene={**(old or {}),'id':old['id'] if old else uid('scene'),'projectId':p,'externalSceneId':e['sceneId'],'externalRevision':e.get('revision'),'sourceRevisions':e.get('sourceRevisions',{}),'order':order,'title':e.get('contract',{}).get('summary','场次 '+str(i+1)),
     'source':{'type':'script','ref':e['sceneId']},'sourceText':scene_export_text(body,canon),'body':body,'informationPayload':list(dict.fromkeys(x for x in information if isinstance(x,str))),'tensionType':tension,'knowledgeDelta':narrative.get('knowledgeDelta',[]),'narrativeContext':narrative,'directives':directives,'visualMotifs':motifs,
     'characterNames':[x['name'] for x in canon.get('characters',[])],'characters':old.get('characters',[]) if old else [],'props':old.get('props',[]) if old else [],'location':body.get('location','待确认'),'locationId':old.get('locationId') if old else None,'timeOfDay':body.get('timeOfDay','夜'),'targetDuration':directives.get('targetDuration',20),'status':old.get('status','accepted') if old else 'accepted','freshness':'broken' if old and old.get('status')=='locked' and mode else 'clean','freshnessNotes':([{'source':e['sceneId'],'message':'已锁定场次的上游输入发生变化，请复核','at':now()}] if old and old.get('status')=='locked' and mode else []),'flat':False,'flatness':{},
     **hashes,'sourceHashes':hashes,'semanticHash':e.get('semanticHash',digest({**hashes,'order':order})),'sourceCanon':canon}
    if old and 'bodyHash' in changes and old.get('presentation'):
     prior={'text':old['presentation'],'sourceBodyHash':before.get('bodyHash'),'archivedAt':now(),'reason':'源剧本正文已更新，旧呈现需重新确认'}
     scene['presentationHistory']=[*old.get('presentationHistory',[]),prior];scene['stalePresentation']=prior;scene['presentationFreshness']='broken';scene.pop('presentation',None)
    self.s.put('scene',scene,p,conn=c);created.append(scene['id'])
   self.s.audit(p,'import_scene_export',created,{'sourceProject':data.get('project'),'independentImport':True},c)
  return {'sceneIds':created}
 def asset_render_plan(self,p,data):
  asset=self.s.get(data['assetId']);style=self.style(p);ensure(asset['projectId']==p,'资产不属于项目');ensure(style['status']=='locked','先人工定稿风格包','style_gate',409)
  ensure(data.get('quality','proxy') in ('proxy','final'),'质量档无效')
  cfg=self.settings.read();cfg['media']=self.settings.media('keyframe');runner_id=self.runners.route({'role':'operator','stage':'B2','task':'asset_gen'},data.get('runner'));runner=self.runners.profiles()[runner_id];execution_cost=float(runner['limits'].get('costPerRunEstimate',0));estimate=execution_cost+(0 if cfg['media']['provider']=='demo' else float(cfg['media'].get('imageCost',0)));ensure(cfg['media']['provider']=='demo' or cfg['media'].get('priceConfigured'),'请先填写渲染单价')
  variant=self.s.get(data['variantId']) if data.get('variantId') else self.s.get(asset['defaultVariantId']);ensure(variant['masterId']==asset['id'],'变体不属于主资产')
  from .asset_policy import mother_brief,child_brief
  renderer_profile=self.renderer_profile(p,'keyframe')
  base_variant=self.s.get(asset['defaultVariantId'])
  parent_variant=self.s.get(variant.get('parentVariantId') or asset['defaultVariantId'])
  ensure(parent_variant['masterId']==asset['id'],'子图上级须属于同一资产','asset_parent',422)
  if variant['id']==base_variant['id']:
   reference_brief=mother_brief(asset['kind'])
   prompt='\n'.join([style['promptPrefix'],asset['freezeString'],'Declared baseline appearance: '+canonical(asset.get('baselineAppearance',{})),reference_brief,*renderer_profile.get('productionGuidance',[])])
  else:
   ensure(variant.get('requiresImage') or data.get('forceStateReference'),'该变化是镜头状态，默认复用基础图；无需新增图片','shot_state_only',409)
   if not variant.get('requiresImage'):
    ensure(asset['kind']=='prop' and any(key in variant.get('claims',{}) for key in ('lid','open','closed','damage','damaged','@contents','contents','开合','损坏','内容物')),
           '额外状态图只用于必要的道具物理外观；人物表情与握持在分镜中表达','shot_state_only',409)
   prompt=child_brief(asset,variant,parent_variant)
  reference_paths=[]
  reference_id=parent_variant.get('referenceFileId') or (asset.get('referenceFileId') if parent_variant['id']==base_variant['id'] else None)
  if asset.get('sourceEntityId') and variant['id']==base_variant['id'] and base_variant.get('visualReview',{}).get('identityHash')!=asset.get('identityHash'):reference_id=None
  if asset.get('sourceEntityId') and variant['id']!=base_variant['id']:
   review=parent_variant.get('visualReview',{})
   ensure(reference_id and review.get('identityHash')==asset.get('identityHash'),'先生成或复用该资产的身份主图并核对，再为必要状态补图','identity_reference_required',409,{'variantId':parent_variant['id']})
  if reference_id:
   file=self.s.get(reference_id);ensure(file['projectId']==p,'参考图不属于项目');source=Path(file['path']);ensure(source.is_file(),'身份参考文件不存在','media_missing',409)
   if asset.get('sourceEntityId'):
    review=parent_variant.get('visualReview',{});ensure(review.get('identityHash')==asset.get('identityHash') and review.get('fileHash')==hashlib.sha256(source.read_bytes()).hexdigest(),'身份主图已变化，请重新核对后补图','identity_reference_required',409)
   reference_paths.append(str(source.resolve()))
  for entity in variant.get('embedded',{}):
   child=next((m for m in self.list_active(p,'master') if m.get('sourceEntityId')==entity),None)
   ensure(child,'容纳物缺少身份记录，请重新提取素材','identity_reference_required',409)
   child_variant=self.s.get(child['defaultVariantId']);child_review=child_variant.get('visualReview',{});child_file=self.s.get(child_variant.get('referenceFileId',''),required=False)
   ensure(child_file and child_review.get('identityHash')==child.get('identityHash'),'请先核对容纳物「'+child['name']+'」的身份主图，再生成带容纳物的状态图','identity_reference_required',409)
   source=Path(child_file['path']);ensure(source.is_file() and child_review.get('fileHash')==hashlib.sha256(source.read_bytes()).hexdigest(),'容纳物身份主图已变化，请重新核对','identity_reference_required',409)
   reference_paths.append(str(source.resolve()));prompt+='\n参考图 '+str(len(reference_paths))+' 是容纳物「'+child['name']+'」，保持其身份与形制。'
  key=digest({'scope':p,'prompt':prompt,'negativePrompt':style['negativePrompt'],'referenceHashes':[hashlib.sha256(Path(path).read_bytes()).hexdigest() for path in reference_paths],'rendererProfile':renderer_profile,'compilerVersion':COMPILER_VERSION,'seed':asset['seed'],'quality':data.get('quality','proxy')})
  hit=bool(self.s.cached(key))
  ensure(hit or runner.get('enabled') and self.runners.qualified(runner),'执行器未启用或未完成当前配置验收','runner_unqualified',409)
  preview={'assetId':asset['id'],'variantId':variant['id'],'renderKey':key,'estimatedCost':0 if hit else estimate,'currency':self.s.get(p)['currency'],'cacheHit':hit,'baseAssetVersion':asset['_version'],'baseVariantVersion':variant['_version'],'runnerHash':digest(runner),'promptMode':'generate' if variant['id']==base_variant['id'] else 'edit','parentVariantId':parent_variant['id'],'prompt':prompt}
  preview['planHash']=digest(preview)
  return preview,asset,variant,prompt,reference_paths,cfg
 def asset_dry_run(self,p,data):return self.asset_render_plan(p,data)[0]
 def asset_render(self,p,data,progress=lambda *_:None,check=lambda:None):
  preview,asset,variant,prompt,reference_sources,cfg=self.asset_render_plan(p,data);style=self.style(p);estimate=preview['estimatedCost'];key=preview['renderKey']
  ensure(data.get('confirmed'),f'生成资产图需确认本次费用 {estimate} USD','confirmation_required',409)
  if self.s.get(p).get('workflowVersion',1)>=2:ensure(data.get('planHash')==preview['planHash'],'请确认最新素材补图费用预览','plan_required',409,preview)
  check();taskid=uid('task');work=self.s.root/'media'/p/'assets'/taskid;work.mkdir(parents=True,exist_ok=True);reference_paths=[]
  for index,path in enumerate(reference_sources):
   source=Path(path);dest=work/('base-reference-'+str(index)+source.suffix);shutil.copy2(source,dest);reference_paths.append(str(dest.resolve()))
  task={'taskId':taskid,'renderKey':key,'role':'operator','stage':'B2','task':'asset_gen','objective':'生成冻结资产参考图，不得修改 freezeString。','inputs':{'prompt':prompt,'negativePrompt':style['negativePrompt'],'freezeStrings':[asset['freezeString']],'seed':asset['seed'],'width':640 if data.get('quality','proxy')=='proxy' else 1280,'height':(360 if data.get('quality','proxy')=='proxy' else 720) if asset['kind']=='location' else (640 if data.get('quality','proxy')=='proxy' else 1280),'kind':'keyframe','media':cfg['media'],'referencePaths':reference_paths,'recoveryRequest':{'mode':'asset','assetId':asset['id'],'variantId':variant['id'],'quality':data.get('quality','proxy')}},'tools':['render','read_task','write_report'],'workdir':str(work.resolve()),'acceptance':{'minBytes':64,'extensions':['.png','.jpg','.jpeg','.webp']},'limits':{'maxTurns':10,'timeout':cfg['media'].get('timeout',900),'budget':0},'reportSchema':{}}
  hit=self.s.cached(key)
  if not hit:self.reserve(p,taskid,estimate)
  try:result=self.runners.execute(p,task,data.get('runner'),check)
  except Exception:
   if not hit:self.finish_reservation(p,taskid,{'status':'failed'})
   raise
  if not hit:self.finish_reservation(p,taskid,result)
  ensure(result['status']=='ok','资产生成失败','render_failed',502,result);f=self.register_file(p,Path(result['artifacts'][0]['path']),'asset')
  obj={'id':uid('asset_option'),'projectId':p,'assetId':asset['id'],'variantId':variant['id'],'fileId':f['id'],'url':f['url'],'renderKey':key,'status':'proposed','createdAt':now(),'baseAssetVersion':asset['_version'],'baseVariantVersion':variant['_version']};self.s.put('asset_option',obj,p);progress(1,'资产候选已生成，需人工设为参考并定稿');return obj
 def recover_remote(self,p,runner_run_id,progress=lambda *_:None,check=lambda:None):
  record=self.s.get(runner_run_id);ensure(record['projectId']==p,'执行记录不属于本项目')
  remote=record.get('result',{}).get('remote',{});ensure(remote.get('provider')=='dreamina' and remote.get('submitId'),'该执行记录没有可安全恢复的 Dreamina submit_id','remote_id_missing',409)
  ensure(record.get('result',{}).get('status')!='ok','该任务已经完成，无需恢复','already_complete',409)
  task=copy.deepcopy(record['task']);request=task.get('inputs',{}).get('recoveryRequest');ensure(request,'旧任务缺少恢复目标；保留 submit_id，请人工查询后导入结果','recovery_target_missing',409,remote)
  kind=task['inputs'].get('kind','keyframe');taskid=uid('recovery');work=self.s.root/'media'/p/'recoveries'/taskid;work.mkdir(parents=True,exist_ok=True)
  task.update(taskId=taskid,workdir=str(work.resolve()));task['inputs']['media']=self.settings.media(kind);task['inputs']['resumeSubmitId']=remote['submitId'];task['inputs']['referencePaths']=[];task['inputs']['referenceVideoPath']=None
  result=self.runners.execute(p,task,None,check);ensure(result['status']=='ok','原 Dreamina 任务尚未完成或查询失败','remote_recovery_pending',409,result);progress(.7,'已找回原远程任务，正在恢复到制作流程')
  if request['mode']=='shot':
   data={'shotIds':[request['shotId']],'kind':request['kind'],'quality':request['quality'],'seed':request.get('seed')};plan=self.dry_run(p,data);data['planHash']=plan['planHash'];output=self.render(p,data,progress,check)
  elif request['mode']=='asset':
   data={'assetId':request['assetId'],'variantId':request.get('variantId'),'quality':request.get('quality','proxy'),'confirmed':True};plan=self.asset_dry_run(p,data);data['planHash']=plan['planHash'];output=self.asset_render(p,data,progress,check)
  elif request['mode']=='generation_unit':
   data={'taskIds':[request['taskId']],'quality':request.get('quality','proxy')};plan=self.generation_dry_run(p,data);data['planHash']=plan['planHash'];output=self.execute_generation_tasks(p,data,progress,check)
  else:raise DomainError('未知恢复目标','recovery_target_invalid',409)
  self.s.audit(p,'remote_media_recovered',[runner_run_id],{'submitId':remote['submitId'],'mode':request['mode']});return {'remote':result.get('remote',remote),'output':output}
 def accept_asset_option(self,p,id):
  option=self.s.get(id);asset=self.s.get(option['assetId']);ensure(option['projectId']==p,'资产候选不属于项目');ensure(asset['_version']==option['baseAssetVersion'],'资产已变化，请重新生成参考图','base_changed',409)
  variant=self.s.get(option['variantId']);ensure(not option.get('baseVariantVersion') or variant['_version']==option['baseVariantVersion'],'资产变体已变化，请重新生成参考图','base_changed',409);variant['referenceFileId']=option['fileId'];self.save(p,'variant',variant)
  option['status']='accepted';self.s.put('asset_option',option,p);self.s.audit(p,'asset_reference_accepted',[id],{'fileId':option['fileId']});return option
 def retry_plan(self,p,data):
  shot=self.s.get(data['shotId']);ensure(shot['projectId']==p,'镜头不属于项目');kind=data.get('kind','keyframe');cls=data.get('failureClass');ensure(cls in ('sampling','prompt','design','asset'),'先选择明确失败类型');ensure(data.get('reason'),'重试须保留原因')
  if cls in ('design','asset'):return {'returnTo':'B4' if cls=='design' else 'B2','automatic':False}
  history=[r for r in self.s.list(p,'retry_request') if r['shotId']==shot['id'] and r['kind']==kind and r['failureClass']==cls and r['contractHash']==digest(shot)]
  limit=3 if cls=='sampling' else 2;ensure(len(history)<limit,'该设计已到重试上限；请返回 B4 或 B2 修正','retry_limit',409)
  attempt=len(history)+1;project=self.s.get(p);compiled=compile_prompt(shot,self.manifest(p,shot['sceneId']),self.style(p),self.renderer_profile(p));params={'shotIds':[shot['id']],'kind':kind,'quality':data.get('quality','proxy')}
  if cls=='sampling':params['seed']=int(digest({'baseSeed':compiled['seed'],'attempt':attempt,'shotId':shot['id']})[:8],16)
  else:
   rules=self.settings.read().get('promptRepairRules',[]);rule=rules[min(attempt-1,len(rules)-1)] if rules else None
   ensure(rule,'未配置经过审阅的 Prompt 修正规则，不能自由自愈；请在设置中登记 promptRepairRules','repair_rule_required',409)
   ensure(rule.get('negativeSuffix') and not rule.get('replaceFreeze'),'规则只能追加已批准负面词，不得改冻结身份串')
   params['repairRuleId']=rule.get('id',str(attempt))
  record={'id':uid('retry'),'projectId':p,'shotId':shot['id'],'kind':kind,'failureClass':cls,'reason':data['reason'],'attempt':attempt,'contractHash':digest(shot),'params':params,'createdAt':now()};self.s.put('retry_request',record,p);self.s.audit(p,'classified_retry',[shot['id']],record);return {'params':params,'attempt':attempt,'limit':limit}
