import copy,json,xml.etree.ElementTree as ET
import pytest
from app.core import DomainError,digest
from app.story import choose_diverse,contract_equal
from test_common import studio

@pytest.fixture
def story(studio):
    s=studio.state.service;p=s.create({'title':'回归测试故事','seed':'门外的鞋子每天少一只','targetDuration':48,'compact':True})['project']['id']
    return s,p

def generate(s,p,node=None,op='expand',**extra):
    d={'nodeId':node,'op':op,'count':2,**extra}
    if node and op in ('rewrite','split','move_reveal','merge'):d['planHash']=s.plan(p,d)['planHash']
    result=s.generate(p,d)
    assert not result['allFailed'],result
    return result

def adopt_root(s,p):
    result=generate(s,p);s.adopt(p,result['candidateIds'][0])
    for patch in s.s.list(p,'canon_patch'):
        if patch['status']=='pending':s.patch(p,patch['id'],True)
    return s.nodes(p)[0]

def fill(s,p,node):
    c=generate(s,p,node,'fill')['candidateIds'][0];s.adopt(p,c);return s.s.get(node)

def structural(s,p,node,op,**more):
    task={'nodeId':node,'op':op,**more};task['planHash']=s.plan(p,task)['planHash'];return s.structural(p,task)

def test_generation_only_creates_candidates(story):
    s,p=story;r=generate(s,p)
    assert len(r['candidateIds'])==3
    assert s.nodes(p)==[]
    assert len(s.s.list(p,'candidate'))==3
    assert all(x['status']=='provisional' for x in s.s.list(p,'canon_patch'))

def test_candidate_strategies_are_distinct(story):
    s,p=story;generate(s,p);cs=s.s.list(p,'candidate')
    assert len({x['strategy'] for x in cs})==len(cs)
    assert {x['slot'] for x in cs if x['visible']}=={'最佳稳妥','最佳新颖','最佳另类'}

def test_two_phase_expand_requires_human_adopt(story):
    s,p=story;n=adopt_root(s,p)
    assert n['body']=={} and not n['generationComplete']
    c=generate(s,p,n['id'],'fill')['candidateIds'][0]
    assert not s.s.get(n['id'])['generationComplete']
    s.adopt(p,c);assert s.s.get(n['id'])['generationComplete']
    r=generate(s,p,n['id']);assert len(s.nodes(p))==1
    s.adopt(p,r['candidateIds'][0]);assert len(s.nodes(p))==3
    assert all(not x['body'] for x in s.nodes(p) if x['parentId'])

def test_canon_proposals_not_silently_written(story):
    s,p=story;c=generate(s,p)['candidateIds'][0]
    assert not s.s.get(p)['canon']['entities']
    s.adopt(p,c);assert not s.s.get(p)['canon']['entities']
    patches=[x for x in s.s.list(p,'canon_patch') if x['status']=='pending'];assert patches
    s.patch(p,patches[0]['id'],True);assert s.s.get(p)['canon']['entities']

def test_duplicate_adopt_does_not_duplicate_nodes(story):
    s,p=story;c=generate(s,p)['candidateIds'][0];s.adopt(p,c);count=len(s.nodes(p));s.adopt(p,c);assert len(s.nodes(p))==count

def test_reject_reason_enters_next_context(story):
    s,p=story;c=generate(s,p)['candidateIds'][0];s.reject(p,c,'不要时间循环')
    assert '不要时间循环' in json.dumps(s.context(p,None,'expand'),ensure_ascii=False)

def test_stale_candidate_cannot_overwrite_new_revision(story):
    s,p=story;n=adopt_root(s,p);r1=generate(s,p,n['id'],'fill');r2=generate(s,p,n['id'],'fill')
    s.adopt(p,r1['candidateIds'][0])
    with pytest.raises(DomainError):s.adopt(p,r2['candidateIds'][0])

def test_locked_and_broken_are_independent_and_exportable(story):
    s,p=story;n=adopt_root(s,p);fill(s,p,n['id']);structural(s,p,n['id'],'lock')
    current=s.s.get(n['id']);current['freshness']='broken';current['freshnessNotes']=[{'id':'conflict','message':'待仲裁'}];s.s.put('node',current,p)
    with pytest.raises(DomainError):generate(s,p,n['id'],'fill')
    with pytest.raises(DomainError):generate(s,p,n['id'],'expand')
    assert s.s.get(n['id'])['status']=='locked'
    assert s.export(p,'fountain')[0]

