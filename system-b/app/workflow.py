"""Small, deterministic proposal orchestration and dependency snapshots.

Creative choices remain proposals. Advancing performs at most one model task;
there is no autonomous accept/regenerate loop and media is never auto-submitted.
"""
from .core import digest,ensure,DomainError
from .cinema import shot_count


class ProposalWorkflow:
 def proposal_read_set(self,p,stage,sceneid=None,conn=None):
  project=self.s.get(p,conn);scenes=self.list_active(p,'scene',conn)
  targets=[s for s in scenes if not sceneid or s['id']==sceneid]
  ids={s['id'] for s in targets};assetids={a for s in targets for a in [*s.get('characters',[]),*s.get('props',[]),s.get('locationId')] if a}
  masters=self.list_active(p,'master',conn)
  if stage not in ('B0','B1','B2'):masters=[a for a in masters if a['id'] in assetids]
  assetids={a['id'] for a in masters}
  def fingerprint(rows):
   return {r['id']:digest({k:v for k,v in r.items() if k not in ('_version','freshnessNotes','createdAt')}) for r in rows}
  project_input={k:project.get(k) for k in ('constraints','sourceType')}
  if stage in ('B0','B1'):project_input.update(source=project.get('source'),targetDuration=project.get('targetDuration'))
  if stage!='B0':project_input['curves']=[c for c in project.get('curves',[]) if c.get('sceneId') in ids]
  result={'project':digest(project_input),'style':fingerprint([self.s.get(project['styleId'],conn)]),'scenes':fingerprint(targets),'masters':fingerprint(masters)}
  if stage in ('B3','B4'):
   result['sceneOrder']=[s['id'] for s in sorted(scenes,key=lambda x:x['order'])]
   result['variants']=fingerprint([v for v in self.list_active(p,'variant',conn) if v['masterId'] in assetids])
   result['states']=fingerprint([a for a in self.list_active(p,'asset_state',conn) if a['assetId'] in assetids])
   result['transitions']=fingerprint([t for t in self.list_active(p,'transition',conn) if t['fromScene'] in ids or t['toScene'] in ids])
   result['foreshadows']=fingerprint([f for f in self.list_active(p,'foreshadow',conn) if f.get('setupSceneId',f.get('setupScene')) in ids or f.get('payoffSceneId',f.get('payoffScene')) in ids])
  if stage=='B4':
   result['directions']=fingerprint([d for d in self.list_active(p,'direction',conn) if d['sceneId'] in ids])
   localshots=[s for s in self.list_active(p,'shot',conn) if s['sceneId'] in ids];shotids={s['id'] for s in localshots};result['shots']=fingerprint(localshots)
   result['links']=fingerprint([l for l in self.list_active(p,'link',conn) if l['from'] in shotids or l['to'] in shotids])
  return result

 def proposal_current(self,p,proposal,conn=None):
  readset=proposal.get('base',{}).get('readSet')
  return bool(readset is not None and readset==self.proposal_read_set(p,proposal['stage'],proposal.get('sceneId'),conn))

 def timing_attention(self,p,scene,direction=None):
  if scene.get('targetDuration') is None:return {'state':'ready','stage':'B1','sceneId':None,'action':'propose','label':'按剧本内容估算场次节奏','reason':'场次已拆分，接下来由 AI 根据对白、动作与情绪停顿提出时长方案。'}
  style=self.style(p);durations=[('场次',scene['targetDuration'])]
  if direction and direction.get('freshness')!='broken' and direction.get('status') in ('accepted','locked'):durations.append(('导演方案',direction['targetDuration']))
  for source,value in durations:
   try:shot_count(float(value),style)
   except DomainError as error:
    if error.code!='infeasible_schedule':raise
    interval=error.details['feasibleDuration'];reason=f"本场{source}目标 {float(value):g} 秒与当前风格不兼容；可行区间为 {interval[0]:g}–{interval[1]:g} 秒。请在 B1 调整节奏曲线或风格，再继续导演与分镜。"
    return {'state':'needs_attention','stage':'B1','sceneId':scene['id'],'action':'review_timing','label':'调整本场时长或风格','reason':reason,'targetDuration':value,'feasibleDuration':interval,'timingSource':'scene' if source=='场次' else 'direction'}
  return None

 def next_step(self,p,sceneid=None):
  if self.s.get(p).get('workflowVersion',1)>=2:return self.next_creative_step(p,sceneid)
  project=self.s.get(p);scenes=sorted(self.list_active(p,'scene'),key=lambda s:s['order'])
  if sceneid:ensure(any(s['id']==sceneid for s in scenes),'场次不属于项目')
  proposals=self.s.list(p,'proposal');readsets={}
  def current(q):
   key=(q['stage'],q.get('sceneId'))
   if key not in readsets:readsets[key]=self.proposal_read_set(p,*key)
   return q.get('base',{}).get('readSet')==readsets[key]
  pending=[q for q in proposals if q['status']=='proposed' and (not sceneid or not q.get('sceneId') or q['sceneId']==sceneid) and current(q)]
  if pending:
   q=pending[-1]
   if q['stage'] in ('B3','B4') and q.get('sceneId'):
    local=self.s.get(q['sceneId']);direction=next((d for d in self.list_active(p,'direction') if d['sceneId']==local['id']),None);timing=self.timing_attention(p,local,direction)
    if timing:return timing
   return {'state':'awaiting_choice','stage':q['stage'],'sceneId':q.get('sceneId'),'action':'choose_proposal','label':'选择创作候选','reason':'已有基于当前内容的候选，请先选择、调整或拒绝。','proposalIds':[x['id'] for x in pending]}
  def step(state,stage,reason,action='propose',scene=None,**extra):
   return {'state':state,'stage':stage,'sceneId':scene,'action':action,'label':reason,'reason':reason,**extra}
  latest={}
  for q in proposals:
   if not sceneid or not q.get('sceneId') or q['sceneId']==sceneid:latest[(q['stage'],q.get('sceneId'))]=q
  relevant=[q for q in proposals if q is latest.get((q['stage'],q.get('sceneId'))) and current(q)]
  if relevant and relevant[-1]['status']=='rejected':
   q=relevant[-1]
   if q['stage'] in ('B3','B4') and q.get('sceneId'):
    local=self.s.get(q['sceneId']);direction=next((d for d in self.list_active(p,'direction') if d['sceneId']==local['id']),None);timing=self.timing_attention(p,local,direction)
    if timing:return timing
   return step('ready',q['stage'],'根据你拒绝时的反馈改进候选',scene=q.get('sceneId'),shotIds=q.get('base',{}).get('shotIds',[]),rejectedProposalId=q['id'])
  if not scenes:
   return step('ready','B0','整理剧本与场次') if project.get('source','').strip() else step('needs_attention','B0','先输入或导入剧本','edit_source')
  if self.style(p)['status']!='locked':return step('needs_attention','B1','选择并确认全片视觉风格','finalize_style')
  if not project.get('curves'):return step('ready','B1','设计改编与场次节奏')
  targets=[s for s in scenes if not sceneid or s['id']==sceneid]
  for scene in targets:
   sid=scene['id']
   direction=next((d for d in self.list_active(p,'direction') if d['sceneId']==sid),None);timing=self.timing_attention(p,scene,direction)
   if timing:return timing
   if any(isinstance(v,dict) and v.get('needed') and not v.get('decision') for v in scene.get('narrativeHandling',{}).values()):return step('needs_attention','B0','选择本场内心、概述等内容的呈现方式','scene_decisions',sid)
   if not scene.get('assetsPlanned') and not (scene.get('characters') or scene.get('locationId') or scene.get('props')):return step('ready','B2','提取本场可复用视觉资产',scene=sid)
   required=set(scene.get('characters',[])+scene.get('props',[])+([scene['locationId']] if scene.get('locationId') else []))
   unlocked=[a['id'] for a in self.list_active(p,'master') if a['id'] in required and a['status']!='locked']
   if unlocked:return step('needs_attention','B2','确认本场角色、场景和道具身份','finalize_assets',sid,assetIds=unlocked)
   if not direction or direction['freshness']=='broken' or direction['status'] not in ('accepted','locked'):
    if direction and direction['status']=='locked':return step('needs_attention','B3','已锁定导演方案需要你处理上游变更','review_direction',sid)
    return step('ready','B3','设计本场信息、情绪与调度',scene=sid)
   shots=[s for s in self.list_active(p,'shot') if s['sceneId']==sid]
   if not shots or any(s['freshness']=='broken' for s in shots):
    if any(s['freshness']=='broken' and s['status']=='locked' for s in shots):return step('needs_attention','B4','已锁定分镜需要你处理上游变更','review_shots',sid)
    return step('ready','B4','生成或修复本场分镜候选',scene=sid,shotIds=[s['id'] for s in shots if s['freshness']=='broken'])
  return step('complete','B4','当前范围的分镜已就绪，可以局部精修或选做关键帧','review_storyboard',sceneid)

 def advance(self,p,data,progress=lambda *_:None,check=lambda:None):
  if self.s.get(p).get('workflowVersion',1)>=2:return self.advance_creative(p,data,progress,check)
  step=self.next_step(p,data.get('sceneId'))
  if step['state']!='ready':return {'nextStep':step,'advanced':False}
  params={**data,'sceneId':step.get('sceneId')}
  if step.get('shotIds'):params['shotIds']=step['shotIds']
  proposal=self.propose(p,step['stage'],params,progress,check)
  return {'proposal':proposal,'advanced':True,'nextStep':self.next_step(p,data.get('sceneId'))}
