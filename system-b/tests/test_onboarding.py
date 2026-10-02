import copy
import pytest
from fastapi.testclient import TestClient
from app.cinema import shot_count, render_dimensions
from app.core import DomainError
from app.reading_export import export_reading
from test_common import studio
from test_production import project


@pytest.mark.parametrize('preset', ['vertical', 'series', 'cinema'])
@pytest.mark.parametrize('aspect', ['16:9', '9:16', '1:1', '2.39:1'])
def test_aspect_is_independent_of_style_and_creation_has_no_cap_or_duration(studio, preset, aspect):
    with TestClient(studio, headers={'x-studio-client': 'local-ui'}) as c:
        response = c.post('/api/projects', json={'title': '自由启动', 'source': '他推开门。', 'preset': preset, 'aspectRatio': aspect})
        assert response.status_code == 200, response.text
        data = response.json()
        assert data['style']['aspectRatio'] == aspect
        assert data['project']['targetDuration'] is None
        assert 'budget' not in data['project'] and 'budget' not in data['cost']
        assert c.put('/api/projects/' + data['project']['id'], json={'title': '改名'}).status_code == 200


def test_content_first_path_reaches_storyboards_without_entering_seconds(studio):
    b = studio.state.service
    source = '他推开门。\n\n' + '她讲述自己离开故乡的原因，停顿后递给他一封信。' * 6
    p = b.create({'source': source, 'aspectRatio': '16:9', 'preset': 'vertical'})['project']['id']
    stage0 = b.propose(p, 'B0', {})
    assert all(s['targetDuration'] is None for s in stage0['payload']['scenes'])
    b.adopt_proposal(p, stage0['id'])
    st = b.style(p); b.finalize(p, 'style', st['id'], st['_version'])
    assert b.next_step(p)['stage'] == 'B1'
    stage1 = b.propose(p, 'B1', {})
    curves = stage1['payload']['curves']
    assert curves[0]['targetDuration'] < curves[1]['targetDuration']
    assert all(c['timingReason'] for c in curves)
    b.adopt_proposal(p, stage1['id'])
    assert b.s.get(p)['targetDuration'] is None
    assert b.s.get(p)['estimatedDuration'] == sum(c['targetDuration'] for c in curves)
    assets = b.propose(p, 'B2', {}); b.adopt_proposal(p, assets['id'])
    for master in b.list_active(p, 'master'): b.finalize(p, 'master', master['id'], master['_version'])
    for scene in b.list_active(p, 'scene'):
        direction = b.propose(p, 'B3', {'sceneId': scene['id']}); b.adopt_proposal(p, direction['id'])
        shots = b.propose(p, 'B4', {'sceneId': scene['id']}); b.adopt_proposal(p, shots['id'])
        planned = [s for s in b.list_active(p, 'shot') if s['sceneId'] == scene['id']]
        assert sum(s['duration'] for s in planned) == pytest.approx(scene['targetDuration'])
        assert len(planned) == shot_count(scene['targetDuration'], b.style(p))
    assert b.next_step(p)['state'] == 'complete'


def test_initial_split_never_silently_drops_later_paragraphs(studio):
    b = studio.state.service
    p = b.create({'source': '\n\n'.join('第%s段完整剧情' % i for i in range(15))})['project']['id']
    result = b.propose(p, 'B0', {})
    assert len(result['payload']['scenes']) == 15
    assert result['payload']['scenes'][-1]['sourceText'] == '第14段完整剧情'


def test_missing_timing_is_not_invented_by_director(studio):
    b = studio.state.service
    p = b.create({'source': '他推开门。'})['project']['id']
    proposal = b.propose(p, 'B0', {}); b.adopt_proposal(p, proposal['id'])
    style = b.style(p); b.finalize(p, 'style', style['id'], style['_version'])
    scene = b.list_active(p, 'scene')[0]
    with pytest.raises(DomainError, match='节奏'): b.propose(p, 'B3', {'sceneId': scene['id']})


def test_legacy_budget_cannot_block_media_or_subsequent_model_calls(project, monkeypatch):
    b, p, scene, master, shots = project
    record = b.s.get(p); record['budget'] = 0; b.s.put('project', record, p)
    b.settings.save({'media': {'provider': 'openai', 'imageCost': 100, 'priceConfigured': True},
                     'llm': {'provider': 'openai', 'baseUrl': 'https://unit.invalid/v1', 'model': 'test', 'priceConfigured': True}})
    plan = b.dry_run(p, {'shotIds': [shots[0]['id']], 'kind': 'keyframe', 'quality': 'proxy'})
    assert plan['estimatedCost'] == 100 and not plan['blocked']
    b.reserve(p, 'expensive-media', 1000)
    monkeypatch.setattr(b.llm, '_request', lambda *a: ('{"ok":true}', {'input': 20, 'output': 10}))
    assert b.llm.json(p, 'direction', 'check', {}) == {'ok': True}
    assert b.cost(p)['reserved'] == 1000


def test_reading_export_uses_selected_aspect(project):
    b, p, *_ = project
    style = b.style(p)
    style['aspectRatio'] = '9:16'
    data = b.get(p); data['style'] = style
    page = export_reading(data, 'B', b.s)
    assert 'aspect-ratio:9/16' in page and 'aspect-ratio:16/9' not in page


def test_legacy_budget_setting_is_removed_from_effective_configuration(studio):
    settings = studio.state.settings
    assert 'budget' not in settings.read()
    assert 'budget' not in settings.save({'budget': {'project': 0}})
    assert 'budget' not in settings.read()
