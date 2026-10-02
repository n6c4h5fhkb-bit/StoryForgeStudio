import copy, hashlib
from pathlib import Path
from unittest.mock import Mock
import pytest
from PIL import Image
from app.core import DomainError, digest
from app.story_contract import normalize_document, replay, visible, location_of, state_value, validate_shot_coverage
from test_common import studio
from app.shooting import canonical_reference_ids, canonical_shot_groups


def test_asset_alias_references_resolve_only_explicit_unique_mapping():
    original={'id':'shot-one','references':[{'entityId':'asset-box','role':'start_state','phase':'before'}]}
    result=canonical_reference_ids(original,{'box':{}},{'box':'asset-box'})
    assert result['references']==[{'entityId':'box','role':'start_state','phase':'before'}]
    assert original['references'][0]['entityId']=='asset-box'
    assert result['referenceIdMappings']==[{'fromAssetId':'asset-box','entityId':'box'}]
    with pytest.raises(DomainError) as error:
        canonical_reference_ids(original,{'box':{},'other':{}},{'box':'asset-box','other':'asset-box'})
    assert error.value.code=='reference_entity'
    with pytest.raises(DomainError) as error:
        canonical_reference_ids(original,{'box':{}},{'box':'different-asset'})
    assert error.value.details['entityId']=='asset-box'


def test_director_accepts_asset_aliases_without_another_model_generation(studio):
    b,p,_=modern(studio)
    original=b.llm.json;calls=[]
    def generate(project,role,system,context,*args,**kwargs):
        result=original(project,role,system,context,*args,**kwargs)
        if role=='shots':
            calls.append(role)
            for shot in result['shots']:
                entity=context['events'][0]['participants'][0]
                shot['references']=[{'entityId':context['assetMap'][entity],'role':'identity','phase':'before'}]
        return result
    b.llm.json=generate
    proposal=b.advance(p,{})['proposal']
    assert proposal['passed'],proposal['issues']
    assert calls==['shots']
    assert all(s['references'][0]['entityId']=='alice' for s in proposal['payload']['shots'])


def test_director_identical_retry_keeps_context_and_uses_cached_model_results(studio):
    b,p,_=modern(studio);original=b.llm.json;contexts=[]
    def generate(project,role,system,context,*args,**kwargs):
        if role=='shots':contexts.append(copy.deepcopy(context))
        return original(project,role,system,context,*args,**kwargs)
    b.llm.json=generate
    first=b.advance(p,{})['proposal']
    assert first['passed']
    # An interrupted/rejected proposal can request the same inputs again; UUIDs
    # created solely for the shape example must not cause another inference.
    b.s.put('proposal',{**first,'status':'rejected'},p)
    previous_runs=len(b.s.list(p,'run'))
    second=b.propose_director(p,{'sceneId':first['sceneId']})
    assert second['passed'] and contexts[0]==contexts[1]
    assert all(r['cacheHit'] for r in b.s.list(p,'run')[previous_runs:])
    assert 'contractHash' not in contexts[0]['shapeExample']['shots'][0]


def test_director_draft_groups_reference_stable_ids_before_review(studio):
    b,p,_=modern(studio);original=b.llm.json;reviewed=[]
    def generate(project,role,system,context,*args,**kwargs):
        if role=='reviewer':reviewed.append(copy.deepcopy(context['candidate']))
        result=original(project,role,system,context,*args,**kwargs)
        if role=='shots':
            for index,shot in enumerate(result['shots']):shot['id']='shot_'+str(index+1)
            result['direction']['coverage']['shotGroups']=[{'shotIds':[s['id'] for s in result['shots']]}]
        return result
    b.llm.json=generate;proposal=b.advance(p,{})['proposal']
    assert proposal['passed'],proposal['issues']
    candidate=proposal['payload']
    expected=[s['id'] for s in candidate['shots']]
    assert candidate['direction']['coverage']['shotGroups'][0]['shotIds']==expected
    assert reviewed[-1]['direction']==candidate['direction']
    assert [s['draftShotId'] for s in candidate['shots']]==['shot_1','shot_2','shot_3']


