import time
from fastapi.testclient import TestClient
from test_common import studio


def settled(client, response):
    assert response.status_code == 200, response.text
    for _ in range(200):
        job = client.get('/api/jobs/'+response.json()['id']).json()
        if job['state'] not in ('queued','running'):
            assert job['state']=='succeeded', job
            return job['result']
        time.sleep(.03)
    raise AssertionError('Local demo job did not settle')


def test_reader_api_creates_choices_and_refines_without_overwriting(studio):
    with TestClient(studio,headers={'x-studio-client':'local-ui'}) as c:
        p=c.post('/api/projects',json={'title':'阅读测试','seed':'一封迟到的信','compact':True}).json()['project']['id'];url='/api/projects/'+p
        request={'operationId':'one-reader-click'}
        first=c.post(url+'/advance',json=request);second=c.post(url+'/advance',json=request)
        assert first.json()['id']==second.json()['id']
        result=settled(c,first)
        assert c.get(url).json()['nodes']==[]
        assert c.get(url+'/workflow').json()['state']=='awaiting_choice'
        adopted=c.post(url+'/candidates/'+result['candidateIds'][0]+'/adopt',json={'approveProposals':True})
        assert adopted.status_code==200,adopted.text
        result=settled(c,c.post(url+'/advance',json={}))
        assert c.post(url+'/candidates/'+result['candidateIds'][0]+'/adopt',json={'approveProposals':True}).status_code==200
        before=c.get(url).json()['nodes'][0]
        result=settled(c,c.post(url+'/refine',json={'nodeId':before['id'],'instruction':'让人物主动做出选择'}))
        after=c.get(url).json()['nodes'][0]
        assert after['currentRevision']==before['currentRevision'] and after['body']==before['body']
        assert len(result['candidateIds'])==1
        assert c.post(url+'/refine',json={'nodeId':before['id'],'instruction':'   '}).status_code==400


def test_offline_reader_export_escapes_content(studio):
    with TestClient(studio,headers={'x-studio-client':'local-ui'}) as c:
        p=c.post('/api/projects',json={'title':'<script>alert(1)</script>','seed':'<img src=x onerror=alert(1)>'}).json()['project']['id']
        r=c.get('/api/projects/'+p+'/export/html')
        assert r.status_code==200 and 'text/html' in r.headers['content-type']
        assert '<script>' not in r.text and '<img src=x' not in r.text
        assert '&lt;script&gt;' in r.text and '可离线打开' in r.text
