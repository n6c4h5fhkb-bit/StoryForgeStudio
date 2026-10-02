"""Local persistence, audit, durable task records and optimistic transactions.
A and B share this persistence and task runtime; project workspace tags preserve boundaries.
"""
from __future__ import annotations
import contextlib, copy, hashlib, json, os, re, sqlite3, threading, time, uuid
from pathlib import Path
from typing import Any, Callable
from concurrent.futures import ThreadPoolExecutor

class DomainError(Exception):
    def __init__(self, message: str, code: str='invalid', status: int=400, details: Any=None):
        super().__init__(message); self.code=code; self.status=status; self.details=details

def uid(prefix='id'): return prefix+'_'+uuid.uuid4().hex[:16]
def now(): return time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime())
def canonical(value): return json.dumps(value, ensure_ascii=False,sort_keys=True,separators=(',',':'))
def digest(value): return hashlib.sha256(canonical(value).encode()).hexdigest()
def ensure(condition, message, code='invalid', status=400, details=None):
    if not condition: raise DomainError(message,code,status,details)
def safe_path(root: Path, relative: str) -> Path:
    path=(root/relative).resolve()
    ensure(path.is_relative_to(root.resolve()),'路径超出工作区','path_escape',403)
    return path

def fraction_between(left: str|None, right: str|None) -> str:
    """Arbitrary-precision rational indexing; never renumber siblings on insertion."""
    from fractions import Fraction
    a=Fraction(left) if left is not None else None
    b=Fraction(right) if right is not None else None
    if a is not None and b is not None:
        ensure(a<b,'顺序索引无效');return str((a+b)/2)
    return str((a+1) if a is not None else (b-1 if b is not None else Fraction(0)))
def order_key(item):
    from fractions import Fraction
    return Fraction(item.get('order','0'))

class ClosingConnection(sqlite3.Connection):
    def __exit__(self,exc_type,exc,tb):
        try:return super().__exit__(exc_type,exc,tb)
        finally:self.close()