def test_shot_groups_reject_unknown_labels_without_guessing():
    direction={'coverage':{'shotGroups':[{'shotIds':['missing']} ]}}
    with pytest.raises(DomainError) as error:canonical_shot_groups(direction,{'draft':'stable'},{'stable'})
    assert error.value.code=='shot_reference'
    assert direction['coverage']['shotGroups'][0]['shotIds']==['missing']


@pytest.mark.parametrize('numeric_change',[False,True])
def test_scene_lighting_inheritance_preserves_prose_but_rejects_physical_change(studio,numeric_change):
    b,p,_=modern(studio);original=b.llm.json
    def generate(project,role,system,context,*args,**kwargs):
        result=original(project,role,system,context,*args,**kwargs)
        if role=='shots':
            result['shots'][0]['lighting']['motivation']='同一光源在手部保留层次'
            if numeric_change:result['shots'][0]['lighting']['keyDirection']+=90
        return result
    b.llm.json=generate;proposal=b.advance(p,{})['proposal']
    assert proposal['passed'] is (not numeric_change)
    if not numeric_change:
        shot=proposal['payload']['shots'][0]
        assert shot['lighting']==proposal['payload']['direction']['lighting']
        assert shot['lightingDetail']=='同一光源在手部保留层次'


def box_story():
    entities={
        'room':{'kind':'location','name':'仓库','identity':'砖墙仓库','visualStateKeys':[]},
        'alice':{'kind':'character','name':'阿青','identity':'短发女子','visualStateKeys':['wardrobe']},
        'bob':{'kind':'character','name':'老林','identity':'白发男子','visualStateKeys':['wardrobe','injury']},
        'box':{'kind':'prop','name':'木盒','identity':'黑漆方盒','visualStateKeys':['lid','@contents']},
        'token':{'kind':'prop','name':'玉牌','identity':'裂纹白玉牌','visualStateKeys':[]}}
    state={'room':{},'alice':{'pos':{'rel':'at','target':'room'},'wardrobe':'灰衣','canSpeak':True},'bob':{'pos':{'rel':'at','target':'room'},'wardrobe':'黑衣','injury':'无伤','canSpeak':True},'box':{'pos':{'rel':'at','target':'room'},'lid':'closed','contentsKnown':True},'token':{'pos':{'rel':'inside','target':'box'},'visibleTo':['AUDIENCE'],'active':True,'consumed':False}}
    events=[]
    for id,action,changes in [('open','阿青打开木盒',[{'entityId':'box','field':'lid','from':'closed','to':'open'}]),('take','阿青拿起玉牌',[{'entityId':'token','field':'pos','from':{'rel':'inside','target':'box'},'to':{'rel':'held_by','target':'alice'}}]),('give','阿青把玉牌交给老林',[{'entityId':'token','field':'pos','from':{'rel':'held_by','target':'alice'},'to':{'rel':'held_by','target':'bob'}}])]:
        events.append({'id':id,'sceneId':'s1','locationId':'room','participants':['alice','bob','box','token'],'action':action,'changes':changes,'dialogueIds':['d1'] if id=='give' else [],'origin':'adapted'})
    return normalize_document({'scenes':[{'id':'s1','title':'交接','blocks':[{'id':'a1','type':'action','text':'阿青开盒取玉，交给老林。'},{'id':'d1','type':'dialogue','speakerId':'alice','text':'别弄丢。'}]}],'continuity':{'status':'declared','entities':entities,'initialState':state,'events':events}})


def modern(studio, source=None):
    b=studio.state.service;p=b.create({'title':'协议回归','source':source or '夜，阿青推开仓库门。','workflowVersion':2})['project']['id']
    if source is None:
        pr=b.s.get(p);doc=box_story();pr['storySource']=doc;b.s.put('project',pr,p)
        demo=copy.deepcopy(doc);demo.update(title='拍摄版',mode='fast_drama',sourceMapping=[{'sourceId':v['id'],'targetIds':[v['id']],'reason':'保留'} for s in doc['scenes'] for v in s['blocks']],storyChanges=[])
        original=b.llm.json
        def generated(project,role,system,context,*args,**kwargs):
            if role=='treatment':return copy.deepcopy(demo)
            return original(project,role,system,context,*args,**kwargs)
        b.llm.json=generated
    q=b.propose_shooting(p,{})
    assert q['passed'],q['issues']
    b.adopt_shooting(p,q['id'])
    return b,p,q


