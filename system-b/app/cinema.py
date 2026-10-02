"""Pure-code directing math, continuity constraints and prompt compilation."""
from __future__ import annotations
import copy,math,re
from .core import ensure,DomainError,digest,canonical
from studio.directing_methods import execution_cues

PRESETS={
 'cinema':{'name':'电影感','aslRange':[5,8],'shotCountRange':[8,15],'emptyShotRatio':[.15,.2],'aspectRatio':'2.39:1','shotSizePreference':['LS','MS'],'movementAmplitude':'克制、慢推、固定','informationInterval':[15,30],'hookInterval':0},
 'series':{'name':'剧集','aslRange':[3,5],'shotCountRange':[6,10],'emptyShotRatio':[.05,.1],'aspectRatio':'16:9','shotSizePreference':['MS','MCU'],'movementAmplitude':'中等','informationInterval':[8,15],'hookInterval':0},
 'vertical':{'name':'快节奏短剧','aslRange':[1.5,2.5],'shotCountRange':[4,8],'emptyShotRatio':[0,.03],'aspectRatio':'9:16','shotSizePreference':['MCU','CU'],'movementAmplitude':'按信息、人物行动和空间需要选择；允许固定机位','informationInterval':[3,5],'hookInterval':30}}
SIZES=['ELS','LS','MS','MCU','CU','ECU']
PROFILE={
 'id':'generic-cinematic','version':'1.0','name':'通用电影语言','imageSize':'1024x1024','seedField':'seed',
 'capabilities':{'referenceImage':False,'firstFrame':False,'lastFrame':False,'extension':False,'referenceVideo':False,'audio':False},
 'shotSize':{'ELS':'extreme wide shot','LS':'wide shot','MS':'medium shot','MCU':'medium close-up','CU':'close-up','ECU':'extreme close-up'},
 'angle':{'eye':'eye level','low':'low angle','high':'high angle','overhead':'top down','pov':'POV','shoulder':'over the shoulder'},
 'movement':{'static':'locked-off camera','push':'slow dolly in','pull':'dolly out','pan':'pan','tilt':'tilt','track':'tracking','handheld':'handheld','orbit':'orbit'},
 'prefix':'','negativeSuffix':'','extra':{}}
COMPILER_VERSION='2.1.0'

def ratio(value):
 a,b=value.split(':');return float(a)/float(b)
