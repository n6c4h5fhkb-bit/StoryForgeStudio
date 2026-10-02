import copy, json, threading, time
from concurrent.futures import ThreadPoolExecutor
from types import SimpleNamespace
import httpx, pytest
from app.core import DomainError, Jobs, Store
from app.llm import LLM
from app.settings import Settings


def test_independent_review_inherits_validator_model_and_costs(tmp_path):
    settings=Settings(tmp_path)
    settings.save({'models':{'validator':{'provider':'openai','model':'review-model','baseUrl':'https://review.invalid/v1','inputPerMillion':1.2,'outputPerMillion':4,'priceConfigured':True}}})
    review=settings.model('reviewer')
    assert review['model']=='review-model' and review['inputPerMillion']==1.2 and review['priceConfigured']
    settings.save({'models':{'reviewer':{'model':'explicit-reviewer'}}})
    assert settings.model('reviewer')['model']=='explicit-reviewer'


@pytest.fixture
def studio(tmp_path):
    root=tmp_path/'runtime';store=Store(root);jobs=Jobs(store)
    yield SimpleNamespace(state=SimpleNamespace(store=store,settings=Settings(root),jobs=jobs))
    jobs.pool.shutdown(wait=True,cancel_futures=True)


def configure(studio, **patch):
    studio.state.settings.save({'llm': {'provider':'openai','baseUrl':'https://unit.invalid/v1','model':'test',
        'priceConfigured':True,'inputPerMillion':1,'outputPerMillion':2,**patch}})
    return LLM(studio.state.store, studio.state.settings)


def transport(monkeypatch, payload):
    original=httpx.Client
    monkeypatch.setattr('app.llm.httpx.Client',lambda **kwargs:original(transport=httpx.MockTransport(lambda request:httpx.Response(200,json=payload)),**kwargs))


@pytest.mark.parametrize('field,value', [('max_tokens',20000),('max_completion_tokens',20000),('model','expensive'),
    ('messages',[]),('system','replacement'),('contents',[]),('generationConfig',{'maxOutputTokens':20000}),('n',10),('tools',[])])
def test_extra_body_cannot_bypass_reserved_request(studio,field,value):
    with pytest.raises(DomainError) as error:
        configure(studio,extraBody={field:value})
    assert error.value.code=='unsafe_extra_body'
    assert studio.state.store.list('p','llm_hold')==[]


@pytest.mark.parametrize('patch',[{'provider':'unknown'},{'timeout':-1},{'maxTokens':float('inf')},{'temperature':float('nan')},{'cachedInputPerMillion':-1}])
def test_role_override_validated(studio,patch):
    with pytest.raises(DomainError):studio.state.settings.save({'models':{'story':patch}})


def test_existing_unsafe_config_is_rechecked_before_submission(studio,monkeypatch):
    model=configure(studio);config=studio.state.settings.model('story')
    config['extraBody']={'max_tokens':999999}
    monkeypatch.setattr(studio.state.settings,'model',lambda role:config)
    monkeypatch.setattr(model,'_request',lambda *args:pytest.fail('must not send unsafe request'))
    with pytest.raises(DomainError) as error:model.json('p','story','Test',{})
    assert error.value.code=='unsafe_extra_body'
    assert studio.state.store.list('p','llm_hold')==[]


def test_model_and_endpoint_changes_require_new_price_confirmation(studio):
    configure(studio)
    settings=studio.state.settings
    settings.save({'llm':{'model':'different'}})
    assert not settings.model('story')['priceConfigured']
    settings.save({'llm':{'priceConfigured':True}})
    assert settings.model('story')['priceConfigured']
    settings.save({'models':{'story':{'model':'premium'}}})
    assert not settings.model('story')['priceConfigured']
    settings.save({'models':{'story':{'priceConfigured':True}}})
    assert settings.model('story')['priceConfigured']
    settings.save({'llm':{'baseUrl':'https://other.invalid/v1'}})
    assert not settings.model('story')['priceConfigured']


def test_first_role_form_save_keeps_inherited_secret_and_explicit_price(studio):
    configure(studio,apiKey='unit-base-secret')
    settings=studio.state.settings
    patch={'models':{'script':{'provider':'openai','model':'premium','baseUrl':'https://unit.invalid/v1',
          'apiKey':'__KEEP__','maxTokens':8000,'contextCharacters':32000,
          'inputPerMillion':3,'outputPerMillion':15,'priceConfigured':True}}}
    original=copy.deepcopy(patch)
    saved=settings.save(patch)
    model=settings.model('script')
    assert model['apiKey']=='unit-base-secret' and model['priceConfigured']
    assert 'apiKey' not in saved['models']['script']
    assert patch==original
    settings.save({'llm':{'apiKey':'unit-rotated-secret'}})
    assert settings.model('script')['apiKey']=='unit-rotated-secret'