def test_modes_keep_separate_versions_and_original(studio):
    b,p,q=modern(studio,'同一故事的原稿。')
    original=copy.deepcopy(b.source_document(p))
    film=b.propose_shooting(p,{'mode':'cinema'})
    assert film['passed'] and film['id']!=q['id']
    assert b.active_shooting(p)['id']==q['id']
    b.adopt_shooting(p,film['id'])
    assert b.source_document(p)==original
    b.adopt_shooting(p,q['id'])
    assert b.active_shooting(p)['mode']=='fast_drama'


@pytest.mark.parametrize('params,expected',[
    ({'mode':'until_choice'},'fast_drama'),({'mode':'single'},'fast_drama'),
    ({'advanceMode':'until_choice'},'fast_drama'),
    ({'advanceMode':'single','presentationMode':'cinema'},'cinema'),({'mode':'series'},'series')])
def test_new_project_advance_separates_workflow_mode_from_presentation(studio,params,expected):
    b=studio.state.service;p=b.create({'title':'首次自动推进','source':'雨夜，阿青推开仓库门。','workflowVersion':2})['project']['id']
    result=b.advance(p,params)
    assert result['advanced'] and result['shootingScript']['passed']
    assert result['shootingScript']['mode']==expected
    assert result['nextStep']['action']=='choose_shooting'
    assert not b.list_active(p,'shot') and not b.active_shooting(p)


def test_advance_prepares_assets_and_stops_for_director_choice(studio):
    b,p,q=modern(studio)
    out=b.advance(p,{'mode':'until_choice'})
    assert out['proposal']['passed'],out['proposal']['issues']
    assert out['nextStep']['state']=='awaiting_choice'
    assert not b.list_active(p,'shot')
    b.adopt_proposal(p,out['proposal']['id'])
    assert b.next_step(p)['state']=='complete'
    shots=b.list_active(p,'shot');assert len(shots)==3
    assert b.validate_scene(p,shots[0]['sceneId'])['passed']
    assert sum(len(s['dialogueIds']) for s in shots)==1


def test_generic_save_cannot_bypass_review_of_modern_proposal(studio):
    b,p,q=modern(studio);proposal=b.advance(p,{})['proposal'];tampered=copy.deepcopy(proposal)
    tampered['payload']['shots'][0]['duration']=999
    with pytest.raises(DomainError,match='重新复核'):b.save(p,'proposal',tampered)
    assert b.s.get(proposal['id'])['payload']==proposal['payload']
    tampered.pop('id');tampered['workflowVersion']=1
    with pytest.raises(DomainError,match='重新复核'):b.save(p,'proposal',tampered)


def test_real_treatment_cannot_be_approved_by_demo_reviewer(studio):
    b=studio.state.service;p=b.create({'source':'阿青打开木盒。','workflowVersion':2})['project']['id']
    studio.state.settings.save({'models':{'treatment':{'provider':'openai','model':'writer','baseUrl':'https://writer.invalid/v1','priceConfigured':True},'validator':{'provider':'demo'}}})
    with pytest.raises(DomainError,match='独立复核模型'):b.propose_shooting(p,{})
    assert not b.s.list(p,'run')


def test_replay_box_transfer_hidden_and_unknown():
    doc=box_story();frames=replay(doc['continuity']);entities=doc['continuity']['entities']
    assert not visible(frames['open']['before'],entities,'token')
    assert visible(frames['open']['after'],entities,'token')
    assert state_value(frames['take']['after'],'box','@contents')==[]
    assert frames['give']['after']['token']['pos']=={'rel':'held_by','target':'bob'}
    unknown=copy.deepcopy(frames['take']['after']);unknown['box']['contentsKnown']=False
    assert state_value(unknown,'box','@contents')=={'unknown':True}
    unknown['token']['visibleTo']=[];assert not visible(unknown,entities,'token')