def test_body_change_preserving_contract_does_not_break_descendants(story):
    s,p=story;n=adopt_root(s,p);fill(s,p,n['id']);r=generate(s,p,n['id']);s.adopt(p,r['candidateIds'][0])
    children=[x for x in s.nodes(p) if x['parentId']==n['id']]
    r=generate(s,p,n['id'],'restyle',instruction='更生活化');s.adopt(p,r['candidateIds'][0])
    assert all(s.s.get(x['id'])['freshness']!='broken' for x in children)

def test_probe_is_noncanonical_and_rollout_is_machine_only(story):
    s,p=story;r=generate(s,p);before=len(s.nodes(p));spikes=s.probe(p,r['batchId'])
    assert len(spikes)==3 and len(s.nodes(p))==before
    public=s.get(p)['spikes']
    assert all('rollout' not in x and 'horizontal' not in x for x in public)
    assert all(x.get('signals') and x.get('script') for x in public)

def test_global_facts_reject_conflicting_contract(story):
    s,p=story;n=adopt_root(s,p);canon=copy.deepcopy(s.s.get(p)['canon']);hero=canon['entities'][0]['id'];canon['facts']=[{'subject':hero,'predicate':'alive','object':'true','validFrom':None,'validUntil':None}];s.update_canon(p,{'canon':canon})
    out=s.demo_candidate(p,n,'premise','body',0,{})
    out['items'][0]['contract']['preconditions']=[{'subject':hero,'predicate':'alive','object':'false'}]
    assert any('全局事实' in e for e in s.gate(p,out,n,'rewrite','premise','body'))

def test_false_belief_explicitly_preserved(story):
    s,p=story;n=adopt_root(s,p);canon=copy.deepcopy(s.s.get(p)['canon']);hero=canon['entities'][0]['id'];canon['beliefs']=[{'holder':hero,'content':'邻居无辜','truth':False,'validFrom':{'nodeId':n['id'],'boundary':'entry'},'validUntil':None}]
    s.update_canon(p,{'canon':canon});assert s.s.get(p)['canon']['beliefs'][0]['truth'] is False
    assert not any('邻居无辜' in x.get('message','') for x in s.scan(p)['issues'])

def test_full_scene_script_chain_exports_valid_fdx_and_scene_export(story):
    s,p=story;n=adopt_root(s,p);fill(s,p,n['id'])
    for level in ['premise','sequence','scene']:
        for node in [x for x in s.nodes(p) if x['level']==level and x['status']!='archived']:
            s.adopt(p,generate(s,p,node['id'])['candidateIds'][0])
            for child in [x for x in s.nodes(p) if x['parentId']==node['id'] and x['status']!='archived']:fill(s,p,child['id'])
    scenes=[x for x in s.nodes(p) if x['level']=='scene'];scripts=[x for x in s.nodes(p) if x['level']=='script']
    assert len(scenes)==len(scripts)==4
    assert all(len([x for x in scripts if x['parentId']==scene['id']])==1 for scene in scenes)
    assert not s.scan(p)['issues']
    root=ET.fromstring(s.export(p,'fdx')[0]);assert root.tag=='FinalDraft'
    assert root.findall('.//Paragraph[@Type="Dialogue"]')
    package=json.loads(s.export(p,'scene-export')[0]);assert len(package['scenes'])==4
    assert all(all(k in sc for k in ['contractHash','bodyHash','canonHash','canonSlice','narrativeContext']) for sc in package['scenes'])
    assert sum(sc['directives']['targetDuration'] for sc in package['scenes'])==48

def test_branch_isolated_from_main(story):
    s,p=story;adopt_root(s,p);main=digest(s.nodes(p));branch=s.branch(p,'不同结局')
    bid=branch.get('projectId') or branch.get('branchProjectId') or branch.get('id')
    if bid and s.s.get(bid,required=False) and 'branchProjectId' in s.s.get(bid):bid=s.s.get(bid)['branchProjectId']
    assert digest(s.nodes(p))==main
    assert s.s.list(p,'branch')

def test_length_budget_and_frontier_exist_before_detailed_script(story):
    s,p=story;n=adopt_root(s,p);assert s.readthrough(p);c=s.coverage(p)
    assert 'frontier' in c and c['layers']
    s.adopt(p,generate(s,p,n['id'])['candidateIds'][0]);assert s.readthrough(p)


