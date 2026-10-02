import copy
from types import SimpleNamespace
import pytest
from app.core import Store, DomainError
from app.settings import Settings
from app.creative_review import apply_repairs, generate_reviewed, CHECKS


def test_patch_changes_only_specified_content_and_preserves_source():
    source={'shots':[{'id':'one','phase':'before','action':'开盒'},{'id':'two','phase':'after','action':'交接'}], 'a/b~c':'old'}
    before=copy.deepcopy(source)
    result=apply_repairs(source,{'patches':[{'op':'replace','path':'/shots/1/phase','value':'before'},
        {'op':'replace','path':'/a~1b~0c','value':'new'}]})
    assert source==before and result['shots'][0]==source['shots'][0]
    assert result['shots'][1]=={**source['shots'][1],'phase':'before'} and result['a/b~c']=='new'


@pytest.mark.parametrize('patch',[{'op':'replace','path':'','value':{}},
    {'op':'replace','path':'/missing/name','value':'x'}, {'op':'remove','path':'/shots/-1'},
    {'op':'move','path':'/shots/0','from':'/shots/1'}])
def test_invalid_patch_is_rejected_without_mutating_candidate(patch):
    value={'shots':[{'id':'one'}]};before=copy.deepcopy(value)
    with pytest.raises(DomainError):apply_repairs(value,{'patches':[patch]})
    assert value==before


def test_bounded_repair_accepts_small_patch_and_independently_reviews_merged_result(tmp_path):
    store=Store(tmp_path/'data');settings=Settings(store.root);calls=[]
    def generate(project,role,system,request,**kwargs):
        calls.append((role,request))
        if role=='reviewer':
            assert request['candidate']=={'title':'保留标题','phase':'before','dialogue':'原台词'}
            return {'checks':[{'id':name,'passed':True,'evidence':'具体依据'} for name in CHECKS],'issues':[]}
        if request.get('repairFormat')=='json_patch':
            assert request['previousCandidate']['dialogue']=='原台词'
            return {'patches':[{'op':'replace','path':'/phase','value':'before'}]}
        return {'title':'保留标题','phase':'after','dialogue':'原台词'}
    def validate(value):
        if value['phase']!='before':raise DomainError('修正 phase','reference_phase',422)
        return value
    service=SimpleNamespace(s=store,settings=settings,llm=SimpleNamespace(json=generate))
    result=generate_reviewed(service,'p','shots','创作',{'source':'原文'},None,validate,session_scope='one')
    assert result['passed'] and len(result['attempts'])==2
    assert [role for role,_ in calls]==['shots','shots','reviewer']


@pytest.mark.parametrize('recover',[True,False])
def test_incomplete_review_does_not_rewrite_valid_candidate(tmp_path,recover):
    store=Store(tmp_path/'data');settings=Settings(store.root);calls=[]
    candidate={'title':'已经成立的场景','action':'阿青开盒'}
    def generate(project,role,system,request,**kwargs):
        calls.append(role)
        if role!='reviewer':return copy.deepcopy(candidate)
        if not recover or 'reviewRepair' not in request:
            return {'checks':[{'id':name,'passed':True,'evidence':' '} for name in CHECKS],'issues':[]}
        assert request['candidate']==candidate
        return {'checks':[{'id':name,'passed':True,'evidence':'已核对原文开盒动作与主体'} for name in CHECKS],'issues':[]}
    service=SimpleNamespace(s=store,settings=settings,llm=SimpleNamespace(json=generate))
    result=generate_reviewed(service,'p','shots','创作',{'source':'阿青开盒'},None,lambda x:x,session_scope='scene-one')
    assert result['passed']==recover and result['payload']==candidate
    assert calls==['shots','reviewer','reviewer']
    assert len(store.list('p','creative_review'))==2
    if not recover:assert any(x['code']=='review_incomplete' for x in result['issues'])