def test_cannot_take_from_closed_box_or_remote_holder():
    doc=box_story();doc['continuity']['events']=doc['continuity']['events'][1:]
    with pytest.raises(DomainError,match='打开容器'):replay(doc['continuity'])
    doc=box_story();doc['continuity']['entities']['away']={'kind':'location'};doc['continuity']['initialState']['away']={};doc['continuity']['initialState']['bob']['pos']['target']='away'
    with pytest.raises(DomainError,match='同一地点'):replay(doc['continuity'])


def test_contained_object_moves_with_holder_and_costume_injury_changes():
    doc=box_story();continuity=doc['continuity'];continuity['entities']['away']={'kind':'location'};continuity['initialState']['away']={}
    continuity['events'].append({'id':'leave','sceneId':'s1','locationId':'room','participants':['bob','token'],'origin':'adapted','changes':[{'entityId':'bob','field':'pos','from':{'rel':'at','target':'room'},'to':{'rel':'at','target':'away'}},{'entityId':'bob','field':'wardrobe','from':'黑衣','to':'白衣'},{'entityId':'bob','field':'injury','from':'无伤','to':'手背划伤'}]})
    frame=replay(continuity)['leave']['after']
    assert location_of(frame,continuity['entities'],'token')=='away'
    assert frame['bob']['injury']=='手背划伤' and frame['bob']['wardrobe']=='白衣'


def test_preview_is_declared_and_does_not_mutate_story_state():
    doc=box_story();doc['presentationPlan'].insert(0,{'id':'preview','eventId':'give','kind':'preview','reason':'闪回式预演，随后回切开盒前','phase':'after','dialogueIds':[]})
    result=normalize_document(doc);assert replay(result['continuity'])['open']['before']['box']['lid']=='closed'
    doc['presentationPlan'][0]['kind']='main'
    with pytest.raises(DomainError,match='乱序'):normalize_document(doc)


def test_shot_order_and_dialogue_coverage(studio):
    b,p,q=modern(studio);proposal=b.advance(p,{})['proposal'];b.adopt_proposal(p,proposal['id']);shots=b.list_active(p,'shot')
    for i,s in enumerate(reversed(shots)):s['order']=i
    with pytest.raises(DomainError,match='呈现顺序'):validate_shot_coverage(shots,q['payload'],'s1')
    doc=box_story();doc['presentationPlan'][0]['dialogueIds']=['d1']
    with pytest.raises(DomainError,match='对白'):normalize_document(doc)


def test_story_change_and_removed_dialogue_mapping_block_adoption(studio):
    b,p,q=modern(studio,'保留身份和结局的原稿。');other=b.propose_shooting(p,{'mode':'cinema'})
    other['payload']['storyChanges']=[{'reason':'改变了人物身份'}];b.s.put('shooting_script',other,p)
    with pytest.raises(DomainError,match='故事新版本'):b.adopt_shooting(p,other['id'])


def test_request_reuses_proposal_and_independent_review(studio):
    b,p,q=modern(studio,'有限文本');other=b.propose_shooting(p,{'mode':'cinema'})
    count=len(b.s.list(p,'run'));same=b.propose_shooting(p,{'mode':'cinema'})
    assert same['id']==other['id'] and len(b.s.list(p,'run'))==count
    assert other['attempts'][0]['reviewId']


def test_actual_reference_checks_file_and_identity_and_partial_missing(studio,tmp_path):
    b,p,q=modern(studio);proposal=b.advance(p,{})['proposal'];b.adopt_proposal(p,proposal['id']);shot=b.list_active(p,'shot')[0]
    refs=b.event_manifest(p,shot)['resolved'];assert 'token' not in {r['entityId'] for r in refs}
    for index,r in enumerate(refs):
        folder=b.s.root/'media'/p;folder.mkdir(parents=True,exist_ok=True);path=folder/f'{index}.png';Image.new('RGB',(16,16),'blue').save(path);file=b.register_file(p,path)
        b.review_reference(p,r['variantId'],{'fileId':file['id'],'confirmed':True,'evidence':'实际查看图中主体、衣服、盒盖，状态符合','roles':b.s.get(r['variantId'])['roles']})
    assert not b.event_manifest(p,shot)['missing']
    assert b.event_manifest(p,b.list_active(p,'shot')[-1])['missing']
    f=b.s.get(b.s.get(refs[0]['variantId'])['referenceFileId']);Image.new('RGB',(16,16),'red').save(f['path'])
    assert b.event_manifest(p,shot)['missing']


