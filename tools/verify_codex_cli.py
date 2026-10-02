"""Small live text-only CLI test in an isolated data directory, no media calls."""
import argparse
import json
from pathlib import Path
import sys
import uuid

parser = argparse.ArgumentParser()
parser.add_argument('--system', choices=['system-a', 'system-b'], required=True)
parser.add_argument('--checkpoint', action='store_true')
options = parser.parse_args()
root = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(root / options.system))
from app.core import Store
from app.settings import Settings
from app.llm import LLM
from app.codex_cli import status

store = Store(root / '.validation' / ('codex-' + options.system + '-' + uuid.uuid4().hex[:8]))
settings = Settings(store.root)
settings.save({'llm': {'provider': 'codex_cli', 'timeout': 600}})
print(json.dumps({'data': str(store.root), 'status': status(settings.model('script'))}, ensure_ascii=False), flush=True)
llm = LLM(store, settings)
project = 'smoke'
system = '只按当前任务材料返回 JSON {title:string,prop:string,result:string}。prop 必须是当前 source 中的道具名称。result 写一行对应 instruction 的可表演动作，不补人物背景。'
source = {'characters': ['阿青', '小林'], 'location': '车站', 'prop': '蓝色雨伞',
          'facts': ['阿青持有雨伞。', '小林在门口等她。'] * 20}
request = {'source': source, 'instruction': '阿青把雨伞交给小林。'}
schema = {'type': 'object', 'properties': {k: {'type': 'string'} for k in ('title', 'prop', 'result')}, 'required': ['title', 'prop', 'result']}
first = llm.json(project, 'script', system, request, schema=schema, cache=True, session_scope='smoke')
print(json.dumps({'first': first}, ensure_ascii=False), flush=True)
second_request = {**request, 'instruction': '改为阿青把雨伞挂在门边，小林没有接。'}
second = llm.json(project, 'script', system, second_request, schema=schema, cache=True, session_scope='smoke')
cached = llm.json(project, 'script', system, second_request, schema=schema, cache=True, session_scope='smoke')
runs = store.list(project, 'run')
assert first['prop'] == second['prop'] == '蓝色雨伞'
assert second == cached and runs[-1]['cacheHit']
assert runs[0]['codex']['threadId'] == runs[1]['codex']['threadId']
assert runs[1]['codex']['contextMode'] == 'delta' and runs[1]['codex']['resumed']
assert len(store.list(project, 'codex_session')) == 1
checkpoint_result = None
if options.checkpoint:
    from app.codex_cli import MAX_DELTA_TURNS
    row = store.list(project, 'codex_session')[0]
    row['deltaTurns'] = MAX_DELTA_TURNS
    store.put('codex_session', row, project)
    changed = {'source': {'characters':['阿青','小林'],'location':'车站','prop':'红色手提箱',
                         'facts':['旧雨伞已离场。小林独自提着红色手提箱。']},
               'instruction':'小林把当前道具放到车站长椅上。'}
    checkpoint_result = llm.json(project,'script',system,changed,schema=schema,cache=True,session_scope='smoke')
    assert checkpoint_result['prop'] == '红色手提箱'
    checkpoint_run = store.list(project,'run')[-1]
    assert checkpoint_run['codex']['threadId'] == runs[0]['codex']['threadId']
    assert checkpoint_run['codex']['contextMode'] == 'snapshot' and checkpoint_run['codex']['checkpointReason'] == 'maintenance'
    assert llm.json(project,'script',system,changed,schema=schema,cache=True,session_scope='smoke') == checkpoint_result
    assert store.list(project,'run')[-1]['cacheHit']
    runs = store.list(project,'run')
report = {'system': options.system, 'passed': True, 'first': first, 'second': second,
          'checkpoint': checkpoint_result,
          'runs': [{k: r.get(k) for k in ('status', 'cacheHit', 'usage', 'rawUsage', 'costKnown', 'billingMode', 'codex')} for r in runs]}
(store.root / 'verification.json').write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding='utf-8')
print(json.dumps(report, ensure_ascii=False), flush=True)
