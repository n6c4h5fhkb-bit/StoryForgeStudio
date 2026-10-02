"""Executable fixtures used by the runner admission test, not production rendering."""
import json,sys,time
from pathlib import Path
from PIL import Image
p=Path(sys.argv[1]);task=json.loads(p.read_text(encoding='utf-8'));work=Path(task['workdir']);case=task['inputs'].get('case','normal');prompt=task['inputs'].get('prompt','test')
result={'status':'ok','artifacts':[],'report':{'actions':['fixture:'+case],'actualPrompt':prompt,'notes':''},'usage':{'tokens':0,'cost':0,'wallTime':0,'turns':1},'runner':{}}
if case=='timeout':time.sleep(12)
elif case=='budget':
 print(json.dumps({'type':'turn.completed','usage':{'cost':9}}),flush=True);time.sleep(3)
elif case=='turns':
 for i in range(10):print(json.dumps({'type':'turn.started','turn':i}),flush=True);time.sleep(.15)
elif case=='reject':result['status']='rejected';result['report']['failureClass']='policy';result['report']['notes']='任务请求写入白名单外的内容，拒绝。'
elif case=='cli_error':print('controlled failure',file=sys.stderr);sys.exit(7)
elif case=='malformed':print('not a normalized report');sys.exit(0)
elif case=='escape':
 # A reported artifact outside work must fail admission even if a runner tries
 # to return an existing file. No host file is written by this fixture.
 result['artifacts']=[{'path':str(work.parent/'outside.png')}]
else:
 file=work/('测试图像.png' if case=='unicode' else 'fixture.png');Image.new('RGB',(64,64),(35,90,120)).save(file);result['artifacts']=[{'path':str(file.resolve()),'kind':'keyframe'}]
 if case in ('heal1','heal2'):result['report']['actualPrompt']=prompt+' ; repaired expression';result['report']['actions']+=['self_healed']
(work/'report.json').write_text(json.dumps(result,ensure_ascii=False),encoding='utf-8');print(json.dumps(result,ensure_ascii=False),flush=True)