class Store:
    def __init__(self, root: Path):
        self.root=root;root.mkdir(parents=True,exist_ok=True);self.path=root/'studio.sqlite3'
        self.lock=threading.RLock()
        with self.connect() as c:
            c.executescript("""
            PRAGMA journal_mode=WAL;
            CREATE TABLE IF NOT EXISTS documents(id TEXT PRIMARY KEY,project TEXT NOT NULL,kind TEXT NOT NULL,data TEXT NOT NULL,version INTEGER NOT NULL DEFAULT 1,updated TEXT NOT NULL);
            CREATE INDEX IF NOT EXISTS doc_project_kind ON documents(project,kind);
            CREATE TABLE IF NOT EXISTS operations(seq INTEGER PRIMARY KEY AUTOINCREMENT,id TEXT UNIQUE,project TEXT,op TEXT,scope TEXT,record TEXT,created TEXT);
            CREATE TABLE IF NOT EXISTS events(seq INTEGER PRIMARY KEY AUTOINCREMENT,project TEXT,type TEXT,data TEXT,created TEXT);
            CREATE TABLE IF NOT EXISTS cache(key TEXT PRIMARY KEY,data TEXT,created TEXT);
            CREATE TABLE IF NOT EXISTS redirects(source TEXT PRIMARY KEY,target TEXT,reason TEXT);
            CREATE TABLE IF NOT EXISTS jobs(id TEXT PRIMARY KEY,project TEXT,kind TEXT,state TEXT,progress REAL,data TEXT,result TEXT,error TEXT,cancel INTEGER DEFAULT 0,created TEXT,updated TEXT);
            CREATE TABLE IF NOT EXISTS job_idempotency(project TEXT NOT NULL,kind TEXT NOT NULL,operation_id TEXT NOT NULL,job_id TEXT NOT NULL,request_digest TEXT NOT NULL,PRIMARY KEY(project,kind,operation_id));
            CREATE TABLE IF NOT EXISTS schema_version(version INTEGER PRIMARY KEY,applied TEXT);
            INSERT OR IGNORE INTO schema_version VALUES(1,datetime('now'));
            CREATE TRIGGER IF NOT EXISTS audit_no_update BEFORE UPDATE ON operations BEGIN SELECT RAISE(ABORT,'append-only audit log'); END;
            CREATE TRIGGER IF NOT EXISTS audit_no_delete BEFORE DELETE ON operations BEGIN SELECT RAISE(ABORT,'append-only audit log'); END;
            """)
    def connect(self):
        c=sqlite3.connect(self.path, timeout=30,factory=ClosingConnection);c.row_factory=sqlite3.Row
        c.execute('PRAGMA busy_timeout=30000');return c
    @contextlib.contextmanager
    def transaction(self):
        with self.lock, self.connect() as c:
            c.execute('BEGIN IMMEDIATE')
            try: yield c;c.commit()
            except: c.rollback();raise
    def get(self, id, conn=None, required=True):
        if conn is None:
            with self.connect() as c: return self.get(id,c,required)
        r=conn.execute('SELECT * FROM documents WHERE id=?',(id,)).fetchone()
        if not r:
            if required: raise DomainError('记录不存在：'+str(id),'not_found',404)
            return None
        d=json.loads(r['data']);d['_version']=r['version'];return d
    def list(self, project=None, kind=None, conn=None):
        if conn is None:
            with self.connect() as c: return self.list(project,kind,c)
        sql='SELECT * FROM documents WHERE 1=1';args=[]
        if project is not None: sql+=' AND project=?';args.append(project)
        if kind is not None: sql+=' AND kind=?';args.append(kind)
        sql+=' ORDER BY rowid'
        return [dict(json.loads(r['data']),_version=r['version']) for r in conn.execute(sql,args)]
    def put(self, kind, obj, project=None, expected=None, conn=None):
        if conn is None:
            with self.transaction() as c:return self.put(kind,obj,project,expected,c)
        obj=copy.deepcopy(obj);id=obj['id'];old=self.get(id,conn,False)
        if expected is not None: ensure(old and old['_version']==expected,'内容已变化，请刷新后重试','version_conflict',409)
        version=(old['_version']+1) if old else 1;obj.pop('_version',None)
        conn.execute('INSERT INTO documents VALUES(?,?,?,?,?,?) ON CONFLICT(id) DO UPDATE SET data=excluded.data,version=excluded.version,updated=excluded.updated',
            (id,project or obj.get('projectId',id),kind,canonical(obj),version,now()))
        return dict(obj,_version=version)
    def audit(self, project, op, scope, data=None, conn=None):
        if conn is None:
            with self.transaction() as c:return self.audit(project,op,scope,data,c)
        id=uid('op');record={'who':'local-user','op':op,'scope':scope,'createdAt':now(),**(data or {})}
        conn.execute('INSERT INTO operations(id,project,op,scope,record,created) VALUES(?,?,?,?,?,?)',(id,project,op,canonical(scope),canonical(record),now()))
        self.event(project,'operation',{'id':id,'op':op,'scope':scope},conn);return id
    def history(self, project):
        with self.connect() as c:return [dict(json.loads(r['record']),id=r['id'],seq=r['seq']) for r in c.execute('SELECT * FROM operations WHERE project=? ORDER BY seq DESC',(project,))]
    def event(self, project, type, data, conn=None):
        if conn is None:
            with self.transaction() as c:return self.event(project,type,data,c)
        conn.execute('INSERT INTO events(project,type,data,created) VALUES(?,?,?,?)',(project,type,canonical(data),now()))
    def events(self, since=0, project=None):
        with self.connect() as c:
            q='SELECT * FROM events WHERE seq>?';a=[since]
            if project:q+=' AND project=?';a.append(project)
            return [dict(r,data=json.loads(r['data'])) for r in c.execute(q+' ORDER BY seq LIMIT 100',a)]
    def cached(self,key):
        with self.connect() as c:
            seen=set();original=key
            while key not in seen:
                seen.add(key);r=c.execute('SELECT target FROM redirects WHERE source=?',(key,)).fetchone()
                if not r:break
                key=r['target']
            r=c.execute('SELECT data FROM cache WHERE key=?',(key,)).fetchone()
            if not r:return None
            data=json.loads(r['data'])
            for a in data.get('artifacts',[]):
                if not Path(a['path']).is_file():return None
                if a.get('sha256') and hashlib.sha256(Path(a['path']).read_bytes()).hexdigest()!=a['sha256']:return None
            return {**data,'cacheHit':True,'requestedKey':original,'actualKey':key}
    def cache_put(self,key,result,redirect_from=None):
        with self.transaction() as c:
            c.execute('INSERT OR REPLACE INTO cache VALUES(?,?,?)',(key,canonical(result),now()))
            if redirect_from and redirect_from!=key:c.execute('INSERT OR REPLACE INTO redirects VALUES(?,?,?)',(redirect_from,key,'self_healed'))
    def backup(self,path):
        with self.connect() as source,sqlite3.connect(path) as dest:source.backup(dest)

