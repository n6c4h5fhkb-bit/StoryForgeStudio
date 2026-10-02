import copy
import threading
from unittest.mock import patch

import jsonschema
import pytest
from app.core import DomainError
from app.story import StoryService
from app.creative_review import CHECKS
from test_common import studio
from test_story import generate, adopt_root, fill


def test_original_creation_intent_retries_reuse_results_but_new_intent_generates(studio):
    story=studio.state.service;p=story.create({'seed':'门外的鞋子','compact':True})['project']['id']
    request={'op':'expand','operationId':'first-intent'}
    first=story.generate(p,request);runs=len(story.s.list(p,'run'))
    second=story.generate(p,request)
    assert first==second and len(story.s.list(p,'run'))==runs
    third=story.generate(p,{**request,'operationId':'next-intent'})
    assert third['batchId']!=first['batchId'] and len(story.s.list(p,'run'))>runs


def test_interrupted_creation_keeps_completed_lane_and_strategy_selection(studio):
    story=studio.state.service;p=story.create({'seed':'鞋子的秘密','compact':True})['project']['id']
    original=story.llm.json;lock=threading.Lock();calls=[]
    def interrupted(*args,**kwargs):
        with lock:
            calls.append(kwargs['session_scope']);index=len(calls)
        if index>1:raise DomainError('cancel','cancelled',409)
        return original(*args,**kwargs)
    story.llm.json=interrupted;request={'op':'expand','generationId':'durable-work'}
    with pytest.raises(DomainError):story.generate(p,request)
    completed=story.s.list(p,'candidate');assert len(completed)==1
    record=story.s.list(p,'generation_request')[0]
    story.llm.json=original
    resumed=StoryService(story.s,story.settings,story.llm).generate(p,request)
    assert resumed['batchId']==record['batchId'] and not resumed['allFailed']
    assert len(story.s.list(p,'run'))==3
    assert {c['strategy'] for c in story.s.list(p,'candidate')}==set(record['strategies'])
    assert completed[0]['id'] in resumed['candidateIds']
    assert len(story.s.list(p,'canon_patch'))==sum(len(c.get(k,[])) for c in story.s.list(p,'candidate') for k in ('entityProposals','factProposals','beliefProposals'))


def test_original_gate_repair_uses_valid_patch_schema_and_preserves_unaffected_text(studio):
    story=studio.state.service;p=story.create({'seed':'门外的鞋子','compact':True})['project']['id']
    original=story.llm.json;seen=[];base=[]
    def generated(project,role,system,context,schema=None,**kwargs):
        seen.append((copy.deepcopy(context),kwargs['session_scope'],kwargs['cache']))
        if context.get('repairFormat')=='json_patch':
            result={'patches':[{'op':'replace','path':'/title','value':base[0]['title']}]}
            jsonschema.validate(result,schema);jsonschema.validate(base[0],schema)
            return result
        result=original(project,role,system,context,schema,**kwargs);base.append(copy.deepcopy(result));result['title']='BROKEN'
        return result
    old_gate=story.gate
    story.gate=lambda project,value,*args: ['修正标题'] if value.get('title')=='BROKEN' else old_gate(project,value,*args)
    story.llm.json=generated
    result=story.generate(p,{'op':'expand','candidateCount':1})
    assert not result['allFailed'] and len(seen)==2
    assert seen[0][1]==seen[1][1] and all(c[2] for c in seen)
    candidate=story.s.get(result['candidateIds'][0]);assert candidate['items']==base[0]['items']


def test_review_sessions_are_scoped_to_actual_story_node(studio):
    story=studio.state.service;p=story.create({'seed':'鞋子的秘密','compact':True})['project']['id']
    root=adopt_root(story,p);fill(story,p,root['id'])
    expanded=generate(story,p,root['id']);story.adopt(p,expanded['candidateIds'][0])
    targets=[n for n in story.nodes(p) if n['parentId']==root['id']]
    studio.state.settings.save({'models':{'validator':{'provider':'openai','model':'review','baseUrl':'https://unused.invalid'}}})
    original=story.llm.json;scopes=[]
    def generate_review(project,role,system,context,*args,**kwargs):
        if role=='validator':
            scopes.append(kwargs.get('session_scope'));return approved_report(context)
        return original(project,role,system,context,*args,**kwargs)
    story.llm.json=generate_review
    for node in targets:story.generate(p,{'nodeId':node['id'],'op':'fill','candidateCount':1})
    assert len(scopes)==2 and scopes[0]!=scopes[1]
    assert all(node['id'] in scope for node,scope in zip(targets,scopes))