def test_blind_probe_hides_candidate_mapping_until_second_choice(story,studio):
    from fastapi.testclient import TestClient
    import time
    s,p=story;result=generate(s,p)
    client=TestClient(studio,base_url='http://localhost',headers={'x-studio-client':'local-ui'})
    reply=client.post(f'/api/projects/{p}/experiments/blind',json={'batchId':result['batchId'],'outlineChoice':result['candidateIds'][0],'reason':'因果关系清楚'})
    assert reply.status_code==200,reply.text
    job=reply.json()
    for _ in range(100):
        job=client.get('/api/jobs/'+job['id']).json()
        if job['state'] not in ('running','queued'):break
        time.sleep(.02)
    assert job['state']=='succeeded',job
    cards=job['result']['cards'];assert len(cards)==3
    assert all('candidateId' not in c and 'horizontal' not in c for c in cards)
    end=client.post(f'/api/projects/{p}/experiments/'+job['result']['experimentId']+'/choose',json={'index':0})
    assert end.status_code==200
    assert isinstance(end.json()['switched'],bool)
    assert client.get(f'/api/projects/{p}/experiments').json()['switchRate'] in (0,1)


def add_test_node(s,p,root,id,level='scene',parent=None,order=0,pre=None,post=None,complete=True):
    hero=s.s.get(p)['canon']['entities'][0]['id']
    contract=copy.deepcopy(root['contract']);contract['preconditions']=pre or [];contract['postconditions']=post or []
    body={'location':'门口','timeOfDay':'夜','action':'人物站在门口。','targetDuration':12,'dialogue':[{'character':hero,'text':id+'的台词'}]}
    if level=='script':body['sceneHeading']='INT. 门口 - 夜'
    node={'id':id,'projectId':p,'level':level,'parentId':parent or root['id'],'order':str(order),'title':id,'contract':contract,'body':body,'status':'accepted','freshness':'clean','freshnessNotes':[],'resolution':4,'speculative':False,'generationComplete':complete,'currentRevision':''}
    return s.revise(p,node,None,'test_setup')


def test_script_context_contains_scene_and_adjacent_scene_script(story):
    s,p=story;root=adopt_root(s,p)
    first=add_test_node(s,p,root,'first');add_test_node(s,p,root,'first_script','script',first['id'])
    second=add_test_node(s,p,root,'second',order=1);script=add_test_node(s,p,root,'second_script','script',second['id'])
    context=s.context(p,script['id'],'rewrite')
    assert context['08_task']['scene']['body']==second['body']
    assert context['04_neighbors'][0]['id']=='first'
    assert context['04_neighbors'][0]['body']['dialogue'][0]['text']=='first_script的台词'
    candidate=generate(s,p,script['id'],'restyle')['candidateIds'][0]
    before=s.s.get('first_script');updated=copy.deepcopy(before);updated['body']['action']='前场已改变'
    s.revise(p,updated,before,'rewrite')
    with pytest.raises(DomainError,match='依赖内容'):s.adopt(p,candidate)


def test_scene_context_injects_only_facts_known_at_entry(story):
    s,p=story;root=adopt_root(s,p);scene=add_test_node(s,p,root,'scene');script=add_test_node(s,p,root,'script','script',scene['id'])
    canon=copy.deepcopy(s.s.get(p)['canon']);hero=canon['entities'][0]['id']
    canon['facts']=[{'subject':hero,'predicate':'state','object':'alive','validFrom':None,'validUntil':{'nodeId':scene['id'],'boundary':'exit'}},{'subject':hero,'predicate':'state','object':'dead','validFrom':{'nodeId':scene['id'],'boundary':'exit'},'validUntil':None}]
    s.update_canon(p,{'canon':canon})
    assert [x['object'] for x in s.context(p,script['id'],'rewrite')['05_canon']['facts']]==['alive']


@pytest.mark.parametrize('level',['premise','spine','sequence','scene','script'])
def test_nonempty_unreadable_body_fails_gate(story,level):
    s,p=story;root=adopt_root(s,p);out=s.demo_candidate(p,root,level,'body',0,{})
    out['items'][0]['body']={'unrelated':True}
    assert any('正文结构' in error for error in s.gate(p,out,root,'fill',level,'body'))