def test_legacy_import_creates_completion_proposal_without_overwrite(studio):
    b,p,q=modern(studio,'原制作内容');before=b.list_active(p,'scene')
    b.import_scene_export(p,{'format':'SceneExport-v1','scenes':[{'sceneId':'new','body':{'action':'新来稿'},'contract':{'summary':'新场'}}]})
    assert b.list_active(p,'scene')==before
    assert b.next_step(p)['action']=='propose_shooting'


def provide_references(b,p):
    folder=b.s.root/'media'/p;folder.mkdir(parents=True,exist_ok=True)
    for index,variant in enumerate(b.list_active(p,'variant')):
        path=folder/f'ref-{index}.png';Image.new('RGB',(64,64),(index*12%256,40,80)).save(path);file=b.register_file(p,path)
        b.review_reference(p,variant['id'],{'fileId':file['id'],'confirmed':True,'evidence':'自动化测试中模拟人工核对，不代表真实人物画面','roles':variant['roles']})
    b.finalize(p,'style',b.style(p)['id'])


def test_grouped_generation_uses_actual_limits_and_current_shots(studio):
    b,p,q=modern(studio);out=b.advance(p,{})['proposal'];b.adopt_proposal(p,out['id']);provide_references(b,p)
    ids=[s['id'] for s in b.ordered_shots(p,b.list_active(p,'shot'))]
    task=b.plan_generation_tasks(p,{'shotIds':ids,'groups':[{'shotIds':ids,'focus':'开盒、取物、交接组成完整动作'}]})['tasks'][0]
    assert task['shotIds']==ids and len(task['shots'])==3 and not task['capabilitiesVerified']
    assert '别弄丢。' in task['prompt']
    again=b.plan_generation_tasks(p,{'shotIds':ids,'groups':[{'shotIds':ids,'focus':'开盒、取物、交接组成完整动作'}]})['tasks'][0]
    assert again['id']==task['id'] and len(b.s.list(p,'generation_task'))==1
    project=b.s.get(p);project['rendererProfile']={'maxSeconds':1,'maxImages':10};b.s.put('project',project,p)
    with pytest.raises(DomainError,match='时长上限'):b.plan_generation_tasks(p,{'shotIds':ids,'groups':[{'shotIds':ids,'focus':'合并动作'}]})


def test_local_shot_patch_and_identity_change_propagation(studio):
    b,p,q=modern(studio);out=b.advance(p,{})['proposal'];b.adopt_proposal(p,out['id']);shots=b.list_active(p,'shot');provide_references(b,p)
    before={s['id']:b.s.get(s['id']) for s in shots};last=shots[-1]['id']
    original=b.llm.json
    def modified(project,role,system,context,*args,**kwargs):
        if role=='shots':
            result=copy.deepcopy(kwargs['demo']);result['shots'][0]['actionLine']='阿青停顿一下，把玉牌交到老林掌心。';return result
        return original(project,role,system,context,*args,**kwargs)
    b.llm.json=modified
    proposal=b.propose_director(p,{'sceneId':shots[0]['sceneId'],'shotIds':[last],'instruction':'调整最后一个动作的表演'})
    assert proposal['passed'],proposal['issues'];b.adopt_proposal(p,proposal['id'])
    for shot in shots[:-1]:assert b.s.get(shot['id'])==before[shot['id']]
    assert b.s.get(last)['actionLine'].startswith('阿青停顿')
    master=b.s.get(b.s.get(shots[0]['sceneId'])['entityAssetMap']['alice']);variant=next(v for v in b.s.list(p,'variant') if v['masterId']==master['id'] and v.get('claims'))
    master['freezeString']='短发女子，左眼下有痣';plan=b.change_plan(p,'master',master);b.save(p,'master',master,plan['planHash'])
    with pytest.raises(DomainError,match='身份设计已变化'):b.event_manifest(p,b.s.get(shots[0]['id']))


