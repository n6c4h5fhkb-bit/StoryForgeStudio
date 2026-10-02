"""Offline A -> SceneExport v4 + legacy v2 -> B integration check, isolated under .validation.

Run with any Python: python tools/validate_handoff.py
The two applications run in separate subprocesses using their own .venv. Model
providers stay in demo mode and HTTP model requests are explicitly forbidden.
Render records are labelled fixtures; this check never generates paid media.
"""
from __future__ import annotations

import argparse
import copy
import json
import os
from pathlib import Path
import subprocess
import sys
import traceback
import uuid

REPOSITORY = Path(__file__).resolve().parents[1]
VALIDATION = REPOSITORY / '.validation'
MARKERS = ['她把车票折成四角，放进玻璃杯。', '末班车还没到，别急着说再见。', '话音落下，她转身背对出口。']


def write_json(path, value):
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2), encoding='utf-8')


def read_json(path):
    return json.loads(path.read_text(encoding='utf-8'))


def forbidden_request(*args, **kwargs):
    raise AssertionError('This validation must not send an HTTP model request')


def isolated_service(root, system):
    sys.path.insert(0, str(REPOSITORY / system))
    from app.core import Store
    from app.settings import Settings
    from app.llm import LLM
    store = Store(root / system / 'runtime')
    settings = Settings(store.root)
    assert settings.model('story' if system == 'system-a' else 'direction')['provider'] == 'demo'
    llm = LLM(store, settings)
    llm._request = forbidden_request
    if system == 'system-a':
        from app.story import StoryService
        return StoryService(store, settings, llm)
    from app.production import ProductionService
    return ProductionService(store, settings, llm, None, REPOSITORY / system)


def worker_a(root):
    service = isolated_service(root, 'system-a')
    p = service.create({'title': '跨平台验收：末班车', 'seed': '末班车到站前，两个人必须决定是否说出真相。', 'targetDuration': 48, 'compact': True})['project']['id']
    for step in range(30):
        result = service.advance(p, {'count': 2, 'candidateCount': 1})
        if result['state'] == 'complete':
            break
        assert result['state'] == 'awaiting_choice', result
        service.adopt(p, result['candidateIds'][0], approve_proposals=True)
    else:
        raise AssertionError('A did not reach a complete script within 30 choices')
    rows = service.readthrough(p)
    assert len(rows) == 4 and all(r['level'] == 'script' and not r['rough'] for r in rows)
    baseline = json.loads(service.export(p, 'scene-export')[0])
    assert baseline['schemaVersion'] == 4 and baseline['completeManifest']
    assert baseline['analysisCoverage'] and baseline['knowledgeSnapshot']
    target = baseline['scenes'][1]
    script = next(n for n in service.nodes(p) if n['parentId'] == target['sceneId'] and n['level'] == 'script' and n['status'] != 'archived')
    canon = copy.deepcopy(service.s.get(p)['canon'])
    hero = next(e['id'] for e in canon['entities'] if e['kind'] == 'character')
    belief = {'holder': hero, 'content': '车票已经被同伴换走', 'truth': False, 'validFrom': {'nodeId': target['sceneId'], 'boundary': 'entry'}, 'validUntil': {'nodeId': target['sceneId'], 'boundary': 'exit'}}
    canon['beliefs'].append(belief)
    service.update_canon(p, {'canon': canon})
    baseline = json.loads(service.export(p, 'scene-export')[0])
    write_json(root / 'a-baseline.json', baseline)
    (root / 'a-reading-before.md').write_text(service.export(p, 'md')[0], encoding='utf-8')

    # A deterministic local model fixture exercises the real candidate gate and
    # adoption path with a valid blocks-only, interleaved action/dialogue script.
    original_demo = service.demo_candidate
    def revised_demo(project, node, level, phase, index, data):
        output = original_demo(project, node, level, phase, index, data)
        if node and node['id'] == script['id']:
            output['items'][0]['body'] = {
                'sceneHeading': 'INT. 候车室 - 夜', 'action': '', 'dialogue': [], 'targetDuration': script['body']['targetDuration'],
                'blocks': [{'type': 'action', 'text': MARKERS[0]}, {'type': 'dialogue', 'character': hero, 'text': MARKERS[1]}, {'type': 'action', 'text': MARKERS[2]}],
            }
        return output
    service.demo_candidate = revised_demo
    revised = service.generate(p, {'nodeId': script['id'], 'op': 'polish', 'candidateCount': 1, 'instruction': '保留故事契约，以动作、对白、动作的顺序改写。'})
    assert not revised['allFailed'], revised
    service.adopt(p, revised['candidateIds'][0], approve_proposals=True)
    body_edit = json.loads(service.export(p, 'scene-export')[0])
    changed = [new['sceneId'] for old, new in zip(baseline['scenes'], body_edit['scenes']) if old['semanticHash'] != new['semanticHash']]
    assert changed == [target['sceneId']], changed
    after_text = service.readthrough(p)[1]['text']
    assert [after_text.index(marker) for marker in MARKERS] == sorted(after_text.index(marker) for marker in MARKERS)
    write_json(root / 'a-body-edit.json', body_edit)
    (root / 'a-reading-after.md').write_text(service.export(p, 'md')[0], encoding='utf-8')

    canon = copy.deepcopy(service.s.get(p)['canon'])
    next(b for b in canon['beliefs'] if b['content'] == belief['content'])['truth'] = True
    service.update_canon(p, {'canon': canon})
    knowledge_edit = json.loads(service.export(p, 'scene-export')[0])
    changed = [new['sceneId'] for old, new in zip(body_edit['scenes'], knowledge_edit['scenes']) if old['semanticHash'] != new['semanticHash']]
    assert changed == [target['sceneId']], changed
    write_json(root / 'a-knowledge-edit.json', knowledge_edit)
    metadata = {'projectId': p, 'sceneIds': [s['sceneId'] for s in baseline['scenes']], 'targetSceneId': target['sceneId'], 'heroId': hero, 'heroName': next(e['name'] for e in canon['entities'] if e['id'] == hero), 'markers': MARKERS, 'choices': step, 'scenes': 4, 'bodyChangeOnlyTarget': True, 'knowledgeChangeOnlyTarget': True}
    write_json(root / 'a-result.json', metadata)
    return metadata


