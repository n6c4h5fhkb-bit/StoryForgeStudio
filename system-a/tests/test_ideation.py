import copy
from concurrent.futures import ThreadPoolExecutor
import pytest
from fastapi.testclient import TestClient
from app.core import DomainError
from app.ideation import IdeationService, SCOPE
from test_common import studio
from test_reader_api import settled


def test_zero_input_brainstorm_select_and_continue(studio):
    with TestClient(studio, headers={'x-studio-client': 'local-ui'}) as client:
        assert client.get('/api/brainstorms').json()['batches'] == []
        request = {'operationId': 'first-empty-brainstorm'}
        first = client.post('/api/brainstorms', json=request)
        repeated = client.post('/api/brainstorms', json=request)
        assert first.json()['id'] == repeated.json()['id']
        batch = settled(client, first)
        assert batch['demo'] and len(batch['ideas']) == 4
        assert client.get('/api/projects').json() == []
        assert len(studio.state.store.list(SCOPE, 'run')) == 1
        # Reloading is read-only: the first paid call is not repeated.
        assert client.get('/api/brainstorms').json()['batches'][0]['id'] == batch['id']
        assert len(studio.state.store.list(SCOPE, 'run')) == 1
        idea = batch['ideas'][0]
        url = f"/api/brainstorms/{batch['id']}/ideas/{idea['id']}/adopt"
        result = client.post(url, json={})
        assert result.status_code == 200, result.text
        project = result.json()['project']
        assert project['title'] == idea['title'] and idea['premise'] in project['seed']
        assert idea['hook'] in project['seed'] and idea['conflict'] in project['seed']
        assert client.post(url, json={}).json()['project']['id'] == project['id']
        assert len(client.get('/api/projects').json()) == 1
        next_result = settled(client, client.post('/api/projects/' + project['id'] + '/advance', json={}))
        assert len(next_result['candidateIds']) == 3


def test_reroll_and_branch_use_model_with_stored_context(studio, monkeypatch):
    service = IdeationService(studio.state.service)
    first = service.generate({})
    original = service.llm.json
    calls = []
    def spy(project, role, system, user, **kw):
        calls.append((project, role, copy.deepcopy(user), kw['cache']))
        return original(project, role, system, user, **kw)
    monkeypatch.setattr(service.llm, 'json', spy)
    second = service.generate({'mode': 'fast_drama', 'preferences': '只要都市悬疑', 'operationId': 'fresh-round'})
    branch = service.generate({'anchor': {'batchId': first['id'], 'ideaId': first['ideas'][1]['id']}})
    assert second['id'] != first['id']
    assert {i['title'] for i in first['ideas']}.isdisjoint(i['title'] for i in second['ideas'])
    assert calls[0][0:2] == (SCOPE, 'ideation')
    assert calls[0][2]['preferences'] == '只要都市悬疑' and calls[0][2]['previousIdeas']
    assert calls[0][3] is True
    assert calls[1][2]['anchor']['premise'] == first['ideas'][1]['premise']
    assert branch['anchor']['ideaId'] == first['ideas'][1]['id']


def test_failed_model_does_not_create_fake_topics_or_projects(studio, monkeypatch):
    service = IdeationService(studio.state.service)
    def fail(*args, **kwargs):
        raise DomainError('服务连接失败', 'provider_error', 502)
    monkeypatch.setattr(service.llm, 'json', fail)
    with pytest.raises(DomainError): service.generate({})
    assert service.batches() == []
    assert studio.state.store.list(kind='project') == []


def test_concurrent_selection_only_creates_one_project(studio):
    service = IdeationService(studio.state.service)
    batch = service.generate({})
    with ThreadPoolExecutor(max_workers=2) as pool:
        projects = list(pool.map(lambda _: service.adopt(batch['id'], batch['ideas'][0]['id']), range(2)))
    assert projects[0]['project']['id'] == projects[1]['project']['id']
    assert len(studio.state.store.list(kind='project')) == 1


def test_ideation_uses_configured_structure_model_and_explicit_override(studio):
    settings = studio.state.settings
    settings.save({'models': {'structure': {'model': 'story-model'}}})
    assert settings.model('ideation')['model'] == 'story-model'
    settings.save({'models': {'ideation': {'model': 'idea-model'}}})
    assert settings.model('ideation')['model'] == 'idea-model'


def test_partial_ideation_configuration_retains_inherited_model(studio):
    settings = studio.state.settings
    settings.save({'models': {'structure': {'model': 'story-model', 'maxTokens': 4000}}})
    settings.save({'models': {'ideation': {'maxTokens': 5000}}})
    assert settings.model('ideation')['model'] == 'story-model'
    assert settings.model('ideation')['maxTokens'] == 5000


def test_live_ideation_uses_provider_output_without_seed(studio, monkeypatch):
    service = IdeationService(studio.state.service)
    fixture = service.generate({})
    output = {'ideas': [{k: v for k, v in i.items() if k != 'id'} for i in fixture['ideas']]}
    for i, idea in enumerate(output['ideas']): idea['title'] = '真实协议返回的选题 ' + str(i)
    studio.state.settings.save({'llm': {'provider': 'openai', 'baseUrl': 'https://unit.invalid/v1', 'model': 'test', 'priceConfigured': True}})
    import json
    seen = []
    def provider(cfg, system, user, schema, images):
        seen.append(user)
        return json.dumps(output, ensure_ascii=False), {'input': 100, 'output': 100}
    monkeypatch.setattr(service.llm, '_request', provider)
    batch = service.generate({})
    assert not batch['demo'] and batch['ideas'][0]['title'] == '真实协议返回的选题 0'
    assert len(seen) == 1 and seen[0]['anchor'] is None and seen[0]['preferences'] == ''