def render_dimensions(aspect,quality='proxy'):
 r=ratio(aspect);long=640 if quality=='proxy' else 1280
 return (long,int(long/r)//2*2) if r>=1 else (int(long*r)//2*2,long)
def shot_count(duration,style):
 ensure(math.isfinite(duration) and duration>0,'先在改编与节奏阶段确认本场时长','timing_required',409)
 if style.get('shotCountMode')=='content':return max(1,round(duration/(sum(style['aslRange'])/2)))
 lo=max(style['shotCountRange'][0],math.ceil(duration/style['aslRange'][1]));hi=min(style['shotCountRange'][1],math.floor(duration/style['aslRange'][0]))
 ensure(lo<=hi,'场景时长与 ASL / 镜头数区间无交集；请调整节奏曲线或风格参数','infeasible_schedule',409,{'duration':duration,'style':style['name'],'feasibleDuration':[style['shotCountRange'][0]*style['aslRange'][0],style['shotCountRange'][1]*style['aslRange'][1]]})
 return max(lo,min(hi,round(duration/(sum(style['aslRange'])/2))))
def allocate_durations(total,weights):
 ensure(weights and total>0,'镜头分配参数无效');weights=[max(.25,min(4,float(w))) for w in weights];raw=[total*w/sum(weights) for w in weights];result=[round(x,3) for x in raw];result[-1]=round(total-sum(result[:-1]),3);return result

def resolve_manifest(scene,assets,variants,states,scenes):
 idx={s['id']:i for i,s in enumerate(sorted(scenes,key=lambda x:x['order']))};index=idx[scene['id']];resolved=[];missing=[];risky=[]
 required=list(dict.fromkeys(scene.get('characters',[])+scene.get('props',[])+([scene['locationId']] if scene.get('locationId') else [])))
 for aid in required:
  asset=next((a for a in assets if a['id']==aid),None)
  if not asset:missing.append({'assetId':aid,'reason':'缺少主资产'});continue
  active=[s for s in states if s['assetId']==aid and idx.get(s['validFrom'],10**9)<=index<idx.get(s.get('validUntil'),float('inf'))]
  if len(active)>1:missing.append({'assetId':aid,'reason':'资产状态区间重叠'});continue
  vid=active[0]['variantId'] if active else asset.get('defaultVariantId')
  variant=next((v for v in variants if v['id']==vid),None)
  if not variant:missing.append({'assetId':aid,'reason':'缺少可用变体'});continue
  media=variant.get('referenceFileId') or asset.get('referenceFileId')
  if variant.get('requiresImage',False) and not media:missing.append({'assetId':aid,'variantId':vid,'reason':'该变体需要独立参考图'})
  resolved.append({'assetId':aid,'variantId':vid,'variantVersion':variant.get('_version',1),'referenceFileId':media,'freezeString':asset['freezeString'],'deltaString':variant.get('deltaString',''),'seed':asset['seed'],'kind':asset['kind'],'reason':'时间轴状态' if active else '默认变体'})
 chars=[r for r in resolved if r['kind']=='character']
 if len(chars)>3:risky.append({'code':'many_subjects','message':'同框超过 3 人，身份混淆风险较高'})
 return {'sceneId':scene['id'],'resolved':resolved,'missing':missing,'risky':risky}

def producibility(skeleton):
 text=skeleton['actionLine'];count=len(skeleton.get('subjects',[]));hands=bool(re.search(r'手指|捏|穿针|握|手部',text));hastext=bool(re.search(r'文字|铭牌|字幕|手机屏幕',text));fast=skeleton.get('movement',{}).get('speed')=='fast' or bool(re.search(r'奔跑|打斗|快速',text));talk=bool(re.search(r'说|喊|嘴|对话',text))
 score=min(1,max(0,(count-1)*.13)+hands*.2+hastext*.2+fast*.23+talk*.16)
 return {'subjectCount':count,'hasHands':hands,'hasText':hastext,'fastMotion':fast,'lipSync':talk,'score':round(score,2),'recommendation':'考虑 frame_chain / extension 或保守机位' if score>.5 else ''}

def complete_shots(skeletons,direction,scene,manifest,style):
 from .core import uid
 durations=allocate_durations(direction['targetDuration'],[1/max(.25,float(s.get('emotionWeight',1))) for s in skeletons]);out=[]
 positions=direction.get('blocking',{}).get('positions',{});axis=direction.get('blocking',{}).get('axisGroup') or 'axis_'+scene['id']
 for i,s in enumerate(skeletons):
  subjects=s['subjects'] if 'subjects' in s else ([] if s.get('isEmpty') else scene.get('characters',[]));side=s.get('cameraSide','positive');sign=-1 if side=='negative' else 1
  screen={};eyeline={}
  for j,aid in enumerate(subjects):
   x=float(positions.get(aid,{}).get('x',(-1 if j%2==0 else 1)));screen[aid]=max(-1,min(1,x*sign));eyeline[aid]='right' if x*sign<0 else 'left'
  chosen=[r['variantId'] for r in manifest['resolved'] if r['assetId'] in subjects or r['kind'] in ('location','prop')]
  out.append({'id':uid('shot'),'projectId':scene['projectId'],'sceneId':scene['id'],'order':i,'informationPayload':s.get('informationPayload',[]),'shotSize':s['shotSize'],'angle':s.get('angle','eye'),'lens':s.get('lens',50),
   'movement':s.get('movement',{'type':'static','speed':'slow','startFraming':'','endFraming':''}),'duration':durations[i],'subjects':subjects,'assetVariants':chosen,'lighting':copy.deepcopy(direction['lighting']),
   'continuity':{'axisGroup':axis,'cameraSide':side,'eyeline':eyeline,'screenPosition':screen,'explicitCrossing':s.get('explicitCrossing',False),'linkToPrev':'cut'},'actionLine':s['actionLine'],'isEmpty':s.get('isEmpty',False),'producibilityRisk':producibility(s),
   'status':'draft','freshness':'clean','freshnessNotes':[],'contractHash':'','bodyHash':'','canonHash':'','directionVersion':direction.get('_version',1),'styleVersion':style.get('_version',1),'framing':s.get('framing',{})})
 for s,source in zip(out,skeletons):
  for field in ('performanceBeats','cameraCue','cutPoint'):
   if field in source:s[field]=copy.deepcopy(source[field])
  s['contractHash']=digest({k:v for k,v in s.items() if k not in ('contractHash','bodyHash','canonHash')});s['bodyHash']=digest(s['actionLine']);s['canonHash']=digest(manifest['resolved'])
 return out

def validate_shots(shots,direction,style,transitions=None,foreshadows=None,variants=None):
 issues=[];shots=sorted(shots,key=lambda x:x['order']);n=len(shots)
 def issue(code,message,ids,severity='error'):issues.append({'code':code,'message':message,'shotIds':ids,'severity':severity})
 if style.get('shotCountMode')!='content' and not style['shotCountRange'][0]<=n<=style['shotCountRange'][1]:issue('shot_count','镜头数不在风格区间',[s['id'] for s in shots])
 total=sum(s['duration'] for s in shots)
 if abs(total-direction['targetDuration'])>.08:issue('duration','时长合计与场景预算不符',[])
 empty=sum(s.get('isEmpty',False) for s in shots)/max(1,n)
 if empty>style['emptyShotRatio'][1]+1/max(1,n):issue('empty_ratio','空镜比例超标',[], 'warning')
 for i,s in enumerate(shots):
  if s['lighting']!=direction['lighting']:issue('light_jump','镜头光位不继承场景方案',[s['id']])
  if i and shots[i-1]['continuity']['axisGroup']==s['continuity']['axisGroup']:
   prev=shots[i-1];a=prev['continuity'];b=s['continuity']
   if a.get('cameraSide')!=b.get('cameraSide') and 'axis' not in (a.get('cameraSide'),b.get('cameraSide')) and not b.get('explicitCrossing'):issue('axis_cross','同轴线组发生未经声明的越轴',[prev['id'],s['id']])
   for who,pos in b.get('screenPosition',{}).items():
    if who in a.get('screenPosition',{}) and a['screenPosition'][who]*pos<0 and not b.get('explicitCrossing'):issue('screen_flip','人物屏幕左右位置跳变',[prev['id'],s['id']])
  gaze=s['continuity'].get('eyeline',{});position=s['continuity'].get('screenPosition',{})
  if len(s.get('subjects',[]))>=2:
   left=[who for who,x in position.items() if x<0];right=[who for who,x in position.items() if x>0]
   if left and right and not s['continuity'].get('intentionalGazeBreak'):
    for who in left:
     if gaze.get(who) not in ('right','forward',None):issue('eyeline_mismatch','左侧角色视线没有与对手匹配',[s['id']])
    for who in right:
     if gaze.get(who) not in ('left','forward',None):issue('eyeline_mismatch','右侧角色视线没有与对手匹配',[s['id']])
  if i>=2 and all(x['shotSize']==s['shotSize'] for x in shots[i-2:i]):issue('same_size','连续三个镜头景别相同',[x['id'] for x in shots[i-2:i+1]],'warning')
  if not s['informationPayload'] and not s.get('isEmpty'):issue('no_information','镜头没有显式信息任务',[s['id']],'warning')
  if s.get('producibilityRisk',{}).get('score',0)>.5:issue('generation_risk','生成风险较高，建议调整衔接或设计',[s['id']],'warning')
 for t in transitions or []:
  isfrom=t['fromScene']==direction.get('sceneId');isto=t['toScene']==direction.get('sceneId')
  if not (isfrom or isto) or not shots:continue
  target=shots[-1] if isfrom else shots[0];req=t.get('requirement',{}).get('fromShotSpec' if isfrom else 'toShotSpec',{})
  if isinstance(req,dict):
   for field,val in req.items():
    if field in ('shotSize','angle') and target.get(field)!=val:issue('transition_constraint','转场两侧镜头未满足约束：'+field,[target['id']])
  elif req:issue('transition_manual','此转场仍有自然语言约束，须人工确认：'+req,[target['id']],'warning')
 variant_index={v['id']:v for v in variants or []}
 for f in foreshadows or []:
  asset=f.get('assetId') or variant_index.get(f.get('variantId'),{}).get('masterId')
  relevant=[s for s in shots if any(variant_index.get(vid,{}).get('masterId')==asset for vid in s['assetVariants'])] if asset and variant_index else [s for s in shots if f.get('variantId') in s['assetVariants']]
  for phase,field in (('setup','setupSceneId'),('payoff','payoffSceneId')):
   if f.get(field,f.get('setupScene' if phase=='setup' else 'payoffScene'))!=direction.get('sceneId'):continue
   delivery=f.get(phase+'Delivery',{})
   channel=delivery.get('channel') if isinstance(delivery,dict) else None
   if channel=='visual' and not relevant:
    issue(phase+'_identity_missing','采用的视觉交付要求缺少同一道具身份；不同状态可以使用不同变体',[])
   elif channel in ('sound','dialogue','action'):
    issue(phase+'_delivery_review','按采用稿核对声音、对白或行动中的伏笔交付；不要求强制物件特写',[], 'warning')
   elif not relevant:
    issue(phase+'_delivery_unknown','旧伏笔记录缺少交付方式，请结合采用剧本核对，不能据此强制补图',[], 'warning')
 return {'passed':not any(i['severity']=='error' for i in issues),'issues':issues,'totalDuration':round(total,3),'actualASL':round(total/max(1,n),3),'count':n}

def compile_prompt(shot,manifest,style,profile=None,kind=None):
 """No LLM. freezeString is inserted verbatim, never rewritten or normalized."""
 profile=profile or PROFILE;selected=[x for x in manifest['resolved'] if x['variantId'] in shot['assetVariants']]
 if kind=='keyframe':selected=[x for x in selected if x.get('role')!='end_state']
 size=profile.get('shotSize',PROFILE['shotSize']).get(shot['shotSize'],shot['shotSize']);angle=profile.get('angle',PROFILE['angle']).get(shot['angle'],shot['angle']);move=profile.get('movement',PROFILE['movement']).get(shot['movement']['type'],shot['movement']['type'])
 parts=[style.get('promptPrefix',''),profile.get('prefix',''),f"{size}, {angle}, {shot['lens']}mm lens"]
 for x in selected:
  parts.append((f"Reference role: {x.get('referenceRole',x['role'])}; state: {x.get('phase','before')}. " if x.get('role') else '')+x['freezeString'])
  if x.get('controls'):parts.append('This reference controls only: '+', '.join(x['controls'])+'.')
  if x.get('excludeInheritance'):parts.append('Do not inherit from this reference: '+', '.join(x['excludeInheritance'])+'.')
  if x.get('deltaString'):parts.append(x['deltaString'])
 visual_parts=list(parts)
 tail=[shot.get('dialogueText',''),shot.get('soundCue',''),f"key light at {shot['lighting']['keyDirection']} degrees, ratio {shot['lighting']['ratio']}:1, motivated by {shot['lighting']['motivation']}",style.get('palette',''),style.get('texture','')]
 parts += [shot['actionLine'],*tail]
 negative=', '.join(x for x in (style.get('negativePrompt',''),profile.get('negativeSuffix','')) if x)
 image='\n'.join(x for x in parts if x);video=image+'\n'+f"{move}; speed {shot['movement'].get('speed','slow')}; {shot['duration']} seconds. Start: {shot['movement'].get('startFraming','')}. End: {shot['movement'].get('endFraming','')}."
 cues=execution_cues(shot)
 if cues['performanceBeats']:
  action='Performance progression:\n'+'\n'.join(str(i+1)+'. '+('When '+beat['trigger']+': ' if beat.get('trigger') else '')+beat['action']+(' End condition: '+beat['endCue'] if beat.get('endCue') else '') for i,beat in enumerate(cues['performanceBeats']))
  video='\n'.join(x for x in [*visual_parts,action,*tail] if x)+'\n'+f"{move}; speed {shot['movement'].get('speed','slow')}; {shot['duration']} seconds. Start: {shot['movement'].get('startFraming','')}. End: {shot['movement'].get('endFraming','')}."
 for key,label in (('start','Camera starts when'),('follow','Camera follows'),('end','Camera stops when')):
  if cues['cameraCue'].get(key):video+='\n'+label+': '+cues['cameraCue'][key]
 if cues['cutCue']:video+='\nEnd this shot at: '+cues['cutCue']
 if shot.get('eventId'):
  start=[{'entity':x.get('entityId'),'identity':x['freezeString'],'state':x.get('claims',{}),'controlsOnly':x.get('controls',[]),'doNotInherit':x.get('excludeInheritance',[])} for x in selected if x.get('role')!='end_state']
  image='\n'.join([style.get('promptPrefix',''),f"{size}, {angle}, {shot['lens']}mm lens",'Opening still at the declared '+shot.get('eventPhase','before')+' phase. Preserve these visible states exactly; do not substitute the other event phase:',canonical(start),shot['movement'].get('startFraming',''),f"key light at {shot['lighting']['keyDirection']} degrees, motivated by {shot['lighting']['motivation']}",style.get('palette',''),style.get('texture','')])
 return {'imagePrompt':image,'videoPrompt':video,'negativePrompt':negative,'compilerVersion':COMPILER_VERSION,'cueCompilerVersion':1 if any(cues.values()) else 0,'referenceFileIds':[r['referenceFileId'] for r in selected if r.get('referenceFileId')],'seed':next((r['seed'] for r in selected if r['kind']=='character'),next((r['seed'] for r in selected),0))}

def shot_design(shot):
 """Content that changes a shot, independent of record identity and review state."""
 ignored={'id','projectId','sceneId','order','_version','freshness','freshnessNotes','status','pinned','contractHash','bodyHash','canonHash','directionVersion','styleVersion','reviewRequired','reviewNotes'}
 return {k:v for k,v in shot.items() if k not in ignored}

def render_key(shot,variants,style,profile,seed,quality='proxy',kind='keyframe',references=None,compiled=None):
 # Scope prevents a cached local artifact from escaping another project's media
 # directory. Shot/asset record IDs and review versions do not define pixels.
 refs=[]
 for ref in references or []:
  role='keyframe' if 'keyframe' in ref else 'upstream' if 'upstream' in ref else 'asset'
  refs.append({'role':role,**{k:ref[k] for k in ('sha256','type','adoptionHash') if k in ref}})
 if compiled:
  effective={'prompt':compiled['imagePrompt' if kind=='keyframe' else 'videoPrompt'],'negativePrompt':compiled['negativePrompt']}
 else:
  effective={'shot':shot_design(shot),'variants':variants,'style':{k:v for k,v in style.items() if k not in ('id','projectId','_version','status','freshness','freshnessNotes')}}
 return digest({'scope':shot.get('projectId'),'effectiveInputs':effective,'references':refs,'dimensions':render_dimensions(style['aspectRatio'],quality),
  'rendererProfile':{**profile,'quality':quality,'kind':kind},'promptCompilerVersion':COMPILER_VERSION,'seed':seed})

def strong_order(shots,links):
 ids={s['id'] for s in shots};parents={i:set() for i in ids};children={i:set() for i in ids}
 for link in links:
  if link['type'] in ('frame_chain','extension','ref_video') and link['from'] in ids and link['to'] in ids:parents[link['to']].add(link['from']);children[link['from']].add(link['to'])
 ready=sorted(i for i in ids if not parents[i]);result=[]
 while ready:
  i=ready.pop(0);result.append(i)
  for j in children[i]:
   parents[j].discard(i)
   if not parents[j]:ready.append(j)
 ensure(len(result)==len(ids),'镜间强依赖存在环','dependency_cycle',409);return result
