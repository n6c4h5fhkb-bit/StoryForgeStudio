"""Small real original-story trial. Uses account quota; isolated from user projects."""
import json
import os
from pathlib import Path
import sys
import uuid

root=Path(__file__).resolve().parents[1]
data=root/'.validation'/('collaboration-real-a-'+uuid.uuid4().hex[:8])
os.environ['STUDIO_DATA']=str(data)
sys.path.insert(0,str(root/'system-a'))
from app.main import app

service=app.state.service;store=app.state.store
app.state.settings.save({'llm':{'provider':'codex_cli','timeout':600,'contextCharacters':64000}})
report={'data':str(data),'checks':[]}
def progress(_,message):print(message,flush=True)
try:
    project=service.create({'title':'协作实测：归还雨伞','seed':'车站值班员阿青发现一把乘客遗落的蓝色长柄雨伞。乘客小林回站寻找，误以为阿青占为己有。阿青本想用监控证明清白，却看到伞袋里有一封写给失联父亲的信，选择当面归还并陪他等末班车。人物只有阿青、小林，现实主义，用行动和选择完成和解，无超自然设定。','compact':True})['project']['id']
    first=service.generate(project,{'op':'expand','candidateCount':1,'generationId':'trial-direction'},progress=progress)
    assert not first['allFailed'],[c.get('gate') for c in store.list(project,'candidate')]
    report['checks'].append({'task':'original_direction_independent_review','passed':True})
    runs=len(store.list(project,'run'))
    duplicate=service.generate(project,{'op':'expand','candidateCount':1,'generationId':'trial-direction'})
    assert first==duplicate and len(store.list(project,'run'))==runs
    report['checks'].append({'task':'same_intent_no_extra_call','passed':True})
    adopted=service.adopt(project,first['candidateIds'][0],approve_proposals=True)
    assert len(adopted['nodeIds'])==1,'one candidate must adopt one story root'
    report['checks'].append({'task':'single_story_root','passed':True})
    node=adopted['nodeIds'][0]
    body=service.generate(project,{'op':'fill','nodeId':node,'candidateCount':1,'generationId':'trial-body'},progress=progress)
    assert not body['allFailed'],[c.get('gate') for c in store.list(project,'candidate') if c['batchId']==body['batchId']]
    service.adopt(project,body['candidateIds'][0],approve_proposals=True)
    report['checks'].append({'task':'body_and_independent_review_adopted','passed':True})
    report.update(passed=True,project=project)
except Exception as error:
    report.update(passed=False,error=str(error),code=getattr(error,'code',None))
    raise
finally:
    report['runs']=[{k:row.get(k) for k in ('role','status','cacheHit','usage','codex','error')} for row in store.list(kind='run')]
    (data/'verification.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
    print(json.dumps(report,ensure_ascii=False),flush=True)
    app.state.jobs.pool.shutdown(wait=True,cancel_futures=True)