def test_script_gate_accepts_silent_action_and_rejects_unknown_speaker(story):
    s,p=story;root=adopt_root(s,p);out=s.demo_candidate(p,root,'script','body',0,{})
    body=out['items'][0]['body'];body['dialogue']=[];body['blocks']=[]
    assert not s.gate(p,out,root,'fill','script','body')
    body['dialogue']=[{'character':'unknown','text':'是谁？'}]
    assert any('未知角色' in error for error in s.gate(p,out,root,'fill','script','body'))
    body['dialogue']=[];body['blocks']=[{'type':'dialogue','character':'unknown','text':'是谁？'}]
    assert any('未知角色' in error for error in s.gate(p,out,root,'fill','script','body'))


def test_candidate_budget_is_operation_specific_and_explicit(story):
    s,p=story;root=adopt_root(s,p)
    assert len(generate(s,p,root['id'],'fill')['candidateIds'])==1
    assert len(generate(s,p,root['id'],'fill',candidateCount=2)['candidateIds'])==2
    assert len(generate(s,p,root['id'],'restyle')['candidateIds'])==2
    with pytest.raises(DomainError,match='候选数量'):generate(s,p,root['id'],'fill',candidateCount=0)


def test_exit_propagation_respects_nested_entry_and_later_state_override(story):
    s,p=story;root=adopt_root(s,p);hero=s.s.get(p)['canon']['entities'][0]['id']
    state=lambda value:{'subject':hero,'predicate':'alive','object':value}
    source=add_test_node(s,p,root,'source',post=[state('true')])
    child=add_test_node(s,p,root,'child','script',source['id'],pre=[state('true')])
    downstream=add_test_node(s,p,root,'downstream',order=1,pre=[state('true')])
    reset=add_test_node(s,p,root,'reset',order=2,post=[state('true')])
    later=add_test_node(s,p,root,'later',order=3,pre=[state('true')])
    changed=copy.deepcopy(source);changed['contract']['postconditions']=[state('false')]
    with s.s.transaction() as conn:
        changed=s.revise(p,changed,source,'rewrite',conn=conn);s.propagate(p,source,changed,conn)
    assert s.s.get(child['id'])['freshness']=='clean'
    assert s.s.get(downstream['id'])['freshness']=='broken'
    assert s.s.get(later['id'])['freshness']=='clean'
    with s.s.transaction() as conn:
        restored=s.revise(p,source,changed,'restore',conn=conn);s.propagate(p,changed,restored,conn)
    assert s.s.get(downstream['id'])['freshness']=='clean'


def test_scene_export_tracks_semantics_and_ignores_unrelated_props(story):
    s,p=story;root=adopt_root(s,p);scene=add_test_node(s,p,root,'scene');script=add_test_node(s,p,root,'script','script',scene['id'])
    export=lambda:json.loads(s.export(p,'scene-export')[0])['scenes'][0]
    before=export();canon=copy.deepcopy(s.s.get(p)['canon'])
    canon['entities'].append({'id':'unrelated','kind':'prop','name':'无关道具','freezeString':'红色箱子'})
    s.update_canon(p,{'canon':canon});assert export()['semanticHash']==before['semanticHash']
    canon['beliefs'].append({'holder':'AUDIENCE','content':'观众知道门后有人','truth':True,'validFrom':{'nodeId':scene['id'],'boundary':'entry'},'validUntil':None})
    s.update_canon(p,{'canon':canon});with_knowledge=export()
    assert with_knowledge['narrativeHash']!=before['narrativeHash']
    assert with_knowledge['bodyHash']==before['bodyHash']
    s.update_project(p,{'tone':'更压抑'});assert export()['directivesHash']!=with_knowledge['directivesHash']
    updated=copy.deepcopy(script);updated['body']['action']='他终于推开了门。';s.revise(p,updated,script,'rewrite')
    assert export()['revision']!=before['revision']
    assert export()['sourceRevisions']['scene']==before['sourceRevisions']['scene']


def test_advance_reuses_pending_choice_and_group_adoption_can_continue(story):
    s,p=story;assert s.next_step(p)['state']=='ready'
    first=s.advance(p,{});runs=len(s.s.list(p,'run'))
    assert first['state']=='awaiting_choice'
    assert s.advance(p,{})['batchId']==first['batchId']
    assert len(s.s.list(p,'run'))==runs and not s.nodes(p)
    s.adopt(p,first['candidateIds'][0],approve_proposals=True)
    assert s.s.get(p)['canon']['entities']
    next_step=s.next_step(p);assert next_step['state']=='ready' and next_step['op']=='fill'
    result=s.advance(p,{});assert result['state']=='awaiting_choice' and result['candidateCount']==1


