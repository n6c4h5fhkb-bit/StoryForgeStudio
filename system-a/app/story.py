from __future__ import annotations
import copy,json,re,random,math,difflib,statistics,base64,mimetypes
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor
from xml.etree import ElementTree as ET
from pydantic import ValidationError
from .core import Store,DomainError,ensure,uid,now,digest,canonical,order_key,fraction_between
from .models import Contract,Node,CandidateOutput,CANDIDATE_SCHEMA,ProbeSpec,Entity,Fact,Belief,BODY_MODELS,candidate_schema
from .creative_review import apply_repairs
from .story_review import review_candidates, payload as candidate_payload

LEVELS=['premise','spine','sequence','scene','script']
STRATEGIES={
 'premise':['日常目标遭遇不可逆代价','人物关系而非谜题驱动','主角主动犯错引发连锁后果','信息不对称','资源被逐步剥夺','目标实现但代价改变意义'],
 'spine':['外部压力递增','关系逐步恶化','因果逆转但时间线不变','连续主动选择与代价','隐藏信息改变理解'],
 'sequence':['提高外部压力','抽走依赖资源','反转人物内部立场','引入观众独知信息','制造错误信念','让人物交换主动权'],
 'scene':['对手主动行动','主角自毁式选择','资源或盟友消失','观众独知的信息','角色错误信念','两人信息不对称','延迟信息揭示','身份关系发生变化'],
 'script':['以动作替代解释','通过回避和试探形成潜台词','言行矛盾但动机一致','日常口语中的攻防','沉默与物件承载信息']}
PROBES=[
 {'id':'compare_premise','decisionType':'compare_premise','sceneSelector':'第一次具体展现核心机制并让主角付出代价的场景','renderTo':'script','horizontalDepth':4},
 {'id':'compare_engine','decisionType':'compare_engine','sceneSelector':'主角第一次因所选发展引擎付出不可逆代价的场景','renderTo':'script','horizontalDepth':4},
 {'id':'compare_relation','decisionType':'compare_relation','sceneSelector':'双方第一次因价值观冲突做出有代价的选择的场景','renderTo':'script','horizontalDepth':4}]
OPS={'expand','fill','vary','rewrite','restyle','transform','escalate','tighten','compress','deepen','interpolate','split','merge','twist','add_setup','add_payoff','move_reveal','polish'}
BODY_GUIDE={
 'premise':{'logline':'一句话故事','theme':'主题','coreConflict':'核心矛盾','stakes':'赌注','synopsis':'必须包含起点、推进、结局的完整短梗概','targetDuration':120},
 'spine':{'summary':'整段结构','valueTrajectory':[],'ending':'结尾承诺'},
 'sequence':{'goal':'目标','obstacle':'阻碍','turn':'转折','cost':'代价','summary':'完整事件发展','targetDuration':40},
 'scene':{'location':'地点','timeOfDay':'夜','action':'可看见的行动','beats':[{'id':'b1','action':'动作','informationPayload':[]}],'dialogue':[],'targetDuration':20,'tensionType':'mystery'},
 'script':{'sceneHeading':'INT. 地点 - 夜','action':'动作行','dialogue':[{'character':'角色ID','text':'台词','parenthetical':''}],'blocks':[{'type':'action','text':'动作'},{'type':'dialogue','character':'角色ID','text':'台词'}],'targetDuration':20}}

def clean(obj):return {k:v for k,v in obj.items() if k!='_version'}
def contract_equal(a,b):return digest(a)==digest(b)
def tokens(text):
 t=re.sub(r'\s+','',text);return set(t[i:i+2] for i in range(max(1,len(t)-1)))
def distance(a,b):
 x,y=tokens(a),tokens(b);return 1-len(x&y)/max(1,len(x|y))
def descendants(nodes,id):
 result=[];front=[id]
 while front:
  p=front.pop(0)
  for n in nodes:
   if n.get('parentId')==p:result.append(n);front.append(n['id'])
 return result

def flatten(nodes):
 active=[n for n in nodes if n['status']!='archived'];result=[]
 def walk(parent):
  for n in sorted((x for x in active if x.get('parentId')==parent),key=order_key):result.append(n);walk(n['id'])
 walk(None);return result

def choose_diverse(candidates,threshold=2,distances=None):
 valid=[c for c in candidates if c['gate']['passed']]
 if not valid:return []
 first=max(valid,key=lambda c:c['quality']);rest=[x for x in valid if x['id']!=first['id'] and x['quality']>=threshold]
 chosen=[first];first['slot']='最佳稳妥'
 if rest:
  second=max(rest,key=lambda c:c['novelty']);second['slot']='最佳新颖';chosen.append(second);rest=[x for x in rest if x['id']!=second['id']]
 if rest:
  third=max(rest,key=lambda c:min((distances or {}).get(tuple(sorted((c['id'],o['id']))),distance(c['summary'],o['summary'])) for o in chosen));third['slot']='最佳另类';chosen.append(third)
 return chosen

def candidate_count(data,level=None):
 default=1 if data.get('op') in ('fill','polish','tighten','compress') or (level=='script' and data.get('op') in ('expand','deepen')) else 2 if data.get('op')=='restyle' else 3
 count=data.get('candidateCount',default)
 ensure(isinstance(count,int) and not isinstance(count,bool) and 1<=count<=5,'候选数量必须是 1–5 的整数','candidate_count',422)
 return count

def entity_references(value,known):
 if isinstance(value,dict):return set().union(*(entity_references(v,known) for v in value.values())) if value else set()
 if isinstance(value,list):return set().union(*(entity_references(v,known) for v in value)) if value else set()
 return {value} if isinstance(value,str) and value in known else set()

