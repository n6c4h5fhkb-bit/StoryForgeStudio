import json
import httpx,pytest
from app.llm import LLM,parse_json
from app.core import DomainError
from test_common import studio

@pytest.mark.parametrize('text',[r'{"ok":true}','```json\n{"ok":true}\n```','Here is the answer: {"ok":true}'])
def test_json_parsing(text):assert parse_json(text)=={'ok':True}

@pytest.mark.parametrize('provider,endpoint',[('openai','/v1/chat/completions'),('anthropic','/v1/messages'),('gemini','/v1/models/test:generateContent')])
def test_direct_http_protocol_request_and_usage(studio,monkeypatch,provider,endpoint):
    st=studio.state.settings;st.save({'llm':{'provider':provider,'baseUrl':'https://unit.invalid/v1','model':'test','apiKey':'test-secret','priceConfigured':True,'inputPerMillion':1,'outputPerMillion':2}})
    seen=[];original=httpx.Client
    def handler(request):
        seen.append(request);body=json.loads(request.content);assert request.url.path==endpoint
        assert 'test-secret' in ' '.join(request.headers.values())
        if provider=='anthropic':payload={'content':[{'type':'text','text':'{"ok":true}'}],'usage':{'input_tokens':20,'output_tokens':10}}
        elif provider=='gemini':payload={'candidates':[{'content':{'parts':[{'text':'{"ok":true}'}]}}],'usageMetadata':{'promptTokenCount':20,'candidatesTokenCount':10}}
        else:payload={'choices':[{'message':{'content':'{"ok":true}'},'finish_reason':'stop'}],'usage':{'prompt_tokens':20,'completion_tokens':10}}
        return httpx.Response(200,json=payload)
    monkeypatch.setattr('app.llm.httpx.Client',lambda **kwargs:original(transport=httpx.MockTransport(handler),**kwargs))
    model=LLM(studio.state.store,st);schema={'type':'object','properties':{'ok':{'type':'boolean'}},'required':['ok']}
    assert model.json('p','story','Test',{'test':1},schema,cache=True)=={'ok':True}
    assert model.json('p','story','Test',{'test':1},schema,cache=True)=={'ok':True}
    assert len(seen)==1
    run=studio.state.store.list('p','run')[0];assert run['usage']['input']==20 and run['usage']['output']==10
    assert run['cost']==pytest.approx(.00004)
    cached=studio.state.store.list('p','run')[1]
    assert cached['cacheHit'] and cached['cost']==0 and cached['sourceRunId']==run['id']
    assert run['rawUsage']

def test_invalid_json_still_records_charged_usage(studio,monkeypatch):
    st=studio.state.settings;st.save({'llm':{'provider':'openai','baseUrl':'https://unit.invalid/v1','model':'test','priceConfigured':True,'inputPerMillion':1,'outputPerMillion':2}})
    model=LLM(studio.state.store,st);monkeypatch.setattr(model,'_request',lambda *a:('not json',{'input':50,'output':20}))
    with pytest.raises(DomainError):model.json('p','story','Test',{},schema={'type':'object'})
    run=studio.state.store.list('p','run')[0];assert run['status']=='failed' and run['cost']==pytest.approx(.00009)
    assert all(h['status']=='settled' for h in studio.state.store.list('p','llm_hold'))

def test_live_model_requires_price_confirmation(studio):
    st=studio.state.settings;st.save({'llm':{'provider':'openai','baseUrl':'https://unit.invalid/v1','model':'test','priceConfigured':False}})
    with pytest.raises(DomainError,match='单价'):LLM(studio.state.store,st).json('p','story','Test',{})

@pytest.mark.parametrize('config',[{'llm':{'inputPerMillion':-1}},{'media':{'imageCost':-1}},{'budget':{'project':-1}}])
def test_negative_cost_settings_rejected(studio,config):
    with pytest.raises(DomainError):studio.state.settings.save(config)