def approved_report(context):
    return {'scores':[{'id':identifier,'quality':4,'novelty':4,'evidence':'人物主动选择推动当前契约变化',
        'checks':[{'id':check,'passed':True,'evidence':'依据当前候选契约和故事种子'} for check in CHECKS],
        'issues':[]} for identifier in context['reviewIds']],'distances':[]}


def test_original_independent_reviewer_repairs_only_failed_lane_with_global_attempt_bound(studio):
    story=studio.state.service;p=story.create({'seed':'阿青为找回母亲的信，主动打开旧盒子。','compact':True})['project']['id']
    studio.state.settings.save({'models':{'validator':{'provider':'openai','model':'review','baseUrl':'https://unused.invalid'}}})
    original=story.llm.json;calls=[];review_count=0
    def model(project,role,system,context,*args,**kwargs):
        nonlocal review_count
        calls.append((role,copy.deepcopy(context),kwargs.get('session_scope')))
        if role=='validator':
            review_count+=1;report=approved_report(context)
            if review_count==1:
                report['scores'][0]['checks'][1].update(passed=False,evidence='summary 的失忆设定没有采用依据，请移除')
            return report
        if context.get('repairFormat')=='json_patch':
            return {'patches':[{'op':'replace','path':'/summary','value':'她主动打开旧盒子寻找母亲的信。'}]}
        return original(project,role,system,context,*args,**kwargs)
    story.llm.json=model
    result=story.generate(p,{'op':'expand','candidateCount':2})
    assert not result['allFailed']
    author=[c for c in calls if c[0]!='validator'];reviews=[c for c in calls if c[0]=='validator']
    assert len(author)==3 and len(reviews)==2
    assert len(reviews[0][1]['reviewIds'])==2 and len(reviews[1][1]['reviewIds'])==1
    assert author[-1][1]['repairFormat']=='json_patch'
    assert author[-1][2] in [c[2] for c in author[:2]]
    assert reviews[0][2]==reviews[1][2] and 'storyBible' in reviews[0][1]
    assert all(story.s.get(i)['qualityReview']['passed'] for i in result['candidateIds'])


def test_missing_review_evidence_blocks_adoption_and_does_not_rewrite_creator(studio):
    story=studio.state.service;p=story.create({'seed':'旧盒子的秘密','compact':True})['project']['id']
    studio.state.settings.save({'models':{'validator':{'provider':'openai','model':'review','baseUrl':'https://unused.invalid'}}})
    original=story.llm.json;authors=[]
    def model(project,role,system,context,*args,**kwargs):
        if role=='validator':return {'scores':[]}
        authors.append(role);return original(project,role,system,context,*args,**kwargs)
    story.llm.json=model
    result=story.generate(p,{'op':'expand','candidateCount':1})
    assert result['allFailed'] and len(authors)==1
    candidate=story.s.list(p,'candidate')[0]
    with pytest.raises(DomainError):story.adopt(p,candidate['id'])


def test_real_original_cannot_use_demo_review(studio):
    story=studio.state.service;p=story.create({'seed':'旧盒子的秘密'})['project']['id']
    studio.state.settings.save({'models':{'structure':{'provider':'codex_cli'},'validator':{'provider':'demo'}}})
    with pytest.raises(DomainError) as exc:story.generate(p,{'op':'expand'})
    assert exc.value.code=='reviewer_required' and not story.s.list(p,'run')


def test_root_candidate_cannot_adopt_several_alternative_stories(studio):
    story=studio.state.service;p=story.create({'seed':'旧盒子的秘密'})['project']['id']
    original=story.llm.json;counts=[]
    def model(project,role,system,context,*args,**kwargs):
        counts.append(context['08_task']['count'])
        result=original(project,role,system,context,*args,**kwargs)
        result['items'].append(copy.deepcopy(result['items'][0]))
        return result
    story.llm.json=model
    result=story.generate(p,{'op':'expand','candidateCount':1,'count':3})
    assert result['allFailed'] and set(counts)=={1}
    candidate=story.s.list(p,'candidate')[0]
    assert any('故事根节点' in e for e in candidate['gate']['errors'])
    with pytest.raises(DomainError):story.adopt(p,candidate['id'])