def test_optional_cache_prices_can_be_cleared_and_do_not_follow_different_models(studio):
    configure(studio,cachedInputPerMillion=.1,cacheWritePerMillion=1.25)
    settings=studio.state.settings
    settings.save({'models':{'script':{'model':'premium','inputPerMillion':3,'outputPerMillion':15,'priceConfigured':True}}})
    assert 'cachedInputPerMillion' not in settings.model('script')
    assert 'cacheWritePerMillion' not in settings.model('script')
    settings.save({'models':{'script':{'cachedInputPerMillion':.3}}})
    assert settings.model('script')['cachedInputPerMillion']==.3
    settings.save({'models':{'script':{'cachedInputPerMillion':None}}})
    assert 'cachedInputPerMillion' not in settings.model('script')
    saved=settings.save({'llm':{'cachedInputPerMillion':None,'cacheWritePerMillion':None}})
    assert 'cachedInputPerMillion' not in saved['llm'] and 'cacheWritePerMillion' not in saved['llm']
    settings.save({'llm':{'cachedInputPerMillion':.1}})
    settings.save({'llm':{'model':'another','priceConfigured':True}})
    assert 'cachedInputPerMillion' not in settings.model('story')


def test_anthropic_cached_usage_priced_and_preserved(studio,monkeypatch):
    model=configure(studio,provider='anthropic',cachedInputPerMillion=.1,cacheWrite5mPerMillion=1.25,cacheWrite1hPerMillion=2)
    raw={'input_tokens':10,'output_tokens':20,'cache_read_input_tokens':2000,'cache_creation_input_tokens':1000,
         'cache_creation':{'ephemeral_5m_input_tokens':600,'ephemeral_1h_input_tokens':400}}
    transport(monkeypatch,{'content':[{'type':'text','text':'{"ok":true}'}],'usage':raw})
    model.json('p','story','Test',{})
    run=studio.state.store.list('p','run')[0]
    assert run['rawUsage']==raw
    assert run['usage']['input']==3010
    assert run['cost']==pytest.approx((10+40+200+750+800)/1e6)
    assert run['costKnown'] and not run['costEstimated']


def test_missing_cache_price_is_an_estimate(studio,monkeypatch):
    model=configure(studio,provider='anthropic')
    transport(monkeypatch,{'content':[{'type':'text','text':'{"ok":true}'}],
                          'usage':{'input_tokens':10,'output_tokens':20,'cache_read_input_tokens':2000,'cache_creation_input_tokens':1000}})
    model.json('p','story','Test',{})
    run=studio.state.store.list('p','run')[0]
    assert run['cost']==pytest.approx((10+40+2000+2000)/1e6)
    assert not run['costKnown'] and run['costEstimated']


def test_openai_cached_input_is_a_subset_and_reasoning_not_double_charged(studio,monkeypatch):
    model=configure(studio,cachedInputPerMillion=.1)
    transport(monkeypatch,{'choices':[{'message':{'content':'{"ok":true}'}}],
        'usage':{'prompt_tokens':100,'completion_tokens':50,'prompt_tokens_details':{'cached_tokens':80},'completion_tokens_details':{'reasoning_tokens':30}}})
    model.json('p','story','Test',{})
    run=studio.state.store.list('p','run')[0]
    assert run['cost']==pytest.approx((20+8+100)/1e6)
    assert run['usage']['reasoning']==30 and run['usage']['output']==50


def test_gemini_thinking_is_counted_in_billable_output(studio,monkeypatch):
    model=configure(studio,provider='gemini',cachedInputPerMillion=.1)
    transport(monkeypatch,{'candidates':[{'content':{'parts':[{'text':'{"ok":true}'}]}}],
        'usageMetadata':{'promptTokenCount':100,'candidatesTokenCount':20,'thoughtsTokenCount':30,'cachedContentTokenCount':80}})
    model.json('p','story','Test',{})
    run=studio.state.store.list('p','run')[0]
    assert run['usage']['output']==50 and run['cost']==pytest.approx((20+8+100)/1e6)