def test_adopted_interval_and_replaced_parent_invalidate_chain_only(studio):
    import subprocess
    from app.assembly import get_ffmpeg
    b,p,q=modern(studio);out=b.advance(p,{})['proposal'];b.adopt_proposal(p,out['id']);shots=b.list_active(p,'shot');provide_references(b,p)
    project=b.s.get(p);project['rendererProfile']={'capabilities':{'firstFrame':True}};b.s.put('project',project,p)
    folder=b.s.root/'media'/p;video=folder/'test-only.mp4'
    subprocess.run([get_ffmpeg(b.settings.read()),'-y','-v','error','-f','lavfi','-i','color=c=blue:s=64x64:r=10:d=4','-c:v','libx264','-pix_fmt','yuv420p',str(video)],check=True,capture_output=True)
    file=b.register_file(p,video,'clip');frames=replay(q['payload']['continuity'])
    for i,shot in enumerate(shots):
        image=folder/f'key-{i}.png';Image.new('RGB',(64,64),'blue').save(image);key=b.register_file(p,image,'keyframe')
        for kind,f in [('keyframe',key),('clip',file)]:b.s.put('render',{'id':f'{kind}-{i}','projectId':p,'shotId':shot['id'],'kind':kind,'fileId':f['id'],'url':f['url'],'selected':kind=='keyframe','pinned':False,'freshness':'clean','status':'accepted','assetVariants':shot['assetVariants'],'demo':True,'gate':{'status':'passed'}},p)
        b.select_render(p,f'clip-{i}',{'selected':True,'humanReview':True,'adoptedInterval':{'in':0,'out':2},'observedEndState':frames[shot['eventId']]['after'],'observationEvidence':'测试夹具模拟观察；非真实创作视频'})
    for i in (0,1):b.save(p,'link',{'from':shots[i]['id'],'to':shots[i+1]['id'],'type':'frame_chain'})
    # The link edit invalidates previous video candidates. Fixtures here model
    # completed, reviewed renders with the newly established dependencies.
    for i in (1,2):r=b.s.get(f'clip-{i}');r['freshness']='clean';b.s.put('render',r,p)
    b.s.put('render',{'id':'unrelated','projectId':p,'shotId':'other','kind':'clip','freshness':'clean','status':'accepted'},p)
    before=b.render_request(p,{'shotId':shots[1]['id'],'kind':'clip'})['key']
    adoption={'selected':True,'humanReview':True,'adoptedInterval':{'in':.5,'out':3},'observedEndState':frames[shots[0]['eventId']]['after'],'observationEvidence':'测试中调整实际采用区间'}
    b.select_render(p,'clip-0',adoption)
    after=b.render_request(p,{'shotId':shots[1]['id'],'kind':'clip'})
    assert before!=after['key'] and after['bound'][0]['adoption']['endFrameTime']<3
    assert b.s.get('clip-1')['freshness']==b.s.get('clip-2')['freshness']=='broken'
    assert b.s.get('keyframe-1')['freshness']==b.s.get('unrelated')['freshness']=='clean'
    assembly=b.assembler.plan(p,{'shotIds':[shots[0]['id']]})
    assert assembly['entries'][0]['sourceIn']==.5 and assembly['entries'][0]['duration']==2.5
    replacement=b.s.get('clip-0');replacement.update(id='replacement',selected=False);b.s.put('render',replacement,p)
    for i in (1,2):r=b.s.get(f'clip-{i}');r['freshness']='clean';b.s.put('render',r,p)
    b.select_render(p,'replacement',adoption)
    assert b.s.get('clip-2')['freshness']=='broken'


def test_independent_review_protects_facts_and_stops_without_progress(studio):
    b=studio.state.service;p=b.create({'source':'阿青保留玉牌。','workflowVersion':2})['project']['id'];original=b.llm.json;calls=[]
    def failing_review(project,role,system,context,*args,**kwargs):
        calls.append(role)
        if role=='reviewer':return {'checks':[{'id':k,'passed':False,'evidence':'候选改变了保留玉牌的结局。'} for k in ('source_fidelity','cause_effect','dialogue','event_coverage','continuity','presentation')],'issues':[{'code':'protected_fact','severity':'major','message':'结局被改变','location':'场次 1'}]}
        return original(project,role,system,context,*args,**kwargs)
    b.llm.json=failing_review;row=b.propose_shooting(p,{})
    assert not row['passed'] and calls.count('treatment')<=3 and calls.count('reviewer')==1
    assert any(i['code']=='protected_fact' for i in row['issues'])
    with pytest.raises(DomainError,match='尚未通过'):b.adopt_shooting(p,row['id'])


