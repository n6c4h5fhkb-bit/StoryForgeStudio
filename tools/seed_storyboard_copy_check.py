"""Prepare an isolated, offline B project for clipboard UI regression."""
import copy
import json
import os
from pathlib import Path
import sys

root = Path(__file__).resolve().parents[1]
data = root / '.validation' / 'storyboard-copy'
os.environ['STUDIO_DATA'] = str(data)
sys.path[:0] = [str(root / 'system-b'), str(root / 'system-b' / 'tests')]
from app.main import app
from app.story_contract import normalize_document
from test_shooting_upgrade import box_story

b = app.state.service
assert not b.s.list(kind='project'), 'Use a fresh isolated directory for this fixture'
doc = box_story()
doc['scenes'][0]['blocks'].append({'id':'a2','type':'action','text':'老林将玉牌举到灯下。'})
doc['continuity']['events'].append({'id':'inspect','sceneId':'s1','locationId':'room','participants':['bob','token'],'action':'老林将玉牌举到灯下。','changes':[],'dialogueIds':[],'origin':'adapted'})
doc['scenes'].append({'id':'s2','title':'仓库门口','blocks':[{'id':'a3','type':'action','text':'老林在仓库门口停步。'},{'id':'d2','type':'dialogue','speakerId':'bob','mode':'speech','text':'交接完成。'}]})
doc['continuity']['events'].append({'id':'leave','sceneId':'s2','locationId':'room','participants':['bob','token'],'action':'老林在仓库门口停步。','changes':[],'dialogueIds':['d2'],'origin':'adapted'})
doc.pop('presentationPlan', None)
doc.pop('dialogueLines', None)
doc = normalize_document(doc)
p = b.create({'title':'分镜勾选复制验收','workflowVersion':2})['project']['id']
project = b.s.get(p);project['storySource'] = doc;b.s.put('project',project,p)
candidate = copy.deepcopy(doc)
candidate.update(title='分镜勾选复制验收',sourceMapping=[{'sourceId':v['id'],'targetIds':[v['id']],'reason':'保留'} for s in doc['scenes'] for v in s['blocks']])
original = b.llm.json
def fixture(project,role,system,context,*args,**kwargs):
    return copy.deepcopy(candidate) if role=='treatment' else original(project,role,system,context,*args,**kwargs)
b.llm.json = fixture
q = b.propose_shooting(p,{})
assert q['passed'],q['issues']
b.adopt_shooting(p,q['id'])
b.llm.json = original
for _ in range(2):
    q = b.advance(p,{})['proposal']
    assert q['passed'],q['issues']
    b.adopt_proposal(p,q['id'])
shots = b.get(p)['shots']
locked = shots[1];locked['status']='locked';b.s.put('shot',locked,p)
other = b.create({'title':'空项目用于检查选择隔离'})['project']['id']
(data/'fixture.json').write_text(json.dumps({'projectId':p,'otherProjectId':other,'shots':[{'id':s['id'],'sceneId':s['sceneId'],'actionLine':s['actionLine']} for s in shots]},ensure_ascii=False),encoding='utf-8')
app.state.jobs.pool.shutdown(wait=True,cancel_futures=True)
print(json.dumps({'data':str(data),'projectId':p,'shots':len(shots)}))