def test_missing_usage_keeps_reservation_as_estimate(studio,monkeypatch):
    model=configure(studio)
    transport(monkeypatch,{'choices':[{'message':{'content':'{"ok":true}'}}]})
    model.json('p','story','Test',{})
    run=studio.state.store.list('p','run')[0]
    assert run['cost']==studio.state.store.list('p','llm_hold')[0]['estimate']
    assert run['cost']>0 and not run['costKnown']


def test_truncation_preserves_actual_usage_before_raising(studio,monkeypatch):
    model=configure(studio)
    transport(monkeypatch,{'choices':[{'message':{'content':'{"ok":'},'finish_reason':'length'}],
        'usage':{'prompt_tokens':100,'completion_tokens':50}})
    with pytest.raises(DomainError) as error:model.json('p','story','Test',{})
    assert error.value.code=='truncated_output'
    run=studio.state.store.list('p','run')[0]
    assert run['cost']==pytest.approx(.0002) and run['rawUsage']['completion_tokens']==50


def test_same_key_singleflight_and_cache_provenance(studio,monkeypatch):
    model=configure(studio);store=studio.state.store;calls=[];barrier=threading.Barrier(2);guard=threading.Lock();lookups=0
    original=store.cached
    def cached(key):
        nonlocal lookups
        with guard:lookups+=1;number=lookups
        result=original(key)
        if number<=2:barrier.wait(timeout=5)
        return result
    monkeypatch.setattr(store,'cached',cached)
    def request(*args):calls.append(1);return '{"ok":true}',{'input':20,'output':10}
    monkeypatch.setattr(model,'_request',request)
    with ThreadPoolExecutor(2) as pool:
        values=list(pool.map(lambda _:model.json('p','story','same',{},cache=True),range(2)))
    assert values==[{'ok':True},{'ok':True}] and len(calls)==1
    runs=store.list('p','run');source=next(r for r in runs if not r['cacheHit']);hit=next(r for r in runs if r['cacheHit'])
    assert hit['sourceRunId']==source['id'] and hit['cost']==0
    assert len([e for e in store.events(project='p') if e['type']=='model_completed'])==2


def test_creative_requests_are_fresh_and_project_cache_isolated(studio,monkeypatch):
    model=configure(studio);calls=[]
    def request(*args):calls.append(1);return json.dumps({'take':len(calls)}),{'input':20,'output':10}
    monkeypatch.setattr(model,'_request',request)
    assert model.json('p','story','same',{})!=model.json('p','story','same',{})
    first=model.json('p','story','same',{},cache=True)
    assert model.json('p','story','same',{},cache=True)==first
    assert model.json('q','story','same',{},cache=True)!=first


def test_provider_concurrency_bound(studio,monkeypatch):
    model=configure(studio);studio.state.settings.save({'llmConcurrency':{'openai':1}})
    active=peak=0;lock=threading.Lock()
    def request(*args):
        nonlocal active,peak
        with lock:active+=1;peak=max(active,peak)
        time.sleep(.03)
        with lock:active-=1
        return '{"ok":true}',{'input':20,'output':10}
    monkeypatch.setattr(model,'_request',request)
    with ThreadPoolExecutor(4) as pool:list(pool.map(lambda i:model.json('p','story','test',{'i':i}),range(4)))
    assert peak==1


def test_job_idempotency_survives_new_jobs_instance_and_rejects_changed_input(studio):
    jobs=studio.state.jobs;calls=[]
    def work(progress,check):calls.append(1);return {'ok':True}
    first=jobs.submit('p','generate',{'take':1},work,operation_id='operation-1')
    jobs.pool.shutdown(wait=True)
    restarted=Jobs(studio.state.store)
    try:
        duplicate=restarted.submit('p','generate',{'take':1},work,operation_id='operation-1')
        assert first['id']==duplicate['id'] and len(calls)==1
        with pytest.raises(DomainError) as error:restarted.submit('p','generate',{'take':2},work,operation_id='operation-1')
        assert error.value.code=='idempotency_conflict'
        new=restarted.submit('p','generate',{'take':2},work,operation_id='operation-2')
        assert new['id']!=first['id']
    finally:restarted.pool.shutdown(wait=True)


def test_concurrent_duplicate_job_submissions_execute_once(studio):
    jobs=studio.state.jobs;calls=[];release=threading.Event()
    def work(progress,check):calls.append(1);assert release.wait(5);return {'ok':True}
    try:
        with ThreadPoolExecutor(3) as pool:
            results=list(pool.map(lambda _:jobs.submit('p','generate',{'take':1},work,operation_id='double-click'),range(3)))
        assert len({result['id'] for result in results})==1
    finally:release.set();jobs.pool.shutdown(wait=True)
    assert len(calls)==1
