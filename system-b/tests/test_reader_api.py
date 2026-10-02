import copy,time
from fastapi.testclient import TestClient
from test_common import studio
from test_production import project


def settled(client, response):
    assert response.status_code==200,response.text
    for _ in range(200):
        job=client.get('/api/jobs/'+response.json()['id']).json()
        if job['state'] not in ('queued','running'):
            assert job['state']=='succeeded',job
            return job['result']
        time.sleep(.03)
    raise AssertionError('Local demo job did not settle')


def test_reader_next_step_and_one_click_are_idempotent(studio):
    with TestClient(studio,headers={'x-studio-client':'local-ui'}) as c:
        p=c.post('/api/projects',json={'title':'分镜阅读','source':'一个人走进雨夜便利店。','targetDuration':12}).json()['project']['id'];url='/api/projects/'+p
        assert c.get(url).json()['workflow']['stage']=='B0'
        request={'operationId':'reader-b-click'}
        first=c.post(url+'/advance',json=request);second=c.post(url+'/advance',json=request)
        assert first.json()['id']==second.json()['id']
        result=settled(c,first)
        assert result['advanced'] and c.get(url).json()['scenes']==[]
        assert c.get(url+'/workflow').json()['state']=='awaiting_choice'


def test_reader_local_refine_retains_other_shots(project,studio):
    b,p,scene,asset,shots=project
    direction=b.list_active(p,'direction')[0];b.finalize(p,'direction',direction['id'],direction['_version'])
    before=copy.deepcopy(b.list_active(p,'shot'))
    with TestClient(studio,headers={'x-studio-client':'local-ui'}) as c:
        url='/api/projects/'+p
        result=settled(c,c.post(url+'/refine',json={'sceneId':scene['id'],'shotIds':[shots[1]['id']],'instruction':'保留主体，增强动作细节'}))
        assert b.list_active(p,'shot')==before
        accepted=c.post(url+'/proposals/'+result['id']+'/adopt',json={})
        assert accepted.status_code==200,accepted.text
        after={s['id']:s for s in b.list_active(p,'shot')}
        for shot in before:
            if shot['id']!=shots[1]['id']:assert after[shot['id']]==shot
        assert set(after)=={s['id'] for s in before}
        exported=c.get(url+'/export/storyboard.html')
        assert exported.status_code==200 and 'text/html' in exported.headers['content-type']
        assert '镜 01' in exported.text and '<script>' not in exported.text
        assert c.post(url+'/refine',json={'sceneId':scene['id'],'instruction':'更紧张'}).status_code==400
