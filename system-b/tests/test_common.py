import copy,hashlib,sqlite3,io,zipfile,json,os
from fractions import Fraction
from pathlib import Path
import pytest
from fastapi.testclient import TestClient
from app.core import Store,DomainError,digest,fraction_between,safe_path,Jobs
from app.main import create_app

@pytest.fixture
def studio(tmp_path):
    app=create_app(tmp_path/'runtime')
    yield app
    app.state.jobs.pool.shutdown(wait=True,cancel_futures=True)


def test_default_asgi_instance_is_isolated_from_live_data_during_tests():
    from app.main import app as default_app
    assert default_app.state.store.root==Path(os.environ['STUDIO_DATA']).resolve()
    assert default_app.state.store.root.name.startswith('storysystems-b-tests-')

@pytest.mark.parametrize('left,right',[('0','1'),('-1','0'),('1/3','1/2'),(None,'0'),('2',None)])
def test_fractional_index_is_between(left,right):
    v=Fraction(fraction_between(left,right))
    assert left is None or Fraction(left)<v
    assert right is None or v<Fraction(right)

def test_canonical_hash_is_key_order_independent():
    assert digest({'b':2,'a':1})==digest({'a':1,'b':2})

@pytest.mark.parametrize('path',['../secret','a/../../secret'])
def test_workdir_path_escape_rejected(tmp_path,path):
    with pytest.raises(DomainError):safe_path(tmp_path,path)

def test_optimistic_version_conflict(studio):
    s=studio.state.store;first=s.put('test',{'id':'x','projectId':'p','value':1})
    second=s.put('test',{**first,'value':2},expected=first['_version'])
    with pytest.raises(DomainError):s.put('test',{**first,'value':3},expected=first['_version'])
    assert s.get('x')['value']==2

def test_audit_log_is_append_only(studio):
    s=studio.state.store;s.audit('p','test',[],{})
    for statement in ('DELETE FROM operations','UPDATE operations SET op="bad"'):
        with pytest.raises(sqlite3.IntegrityError):
            with s.transaction() as c:c.execute(statement)
    assert s.history('p')[0]['op']=='test'

def test_failed_transaction_rolls_back(studio):
    s=studio.state.store
    with pytest.raises(RuntimeError):
        with s.transaction() as c:
            s.put('test',{'id':'uncommitted'},'p',conn=c)
            raise RuntimeError('rollback')
    assert s.get('uncommitted',required=False) is None

def test_cache_verifies_artifact_hash(studio,tmp_path):
    f=tmp_path/'artifact.bin';f.write_bytes(b'original');s=studio.state.store
    s.cache_put('key',{'artifacts':[{'path':str(f),'sha256':hashlib.sha256(f.read_bytes()).hexdigest()}]})
    assert s.cached('key')['cacheHit']
    f.write_bytes(b'changed');assert s.cached('key') is None

def test_cache_redirect_preserves_requested_and_actual_keys(studio):
    s=studio.state.store;s.cache_put('healed',{'artifacts':[]},redirect_from='requested')
    assert s.cached('requested')['actualKey']=='healed'
    assert s.cached('requested')['requestedKey']=='requested'

def test_settings_secrets_redacted(studio):
    st=studio.state.settings;st.save({'llm':{'apiKey':'private-test-key'}})
    assert st.read(True)['llm']['apiKey']=='__KEEP__'
    st.save({'llm':{'apiKey':'__KEEP__','model':'test'}})
    assert st.read()['llm']['apiKey']=='private-test-key'

def test_same_origin_and_mutation_guard(studio):
    c=TestClient(studio,base_url='http://localhost')
    assert c.post('/api/projects',json={'title':'blocked'}).status_code==403
    assert c.post('/api/projects',json={'title':'blocked'},headers={'x-studio-client':'local-ui','origin':'https://evil.invalid'}).status_code==403
    assert c.get('/api/health').status_code==200

def test_static_page_and_openapi(studio):
    c=TestClient(studio,base_url='http://localhost')
    for path in ('/','/static/app.js','/static/style.css','/openapi.json'):
        assert c.get(path).status_code==200

def test_backup_restore_creates_new_project(studio):
    c=TestClient(studio,base_url='http://localhost',headers={'x-studio-client':'local-ui'})
    created=c.post('/api/projects',json={'title':'中文备份','seed':'一个种子','source':'一场戏'})
    assert created.status_code==200,created.text
    pid=created.json()['project']['id'];backup=c.get(f'/api/projects/{pid}/backup')
    assert backup.status_code==200
    restored=c.post('/api/backups/restore',files={'file':('project.zip',backup.content,'application/zip')})
    assert restored.status_code==200,restored.text
    nid=restored.json()['projectId'];assert nid!=pid
    assert c.get(f'/api/projects/{pid}').status_code==200
    assert c.get(f'/api/projects/{nid}').status_code==200

def test_restart_does_not_automatically_replay_queued_jobs(studio):
    from app.core import now,canonical
    s=studio.state.store
    with s.transaction() as c:
        c.execute('INSERT INTO jobs VALUES(?,?,?,?,?,?,?,?,?,?,?)',('job_stale','p','render','running',.2,'{}','null','',0,now(),now()))
    restart=Jobs(s,1)
    assert restart.get('job_stale')['state']=='interrupted'
    restart.pool.shutdown()