def test_advance_stops_at_locked_unfinished_node(story):
    s,p=story;root=adopt_root(s,p);structural(s,p,root['id'],'lock');runs=len(s.s.list(p,'run'))
    result=s.advance(p,{})
    assert result['state']=='needs_attention' and result['nodeId']==root['id']
    assert len(s.s.list(p,'run'))==runs


def test_grouped_canon_conflict_rolls_back_story_adoption(story):
    s,p=story;root=adopt_root(s,p);result=generate(s,p,root['id'],'fill');candidate=s.s.get(result['candidateIds'][0])
    hero=copy.deepcopy(s.s.get(p)['canon']['entities'][0]);hero['name']='偷偷改名'
    s.s.put('canon_patch',{'id':'conflict_patch','projectId':p,'candidateId':candidate['id'],'kind':'entity','value':hero,'status':'provisional'},p)
    with pytest.raises(DomainError,match='设定冲突'):s.adopt(p,candidate['id'],approve_proposals=True)
    assert not s.s.get(root['id'])['generationComplete']
    assert s.s.get(candidate['id'])['status']=='proposed'
    assert s.s.get('conflict_patch')['status']=='provisional'


def test_continue_creation_reaches_readable_script_without_manual_ops(story):
    s,p=story
    for _ in range(30):
        result=s.advance(p,{'count':2,'candidateCount':1})
        if result['state']=='complete':break
        assert result['state']=='awaiting_choice',result
        s.adopt(p,result['candidateIds'][0],approve_proposals=True)
    else:pytest.fail('继续创作没有在有限步骤内收敛')
    rows=s.readthrough(p)
    assert len(rows)==4 and all(x['level']=='script' and not x['rough'] for x in rows)
    assert s.next_step(p)['state']=='complete'
    assert not [x for x in s.s.list(p,'canon_patch') if x['status']=='pending']


def test_ordered_script_blocks_remain_readable_and_export_in_order(story):
    s,p=story;root=adopt_root(s,p);scene=add_test_node(s,p,root,'scene');script=add_test_node(s,p,root,'script','script',scene['id'])
    hero=s.s.get(p)['canon']['entities'][0]['id'];script['body'].update(action='',dialogue=[],blocks=[{'type':'action','text':'先走进来。'},{'type':'dialogue','character':hero,'text':'你好。'},{'type':'action','text':'随后转身。'}])
    s.revise(p,script,s.s.get(script['id']),'rewrite')
    text=s.readthrough(p)[0]['text'];assert text.index('先走进来')<text.index('你好')<text.index('随后转身')
    exported=s.export(p,'fountain')[0];assert exported.index('先走进来')<exported.index('你好')<exported.index('随后转身')


def test_continue_does_not_skip_a_pending_local_revision(story):
    s,p=story;root=adopt_root(s,p);fill(s,p,root['id'])
    pending=generate(s,p,root['id'],'restyle');run_count=len(s.s.list(p,'run'))
    result=s.advance(p,{})
    assert result['state']=='awaiting_choice' and result['batchId']==pending['batchId']
    assert result['op']=='restyle' and len(s.s.list(p,'run'))==run_count


def test_stale_expansion_cannot_replace_new_child_structure(story):
    s,p=story;root=adopt_root(s,p);fill(s,p,root['id'])
    first=generate(s,p,root['id']);second=generate(s,p,root['id'])
    s.adopt(p,first['candidateIds'][0])
    with pytest.raises(DomainError,match='子结构已变化'):s.adopt(p,second['candidateIds'][0])
    assert s.next_step(p)['state']=='ready' and s.next_step(p)['op']=='fill'


def test_semantic_scan_reuses_content_but_invalidates_after_text_change(story):
    s,p=story;root=adopt_root(s,p);fill(s,p,root['id'])
    s.scan(p,semantic=True)
    current=s.s.get(root['id']);current['freshness']='opportunity';s.s.put('node',current,p)
    s.scan(p,semantic=True)
    runs=[r for r in s.s.list(p,'run') if r['role']=='validator']
    assert len(runs)==2 and runs[-1]['cacheHit'] and runs[-1]['cost']==0
    current['body']['synopsis']='这一次主角作出完全不同的选择。';s.revise(p,current,s.s.get(root['id']),'rewrite')
    s.scan(p,semantic=True)
    assert not [r for r in s.s.list(p,'run') if r['role']=='validator'][-1]['cacheHit']
