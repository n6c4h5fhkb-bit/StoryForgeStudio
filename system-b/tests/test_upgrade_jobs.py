import threading,time
from fastapi.testclient import TestClient
from test_common import studio


def wait(client, identifier):
    for _ in range(200):
        row=client.get('/api/jobs/'+identifier).json()
        if row['state'] not in ('queued','running'):return row
        time.sleep(.02)
    raise AssertionError('job did not settle')


def test_cancel_resume_and_duplicate_operation(studio):
    b=studio.state.service;entered=threading.Event();release=threading.Event();original=b.propose_shooting;calls=[]
    def held(p,data,progress,check):
        calls.append(data)
        if len(calls)==1:entered.set();release.wait(3);check()
        return original(p,data,progress,check)
    b.propose_shooting=held
    with TestClient(studio,headers={'x-studio-client':'local-ui'}) as client:
        p=client.post('/api/projects',json={'source':'阿青推开门。','workflowVersion':2}).json()['project']['id']
        first=client.post(f'/api/projects/{p}/shooting/propose',json={'operationId':'one-click'}).json()
        duplicate=client.post(f'/api/projects/{p}/shooting/propose',json={'operationId':'one-click'}).json()
        assert first['id']==duplicate['id'] and entered.wait(2)
        client.post('/api/jobs/'+first['id']+'/cancel');release.set()
        assert wait(client,first['id'])['state']=='cancelled'
        assert not b.s.list(p,'shooting_script')
        resumed=client.post('/api/jobs/'+first['id']+'/resume').json()
        repeated=client.post('/api/jobs/'+first['id']+'/resume').json()
        assert resumed['id']==repeated['id']
        done=wait(client,resumed['id']);assert done['state']=='succeeded',done
        assert len(b.s.list(p,'shooting_script'))==1 and len(calls)==2


def test_paid_media_cannot_be_silently_resumed(studio):
    b=studio.state.service;jobs=studio.state.jobs;p=b.create({'source':'测试'})['project']['id']
    job=jobs.submit(p,'render',{},lambda *_:[]);jobs.pool.shutdown(wait=True);jobs.update(job['id'],state='interrupted')
    with TestClient(studio,headers={'x-studio-client':'local-ui'}) as client:
        response=client.post('/api/jobs/'+job['id']+'/resume')
        assert response.status_code==409 and response.json()['code']=='manual_resume'