def test_cross_scene_preview_controls_actual_playback_order(studio):
    b,p,q=modern(studio);doc=copy.deepcopy(q['payload']);doc['scenes'].append({'id':'s2','title':'未来','blocks':[{'id':'a2','type':'action','text':'老林握紧玉牌。'}]});doc['continuity']['events'].append({'id':'future','sceneId':'s2','locationId':'room','participants':['bob','token'],'origin':'adapted','action':'老林握紧玉牌','changes':[],'dialogueIds':[]});doc['presentationPlan'].append({'id':'future-main','eventId':'future','kind':'main','phase':'before','dialogueIds':[]});doc['presentationPlan'].insert(0,{'id':'future-preview','eventId':'future','kind':'preview','phase':'after','reason':'先给握玉牌预演，再回切开盒','dialogueIds':[]});doc=normalize_document(doc)
    stored=b.s.get(q['id']);stored['payload']=doc;b.s.put('shooting_script',stored,p)
    fake=[{'id':'normal','presentationId':'open_main','sceneId':'ignore','order':0},{'id':'future','presentationId':'future-main','sceneId':'ignore','order':1},{'id':'preview','presentationId':'future-preview','sceneId':'ignore','order':0}]
    assert [s['id'] for s in b.ordered_shots(p,fake)]==['preview','normal','future']


def test_opening_frame_does_not_take_end_state_reference(studio):
    b,p,q=modern(studio);proposal=b.advance(p,{})['proposal'];b.adopt_proposal(p,proposal['id']);shot=b.list_active(p,'shot')[0];provide_references(b,p)
    manifest=b.event_manifest(p,shot);ends=[r for r in manifest['resolved'] if r['role']=='end_state'];assert ends
    # Removing the final-state picture must not block an opening still.
    for ref in ends:
        variant=b.s.get(ref['variantId']);variant['referenceFileId']=None;b.s.put('variant',variant,p)
    req=b.render_request(p,{'shotId':shot['id'],'kind':'keyframe'})
    assert all(r['role']!='end_state' for r in req['manifest']['resolved'])
    assert 'closed' in req['compiled']['imagePrompt'] and 'Opening still' in req['compiled']['imagePrompt']


def test_destroyed_asset_cannot_still_be_held():
    doc=box_story();doc['continuity']['initialState']['token']['destroyed']=True
    with pytest.raises(DomainError,match='不能继续持有'):replay(doc['continuity'])


def test_multi_shot_unit_uses_paid_preview_cache_and_returns_unadopted_video(studio):
    b,p,q=modern(studio);out=b.advance(p,{})['proposal'];b.adopt_proposal(p,out['id']);provide_references(b,p)
    studio.state.settings.save({'media':{'provider':'demo'}})
    ids=[s['id'] for s in b.ordered_shots(p,b.list_active(p,'shot'))]
    task=b.plan_generation_tasks(p,{'shotIds':ids,'groups':[{'shotIds':ids,'focus':'连续开盒与交接'}]})['tasks'][0]
    request={'taskIds':[task['id']]};preview=b.generation_dry_run(p,request);assert not preview['blocked'],preview
    with pytest.raises(DomainError,match='费用预览'):b.execute_generation_tasks(p,request)
    result=b.execute_generation_tasks(p,{**request,'planHash':preview['planHash']})['tasks'][0]
    assert result['status']=='awaiting_segmentation' and result['demo']
    assert Path(b.s.get(result['generationFileId'])['path']).is_file()
    assert not any(r.get('selected') for r in b.s.list(p,'render'))
    next_preview=b.generation_dry_run(p,request)
    assert next_preview['requests'][0]['cacheHit'] and next_preview['estimatedCost']==0
    assert b.generation_dry_run(p,{**request,'quality':'final'})['requests'][0]['renderKey']!=next_preview['requests'][0]['renderKey']
    duration=float(b.gates.probe(b.s.get(result['generationFileId'])['path'])['format']['duration'])
    imported=b.attach_generation_task(p,task['id'],{'fileId':result['generationFileId'],'ranges':[{'shotId':sid,'in':i*duration/len(ids),'out':(i+1)*duration/len(ids)} for i,sid in enumerate(ids)]})
    assert len(imported['renders'])==3 and all(not r['selected'] and r['proposedInterval'] for r in imported['renders'])


