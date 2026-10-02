"""Offline executable fixture: emulate the documented Codex exec JSON protocol."""
import json
from pathlib import Path
import subprocess
import sys
import time
import uuid

args = sys.argv[1:]
cwd = Path.cwd()
request = json.loads(sys.stdin.buffer.read().decode('utf-8'))
saved = cwd / 'fixture-state.json'
prior = json.loads(saved.read_text(encoding='utf-8')) if 'resume' in args and saved.exists() else {}
thread = args[args.index('resume') + 1] if 'resume' in args else str(uuid.uuid4())
print(json.dumps({'type': 'thread.started', 'thread_id': thread}), flush=True)
calls = cwd / 'fixture-calls.jsonl'
with calls.open('a', encoding='utf-8') as f:
    f.write(json.dumps({'args': args, 'request': request, 'thread': thread}, ensure_ascii=False) + '\n')
if request['kind'] == 'snapshot':
    value = request['input']
else:
    value = prior['input']
    for op in request['patch']:
        parts = [s.replace('~1', '/').replace('~0', '~') for s in op['path'].lstrip('/').split('/')]
        if op['path'] == '':
            value = op['value']; continue
        parent = value
        for key in parts[:-1]:
            parent = parent[int(key)] if isinstance(parent, list) else parent[key]
        key = int(parts[-1]) if isinstance(parent, list) else parts[-1]
        if op['op'] == 'remove':
            del parent[key]
        else:
            parent[key] = op['value']
for binding in request.get('resultBindings', []):
    assert binding['path'] == '/context/previousCandidate'
    value['context']['previousCandidate'] = prior['lastResult']
context = value['context']
mode = context.get('fixtureMode') if isinstance(context, dict) else None
if mode == 'error':
    print(json.dumps({'type': 'turn.failed', 'error': {'message': '401 unauthorized SECRET_MUST_NOT_LEAK'}}), flush=True)
    sys.exit(1)
if mode == 'slow':
    marker = str(cwd / 'orphan-marker.txt')
    subprocess.Popen([sys.executable, '-c', 'import time;from pathlib import Path;time.sleep(2);Path(' + repr(marker) + ').write_text("orphan")'])
    time.sleep(20)
if mode == 'delay':
    time.sleep(.3)
output = {'context': context, 'thread': thread}
payload = 'not json' if mode == 'invalid' else json.dumps(output, ensure_ascii=False)
result = {'payload': payload, 'inputHash': request['inputHash']}
if mode == 'stale' or (mode == 'lost_context' and request['kind'] == 'delta'):
    result['inputHash'] = 'old-context'
Path(args[args.index('--output-last-message') + 1]).write_text(json.dumps(result, ensure_ascii=False), encoding='utf-8')
turns = prior.get('turns', 0) + 1
usage = {'input_tokens': turns * 1000, 'output_tokens': turns * 50,
         'cached_input_tokens': max(0, turns - 1) * 800, 'reasoning_output_tokens': turns * 20}
saved.write_text(json.dumps({'input': value, 'turns': turns, 'lastResult': output}), encoding='utf-8')
print(json.dumps({'type': 'turn.completed', 'usage': usage}), flush=True)
