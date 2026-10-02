"""Real CLI inference through the production creative/review workflows, isolated."""
import argparse
import json
import os
from pathlib import Path
import sys
import uuid

parser = argparse.ArgumentParser()
parser.add_argument('--system', choices=['system-a', 'system-b'], required=True)
parser.add_argument('--resume-director', help='Existing isolated B validation directory')
args = parser.parse_args()
root = Path(__file__).resolve().parents[1]
runtime = Path(args.resume_director).resolve() if args.resume_director else root / '.validation' / ('codex-workflow-' + args.system + '-' + uuid.uuid4().hex[:8])
assert runtime.is_relative_to(root / '.validation')
os.environ['STUDIO_DATA'] = str(runtime)
sys.path.insert(0, str(root / args.system))
from app.main import app

service = app.state.service
settings = app.state.settings
settings.save({'llm': {'provider': 'codex_cli', 'timeout': 600, 'contextCharacters': 64000}})
text = '第一章 雨伞\n车站门口下着雨。阿青拿着一把合拢的蓝色长柄雨伞，小林空着手站在她面前。阿青把雨伞递给小林，小林接稳后，阿青才松手。阿青说：“到了给我消息。”小林点头，握着合拢的雨伞走出车站。'
report = {'system': args.system, 'data': str(runtime), 'checks': []}

def progress(_, message):
    print(message, flush=True)

try:
    if args.system == 'system-a':
        from app.novel import NovelService
        novel = NovelService(service)
        p = novel.create({'title': 'CLI 实测：雨伞', 'text': text})['project']['id']
        draft = novel.propose(p, {}, progress=progress)
        report['checks'].append({'task': 'novel_adaptation_and_review', 'passed': draft['passed'], 'issues': draft['issues']})
        assert draft['passed'], draft['issues']
        novel.adopt(p, draft['id'])
        report['checks'].append({'task': 'adoption', 'passed': True})
    elif args.resume_director:
        p = app.state.store.list(kind='project')[0]['id']
        scene = service.list_active(p, 'scene')[0]
        proposal = service.propose_director(p, {'sceneId': scene['id'], 'instruction':
            '保持已采用拍摄版的事件、人物和道具事实，只修正分镜接口与连续性标注：references.entityId 用 entities 的故事实体 ID，subjects 用 assetMap 的素材 ID。镜头物理灯光继承 direction.lighting。对视时 eyeline 使用 left/right/forward；小林转身向出口离开时，明确设置 continuity.intentionalGazeBreak=true 并写 gazeBreakReason，不要把动作描述塞进 eyeline 的方向值。不要为通过校验删掉原本的交接、叮嘱、点头或离开。'}, progress=progress)
        report['checks'].append({'task': 'focused_director_recovery', 'passed': proposal['passed'], 'issues': proposal['issues']})
        assert proposal['passed'], proposal['issues']
        service.adopt_director(p, proposal['id'])
    else:
        p = service.create({'title': 'CLI 实测：雨伞', 'source': text, 'workflowVersion': 2})['project']['id']
        for mode in ('cinema', 'fast_drama'):
            candidate = service.propose_shooting(p, {'mode': mode, 'instruction': '保持一次雨伞交接，勿增加其他人物、道具或重大情节。体现当前方向的呈现差异。'}, progress=progress)
            report['checks'].append({'task': mode + '_conversion_and_review', 'passed': candidate['passed'], 'issues': candidate['issues']})
            assert candidate['passed'], candidate['issues']
            service.adopt_shooting(p, candidate['id'])
        out = service.advance(p, {'mode': 'until_choice'}, progress=progress)
        report['checks'].append({'task': 'direction_and_shots', 'passed': out['proposal']['passed'], 'issues': out['proposal']['issues']})
        assert out['proposal']['passed'], out['proposal']['issues']
        service.adopt_proposal(p, out['proposal']['id'])
    report['project'] = p
    report['passed'] = True
except Exception as exc:
    report.update(passed=False, error=str(exc), code=getattr(exc, 'code', None))
    raise
finally:
    rows = app.state.store.list(kind='run')
    report['runs'] = [{k: r.get(k) for k in ('role', 'status', 'cacheHit', 'usage', 'codex', 'error')} for r in rows]
    (runtime / ('recovery-verification.json' if args.resume_director else 'verification.json')).write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding='utf-8')
    print(json.dumps(report, ensure_ascii=False), flush=True)
    app.state.jobs.pool.shutdown(wait=True, cancel_futures=True)