class Jobs:
    """Persist status; interrupted expensive work never silently restarts."""
    def __init__(self,store: Store,workers=3):
        self.store=store;self.pool=ThreadPoolExecutor(max_workers=workers,thread_name_prefix='studio')
        with store.transaction() as c:c.execute("UPDATE jobs SET state='interrupted',error='服务已重启；请核对远端任务后手动重试',updated=? WHERE state IN ('queued','running')",(now(),))
        for hold in store.list(kind='llm_hold'):
            if hold.get('status')=='reserved':
                run=store.get(hold['runId'],required=False)
                if run and run.get('status')=='running':
                    run.update(status='interrupted',cost=hold['estimate'],costKnown=False,costEstimated=True,error='重启中断；费用按预留额保守计入，需与服务商对账')
                    store.put('run',run,run['projectId'])
                hold['status']='settled';store.put('llm_hold',hold,hold['projectId'])
    def submit(self,project,kind,data,fn:Callable,operation_id=None):
        if operation_id is not None:
            ensure(isinstance(operation_id,str) and 1<=len(operation_id)<=200,'操作标识必须是 1–200 字符','invalid_operation_id')
        id=uid('job')
        with self.store.transaction() as c:
            if operation_id is not None:
                previous=c.execute('SELECT job_id,request_digest FROM job_idempotency WHERE project=? AND kind=? AND operation_id=?',(project,kind,operation_id)).fetchone()
                if previous:
                    ensure(previous['request_digest']==digest(data),'同一操作标识不能提交不同内容；新一版请使用新标识','idempotency_conflict',409)
                    return self.get(previous['job_id'])
            c.execute('INSERT INTO jobs VALUES(?,?,?,?,?,?,?,?,?,?,?)',(id,project,kind,'queued',0,canonical(data),'null','',0,now(),now()))
            if operation_id is not None:
                c.execute('INSERT INTO job_idempotency VALUES(?,?,?,?,?)',(project,kind,operation_id,id,digest(data)))
            self.store.event(project,'job',{'id':id,'state':'queued'},c)
        self.pool.submit(self._run,id,fn);return self.get(id)
    def _run(self,id,fn):
        try:
            self.check(id);self.update(id,state='running',progress=.02)
            result=fn(lambda p,m='':self.progress(id,p,m),lambda:self.check(id))
            self.check(id);self.update(id,state='succeeded',progress=1,result=result)
        except DomainError as e:self.update(id,state='cancelled' if e.code=='cancelled' else 'failed',error=str(e),result={'code':e.code,'details':e.details})
        except Exception as e:
            import traceback;traceback.print_exc();self.update(id,state='failed',error=type(e).__name__+': '+str(e))
    def check(self,id):
        j=self.get(id)
        if j['cancel']:raise DomainError('任务已取消；已提交的远端任务可能仍会计费','cancelled',409)
    def progress(self,id,p,message=''):
        self.check(id);self.update(id,progress=max(0,min(1,p)),error=message)
    def get(self,id):
        with self.store.connect() as c:r=c.execute('SELECT * FROM jobs WHERE id=?',(id,)).fetchone()
        ensure(r is not None,'任务不存在','not_found',404)
        d=dict(r);d['data']=json.loads(d['data']);d['result']=json.loads(d['result']);return d
    def list(self,project=None):
        with self.store.connect() as c:
            rows=c.execute('SELECT id FROM jobs '+('WHERE project=? ' if project else '')+'ORDER BY created DESC LIMIT 200',(project,) if project else ()).fetchall()
        return [self.get(r['id']) for r in rows]
    def update(self,id,**fields):
        fields['updated']=now()
        if 'result' in fields:fields['result']=canonical(fields['result'])
        with self.store.transaction() as c:
            c.execute('UPDATE jobs SET '+','.join(k+'=?' for k in fields)+' WHERE id=?',(*fields.values(),id))
            project=c.execute('SELECT project FROM jobs WHERE id=?',(id,)).fetchone()[0]
            self.store.event(project,'job',{'id':id,**{k:v for k,v in fields.items() if k!='result'}},c)
    def cancel(self,id):self.update(id,cancel=1);return self.get(id)