def worker_b(root):
    service = isolated_service(root, 'system-b')
    from app.core import digest
    from app.reading_export import export_reading
    baseline = read_json(root / 'a-baseline.json')
    body_edit = read_json(root / 'a-body-edit.json')
    knowledge_edit = read_json(root / 'a-knowledge-edit.json')
    metadata = read_json(root / 'a-result.json')
    originals=[copy.deepcopy(x) for x in (baseline,body_edit,knowledge_edit)]
    # Exercise the unchanged v2 compatibility path explicitly.
    for package in (baseline,body_edit,knowledge_edit):
        package['schemaVersion']=2
        for key in ('storyDocument','source','versionFingerprint','continuityStatus'):package.pop(key,None)
    p = service.create({'title': '跨平台验收：末班车分镜', 'source': '使用 A 的完整剧本交换包', 'sourceType': 'script', 'targetDuration': 48, 'preset': 'vertical'})['project']['id']
    service.import_scene_export(p, baseline)
    style = service.style(p)
    service.finalize(p, 'style', style['id'], style['_version'])
    # Include B1's existing presentation so reimport cannot silently leave the
    # reading view showing an outdated adaptation instead of changed source.
    for stage in ('B1', 'B2'):
        proposal = service.propose(p, stage, {})
        service.adopt_proposal(p, proposal['id'])
    scenes = sorted(service.list_active(p, 'scene'), key=lambda s: s['order'])
    assert len(scenes) == 4
    for scene in scenes:
        for stage in ('B3', 'B4'):
            proposal = service.propose(p, stage, {'sceneId': scene['id']})
            service.adopt_proposal(p, proposal['id'])
    scenes = sorted(service.list_active(p, 'scene'), key=lambda s: s['order'])
    ids = {s['externalSceneId']: s['id'] for s in scenes}
    target_id = ids[metadata['targetSceneId']]
    shot_groups = {s['id']: sorted([sh for sh in service.list_active(p, 'shot') if sh['sceneId'] == s['id']], key=lambda sh: sh['order']) for s in scenes}
    target_shots = {sh['id'] for sh in shot_groups[target_id]}
    dependency_shot = shot_groups[scenes[2]['id']][0]['id']
    service.save(p, 'link', {'from': shot_groups[target_id][0]['id'], 'to': dependency_shot, 'type': 'frame_chain'})
    service.save(p, 'link', {'from': shot_groups[target_id][1]['id'], 'to': shot_groups[scenes[3]['id']][0]['id'], 'type': 'cut'})
    for shot in service.list_active(p, 'shot'):
        service.s.put('render', {'id': 'fixture_' + shot['id'], 'projectId': p, 'shotId': shot['id'], 'kind': 'keyframe', 'status': 'accepted', 'freshness': 'clean', 'freshnessNotes': [], 'selected': True, 'pinned': False, 'demo': True, 'fixtureOnly': True}, p)
    initial_shots = {s['id']: s for s in service.list_active(p, 'shot')}
    initial_masters = digest(service.list_active(p, 'master'))
    initial_knowledge = next(s for s in scenes if s['id'] == target_id)['narrativeContext']
    assert initial_knowledge == baseline['scenes'][1]['narrativeContext']
    assert initial_knowledge['knowledgeAtEntry'][0]['truth'] is False
    (root / 'b-reading-before.html').write_text(export_reading(service.get(p), 'B', service.s), encoding='utf-8')

    result = service.import_scene_export(p, body_edit)
    checks = []
    def check(name, condition, detail=None):
        checks.append({'name': name, 'passed': bool(condition), 'detail': detail})
    check('body import touches only changed source scene', result['sceneIds'] == [target_id], result)
    updated = service.s.get(target_id)
    check('all source blocks preserved', updated['body']['blocks'] == body_edit['scenes'][1]['body']['blocks'])
    positions = [updated['sourceText'].find(marker) for marker in MARKERS]
    check('source reading retains ordered actions and dialogue', all(i >= 0 for i in positions) and positions == sorted(positions), positions)
    check('dialogue preserves readable speaker name', metadata['heroName'] in updated['sourceText'])
    reading = export_reading(service.get(p), 'B', service.s)
    (root / 'b-reading-body-edit.html').write_text(reading, encoding='utf-8')
    check('reading copy shows changed source despite earlier B1 presentation', all(marker in reading for marker in MARKERS))
    check('local visual identities preserved', digest(service.list_active(p, 'master')) == initial_masters)
    check('scene identities preserved', {s['externalSceneId']: s['id'] for s in service.list_active(p, 'scene')} == ids)
    check('shot identities preserved', {s['id'] for s in service.list_active(p, 'shot')} == set(initial_shots))
    check('only target shot design marked opportunity', all(s['freshness'] == ('opportunity' if s['id'] in target_shots else 'clean') for s in service.list_active(p, 'shot')))
    affected_media = target_shots | {dependency_shot}
    check('body change affects target media and strong dependency only', all(r['freshness'] == ('opportunity' if r['shotId'] in affected_media else 'clean') for r in service.list_active(p, 'render')))
    check('character knowledge retained on body-only update', updated['narrativeContext'] == initial_knowledge)
    check('identical reimport produces no changed scenes', not service.import_scene_export(p, body_edit)['sceneIds'])

    result = service.import_scene_export(p, knowledge_edit)
    check('knowledge import touches only scoped source scene', result['sceneIds'] == [target_id], result)
    updated = service.s.get(target_id)
    check('updated belief truth reaches B', updated['narrativeContext'] == knowledge_edit['scenes'][1]['narrativeContext'] and updated['narrativeContext']['knowledgeAtEntry'][0]['truth'] is True)
    check('knowledge update invalidates only target direction', all(d['freshness'] == ('broken' if d['sceneId'] == target_id else 'clean') for d in service.list_active(p, 'direction')))
    check('knowledge update invalidates only target shot designs', all(s['freshness'] == ('broken' if s['id'] in target_shots else 'clean') for s in service.list_active(p, 'shot')))
    check('knowledge update invalidates strong dependent media', all(r['freshness'] == ('broken' if r['shotId'] in affected_media else 'clean') for r in service.list_active(p, 'render')))
    check('unrelated shot contents remain byte-equivalent', all(s == initial_shots[s['id']] for s in service.list_active(p, 'shot') if s['id'] not in target_shots))
    reading = export_reading(service.get(p), 'B', service.s)
    (root / 'b-reading-knowledge-edit.html').write_text(reading, encoding='utf-8')
    modern=service.create({'title':'v4 shooting handoff','source':'','workflowVersion':3})['project']['id']
    service.import_scene_export(modern,originals[0])
    film=service.propose_shooting(modern,{'mode':'cinema'})
    check('v4 film treatment reviewed',film['passed'],film.get('issues'))
    film_plan=service.shooting_adoption_plan(modern,film['id'])
    service.adopt_shooting(modern,film['id'],{'planHash':film_plan['planHash']})
    before=copy.deepcopy(service.list_active(modern,'scene'))
    imported=service.import_scene_export(modern,originals[1])
    check('new story version does not overwrite adopted B manuscript',service.list_active(modern,'scene')==before)
    fast=service.propose_shooting(modern,{'mode':'fast_drama'})
    check('v4 fast drama treatment reviewed',fast['passed'],fast.get('issues'))
    fast_plan=service.shooting_adoption_plan(modern,fast['id'])
    service.adopt_shooting(modern,fast['id'],{'planHash':fast_plan['planHash']})
    check('film and drama retained as separate versions',len(service.s.list(modern,'shooting_script'))==2)
    modern_scenes=service.list_active(modern,'scene')
    check('only changed shooting scene invalidated',sum(a['shootingHash']!=b['shootingHash'] for a,b in zip(before,modern_scenes))==1)
    for scene in modern_scenes:
        service.prepare_event_assets(modern,scene['id'])
        proposal=service.propose_director(modern,{'sceneId':scene['id']})
        check('v4 director proposal reviewed '+scene['id'],proposal['passed'],proposal.get('issues'))
        director_plan=service.director_adoption_plan(modern,proposal['id'])
        service.adopt_director(modern,proposal['id'],{'planHash':director_plan['planHash']})
        check('v4 adopted dialogue coverage '+scene['id'],service.validate_scene(modern,scene['id'])['passed'])
    (root/'b-v4-reading.html').write_text(export_reading(service.get(modern),'B',service.s),encoding='utf-8')
    report = {'passed': all(c['passed'] for c in checks), 'projectId': p, 'scenes': len(scenes), 'shots': len(initial_shots), 'paidRequests': 0, 'renderFixtures': True, 'checks': checks}
    write_json(root / 'b-result.json', report)
    return report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--worker', choices=('a', 'b'))
    parser.add_argument('--output-dir', type=Path)
    args = parser.parse_args()
    root = (args.output_dir or VALIDATION / ('handoff-' + uuid.uuid4().hex)).resolve()
    if not root.is_relative_to(VALIDATION.resolve()) or root == VALIDATION.resolve():
        parser.error('Output must be a dedicated child directory under this repository/.validation')
    root.mkdir(parents=True, exist_ok=True)
    if args.worker:
        result = worker_a(root) if args.worker == 'a' else worker_b(root)
        print(json.dumps({'worker': args.worker, 'passed': result.get('passed', True), 'scenes': result['scenes']}, ensure_ascii=False))
        return 0 if result.get('passed', True) else 1
    # A reused output path could contain a non-demo configuration. Require a new
    # directory for orchestration and never open any application data/settings.
    if any(root.iterdir()):
        parser.error('Output directory must be empty; select a fresh validation directory')
    statuses = []
    for worker, system in (('a', 'system-a'), ('b', 'system-b')):
        python = REPOSITORY / system / '.venv' / ('Scripts/python.exe' if os.name == 'nt' else 'bin/python')
        if not python.is_file():
            raise RuntimeError(f'Missing existing runtime: {python}')
        env = {k: v for k, v in os.environ.items() if not k.startswith('STUDIO_')}
        env.update(STUDIO_DATA=str(root / system / 'runtime'), PYTHONDONTWRITEBYTECODE='1', PYTHONUTF8='1')
        completed = subprocess.run([str(python), str(Path(__file__).resolve()), '--worker', worker, '--output-dir', str(root)], cwd=REPOSITORY / system, env=env, capture_output=True, text=True, encoding='utf-8', timeout=120, creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0))
        (root / f'{worker}-stdout.log').write_text(completed.stdout, encoding='utf-8')
        (root / f'{worker}-stderr.log').write_text(completed.stderr, encoding='utf-8')
        statuses.append({'worker': worker, 'exitCode': completed.returncode})
        if completed.returncode:
            break
    result = {'passed': len(statuses) == 2 and all(s['exitCode'] == 0 for s in statuses), 'outputDirectory': str(root), 'workers': statuses, 'offline': True}
    write_json(root / 'result.json', result)
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0 if result['passed'] else 1


if __name__ == '__main__':
    try:
        sys.exit(main())
    except Exception:
        traceback.print_exc()
        sys.exit(1)