class StoryService:
 def __init__(self,store,settings,llm):self.s=store;self.settings=settings;self.llm=llm
 def create(self,data,origin=None):
  title=str(data.get('title','未命名故事')).strip()[:100];seed=str(data.get('seed','')).strip()
  ensure(seed or data.get('seedImages'),'请输入故事种子或上传图片')
  p={'id':uid('a'),'workspace':'A','presentationMode':data.get('presentationMode','fast_drama'),'title':title,'seed':seed,'seedImages':data.get('seedImages',[]),'targetDuration':float(data.get('targetDuration',120)),'episodes':int(data.get('episodes',1)),
   'genre':data.get('genre','都市故事'),'tone':data.get('tone','写实、有人味'),'template':data.get('template','hook_chain'),'compact':data.get('compact',True),
   'constraints':data.get('constraints',[]),'canon':{'entities':[],'facts':[],'beliefs':[]},'negativeList':[],'styleExamples':[],'status':'active','createdAt':now()}
  ensure(p['presentationMode'] in ('cinema','series','fast_drama'),'呈现方向无效')
  ensure(p['targetDuration']>0,'目标时长必须大于零')
  p['timingMode']='target' if data.get('targetDuration') is not None else 'content'
  p['creationMode']='original'
  with self.s.transaction() as c:
   existing=next((x for x in self.s.list(kind='project',conn=c) if x.get('ideaOrigin')==origin),None) if origin else None
   if existing:p=existing
   else:
    if origin:p['ideaOrigin']=copy.deepcopy(origin)
    self.s.put('project',p,p['id'],conn=c);self.s.audit(p['id'],'create_project',[],{'seed':seed,'ideaOrigin':origin},c)
  return self.get(p['id'])
 def nodes(self,p,conn=None):return self.s.list(p,'node',conn)
 def get(self,p):
  project=self.s.get(p);nodes=self.nodes(p)
  return {'project':project,'nodes':flatten(nodes),'candidates':self.s.list(p,'candidate'),'novelDrafts':self.s.list(p,'novel_draft'),'novelSource':({k:v for k,v in self.s.get(project['sourceId']).items() if k!='text'} if project.get('creationMode')=='novel' else None),'coverage':self.coverage(p,nodes),
   'patches':self.s.list(p,'canon_patch'),'edges':self.s.list(p,'edge'),'spikes':[{k:v for k,v in x.items() if k!='horizontal'} for x in self.s.list(p,'spike')],
   'branches':self.s.list(p,'branch'),'comments':self.s.list(p,'comment'),'probeSpecs':self.probe_specs(p)}
 def probe_specs(self,p):
  custom=self.s.list(p,'probe_spec');return custom or copy.deepcopy(PROBES)
 def update_project(self,p,data):
  with self.s.transaction() as c:
   old=self.s.get(p,c);before=copy.deepcopy(old)
   allowed={'title','targetDuration','episodes','genre','tone','template','constraints','seedImages','compact','presentationMode'}
   for k,v in data.items():
    if k=='compact' and v!=old.get('compact'):ensure(not self.nodes(p,c),'已有节点时不能更换层级模式；新建项目选择完整模式')
    if k in allowed:old[k]=v
   ensure(old.get('presentationMode','fast_drama') in ('cinema','series','fast_drama'),'呈现方向无效')
   if 'presentationMode' in data:
    selected=old.get('scriptVersionsByMode',{}).get(old['presentationMode'])
    if selected:old['activeScriptVersionId']=selected
   out=self.s.put('project',old,p,expected=data.get('_version'),conn=c);self.s.audit(p,'project_settings',[],{'before':before,'after':out},c)
  return out
 def coverage(self,p,nodes=None):
  ns=[x for x in (nodes if nodes is not None else self.nodes(p)) if x['status']!='archived'];project=self.s.get(p);layers=['premise','sequence','scene','script'] if project.get('compact') else LEVELS
  rows=[]
  for i,l in enumerate(layers):
   current=[n for n in ns if n['level']==l and not n.get('speculative')];done=sum(n.get('generationComplete',False) for n in current)
   if i==0:expected=1
   else:
    parents=[n for n in ns if n['level']==layers[i-1] and not n.get('speculative')]
    expected=len(current)+sum(not any(x['parentId']==n['id'] for x in current) for n in parents)
    if not parents:expected=max(1,expected)
   rows.append({'level':l,'done':done,'total':expected,'percent':round(100*done/max(1,expected))})
  frontier=next((x['level'] for x in rows if x['percent']<100),layers[-1])
  return {'frontier':frontier,'layers':rows,'speculative':sum(n.get('speculative',False) for n in ns),'broken':sum(n['freshness']=='broken' for n in ns)}
 def scene_scope(self,nodes,node):
  by={n['id']:n for n in nodes};anchor=node
  while anchor and anchor['level'] not in ('scene','premise','spine','sequence'):
   anchor=by.get(anchor.get('parentId'))
  if not anchor:return None,[]
  # Scene order crosses sequence boundaries: a cut is still adjacent across acts.
  siblings=[x for x in flatten(nodes) if x['level']=='scene'] if anchor['level']=='scene' else sorted([x for x in nodes if x['parentId']==anchor['parentId'] and x['status']!='archived'],key=order_key)
  idx=next((i for i,x in enumerate(siblings) if x['id']==anchor['id']),0)
  return anchor,[x for x in siblings[max(0,idx-2):idx+3] if x['id']!=anchor['id']]
 def scene_body(self,nodes,node):
  script=next((x for x in nodes if x['parentId']==node['id'] and x['level']=='script' and x['status']!='archived' and x.get('generationComplete')),None)
  return {**node['body'],**script['body']} if script else copy.deepcopy(node['body'])
 def canon_slice(self,p,nodes,node,related=None):
  canon=copy.deepcopy(self.s.get(p)['canon'])
  if not node:return canon
  known={e['id'] for e in canon['entities']};scope=[node,*(related or [])]
  refs=set().union(*(entity_references({'contract':n['contract'],'body':self.scene_body(nodes,n)},known) for n in scope))
  locations={n['body'].get('location') for n in scope if isinstance(n['body'].get('location'),str)}
  refs|={e['id'] for e in canon['entities'] if e.get('kind')=='rule' or (e.get('kind')=='location' and e.get('name') in locations)}
  canon['entities']=[e for e in canon['entities'] if e['id'] in refs]
  idx=self.time_index(nodes);entry=idx.get(node['id'],0)
  active=lambda item:self.at_time(item.get('validFrom'),idx,-1)<=entry<self.at_time(item.get('validUntil'),idx,float('inf'))
  canon['facts']=[f for f in canon.get('facts',[]) if f.get('subject') in refs and active(f)]
  canon['beliefs']=[b for b in canon.get('beliefs',[]) if b.get('holder') in refs|{'AUDIENCE'} and active(b)]
  return canon
 def snapshot(self,p,target,op):
  project=self.s.get(p);ns=self.nodes(p);by={n['id']:n for n in ns};node=by.get(target);refs={}
  if node:refs[node['id']]={'mode':'revision','hash':node['currentRevision']}
  a=node
  while a and a.get('parentId'):
   a=by[a['parentId']];refs[a['id']]={'mode':'contract','hash':digest(a['contract'])}
  anchor,neighbors=self.scene_scope(ns,node)
  for n in ([anchor] if anchor and anchor['id']!=target else [])+neighbors:
   mode='scene' if n['level']=='scene' else 'contract';refs[n['id']]={'mode':mode,'hash':digest({'contract':n['contract'],'body':n['body']}) if mode=='scene' else digest(n['contract'])}
   if n['level']=='scene':
    for child in ns:
     if child['id']!=target and child['parentId']==n['id'] and child['level']=='script' and child['status']!='archived' and child.get('generationComplete'):refs[child['id']]={'mode':'scene','hash':digest({'contract':child['contract'],'body':child['body']})}
  for premise in ns:
   if premise['level']=='premise' and premise['status']!='archived' and premise['id']!=target:refs[premise['id']]={'mode':'scene','hash':digest({'contract':premise['contract'],'body':premise['body']})}
  result={'refs':refs,'canonHash':digest(project['canon']),'constraintsHash':digest(project['constraints']),'settingsHash':digest({k:project.get(k) for k in ('template','compact','tone','targetDuration','episodes')}),'neighborIds':[x['id'] for x in neighbors]}
  if not target:result['rootIds']=sorted(n['id'] for n in ns if n['parentId'] is None and n['status']!='archived')
  elif op in ('expand','deepen','split'):result['structureRefs']={n['id']:n['currentRevision'] for n in descendants(ns,target) if n['status']!='archived'}
  return result
 def context(self,p,target,op,instruction='',extra=None):
  project=self.s.get(p);ns=self.nodes(p);by={n['id']:n for n in ns};n=by.get(target);anc=[];a=n
  while a and a.get('parentId'):
   a=by[a['parentId']];anc.insert(0,{'id':a['id'],'contract':a['contract']})
  anchor,near=self.scene_scope(ns,n)
  neighbors=[{'id':x['id'],'contract':x['contract'],**({'body':self.scene_body(ns,x)} if x['level']=='scene' else {})} for x in near]
  canon=self.canon_slice(p,ns,anchor,near) if anchor and anchor['level']=='scene' else copy.deepcopy(project['canon'])
  scope_ids={x['id'] for x in near}|({anchor['id']} if anchor else set())|({n['id']} if n else set())
  narrative=[clean(e) for e in self.s.list(p,'edge') if not e.get('archived') and (e.get('from') in scope_ids or e.get('to') in scope_ids)]
  experience=self.experiences.guidance(p,{'stage':'story','operation':op,'targetLevel':(extra or {}).get('targetLevel') or (n or {}).get('level')}) if hasattr(self,'experiences') else {'revisionHash':digest([]),'lessons':[]}
  data={'01_pin':project['constraints'],'02_bible':{'seed':project['seed'],'genre':project['genre'],'tone':project['tone'],'template':project['template'],'targetDuration':project['targetDuration'],'episodes':project['episodes'],'visualSeedObservations':[{k:x.get(k) for k in ('observations','motifs','directions')} for x in self.s.list(p,'observation')]},
    '03_ancestors':anc,'04_neighbors':neighbors,'05_canon':canon,'05_narrative':narrative,'06_experience':experience,
   '08_task':{'operation':op,'instruction':instruction,'target':clean(n) if n else None,**(extra or {})}}
  if project.get('timingMode')=='content':
   data['02_bible'].pop('targetDuration',None);data['02_bible'].pop('episodes',None);data['02_bible']['timingMode']='content'
   data['08_task']['allocatedDuration']=None
   if data['08_task'].get('bodySchemaGuide'):
    data['08_task']['bodySchemaGuide']=copy.deepcopy(data['08_task']['bodySchemaGuide']);data['08_task']['bodySchemaGuide']['targetDuration']='按实际对白、动作和停顿估算的正秒数，仅供参考'
  premise=next((x for x in ns if x['level']=='premise' and x['status']!='archived'),None)
  if premise and (not n or premise['id']!=n['id']):data['02_bible']['acceptedPremise']=premise['body']
  if n and n['level']=='script' and anchor and anchor['level']=='scene':data['08_task']['scene']={'id':anchor['id'],'contract':anchor['contract'],'body':anchor['body']}
  target_level=(extra or {}).get('targetLevel') or (n or {}).get('level');role='structure' if target_level in ('premise','spine') else 'script' if target_level=='script' else 'story'
  limit=int(self.settings.model(role).get('contextCharacters',32000))
  if len(canonical(data))>limit:data['04_neighbors']=[{'id':x['id'],'contract':x['contract']} for x in neighbors]
  from .formats import MODES
  data['02_bible']['presentationMode']=project.get('presentationMode','fast_drama');data['02_bible']['formatFocus']=MODES[project.get('presentationMode','fast_drama')]
  ensure(len(canonical(data))<=limit,'硬约束与必要上下文超过配置预算，请提高 contextCharacters 或缩小范围','context_budget',422)
  return data
 def next_level(self,p,n):
  levels=['premise','sequence','scene','script'] if self.s.get(p).get('compact') else LEVELS
  if n is None:return 'premise'
  i=levels.index(n['level']);ensure(i<len(levels)-1,'已到对白动作层；请选择改写或变体');return levels[i+1]
 def next_step(self,p):
  if self.s.get(p).get('creationMode')=='imported_script':return self.formats.next_step(p)
  """Read-only progressive-resolution planner; never adopts a creative choice."""
  if self.s.get(p).get('creationMode')=='novel':
   from .novel import NovelService
   if getattr(self,'formats',None) and self.s.get(p).get('activeNovelDraft') and not any(row.get('status')=='proposed' and row.get('baseDraftId')==self.s.get(p).get('activeNovelDraft') for row in self.s.list(p,'novel_draft')):
    step=self.formats.next_step(p)
    if step['state']!='complete':return step
   return NovelService(self).next_step(p)
  project=self.s.get(p);nodes=flatten(self.nodes(p));layers=['premise','sequence','scene','script'] if project.get('compact') else LEVELS
  patches=[x for x in self.s.list(p,'canon_patch') if x['status']=='pending']
  if patches:return {'state':'needs_attention','stage':'A2','kind':'canon','label':'确认采用方案中的人物与设定','reason':'这些设定随已选方案提出，确认后继续创作。','patchIds':[x['id'] for x in patches]}
  candidates=self.s.list(p,'candidate');batches=list(dict.fromkeys(c['batchId'] for c in candidates))
  for batch in reversed(batches):
   rows=[c for c in candidates if c['batchId']==batch]
   if any(c['status']=='adopted' for c in rows):continue
   reusable=[]
   for c in rows:
    if c['status']!='proposed' or not c.get('visible') or not c['gate']['passed']:continue
    try:self.check_base(p,c,None)
    except DomainError:continue
    reusable.append(c)
   if reusable:
    first=reusable[0];stage='A1' if not first.get('targetId') else 'A3' if first['targetLevel'] in ('scene','script') else 'A2'
    return {'state':'awaiting_choice','stage':stage,'op':first['op'],'nodeId':first.get('targetId'),'targetLevel':first['targetLevel'],'batchId':batch,'candidateIds':[c['id'] for c in reusable],'candidateCount':len(rows),'label':'已有方案，选择后继续','reason':'复用尚未选择的有效候选，不重复生成，也不跳过当前创作选择。'}
  action=None;blocked=[]
  if not nodes:action={'op':'expand','nodeId':None,'targetLevel':'premise','stage':'A1','label':'生成故事方向'}
  for level in layers:
   if action:break
   current=[n for n in nodes if n['level']==level]
   incomplete=[n for n in current if not n.get('generationComplete')]
   if incomplete:
    eligible=[n for n in incomplete if n['status']!='locked' and n['freshness']!='broken']
    if eligible:
     n=eligible[0];action={'op':'fill','nodeId':n['id'],'targetLevel':level,'stage':'A3' if level in ('scene','script') else 'A2','label':'完善“'+n['title']+'”'}
    else:blocked=incomplete
    break
   if level!='script':
    missing=[n for n in current if not any(x['parentId']==n['id'] for x in nodes)]
    if missing:
     eligible=[n for n in missing if n['freshness']!='broken']
     if eligible:
      n=eligible[0];target_level=self.next_level(p,n);action={'op':'expand','nodeId':n['id'],'targetLevel':target_level,'stage':'A3' if target_level=='script' else 'A2','label':'继续展开“'+n['title']+'”'}
     else:blocked=missing
     break
  if not action:
   blocked=blocked or [n for n in nodes if n['freshness']=='broken']
   if blocked:return {'state':'needs_attention','stage':'A3','kind':'conflict','label':'先处理需要你决定的场景','reason':'存在冲突或尚未完成但已锁定的内容；不会覆盖已有选择。','nodeId':blocked[0]['id'],'nodeIds':[n['id'] for n in blocked]}
   if getattr(self,'formats',None):return self.formats.next_step(p)
   return {'state':'complete','stage':'A4','label':'完整剧本已就绪','reason':'现在可以通读、局部精修或导出交给分镜平台。'}
  action.update(state='ready',candidateCount=candidate_count(action,action['targetLevel']),reason='根据已采纳版本推进下一步；生成结果仍由你选择。')
  return action
 def advance(self,p,data=None,progress=lambda *_:None,check=lambda:None):
  if getattr(self,'formats',None):
   step=self.next_step(p)
   if step.get('action')=='prepare_script':return {'scriptVersion':self.formats.propose(p,data or {},progress,check),'advanced':True,'nextStep':self.next_step(p)}
   if step.get('action')=='choose_script':return {'nextStep':step,'advanced':False}
  if self.s.get(p).get('creationMode')=='novel':
   from .novel import NovelService
   data=data or {};novel=NovelService(self)
   advance_mode=data.get('advanceMode',data.get('mode') if data.get('mode') in ('single','until_choice') else 'single')
   ensure(advance_mode in ('single','until_choice'),'自动推进方式无效','advance_mode',422)
   analysis=None
   for _ in range(3):
    step=novel.next_step(p)
    if step['state']!='ready':return {'nextStep':step,'advanced':False,**({'analysis':analysis} if analysis else {})}
    if step.get('action')=='analyze_novel':
     callback=progress if advance_mode=='single' else lambda value,message:progress(value*.45,message)
     analysis=novel.analyze_all(p,callback,check)
     if advance_mode=='single':return {'analysis':analysis,'advanced':True,'nextStep':novel.next_step(p)}
     continue
    callback=progress if not analysis else lambda value,message:progress(.45+value*.55,message)
    candidate=novel.propose(p,data,callback,check)
    return {'novelDraft':candidate,'analysis':analysis,'advanced':True,'nextStep':novel.next_step(p)}
   raise DomainError('自动推进未能到达选择点','advance_stalled',409)
  check();step=self.next_step(p)
  if step['state']!='ready':return step
  data=data or {};task={k:step[k] for k in ('op','nodeId','candidateCount')}
  for k in ('candidateCount','instruction','count','operationId','generationId'):
   if k in data:task[k]=data[k]
  result=self.generate(p,task,progress,check)
  return {**step,**result,'state':'needs_attention' if result['allFailed'] else 'awaiting_choice','label':'候选需要调整' if result['allFailed'] else '请选择这一轮的创作结果'}
 def plan(self,p,data):
  target=data.get('nodeId');op=data.get('op','vary');ns=self.nodes(p);node=next((x for x in ns if x['id']==target),None)
  affected=descendants(ns,target) if target else []
  if node and op in ('reorder','delete','move_reveal','rewrite','merge','split'):
   affected+= [x for x in ns if x['parentId']==node['parentId'] and x['id']!=node['id']]
  unique={x['id']:x for x in affected};ids=sorted(unique)
  return {'op':op,'scope':[target] if target else [],'affected':[{'id':x['id'],'title':x['title'],'status':x['status'],'freshness':x['freshness']} for x in unique.values()],
   'locked':[x['id'] for x in unique.values() if x['status']=='locked'],'candidateCount':candidate_count(data,node['level'] if node else None),'requiresApproval':op in ('delete','reorder','move_reveal','unlock','merge','split') or op=='rewrite',
   'planHash':digest({'op':op,'snapshot':self.snapshot(p,target,op),'affected':[(x['id'],x['currentRevision']) for x in unique.values()]}),'note':'影响列表是范围预览，不会自动重写；只有结构契约冲突才阻塞继续深化。'}
 def generate(self,p,data,progress=lambda *_:None,check=lambda:None):
  op=data.get('op','vary');ensure(op in OPS,'未知生成操作');target=data.get('nodeId');node=self.s.get(target) if target else None
  if node:
   ensure(node['projectId']==p,'节点不属于此项目',status=404)
   ensure(node['status']!='archived','归档节点不能生成')
   ensure(node['status']!='locked' or op in ('expand','deepen','interpolate'),'锁定正文不能改写；先显式解锁，或展开子节点','locked',409)
   ensure(node['freshness']!='broken' or op not in ('expand','fill','deepen'),'此节点存在冲突，请先仲裁；仍可导出','broken_block',409)
  if op=='fill':ensure(node and not node.get('generationComplete'),'该节点已填充；请选择改写')
  if node and (op in ('rewrite','move_reveal','split') or op=='merge' and data.get('otherNodeId')):
   preview=self.plan(p,data);ensure(data.get('planHash')==preview['planHash'],'此操作可能传播，请先预览并确认','plan_required',409,preview)
  if op in ('split','interpolate'):ensure(node and node.get('parentId'),'不能拆分根节点或在根旁插入')
  if op=='merge' and data.get('otherNodeId'):
   other=self.s.get(data['otherNodeId']);ensure(other['projectId']==p and other['parentId']==node['parentId'] and other['level']==node['level'],'只能合并同层同父节点')
   data={**data,'references':[{'id':other['id'],'contract':other['contract'],'body':other['body']}]}

  level=self.next_level(p,node) if op in ('expand','deepen') else (node['level'] if node else 'premise')
  phase='contracts' if op in ('expand','deepen','split','interpolate') or not node else 'body'
  if op=='split':level=node['level']
  if level=='script' and phase=='contracts':data={**data,'count':1}
  author_role='structure' if level in ('premise','spine') else 'script' if level=='script' else 'story'
  ensure(self.settings.model(author_role)['provider']=='demo' or self.settings.model('validator')['provider']!='demo','真实原创需要独立质量复核模型','reviewer_required',409)
  snap=self.snapshot(p,target,op)
  if data.get('otherNodeId'):
   other=self.s.get(data['otherNodeId']);snap['refs'][other['id']]={'mode':'revision','hash':other['currentRevision']}
  count=candidate_count(data,level)
  # One deliberate creation gets one durable intent. A retry keeps its selected
  # strategies and IDs; a new creation can still explore genuinely new options.
  generation=data.get('generationId') or data.get('operationId') or uid('generation')
  request_id='story_request_'+digest([p,generation])[:32]
  request_hash=digest({k:v for k,v in data.items() if k not in ('operationId','generationId','planHash')})
  with self.s.transaction() as conn:
   request=self.s.get(request_id,conn,False)
   if request:
    ensure(request['requestHash']==request_hash,'恢复任务的内容已变化，请作为新修改提交','idempotency_conflict',409)
    if request.get('result'):return request['result']
    ensure(request['base']==snap,'恢复期间采用稿已变化，请基于当前稿提出新修改','base_changed',409)
   else:
    request={'id':request_id,'projectId':p,'generationId':generation,'requestHash':request_hash,'base':snap,'batchId':uid('batch'),'strategies':random.sample(STRATEGIES[level],count),'createdAt':now()}
    self.s.put('generation_request',request,p,conn=conn)
  batch=request['batchId'];strategies=request['strategies']
  specs=self.probe_specs(p);spec=copy.deepcopy(specs[0 if level=='premise' else 1 if len(specs)>1 else 0]);spec['registeredAt']=now()
  self.s.put('decision_batch',{'id':batch,'projectId':p,'probeSpec':spec,'base':snap,'op':op,'targetId':target,'candidateCount':count,'createdAt':now()},p)
  context=self.context(p,target,op,data.get('instruction',''),{'targetLevel':level,'phase':phase,'bodySchemaGuide':BODY_GUIDE[level],'allocatedDuration':node.get('plannedDuration',node.get('body',{}).get('targetDuration')) if node else self.s.get(p)['targetDuration'],'count':1 if not node else max(1,min(12,int(data.get('count',3)))),'references':data.get('references',[]),'targetNarrativeNodeId':data.get('targetNarrativeNodeId')})
  system=Path(__file__).with_name('prompts').joinpath('generate.txt').read_text(encoding='utf-8')
  if not node:system+='\n本次只创作一个完整故事方向，items 必须恰好一项。平台会分别生成其他候选，不要把多个备选故事放入当前候选的 items。'
  if self.s.get(p).get('timingMode')=='content':system+='\n当前没有用户指定片长或集数。以故事质量为先，正文完成后才估计秒数；不要按示例数字、内部 plannedDuration 或固定分钟数压缩剧情。'
  created=[]
  def run_strategy(index,strategy,previous=None):
   candidate_id=p+'_candidate_'+digest([generation,index])[:24]
   ready=self.s.get(candidate_id,required=False)
   if ready and previous is None:
    if ready.get('reviewRepairNeeded'):previous=ready
    else:return ready
   local=copy.deepcopy(context);local['08_task'].update(strategy=strategy,requestNonce=generation)
   errors=copy.deepcopy(previous['gate']['errors']) if previous else [];out=candidate_payload(previous) if previous else None
   used=previous.get('attemptsUsed',0) if previous else 0;seen={digest(out)} if out else set()
   schema=candidate_schema(level,phase)
   patch_schema={'type':'object','properties':{'patches':{'type':'array','minItems':1,'maxItems':64,'items':{'type':'object','properties':{'op':{'enum':['add','replace','remove']},'path':{'type':'string'},'value':{}},'required':['op','path'],'additionalProperties':False}}},'required':['patches'],'additionalProperties':False}
   for attempt in range(used,3):
    check()
    if errors:local['08_task']['repairErrors']=errors
    repairing=bool(errors and isinstance(out,dict))
    prompt=system
    if repairing:
     local['previousCandidate']=out;local['repairFormat']='json_patch'
     prompt+='\n本轮修复 repairErrors，以 previousCandidate 为基准优先返回 {patches:[{op:add|replace|remove,path:JSON Pointer,value:新值}]}。只改有问题的字段，处理所有同类问题，保留未受影响的正文、人物与因果；程序合并后完整校验。'
    try:
     used=attempt+1
     reply=self.llm.json(p,'structure' if level in ('premise','spine') else 'script' if level=='script' else 'story',prompt,local,{'$defs':schema.get('$defs',{}),'anyOf':[schema,patch_schema]} if repairing else schema,
        demo=lambda:self.demo_candidate(p,node,level,phase,index,data),cache=True,check=check, session_scope="story:"+str(target or 'root')+":"+level+":"+phase+":"+digest(strategy)[:12])
     out=apply_repairs(out,reply) if repairing and isinstance(reply,dict) and 'patches' in reply else reply
     errors=self.gate(p,out,node,op,level,phase)
     if not errors:break
     fingerprint=digest(out)
     if fingerprint in seen:errors.append('修订没有进展，请针对具体问题调整');break
     seen.add(fingerprint)
    except DomainError as e:
     if e.code not in ('schema_validation','invalid_model_output','truncated_output'):raise
     errors=[str(e)]
     if out is None and isinstance(e.details,dict):out=e.details.get('output')
   if out is None:out={'title':'生成未通过校验','summary':'当前策略失败','rationale':'','risks':errors,'items':[]}
   c={**out,'id':candidate_id,'projectId':p,'batchId':batch,'targetId':target,'op':op,'phase':phase,'targetLevel':level,'strategy':strategy,'base':snap,
      'status':'proposed','gate':{'passed':not errors,'errors':errors},'attemptsUsed':used,'reviewRequired':self.settings.model(author_role)['provider']!='demo','quality':3 if not errors else 0,'novelty':3,'slot':'备选','createdAt':now(),'demo':self.settings.model(author_role)['provider']=='demo','otherNodeId':data.get('otherNodeId'),'targetNarrativeNodeId':data.get('targetNarrativeNodeId')}
   self.s.put('candidate',c,p)
   current_patches=set()
   for kind,field in [('entity','entityProposals'),('fact','factProposals'),('belief','beliefProposals')]:
    for patch_index,item in enumerate(c.get(field,[])):
     patch_id=p+'_patch_'+digest([c['id'],kind,patch_index])[:24];current_patches.add(patch_id)
     self.s.put('canon_patch',{'id':patch_id,'projectId':p,'candidateId':c['id'],'kind':kind,'value':item,'status':'provisional'},p)
   for old in self.s.list(p,'canon_patch'):
    if old['candidateId']==c['id'] and old['status']=='provisional' and old['id'] not in current_patches:self.s.put('canon_patch',{**old,'status':'superseded'},p)
   return c
  with ThreadPoolExecutor(max_workers=2) as pool:
   futures=[pool.submit(run_strategy,i,s) for i,s in enumerate(strategies)]
   for i,f in enumerate(futures):created.append(f.result());progress(.12+.7*(i+1)/len(futures),f'已生成并校验 {i+1}/{len(futures)} 路策略')
  check();valid=[x for x in created if x['gate']['passed']];semantic_distances={}
  if valid and self.settings.model('validator')['provider']!='demo':
   semantic_distances=review_candidates(self,p,context,created,lambda c:run_strategy(strategies.index(c['strategy']),c['strategy'],c),check,progress,'story-review:'+str(target or 'root')+':'+level+':'+phase)
  else:
   for i,c in enumerate(created):c.update(quality=4-i*.15 if c['gate']['passed'] else 0,novelty=2+i*.5,scoreEvidence='演示评分，仅测试交互，不代表模型评价')
  chosen=choose_diverse(created,distances=semantic_distances)
  if len(chosen)==1:chosen[0]['slot']='推荐版本'
  for c in created:c['visible']=c in chosen;self.s.put('candidate',c,p)
  self.s.audit(p,op,[target] if target else [],{'instruction':data.get('instruction',''),'contextDigest':digest(context),'batchId':batch,'candidateIds':[c['id'] for c in created],'promptVersion':'1.0'})
  progress(1,'候选已就绪，正式内容未改变')
  result={'batchId':batch,'candidateIds':[c['id'] for c in chosen],'candidateCount':count,'failedCount':sum(not c['gate']['passed'] for c in created),'allFailed':not bool(chosen)}
  self.s.put('generation_request',{**request,'result':result,'completedAt':now()},p)
  if hasattr(self,'experiences'):
   self.experiences.applied(p,{'type':'story_generation','targetId':target,'operation':op,'batchId':batch},context.get('06_experience',{}),batch)
  return result
 def gate(self,p,out,node,op,level,phase):
  errors=[]
  try:parsed=CandidateOutput.model_validate(out)
  except ValidationError as e:return [str(e)]
  if node is None and len(out['items'])!=1:errors.append('每张故事方向候选必须只有一个故事根节点，不能把多个备选方案作为 items 一起采用')
  canon=self.s.get(p)['canon'];proposed=[]
  for entity in out.get('entityProposals',[]):
   try:proposed.append(Entity.model_validate(entity).model_dump())
   except ValidationError as e:errors.append('人物/实体提案格式不合法：'+str(e))
  known={e['id'] for e in canon['entities']}|{e['id'] for e in proposed}
  characters={e['id'] for e in [*canon['entities'],*proposed] if e['kind']=='character'}
  for item in out['items']:
   c=item['contract'];v=c['valueChange']
   if v['from']==v['to']:errors.append('valueChange 必须发生变化')
   if item['level']!=level:errors.append('输出层级不符')
   for e in c['entities']:
    if e not in known:errors.append('未声明 Canon 实体：'+e)
   if phase=='body' and node and op in ('fill','restyle','tighten','polish') and not contract_equal(c,node['contract']):errors.append('此次操作必须保留契约逐字段不变')
   if phase=='contracts' and item.get('body'):errors.append('契约阶段不能生成正文')
   if phase=='body' and not item.get('body'):errors.append('正文不能为空')
   if phase=='body':
    try:BODY_MODELS[level].model_validate(item.get('body',{}))
    except ValidationError as e:errors.append('正文结构不符合 '+level+'：'+str(e))
    body=item.get('body',{});lines=body.get('dialogue',[]) if isinstance(body.get('dialogue',[]),list) else []
    blocks=body.get('blocks',[]) if isinstance(body.get('blocks',[]),list) else []
    for line in lines+[x for x in blocks if isinstance(x,dict) and x.get('type')=='dialogue']:
     if isinstance(line,dict) and line.get('character') not in characters:errors.append('对白引用未知角色 ID：'+str(line.get('character')))
   facts={(f['subject'],f['predicate']):f['object'] for f in canon.get('facts',[]) if not f.get('validFrom')}
   for s in c.get('preconditions',[]):
    if (s['subject'],s['predicate']) in facts and facts[s['subject'],s['predicate']]!=s['object']:errors.append('与全局事实冲突')
  if phase=='contracts' and node and op in ('expand','deepen'):
   delivered={(x['subject'],x['predicate']):x['object'] for item in out['items'] for x in item['contract'].get('postconditions',[])}
   for requirement in node['contract'].get('postconditions',[]):
    if delivered.get((requirement['subject'],requirement['predicate']))!=requirement['object']:errors.append('子契约序列结束时未兑现父契约退出状态：'+canonical(requirement))
  if phase=='body' and len(out['items'])!=1 and op not in ('merge','split'):errors.append('局部正文操作只能产生一个节点实现')
  return list(dict.fromkeys(errors))
 def demo_candidate(self,p,node,level,phase,index,data):
  project=self.s.get(p);seed=project['seed'];heroes=project['canon']['entities'];hero=next((e['id'] for e in heroes if e['kind']=='character'),'hero')
  titles=['失去退路','误判的代价','关系换位','被看见的秘密','兑现承诺'];verb=titles[index%len(titles)]
  count=(1 if level=='script' else max(2,min(6,int(data.get('count',3))))) if phase=='contracts' and node else 1
  items=[]
  for j in range(count):
   summary=(['日常目标被打断，人物必须采取行动','主动验证失败，代价落到关系上','主角作出不可撤回的选择，前面的细节得到回应'][j%3] if count>1 else f'围绕“{seed[:32]}”，用{verb}推动人物主动选择并承担后果。')
   contract=copy.deepcopy(node['contract']) if phase=='body' and node else {'summary':summary,'preconditions':[], 'postconditions':[{'subject':hero,'predicate':'progress','object':f'{level}-{j+1}'}], 'valueChange':{'axis':'掌控感','from':'确信' if j==0 else '怀疑','to':'代价显现' if j<count-1 else '做出选择'},'reveals':[summary],'obligations':['用可见行动推动变化'],'entities':[hero],'producibility':None}
   if phase=='contracts' and node and j==count-1:contract['postconditions']=copy.deepcopy(node['contract'].get('postconditions',[]))
   body={} if phase=='contracts' else copy.deepcopy(BODY_GUIDE[level])
   if body:
    body.update(summary=summary)
    if level=='premise':body.update(logline=summary,synopsis=f'{seed}。主人公原本只想完成一件小事，却在{verb}后主动寻找验证。他的每次补救都付出更大的代价。最终他放弃最安全的退路，以一个明确行动回应最初的问题。',targetDuration=project['targetDuration'])
    if level in ('scene','script'):
     body.update(action=f'人物停在门口，手已经碰到把手，却没有推开。里面传来熟悉的声音。{summary}',targetDuration=round(project['targetDuration']/6,1),dialogue=[{'character':hero,'text':'你先别开门。'},{'character':hero,'text':'刚才那句话，不是说给你的。'}],beats=[{'id':'b1','action':'手停在把手上','informationPayload':['人物正在犹豫']},{'id':'b2','action':'门内的声音改变了选择','informationPayload':[summary]}])
     if level=='script':body['blocks']=[{'type':'action','text':body['action']},*[{'type':'dialogue',**line} for line in body['dialogue']]]
   if body:body['targetDuration']=float(node.get('plannedDuration') or node.get('body',{}).get('targetDuration') or project['targetDuration']) if node else project['targetDuration']
   items.append({'title':f'{verb} · {j+1}' if count>1 else verb,'level':level,'contract':contract,'body':body})
  return {'title':verb,'summary':items[0]['contract']['summary'],'rationale':'离线示例：演示契约、候选、采纳及版本流程。连接模型后使用你的种子实际生成。','risks':['演示内容不是实时模型生成'],'items':items,
          'entityProposals':[] if any(e['id']==hero for e in heroes) else [{'id':hero,'kind':'character','name':'主角','description':'围绕种子采取主动行动的人物','freezeString':'','voiceProfile':{}}],'factProposals':[],'beliefProposals':[]}
 def check_base(self,p,candidate,conn):
  project=self.s.get(p,conn);base=candidate['base']
  ensure(digest(project['canon'])==base['canonHash'] and digest(project['constraints'])==base['constraintsHash'],'生成后设定或硬约束已变化，请重新生成候选','base_changed',409)
  ensure(digest({k:project.get(k) for k in ('template','compact','tone','targetDuration','episodes')})==base['settingsHash'],'生成后项目设置已变化','base_changed',409)
  if 'neighborIds' in base:
   current_target=self.s.get(candidate['targetId'],conn) if candidate.get('targetId') else None
   _,neighbors=self.scene_scope(self.nodes(p,conn),current_target)
   ensure([x['id'] for x in neighbors]==base['neighborIds'],'生成后相邻场景或顺序已变化，请重新生成','base_changed',409)
  if 'rootIds' in base:ensure(sorted(n['id'] for n in self.nodes(p,conn) if n['parentId'] is None and n['status']!='archived')==base['rootIds'],'故事方向已采纳，旧方向不能覆盖当前版本','base_changed',409)
  if 'structureRefs' in base:
   actual={n['id']:n['currentRevision'] for n in descendants(self.nodes(p,conn),candidate['targetId']) if n['status']!='archived'}
   ensure(actual==base['structureRefs'],'生成后子结构已变化，旧结构候选不能覆盖新版本','base_changed',409)
  for id,ref in base['refs'].items():
   current=self.s.get(id,conn)
   if isinstance(ref,str):actual=current['currentRevision'];expected=ref
   else:
    mode=ref['mode'];expected=ref['hash'];actual=current['currentRevision'] if mode=='revision' else digest({'contract':current['contract'],'body':current['body']}) if mode=='scene' else digest(current['contract'])
   ensure(current['status']!='archived' and actual==expected,'生成后依赖内容已变化，旧候选不能覆盖当前版本','base_changed',409,{'nodeId':id})
 def revise(self,p,node,before,op,candidate=None,conn=None):
  rid=uid('rev');node=copy.deepcopy(node);node.pop('_version',None);node['currentRevision']=rid
  Node.model_validate(node)
  self.s.put('revision',{'id':rid,'projectId':p,'nodeId':node['id'],'previous':before.get('currentRevision') if before else None,'snapshot':copy.deepcopy(node),'op':op,'candidateId':candidate,'createdAt':now()},p,conn=conn)
  return self.s.put('node',node,p,conn=conn)
 def approve_candidate_proposals(self,p,candidate_id,conn):
  """Called inside adoption's transaction, so a conflicting proposal rolls back all writes."""
  project=self.s.get(p,conn);canon=copy.deepcopy(project['canon']);patches=[x for x in self.s.list(p,'canon_patch',conn) if x['candidateId']==candidate_id and x['status']=='pending']
  if not patches:return
  for patch in patches:
   if patch['kind']!='entity':continue
   value=Entity.model_validate(patch['value']).model_dump();old=next((x for x in canon['entities'] if x['id']==value['id']),None)
   ensure(old is None or Entity.model_validate(old).model_dump()==value,'新方案试图改变已有实体，请先比较并明确处理设定冲突','canon_conflict',409,{'entityId':value['id']})
   if old is None:canon['entities'].append(value)
  ids={x['id'] for x in canon['entities']};indices=self.time_index(self.nodes(p,conn))
  def interval(value):
   for field in ('validFrom','validUntil'):
    ref=value.get(field)
    ensure(ref is None or isinstance(ref,dict) and ref.get('nodeId') in indices and ref.get('boundary','entry') in ('entry','exit'),'设定提案的时间必须引用已有场景','canon_conflict',409)
   start=self.at_time(value.get('validFrom'),indices,-1);end=self.at_time(value.get('validUntil'),indices,float('inf'))
   ensure(start<end,'设定提案的有效时段不合法','canon_conflict',409)
   return start,end
  for patch in patches:
   if patch['kind']=='entity':continue
   value=copy.deepcopy(patch['value']);field={'fact':'facts','belief':'beliefs'}[patch['kind']]
   if field=='facts':
    ensure(value.get('subject') in ids and all(isinstance(value.get(k),str) and value[k] for k in ('predicate','object')),'事实提案必须引用已知实体并有完整状态','canon_conflict',409)
    same=lambda other:other.get('subject')==value['subject'] and other.get('predicate')==value['predicate']
    conflicts=lambda other:other.get('object')!=value['object']
   else:
    ensure(value.get('holder') in ids|{'AUDIENCE'} and isinstance(value.get('truth'),bool) and isinstance(value.get('content'),str) and value['content'].strip(),'信念提案必须指定已知主体、内容和真假','canon_conflict',409)
    same=lambda other:other.get('holder')==value['holder'] and other.get('content')==value['content']
    conflicts=lambda other:other.get('truth')!=value['truth']
   start,end=interval(value)
   for old in canon[field]:
    if not same(old) or not conflicts(old):continue
    old_start,old_end=interval(old)
    ensure(max(start,old_start)>=min(end,old_end),'新设定与同一时段的既有设定冲突，请先选择采用哪一项','canon_conflict',409,{'existing':old,'proposed':value})
   if value not in canon[field]:canon[field].append(value)
  project['canon']=canon;self.s.put('project',project,p,conn=conn)
  for patch in patches:
   patch['status']='approved';self.s.put('canon_patch',patch,p,conn=conn)
   self.s.audit(p,'canon_patch_approved',[patch['id']],{'value':patch['value'],'candidateId':candidate_id,'grouped':True},conn)
 def adopt(self,p,id,approve_proposals=False):
  with self.s.transaction() as c:
   candidate=self.s.get(id,c);ensure(candidate['projectId']==p,'候选不属于项目')
   if candidate['status']=='adopted':return {'nodeIds':candidate['adoptedNodeIds'],'idempotent':True}
   ensure(candidate['status']=='proposed','该候选已拒绝');ensure(candidate['gate']['passed'],'候选未通过硬门禁，不能直接采用','gate_failed',409)
   if candidate.get('reviewRequired'):
    review=candidate.get('qualityReview',{})
    ensure(review.get('passed') and review.get('candidateHash')==digest(candidate_payload(candidate)),'当前候选需完成独立质量复核后采用','review_required',409)
   self.check_base(p,candidate,c);target=self.s.get(candidate['targetId'],c) if candidate['targetId'] else None
   if target and (candidate['phase']=='body' or candidate['op']=='split'):ensure(target['status']!='locked','目标节点已锁定，请显式解锁','locked',409)
   before=[];after=[];existing=self.nodes(p,c);phase=candidate['phase']
   if not target:ensure(not any(n['parentId'] is None and n['status']!='archived' for n in existing),'根节点已存在，请在根节点上改写','root_exists',409)
   if phase=='contracts':
    parent=target['id'] if target else None
    if candidate['op'] in ('split','interpolate'):parent=target['parentId']
    oldchildren=[n for n in existing if n['parentId']==parent and n['status']!='archived']
    if target and candidate['op'] not in ('split','interpolate'):
     toarchive=descendants(existing,target['id'])
     ensure(not any(n['status']=='locked' for n in toarchive),'展开会替换已锁定的子节点，请先解锁或创建分支','locked',409)
     for n in toarchive:before.append(copy.deepcopy(n));n['status']='archived';after.append(self.revise(p,n,before[-1],'replace_structure',id,c))
    if candidate['op']=='split':
     children=descendants(existing,target['id']);ensure(not any(x['status']=='locked' for x in children),'拆分不能归档锁定子节点','locked',409)
     for child in children:
      before.append(copy.deepcopy(child));child['status']='archived';after.append(self.revise(p,child,before[-1],'split',id,c))
     before.append(copy.deepcopy(target));target['status']='archived';after.append(self.revise(p,target,before[-1],'split',id,c))
    active=[n for n in self.nodes(p,c) if n['status']!='archived'];coverage=self.coverage(p,active);front=coverage['frontier']
    ids=[];insertionLeft=target['order'] if target and candidate['op'] in ('split','interpolate') else None;right=None
    if insertionLeft is not None:
     afterSiblings=sorted([x for x in existing if x['parentId']==parent and x['status']!='archived' and order_key(x)>order_key(target)],key=order_key)
     right=afterSiblings[0]['order'] if afterSiblings else None
    for i,item in enumerate(candidate['items']):
     level=item['level'];layers=['premise','sequence','scene','script'] if self.s.get(p,c).get('compact') else LEVELS;speculative=layers.index(level)>layers.index(front)+1
     n={'id':uid('node'),'projectId':p,'title':item['title'],'level':level,'parentId':parent,'order':fraction_between(insertionLeft,right) if insertionLeft is not None else str(i),'contract':item['contract'],'body':{},'status':'accepted','freshness':'clean','freshnessNotes':[],
        'resolution':LEVELS.index(level)+1,'speculative':speculative,'generationComplete':False,'sourceCandidateId':id,'currentRevision':'','plannedDuration':round(float((target or {}).get('plannedDuration') or (target or {}).get('body',{}).get('targetDuration') or self.s.get(p,c)['targetDuration'])/max(1,len(candidate['items'])),3)}
     after.append(self.revise(p,n,None,'adopt_contract',id,c));ids.append(n['id'])
     if insertionLeft is not None:insertionLeft=n['order']
   else:
    ensure(target is not None,'正文必须有目标节点');item=candidate['items'][0];before.append(copy.deepcopy(target));target.update(title=item['title'],contract=item['contract'],body=item['body'],status='accepted',generationComplete=True,sourceCandidateId=id)
    after.append(self.revise(p,target,before[-1],candidate['op'],id,c));ids=[target['id']]
    self.propagate(p,before[-1],after[-1],c)
   if candidate['op']=='merge' and candidate.get('otherNodeId'):
    other=self.s.get(candidate['otherNodeId'],c);related=[other]+descendants(existing,other['id']);ensure(not any(x['status']=='locked' for x in related),'合并范围有锁定节点','locked',409)
    for x in related:
     before.append(copy.deepcopy(x));x['status']='archived';after.append(self.revise(p,x,before[-1],'merge',id,c))
   if candidate['op'] in ('add_setup','add_payoff','move_reveal') and candidate.get('targetNarrativeNodeId'):
    other=self.s.get(candidate['targetNarrativeNodeId'],c);ensure(other['projectId']==p,'叙事引用跨项目')
    edge={'id':uid('edge'),'projectId':p,'from':other['id'] if candidate['op']=='add_payoff' else ids[0],'to':ids[0] if candidate['op']=='add_payoff' else other['id'],'type':'reveal_dependency' if candidate['op']=='move_reveal' else 'setup_payoff','status':'progressing','candidateId':id};self.s.put('edge',edge,p,conn=c)
   candidate.update(status='adopted',adoptedNodeIds=ids,adoptedAt=now());self.s.put('candidate',candidate,p,conn=c)
   for patch in self.s.list(p,'canon_patch',c):
    if patch['candidateId']==id and patch['status']=='provisional':patch['status']='pending';self.s.put('canon_patch',patch,p,conn=c)
   if approve_proposals:self.approve_candidate_proposals(p,id,c)
   for spike in self.s.list(p,'spike',c):
    if spike['candidateId']==id and spike.get('script'):
     project=self.s.get(p,c);project['styleExamples'].append({'candidateId':id,'text':spike['script'][:3500]});self.s.put('project',project,p,conn=c)
   frontier=self.coverage(p,self.nodes(p,c))['frontier'];layers=['premise','sequence','scene','script'] if self.s.get(p,c).get('compact') else LEVELS
   for specnode in self.nodes(p,c):
    if specnode.get('speculative') and layers.index(specnode['level'])<=layers.index(frontier):
     specnode['speculative']=False
     if specnode['freshness']!='broken':specnode['freshness']='opportunity'
     specnode['freshnessNotes'].append({'id':uid('note'),'code':'frontier_advanced','message':'整体分辨率已推进到此，复看早期探索内容。'});self.s.put('node',specnode,p,conn=c)
   self.s.audit(p,'adopt',ids,{'candidateId':id,'before':before,'after':after,'batchId':candidate['batchId']},c)
  return {'nodeIds':ids}
 def contract_conflicts(self,nodes,canon):
  """Evaluate entry/exit events, allowing later effects and time-scoped facts to override."""
  ns=flatten(nodes);indices=self.time_index(ns);state={};result={}
  events=sorted([(indices[n['id']],False,n) for n in ns]+[(indices[n['id']+':exit'],True,n) for n in ns],key=lambda item:item[0])
  for t,exiting,node in events:
   if exiting:
    state.update({(x['subject'],x['predicate']):x['object'] for x in node['contract'].get('postconditions',[])})
    continue
   active={(f['subject'],f['predicate']):f['object'] for f in canon.get('facts',[]) if self.at_time(f.get('validFrom'),indices,-1)<=t<self.at_time(f.get('validUntil'),indices,float('inf'))}
   current={**state,**active};mismatch=[]
   for pre in node['contract'].get('preconditions',[]):
    key=(pre['subject'],pre['predicate'])
    if key in current and current[key]!=pre['object']:mismatch.append({'expected':pre,'actual':current[key]})
   result[node['id']]=mismatch
  return result
 def propagate(self,p,before,after,conn):
  ns=self.nodes(p,conn);changed=not contract_equal(before['contract'],after['contract']);canon=self.s.get(p,conn)['canon']
  old_conflicts=self.contract_conflicts([before if n['id']==after['id'] else n for n in ns],canon) if changed else {}
  new_conflicts=self.contract_conflicts(ns,canon) if changed else {}
  related={e['to'] for e in self.s.list(p,'edge',conn) if e['from']==after['id'] and not e.get('archived')};descendant_ids={n['id'] for n in descendants(ns,after['id'])}
  for n in flatten(ns):
   if n['id']==after['id']:continue
   original=copy.deepcopy(n);previous=[x for x in n['freshnessNotes'] if x.get('source')==after['id'] and x.get('code')=='contract_conflict']
   mismatch=new_conflicts.get(n['id'],[])
   if changed and previous:n['freshnessNotes']=[x for x in n['freshnessNotes'] if x not in previous]
   if changed and mismatch and (mismatch!=old_conflicts.get(n['id'],[]) or previous):
    n['freshnessNotes'].append({'id':uid('note'),'source':after['id'],'code':'contract_conflict','severity':'broken','message':'上游退出状态到达本场时与进入条件冲突','evidence':mismatch})
   elif n['id'] in related or n.get('speculative') and n['id'] in descendant_ids:
    n['freshnessNotes']=[x for x in n['freshnessNotes'] if not(x.get('source')==after['id'] and x.get('code')=='context_changed')]
    n['freshnessNotes'].append({'id':uid('note'),'source':after['id'],'code':'context_changed','severity':'opportunity','message':'相关语境发生变化，建议复看；不要求重写。'})
   if n['freshnessNotes']!=original['freshnessNotes']:
    n['freshness']='broken' if any(x.get('severity')=='broken' or x.get('code')=='contract_conflict' for x in n['freshnessNotes']) else 'opportunity' if n['freshnessNotes'] else 'clean'
    self.s.put('node',n,p,conn=conn)
 def reject(self,p,id,reason):
  ensure(reason.strip(),'请选择或填写拒绝理由')
  with self.s.transaction() as c:
   candidate=self.s.get(id,c);ensure(candidate['projectId']==p and candidate['status']!='adopted','已采用的候选请使用撤销');candidate.update(status='rejected',rejectReason=reason);self.s.put('candidate',candidate,p,conn=c)
   project=self.s.get(p,c);project['negativeList'].append({'strategy':candidate['strategy'],'summary':candidate['summary'],'reason':reason});self.s.put('project',project,p,conn=c);self.s.audit(p,'reject',[candidate['targetId']],{'candidateId':id,'reason':reason},c)
  if hasattr(self,'experiences'):
   self.experiences.record(p,{'text':reason,'source':'candidate_rejection','explicit':True,'anchor':{'type':'candidate','id':id},'operationId':'reject:'+id})
  return {'ok':True}
 def structural(self,p,data):
  op=data['op'];id=data['nodeId'];node=self.s.get(id);ensure(node['projectId']==p,'节点不属于项目');ns=self.nodes(p)
  if op in ('delete','reorder','unlock'):
   plan=self.plan(p,data);ensure(data.get('planHash')==plan['planHash'],'请预览并确认最新影响范围','plan_required',409,plan)
  with self.s.transaction() as c:
   node=self.s.get(id,c);before=copy.deepcopy(node);extraBefore=[];extraAfter=[]
   ensure(op in ('lock','unlock','delete','reorder','dismiss'),'不支持的结构操作')
   if op not in ('unlock','dismiss'):ensure(node['status']!='locked','节点已锁定，请先解锁','locked',409)
   if op=='lock':node['status']='locked'
   elif op=='unlock':node['status']='accepted'
   elif op=='delete':
    ensure(node['parentId'] is not None,'根节点不能删除，保持端到端草稿；可以改写或创建新项目')
    ds=descendants(ns,id);ensure(not any(x['status']=='locked' for x in ds),'子树含锁定节点','locked',409)
    for d in ds:
     old=copy.deepcopy(d);d['status']='archived';extraBefore.append(old);extraAfter.append(self.revise(p,d,old,'delete',conn=c))
    node['status']='archived'
   elif op=='reorder':
    sib=sorted([n for n in ns if n['parentId']==node['parentId'] and n['status']!='archived' and n['id']!=id],key=order_key)
    idx=max(0,min(len(sib),int(data.get('index',0))));node['order']=fraction_between(sib[idx-1]['order'] if idx>0 else None,sib[idx]['order'] if idx<len(sib) else None)
    node['freshness']='opportunity';node['freshnessNotes'].append({'id':uid('note'),'code':'reordered','message':'顺序已更改，请重新执行连续性检查。'})
   else:
    noteid=data.get('noteId');node['freshnessNotes']=[x for x in node['freshnessNotes'] if x['id']!=noteid] if noteid else []
    node['freshness']='broken' if any(x.get('code')=='contract_conflict' for x in node['freshnessNotes']) else 'opportunity' if node['freshnessNotes'] else 'clean'
    project=self.s.get(p,c);project['negativeList'].append({'reason':data.get('reason','用户确认不是问题'),'nodeId':id});self.s.put('project',project,p,conn=c)
   result=self.revise(p,node,before,op,conn=c);self.s.audit(p,op,[id],{'before':[before]+extraBefore,'after':[result]+extraAfter,'reason':data.get('reason','')},c)
  return result
 def revisions(self,p,id):return [x for x in self.s.list(p,'revision') if x['nodeId']==id]
 def restore(self,p,id,revision):
  with self.s.transaction() as c:
   node=self.s.get(id,c);ensure(node['status']!='locked','先解锁后回滚','locked',409);rev=self.s.get(revision,c);ensure(rev['nodeId']==id and rev['projectId']==p,'版本不属于节点')
   old=copy.deepcopy(node);out=self.revise(p,rev['snapshot'],old,'restore',conn=c);self.propagate(p,old,out,c);self.s.audit(p,'restore',[id],{'before':[old],'after':[out],'restoredRevision':revision},c)
  return out
 def update_canon(self,p,data):
  canon=copy.deepcopy(data['canon'])
  ids=[]
  for e in canon.get('entities',[]):Entity.model_validate(e);ids.append(e['id'])
  ensure(len(ids)==len(set(ids)),'Canon 实体 ID 重复')
  for f in canon.get('facts',[]):
   ensure(f['subject'] in ids,'事实引用未知实体');ensure(all(k in f for k in ('predicate','object')),'事实字段缺失')
  for b in canon.get('beliefs',[]):ensure(b.get('holder') in ids+['AUDIENCE'] and isinstance(b.get('truth'),bool),'信念必须引用合法主体并显式包含 truth 布尔值')
  indices=self.time_index(self.nodes(p))
  for item in canon.get('facts',[])+canon.get('beliefs',[]):
   for field in ('validFrom','validUntil'):
    ref=item.get(field)
    if ref:
     ensure(isinstance(ref,dict) and ref.get('nodeId') in indices and ref.get('boundary','entry') in ('entry','exit'),'时间索引必须引用本项目节点的 entry/exit')
   ensure(self.at_time(item.get('validFrom'),indices,-1)<self.at_time(item.get('validUntil'),indices,float('inf')),'事实/信念的时间区间必须从前到后')
  with self.s.transaction() as c:
   project=self.s.get(p,c);old=copy.deepcopy(project['canon']);project['canon']=canon;self.s.put('project',project,p,expected=data.get('_version'),conn=c)
   self.s.audit(p,'canon_update',ids,{'beforeCanon':old,'afterCanon':canon},c)
  return canon
 def patch(self,p,id,approve):
  with self.s.transaction() as c:
   patch=self.s.get(id,c);ensure(patch['projectId']==p and patch['status']=='pending','补丁不在待审批状态');project=self.s.get(p,c)
   if approve:
    field={'entity':'entities','fact':'facts','belief':'beliefs'}[patch['kind']];value=patch['value'];current=project['canon'][field]
    if field=='entities':Entity.model_validate(value);current[:]=[e for e in current if e['id']!=value['id']]
    if value not in current:current.append(value)
    self.s.put('project',project,p,conn=c)
   patch['status']='approved' if approve else 'rejected';self.s.put('canon_patch',patch,p,conn=c);self.s.audit(p,'canon_patch_'+patch['status'],[id],{'value':patch['value']},c)
  return patch
 def readthrough(self,p):
  ns=flatten(self.nodes(p));by={n['id']:n for n in ns};out=[]
  names={e['id']:e['name'] for e in self.s.get(p)['canon']['entities']}
  def visit(n):
   children=[x for x in ns if x['parentId']==n['id'] and not x['speculative']]
   if children and all(x.get('generationComplete') or x['contract'].get('summary') for x in children):
    for child in children:visit(child)
   else:
    b=n['body'];text=b.get('synopsis') or b.get('action') or b.get('summary') or n['contract']['summary']
    if b.get('blocks'):
     text='\n\n'.join((names.get(block.get('speakerId',block.get('character')),block.get('speakerId',block.get('character','')))+'：' if block.get('type')=='dialogue' else '')+str(block.get('text','')) for block in b['blocks'])
    else:
     dialogue=b.get('dialogue',[]);text+='\n\n'+'\n'.join(names.get(d.get('character'),d.get('character',''))+'：'+str(d.get('text','')) for d in dialogue) if dialogue else ''
    out.append({'id':n['id'],'title':n['title'],'level':n['level'],'text':text,'freshness':n['freshness'],'rough':not n['generationComplete'],'duration':b.get('targetDuration',0)})
  for root in [n for n in ns if n['parentId'] is None]:visit(root)
  if not out:out=[{'id':p,'title':'尚未采纳的故事种子','text':self.s.get(p)['seed'],'level':'seed','rough':True,'freshness':'clean','duration':0}]
  return out
 def add_edge(self,p,data):
  types=('causes','setup_payoff','character_arc','reveal_dependency','contrast');ensure(data['type'] in types,'叙事边类型无效')
  a=self.s.get(data['from']);b=self.s.get(data['to']);ensure(a['projectId']==p and b['projectId']==p,'边端点必须属于项目')
  ensure(a['id']!=b['id'] or data.get('fromBlockId')!=data.get('toBlockId'),'同一个叙事单位不能引用自身')
  for end,n in (('from',a),('to',b)):
   block_id=data.get(end+'BlockId')
   if block_id:
    beat=next((x for x in n['body'].get('beats',[]) if x.get('id')==block_id),None);ensure(beat is not None,'引用的场内节拍不存在')
    address=n['id']+'#'+block_id
    self.s.put('addressable_block',{'id':address,'projectId':p,'nodeId':n['id'],'blockId':block_id,'content':beat,'sourceRevision':n['currentRevision']},p)
    data[end+'Anchor']=address
  edge={**data,'id':uid('edge'),'projectId':p,'status':data.get('status','open')};self.s.put('edge',edge,p);self.s.audit(p,'edge_add',[a['id'],b['id']],{'edge':edge});return edge
 def time_index(self,nodes):
  out={};active=[n for n in nodes if n['status']!='archived'];clock=0
  def walk(parent):
   nonlocal clock
   for n in sorted([x for x in active if x.get('parentId')==parent],key=order_key):
    out[n['id']]=clock;clock+=1;walk(n['id']);out[n['id']+':exit']=clock;clock+=1
  walk(None);return out
 def at_time(self,ref,indices,default):
  if not ref:return default
  if isinstance(ref,str):return indices.get(ref,default)
  return indices.get(ref.get('nodeId','')+(':exit' if ref.get('boundary')=='exit' else ''),default)
 def knowledge(self,p):
  project=self.s.get(p);nodes=flatten(self.nodes(p));idx=self.time_index(nodes);canon=project['canon'];holders=['AUDIENCE']+[e['id'] for e in canon['entities'] if e['kind']=='character'];content=list(dict.fromkeys(b['content'] for b in canon['beliefs']))
  rows=[]
  for n in [x for x in nodes if x['level']=='scene']:
   t=idx[n['id']];matrix={h:{} for h in holders}
   for b in canon['beliefs']:
    if b['holder'] in matrix and self.at_time(b.get('validFrom'),idx,-1)<=t<self.at_time(b.get('validUntil'),idx,float('inf')):matrix[b['holder']][b['content']]='knows' if b['truth'] else 'false_belief'
   counts={'suspense':0,'surprise':0,'mystery':0}
   for h in holders[1:]:
    for info in content:
     audience=matrix['AUDIENCE'].get(info)=='knows';char=matrix[h].get(info)=='knows'
     if audience and not char:counts['suspense']+=1
     elif char and not audience:counts['mystery']+=1
     elif not char and not audience:counts['surprise']+=1
   rows.append({'sceneId':n['id'],'title':n['title'],'matrix':matrix,'tension':counts})
  return {'holders':holders,'information':content,'rows':rows}
 def scan(self,p,semantic=False,check=lambda:None):
  ns=flatten(self.nodes(p));project=self.s.get(p);idx=self.time_index(ns);issues=[];state={};canon=project['canon'];facts=canon['facts']
  events=sorted([(idx[n['id']],False,n) for n in ns]+[(idx[n['id']+':exit'],True,n) for n in ns],key=lambda e:e[0])
  for t,exiting,n in events:
   check()
   if exiting:
    for post in n['contract'].get('postconditions',[]):state[post['subject'],post['predicate']]=post['object']
    continue
   active={}
   for f in facts:
    if self.at_time(f.get('validFrom'),idx,-1)<=t<self.at_time(f.get('validUntil'),idx,float('inf')):
     key=(f['subject'],f['predicate'])
     if key in active and active[key]!=f['object']:issues.append({'nodeId':n['id'],'severity':'broken','code':'overlapping_fact','message':'同一时段有冲突的事实','evidence':[list(key),active[key],f['object']]})
     active[key]=f['object']
   merged={**state,**active}
   for pre in n['contract'].get('preconditions',[]):
    k=(pre['subject'],pre['predicate'])
    if k in merged and merged[k]!=pre['object']:issues.append({'nodeId':n['id'],'severity':'broken','code':'contract_conflict','message':'进入条件与已知状态不符','evidence':{'expected':pre,'actual':merged[k]}})
  for edge in self.s.list(p,'edge'):
   if edge['type']=='setup_payoff' and edge.get('status') not in ('paid',):issues.append({'nodeId':edge['from'],'severity':'opportunity','code':'open_setup','message':'伏笔尚未标记回收','edgeId':edge['id']})
  duration=sum(float(x.get('duration') or 0) for x in self.readthrough(p));target=project['targetDuration']*project['episodes']
  if project.get('timingMode')!='content' and duration and abs(duration-target)>target*.2:issues.append({'nodeId':p,'severity':'opportunity','code':'length_budget','message':f'当前估计 {duration:.1f}s，目标 {target:.1f}s'})
  if semantic:
   result=self.llm.json(p,'validator','只读剧本一致性审计。输出 JSON {"issues":[{"nodeId":"","severity":"opportunity","code":"semantic","message":"具体问题","evidence":"原句证据"}]}。不要改写，不把明确的错误信念当成事实冲突。',{'scenes':[{k:v for k,v in scene.items() if k!='freshness'} for scene in self.readthrough(p)],'canon':canon},demo={'issues':[]},cache=True,check=check)
   issues+=result.get('issues',[])
  with self.s.transaction() as c:
   for issue in issues:
    node=self.s.get(issue['nodeId'],c,False)
    if node and node.get('level'):
     note={'id':uid('note'),**issue};node['freshnessNotes']=[x for x in node['freshnessNotes'] if not(x.get('code')==issue['code'] and x.get('message')==issue['message'])]+[note]
     if issue['severity']=='broken' or node['freshness']!='broken':node['freshness']=issue['severity']
     self.s.put('node',node,p,conn=c)
   self.s.audit(p,'continuity_scan',[],{'issues':issues},c)
  return {'issues':issues,'deterministic':True,'semantic':semantic}
 def probe(self,p,batch_id,progress=lambda *_:None,check=lambda:None):
  batch=self.s.get(batch_id);ensure(batch['projectId']==p,'批次不属于项目');spec=batch['probeSpec'];ensure(not re.search(r'第\s*\d+\s*场',spec['sceneSelector']),'探针选择器必须是功能性的')
  candidates=[x for x in self.s.list(p,'candidate') if x['batchId']==batch_id and x.get('visible')];ensure(candidates,'没有可比较的候选')
  outputs=[]
  for i,c in enumerate(candidates):
   check();demo={'resolved':True,'script':'INT. 门口 - 夜\n\n'+c['summary']+'\n\n主角把钥匙放回口袋，没有开门。\n\n主角\n“我不是来问你的。我是来看看，你还会不会说同一句话。”',
     'horizontal':[{'summary':'主动行动产生后果','newCharacters':False,'passive':False,'conflictSource':f'压力-{j}','lockedConflict':False} for j in range(4)]}
   out=self.llm.json(p,'script','你执行 Comparable Probe。必须按功能选择器找一场具体戏，不能挑最炫高潮替代。JSON {resolved:boolean,reason:string,script:string,horizontal:[{summary,newCharacters:boolean,passive:boolean,conflictSource:string,lockedConflict:boolean}]}。纵向给一场含对白完整戏，横向恰好4场，只做机器检查。探针不建立正式事实。',
    {'spec':spec,'candidate':c['items'],'context':self.context(p,c['targetId'],'probe')},demo=demo,check=check)
   h=out.get('horizontal',[]);complete=len(h)==4 and bool(out.get('resolved'));flags=[{'label':'可定位代表场景','ok':bool(out.get('resolved'))},{'label':'不用新角色续命','ok':complete and not any(x.get('newCharacters') for x in h)},
      {'label':'主角保持主动','ok':complete and not any(all(y.get('passive') for y in h[j:j+3]) for j in range(max(0,len(h)-2)))},
      {'label':'不冲突已锁定结构','ok':complete and not any(x.get('lockedConflict') for x in h)},{'label':'冲突源有变化','ok':complete and len({x.get('conflictSource') for x in h})>1}]
   spike={'id':uid('spike'),'projectId':p,'batchId':batch_id,'candidateId':c['id'],'spec':spec,'script':out.get('script',''),'horizontal':h,'signals':flags,'reason':out.get('reason',''),'nonCanonical':True,'createdAt':now()};self.s.put('spike',spike,p)
   if spec.get('renderTo')=='keyframe':
    from .probe_media import render_probe
    spike.update(render_probe(self,p,spike,check));self.s.put('spike',spike,p)
   outputs.append({k:v for k,v in spike.items() if k!='horizontal'});progress((i+1)/len(candidates),'探针 '+str(i+1)+'/'+str(len(candidates)))
  self.s.audit(p,'probe',[],{'batchId':batch_id,'spikeIds':[s['id'] for s in outputs]});return outputs
 def branch(self,p,title):
  old=self.s.get(p);np=copy.deepcopy(old);np['id']=uid('a');np['title']=title or old['title']+' · 分支';np['branchOf']=p;np['createdAt']=now();np.pop('_version',None)
  nodes=self.nodes(p);mapping={n['id']:uid('node') for n in nodes}
  def remap(v):
   if isinstance(v,dict):return {k:remap(x) for k,x in v.items()}
   if isinstance(v,list):return [remap(x) for x in v]
   if isinstance(v,str):return mapping.get(v,v)
   return v
  np['canon']=remap(np['canon']);base={n['id']:n['currentRevision'] for n in nodes}
  with self.s.transaction() as c:
   self.s.put('project',np,np['id'],conn=c)
   for n in nodes:
    nn=remap(clean(n));nn['projectId']=np['id'];nn['sourceNodeId']=n['id'];self.revise(np['id'],nn,None,'branch',conn=c)
   for edge in self.s.list(p,'edge',c):
    edge=remap(clean(edge));edge['id']=uid('edge');edge['projectId']=np['id'];self.s.put('edge',edge,np['id'],conn=c)
   b={'id':uid('branch'),'projectId':p,'branchProjectId':np['id'],'title':np['title'],'base':base,'baseCanonHash':digest(old['canon']),'status':'active','createdAt':now()};self.s.put('branch',b,p,conn=c);self.s.audit(p,'branch',[],b,c)
  return b
 def compare_branch(self,p,id):
  b=self.s.get(id);ensure(b['projectId']==p,'分支不属于项目');main=self.readthrough(p);other=self.readthrough(b['branchProjectId'])
  text=lambda rows:'\n'.join(x['title']+'\n'+x['text'] for x in rows)
  return {'main':main,'branch':other,'diff':'\n'.join(difflib.unified_diff(text(main).splitlines(),text(other).splitlines(),fromfile='当前主线',tofile=b['title'],lineterm=''))}
 def adopt_branch(self,p,id,abandon=False):
  with self.s.transaction() as c:
   b=self.s.get(id,c);ensure(b['projectId']==p and b['status']=='active','分支不可采用')
   if abandon:b['status']='abandoned';self.s.put('branch',b,p,conn=c);self.s.audit(p,'branch_abandon',[id],{},c);return b
   current=self.nodes(p,c);project=self.s.get(p,c);ensure(digest(project['canon'])==b['baseCanonHash'],'主线 Canon 已变化，先在分支中协调再采用','base_changed',409)
   for n in current:ensure(n['currentRevision']==b['base'].get(n['id']),'主线已发生变化，禁止覆盖；请比较后局部采用','base_changed',409)
   branch_nodes=self.nodes(b['branchProjectId'],c);mapping={n['id']:n.get('sourceNodeId') or uid('node') for n in branch_nodes}
   def remap(v):
    if isinstance(v,dict):return {k:remap(x) for k,x in v.items()}
    if isinstance(v,list):return [remap(x) for x in v]
    return mapping.get(v,v) if isinstance(v,str) else v
   for n in branch_nodes:
    original=next((x for x in current if x['id']==n.get('sourceNodeId')),None)
    if original and original['status']=='locked':ensure(contract_equal(original['contract'],n['contract']) and original['body']==n['body'],'分支修改了主线锁定节点，须先仲裁','locked',409)
    nn=remap(clean(n));nn['projectId']=p;nn.pop('sourceNodeId',None);self.revise(p,nn,original,'branch_adopt',conn=c)
   for existing_edge in self.s.list(p,'edge',c):
    existing_edge['status']='orphan';existing_edge['archived']=True;self.s.put('edge',existing_edge,p,conn=c)
   for branch_edge in self.s.list(b['branchProjectId'],'edge',c):
    copied=remap(clean(branch_edge));copied['id']=uid('edge');copied['projectId']=p;self.s.put('edge',copied,p,conn=c)
   bp=self.s.get(b['branchProjectId'],c);project['canon']=remap(bp['canon']);self.s.put('project',project,p,conn=c)
   b['status']='adopted';self.s.put('branch',b,p,conn=c);self.s.audit(p,'branch_adopt',[id],{'branchProjectId':b['branchProjectId']},c)
  return b
 def metrics(self,p):
  ops=sorted(self.s.history(p),key=lambda x:x['seq']);cs=self.s.list(p,'candidate');adopted=[c for c in cs if c['status']=='adopted'];rates={}
  for horizon in (5,20):
   eligible=survivors=0
   for c in adopted:
    position=next((i for i,o in enumerate(ops) if o.get('candidateId')==c['id'] and o['op']=='adopt'),None)
    if position is None or len(ops)-position-1<horizon:continue
    eligible+=1;ids=set(c['adoptedNodeIds']);later=ops[position+1:position+1+horizon]
    def reverted(o):
     if not ids.intersection(o.get('scope',[])):return False
     if o['op']=='adopt':
      candidate=next((x for x in cs if x['id']==o.get('candidateId')),None)
      return bool(candidate and candidate.get('op') not in ('fill','expand','deepen','interpolate'))
     return o['op'] in ('delete','restore','undo','branch_adopt')
    if not any(reverted(o) for o in later):survivors+=1
   rates['survival'+str(horizon)]={'eligible':eligible,'survivors':survivors,'rate':round(survivors/eligible,3) if eligible else None}
  locks=[o for o in ops if o['op']=='lock'];after_downstream=0
  for lock in locks:
   targets=set(lock.get('scope',[]));subids={n['id'] for t in targets for n in descendants(self.nodes(p),t)}
   if any(o['seq']<lock['seq'] and o['op']=='adopt' and subids.intersection(o.get('scope',[])) for o in ops):after_downstream+=1
  first_after_reads=[]
  for i,o in enumerate(ops):
   if o['op']=='readthrough':
    next_op=next((x for x in ops[i+1:] if x['op'] not in ('readthrough','export','continuity_scan')),None)
    if next_op:first_after_reads.append({'readSeq':o['seq'],'op':next_op['op'],'scope':next_op.get('scope',[])})
  runs=self.s.list(p,'run');return {'adopted':len(adopted),'generated':len(cs),'rejected':sum(c['status']=='rejected' for c in cs),'acceptanceRate':len(adopted)/max(1,len(cs)),**rates,'undo':sum(o['op'] in ('restore','undo') for o in ops),'lock':sum(o['op']=='lock' for o in ops),'vary':sum(o['op']=='vary' for o in ops),'cost':sum(r.get('cost',0) for r in runs),'operations':len(ops),'lockAfterDownstream':after_downstream,'defensiveLocks':len(locks)-after_downstream,'readthroughFollowups':first_after_reads,'costKnown':all(r.get('costKnown',False) for r in runs)}
 def export(self,p,format):
  if format in ('script-package','scene-export') and getattr(self,'formats',None) and self.s.get(p).get('activeScriptVersionId'):
   return json.dumps(self.formats.export_package(p),ensure_ascii=False,indent=2),'application/json','.json'
  project=self.s.get(p);rows=self.readthrough(p);ns=flatten(self.nodes(p))
  if format not in ('scene-export','story-source','json') and project.get('activeScriptVersionId'):
   adopted=self.s.get(project['activeScriptVersionId']);doc=adopted['payload']
   project={**project,'canon':{**project['canon'],'entities':[{'id':identifier,**entity} for identifier,entity in doc['continuity']['entities'].items()]}}
   from .story_contract import readable_scene
   ns=[{'id':scene['id'],'title':scene.get('title','场次'),'level':'scene','generationComplete':True,'body':{'blocks':scene['blocks']}} for scene in doc['scenes']]
   rows=[{'id':scene['id'],'title':scene.get('title','场次'),'text':readable_scene(scene,doc['continuity']['entities'])} for scene in doc['scenes']]
  if format in ('scene-export','story-source'):
   scenes=[];edges=[clean(e) for e in self.s.list(p,'edge') if not e.get('archived')];canon=project['canon']
   motifs=[m for observation in self.s.list(p,'observation') for m in observation.get('motifs',[])]
   for order,n in enumerate(x for x in ns if x['level']=='scene'):
    script=next((x for x in ns if x['level']=='script' and x['parentId']==n['id'] and x.get('generationComplete')),None);body=self.scene_body(ns,n);local=self.canon_slice(p,ns,n)
    slice={'characters':[e for e in local['entities'] if e['kind']=='character'],'location':[e for e in local['entities'] if e['kind']=='location'],'props':[e for e in local['entities'] if e['kind']=='prop'],'rules':[e for e in local['entities'] if e['kind'] in ('rule','faction')],'facts':local['facts'],'beliefs':local['beliefs']}
    scene_ids={n['id']}|{x['id'] for x in descendants(ns,n['id'])};refs={e['id'] for e in local['entities']}
    belongs=lambda item,field:isinstance(item.get(field),dict) and item[field].get('nodeId') in scene_ids
    narrative={'entryState':n['contract']['preconditions'],'exitState':n['contract']['postconditions'],'reveals':n['contract']['reveals'],
     'knowledgeAtEntry':local['beliefs'],'factsAtEntry':local['facts'],
     'knowledgeDelta':[b for b in canon.get('beliefs',[]) if b.get('holder') in refs|{'AUDIENCE'} and belongs(b,'validFrom')],
     'knowledgeExpirations':[b for b in canon.get('beliefs',[]) if b.get('holder') in refs|{'AUDIENCE'} and belongs(b,'validUntil')],
     'factsDelta':[f for f in canon.get('facts',[]) if f.get('subject') in refs and (belongs(f,'validFrom') or belongs(f,'validUntil'))],
     'setups':[e for e in edges if e['type']=='setup_payoff' and e['from'] in scene_ids],'payoffs':[e for e in edges if e['type']=='setup_payoff' and e['to'] in scene_ids]}
    revisions={'scene':n['currentRevision'],'script':script['currentRevision'] if script else None};directives={'tone':project['tone'],'targetDuration':body.get('targetDuration',n.get('plannedDuration',20))}
    scene={'sceneId':n['id'],'order':order,'revision':digest(revisions),'sourceRevisions':revisions,'contractHash':digest(n['contract']),'bodyHash':digest(body),'canonHash':digest(slice),'contract':n['contract'],'body':body,'canonSlice':slice,'narrativeContext':narrative,'directives':directives,'tensionType':body.get('tensionType','mystery'),'visualMotifs':motifs}
    scene['narrativeHash']=digest(narrative);scene['directivesHash']=digest({k:scene[k] for k in ('directives','tensionType','visualMotifs')})
    scene['semanticHash']=digest({k:scene[k] for k in ('contractHash','bodyHash','canonHash','narrativeHash','directivesHash','order')});scenes.append(scene)
   from .interchange import scene_export
   return json.dumps(scene_export(self,project,scenes),ensure_ascii=False,indent=2),'application/json','.json'
  if format=='json':return json.dumps(self.get(p),ensure_ascii=False,indent=2),'application/json','.json'
  if format in ('fdx','fountain'):
   root=ET.Element('FinalDraft',{'DocumentType':'Script','Template':'No','Version':'1'});content=ET.SubElement(root,'Content');lines=['Title: '+project['title'],''];names={e['id']:e['name'] for e in project['canon']['entities']}
   def emit(kind,text):
    if not text:return
    para=ET.SubElement(content,'Paragraph',{'Type':kind});ET.SubElement(para,'Text').text=str(text)
    if kind=='Scene Heading':lines.extend(['.'+str(text),''])
    elif kind=='Character':lines.append('@'+str(text))
    elif kind=='Parenthetical':lines.append('('+str(text).strip('()')+')')
    else:lines.extend([str(text),''])
   for row in rows:
    node=next((x for x in ns if x['id']==row['id']),None);body=node['body'] if node else {}
    if not any(block.get('type')=='scene_heading' for block in body.get('blocks',[])):emit('Scene Heading',body.get('sceneHeading') or row['title'])
    if body.get('blocks'):
     for block in body['blocks']:
      if block.get('type')=='dialogue':emit('Character',names.get(block.get('speakerId',block.get('character')),block.get('speakerId',block.get('character',''))));emit('Parenthetical',block.get('parenthetical',''));emit('Dialogue',block.get('text',''))
      else:emit({'scene_heading':'Scene Heading','parenthetical':'Parenthetical','transition':'Transition'}.get(block.get('type'),'Action'),block.get('text',''))
    elif body.get('dialogue'):
     emit('Action',body.get('action',''))
     for d in body['dialogue']:
      emit('Character',names.get(d.get('character'),d.get('character','')));emit('Parenthetical',d.get('parenthetical',''));emit('Dialogue',d.get('text',''))
    else:emit('Action',row['text'])
   if format=='fdx':return ET.tostring(root,encoding='unicode',xml_declaration=True),'application/xml','.fdx'
   return '\n'.join(lines),'text/plain','.fountain'
  text='Title: '+project['title']+'\n\n' if format=='fountain' else '# '+project['title']+'\n\n'
  for row in rows:text+=('.' if format=='fountain' else '## ')+row['title']+'\n\n'+row['text']+'\n\n'
  return text,'text/plain','.fountain' if format=='fountain' else '.md'