def test_different_treatments_and_dialogue_rewrite_use_adopted_b_version(studio):
    b,p,initial=modern(studio);original=b.llm.json
    def treatments(project,role,system,context,*args,**kwargs):
        if role!='treatment':return original(project,role,system,context,*args,**kwargs)
        doc=box_story();mode=context['mode'];scene=doc['scenes'][0]
        scene['blocks'][0]['text']='阿青凝视木盒许久，指尖擦去浮灰，缓缓打开盒盖，才把玉牌交给老林。' if mode=='cinema' else '盒盖掀开。阿青取出玉牌，塞进老林手里。'
        scene['targetDuration']=26 if mode=='cinema' else 8
        target='d1' if mode=='cinema' else 'd-fast'
        scene['blocks'][1].update(id=target,text='别弄丢。' if mode=='cinema' else '拿稳。')
        doc['continuity']['events'][-1]['dialogueIds']=[target];doc['presentationPlan'][-1]['dialogueIds']=[target]
        doc.update(mode=mode,sourceMapping=[{'sourceId':'a1','targetIds':['a1'],'reason':'按呈现方向调整动作组织'},{'sourceId':'d1','targetIds':[target],'reason':'保留托付意思并调整对白密度'}],storyChanges=[])
        return doc
    b.llm.json=treatments
    film=b.propose_shooting(p,{'mode':'cinema'});assert film['passed'];b.adopt_shooting(p,film['id'])
    fast=b.propose_shooting(p,{'mode':'fast_drama'});assert fast['passed'];b.adopt_shooting(p,fast['id'])
    assert film['payload']['scenes'][0]['blocks']!=fast['payload']['scenes'][0]['blocks']
    assert film['payload']['scenes'][0]['targetDuration']>fast['payload']['scenes'][0]['targetDuration']
    proposal=b.advance(p,{})['proposal'];assert proposal['passed'],proposal['issues'];b.adopt_director(p,proposal['id'])
    lines='\n'.join(b.with_dialogue(p,s)['dialogueText'] for s in b.list_active(p,'shot'))
    assert '拿稳。' in lines and '别弄丢。' not in lines
    assert b.source_document(p)['scenes'][0]['blocks'][1]['text']=='别弄丢。'


def test_reference_generation_preview_cache_and_identity_before_variant(studio):
    b,p,q=modern(studio);proposal=b.advance(p,{})['proposal'];b.adopt_director(p,proposal['id'])
    studio.state.settings.save({'media':{'provider':'demo'}})
    style=b.style(p);b.finalize(p,'style',style['id'])
    master=next(m for m in b.list_active(p,'master') if m.get('sourceEntityId')=='box')
    state=next(v for v in b.list_active(p,'variant') if v['masterId']==master['id'] and v['id']!=master['defaultVariantId'])
    with pytest.raises(DomainError,match='身份主图'):b.asset_dry_run(p,{'assetId':master['id'],'variantId':state['id']})
    request={'assetId':master['id'],'variantId':master['defaultVariantId']};preview=b.asset_dry_run(p,request)
    with pytest.raises(DomainError,match='费用预览'):b.asset_render(p,{**request,'confirmed':True})
    result=b.asset_render(p,{**request,'confirmed':True,'planHash':preview['planHash']})
    assert not b.s.get(master['defaultVariantId']).get('referenceFileId')
    assert b.asset_dry_run(p,request)['cacheHit']
    b.review_reference(p,master['defaultVariantId'],{'fileId':result['fileId'],'evidence':'本地测试卡，仅验证人工采用链路','confirmed':True})
    variant_preview=b.asset_dry_run(p,{'assetId':master['id'],'variantId':state['id']})
    assert variant_preview['renderKey']!=preview['renderKey']
    assert b.asset_render_plan(p,{'assetId':master['id'],'variantId':state['id']})[4]

