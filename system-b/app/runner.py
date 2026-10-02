"""Runner registry, bounded subprocess execution and idempotent outer shell.
The built-in renderer is trusted application code. Arbitrary third-party agents
require Docker isolation and a passing conformance report before routing.
"""
from __future__ import annotations
import copy,hashlib,json,os,queue,shutil,signal,subprocess,sys,threading,time
from pathlib import Path
import jsonschema
from .core import DomainError,ensure,uid,now,digest,canonical,safe_path
from .models import TaskSpec,RunResult

RUNNER_DEFAULTS={
 'subprocess':{'id':'subprocess','kind':'general_tool','adapterVersion':'1.0','enabled':True,'capabilities':{'customTools':True,'maxTurns':True,'budgetLimit':True,'structuredReport':True,'sandbox':'dir','usageReport':True,'concurrencySafe':True},'limits':{'maxConcurrency':2,'defaultTimeout':900,'costPerRunEstimate':0},'invoke':{'cmd':'builtin','argsTemplate':[],'env':{},'cwdStrategy':'task'},'qualification':'builtin_trusted'},
 'pi-agent':{'id':'pi-agent','kind':'general_tool','adapterVersion':'1.0','enabled':False,'capabilities':{'customTools':True,'maxTurns':False,'budgetLimit':False,'structuredReport':True,'sandbox':'container','usageReport':True,'concurrencySafe':True},'limits':{'maxConcurrency':2,'defaultTimeout':900,'costPerRunEstimate':1},'invoke':{'cmd':'pi','argsTemplate':['--print','--mode','json','--no-session','--no-context-files','--no-extensions','--no-skills','--tools','read,bash,write','{objective}'],'env':{},'cwdStrategy':'task'},'sandbox':{'type':'docker','image':'story-runner:local','network':'bridge'},'qualification':'required'},
 'codex':{'id':'codex','kind':'coding','adapterVersion':'1.0','enabled':False,'capabilities':{'customTools':True,'maxTurns':False,'budgetLimit':False,'structuredReport':True,'sandbox':'container','usageReport':True,'concurrencySafe':True},'limits':{'maxConcurrency':1,'defaultTimeout':900,'costPerRunEstimate':1},'invoke':{'cmd':'codex','argsTemplate':['exec','--json','--ephemeral','--sandbox','workspace-write','--skip-git-repo-check','-o','{reportFile}','{objective}'],'env':{},'cwdStrategy':'task'},'sandbox':{'type':'docker','image':'story-runner:local','network':'bridge'},'qualification':'required'}}

def execution_mode(name,profile):
 """'builtin' for the trusted shipped renderer, otherwise the declared isolation.
 Third-party agents must state their isolation explicitly. 'docker' runs them in a
 container; 'host' runs the configured local CLI directly and is only reachable
 after the twelve case admission report passes for the current profile."""
 if name=='subprocess':return 'builtin'
 kind=(profile.get('sandbox') or {}).get('type')
 ensure(kind in ('docker','host'),'第三方 Agent 必须显式声明 sandbox.type 为 docker 或 host；工作目录本身不是安全沙箱','sandbox_required',409)
 return kind

class RunnerRegistry:
 def __init__(self,store,settings,root):self.s=store;self.settings=settings;self.root=root;self.semaphores={};self.mutex=threading.Lock();self.keylocks={}
 def profiles(self):
  result=copy.deepcopy(RUNNER_DEFAULTS)
  for k,v in self.settings.read().get('runners',{}).items():result[k]=v
  return result
 def route(self,task,manual=None):
  cfg=self.settings.read()['routing'];name=manual
  if not name:
   for override in cfg.get('overrides',[]):
    if all(task.get(k)==v for k,v in override.get('match',{}).items()):name=override['runner'];break
  name=name or cfg['roles'].get(task['role'],'subprocess')
  ensure(name in self.profiles(),'Runner 未注册：'+str(name),'runner_not_found',400);return name
 def qualified(self,profile):
  if profile['id']=='subprocess':return True
  report=self.s.get('qualification_'+profile['id'],required=False)
  return bool(report and report.get('passed') and report.get('profileHash')==digest({k:v for k,v in profile.items() if k!='enabled'}))
 def execute(self,project,task,manual=None,check=lambda:None):
  TaskSpec.model_validate(task);key=task.get('renderKey')
  with self.mutex:lock=self.keylocks.setdefault(key or task['taskId'],threading.Lock())
  with lock:
   check()
   if key:
    cached=self.s.cached(key)
    if cached:
     self.s.audit(project,'render_cache_hit',[task['taskId']],{'renderKey':key,'actualKey':cached.get('actualKey')});return cached
   name=self.route(task,manual);profile=self.profiles()[name]
   ensure(profile.get('enabled'),f'Runner {name} 未启用','runner_disabled',409)
   if name!='subprocess':
    ensure(self.qualified(profile),'此 Runner 未通过当前配置对应的 12 项验收，不能进入生产路由','runner_unqualified',409)
    execution_mode(name,profile)
   with self.mutex:sem=self.semaphores.setdefault(name,threading.Semaphore(max(1,int(profile['limits']['maxConcurrency']))))
   self.s.audit(project,'runner_selected',[task['taskId']],{'runner':name,'mode':execution_mode(name,profile),'manual':bool(manual),'role':task['role'],'stage':task.get('stage')})
   with sem:r=self.run_process(task,profile,check)
   actual=r.get('report',{}).get('actualPrompt');original=task['inputs'].get('prompt')
   r['requestedKey']=key;r['actualKey']=key
   if r['status']=='ok' and key:
    freezes=task['inputs'].get('freezeStrings',[])
    if not actual or any(f and f not in actual for f in freezes):
     r['status']='rejected';r['report']['failureClass']='identity_modified';r['report']['notes']='实际 Prompt 未报告，或自愈改写破坏冻结身份串；产物不进入缓存。'
   if r['status']=='ok' and key:
    if actual and actual!=original:
     # Include the original render identity as a namespace. Hashing only the
     # changed prompt would collide across seeds, variants or renderer profiles.
     actualkey=digest({'requestedRenderKey':key,'actualPrompt':actual});r.update(actualKey=actualkey,selfHealed=True)
     self.s.cache_put(actualkey,r,redirect_from=key)
     self.s.put('curator_item',{'id':uid('curator'),'projectId':project,'taskId':task['taskId'],'originalPrompt':original,'actualPrompt':actual,'status':'open','createdAt':now()},project)
    else:self.s.cache_put(key,r)
   self.s.put('runner_run',{'id':uid('runner_run'),'projectId':project,'task':self.redact_task(task),'result':r,'createdAt':now()},project)
   self.s.audit(project,'runner_result',[task['taskId']],{'runner':name,'status':r['status'],'renderKey':key,'actualKey':r.get('actualKey'),'usage':r.get('usage',{})})
   return r
 def redact_task(self,task):
  t=copy.deepcopy(task)
  def scrub(v):
   if isinstance(v,dict):return {k:('***' if k in ('apiKey','secret','token') else scrub(x)) for k,x in v.items()}
   if isinstance(v,list):return [scrub(x) for x in v]
   return v
  return scrub(t)
 def run_process(self,task,profile,check=lambda:None,qualification=False):
  start=time.monotonic();work=Path(task['workdir']).resolve();ensure(work.is_relative_to(self.s.root.resolve()),'Runner 工作区不在数据目录内','path_escape',403);work.mkdir(parents=True,exist_ok=True)
  ensure(task['role']!='operator' or task.get('stage') in ('B2','B5','B6','TEST'),'推理阶段不能路由到 Agent CLI','invalid_runner_role',409)
  tools=set(task.get('tools',[]));ensure(tools.issubset({'render','ffmpeg','read_task','write_report'}),'任务含未授权工具','tool_rejected',403)
  reportfile=work/'report.json';taskfile=work/'task.json';taskfile.write_text(json.dumps(task,ensure_ascii=False,indent=2),encoding='utf-8')
  try:taskfile.chmod(0o600)
  except OSError:pass
  # Windows upper cases os.environ keys, so the allow list must be compared case
  # insensitively or SystemRoot is silently dropped and node aborts on startup.
  keep={'PATH','SYSTEMROOT','WINDIR','COMSPEC','PATHEXT','TEMP','TMP','HOME','USERPROFILE','APPDATA','LOCALAPPDATA','PROGRAMDATA','SYSTEMDRIVE','LANG','LC_ALL','PYTHONIOENCODING'}
  env={k:v for k,v in os.environ.items() if k.upper() in keep}
  env.update({'PYTHONUTF8':'1','PYTHONIOENCODING':'utf-8','STUDIO_TASK_FILE':str(taskfile),'STUDIO_REPORT_FILE':str(reportfile)})
  env.update(profile.get('invoke',{}).get('env',{}));inv=profile['invoke'];name=profile['id']
  mode=execution_mode(name,profile);container_name=None
  if mode=='builtin':
   cmd=[sys.executable,str(self.root/'tools'/('qualification_fixture.py' if qualification else 'render.py')),str(taskfile)]
  else:
   toolsdir=str(self.root/'tools');helper='qualification_fixture.py' if qualification else 'render.py'
   raw=task['objective']
   if mode=='docker':
    base='/opt/studio/tools';taskjson='/work/task.json';reportjson='/work/report.json'
    renderpy='python '+base+'/'+helper+' '+taskjson
    replacements={'taskFile':taskjson,'reportFile':reportjson,'workdir':'/work'}
   else:
    # Native paths use forward slashes so the objective stays valid for shell tools
    # that treat a backslash as an escape character (bash, sh).
    posix=lambda p:str(p).replace('\\','/')
    base=posix(toolsdir);taskjson=posix(taskfile);reportjson=posix(reportfile)
    renderpy='"'+posix(sys.executable)+'" "'+posix(self.root/'tools'/helper)+'" "'+posix(taskfile)+'"'
    raw=raw.replace('/opt/studio/tools',base).replace('/work',posix(work))
    replacements={'taskFile':str(taskfile),'reportFile':str(reportfile),'workdir':str(work)}
   # The helper writes its own receipt for both admission and production tasks.
   # Asking the agent to write that file invites it to overwrite correct evidence.
   rule='The command writes '+reportjson+' itself. Do not rewrite, repair or synthesise that file; whether the command passes or fails, leave its content exactly as produced.'
   objective=raw+'\nRead '+taskjson+'. Only use the tools named in task.tools. Render tool command: '+renderpy+'. All authorized helper tools are read-only at '+base+'. '+rule+' Do not inspect unrelated directories or change identity freeze strings. Never generate story decisions.'
   replacements['objective']=objective
   args=[]
   for arg in inv.get('argsTemplate',[]):
    for k,v in replacements.items():arg=arg.replace('{'+k+'}',v)
    args.append(arg)
   inner=[inv['cmd']]+args
   sandbox=profile.get('sandbox',{})
   if mode=='docker':
    ensure(shutil.which('docker'),'未安装 Docker，不能启用隔离 Runner','configuration_required',400)
    container_task=copy.deepcopy(task)
    def map_paths(v):
     if isinstance(v,dict):return {k:map_paths(x) for k,x in v.items()}
     if isinstance(v,list):return [map_paths(x) for x in v]
     if isinstance(v,str) and v.startswith(str(work)):return '/work'+v[len(str(work)):].replace('\\','/')
     return v
    container_task=map_paths(container_task);taskfile.write_text(json.dumps(container_task,ensure_ascii=False),encoding='utf-8')
    container_name='studio-'+task['taskId'].replace('_','-').lower()
    cmd=['docker','run','--name',container_name,'--rm','--read-only','--cap-drop=ALL','--security-opt=no-new-privileges','--pids-limit=256','--memory=2g','--cpus=2','--network',sandbox.get('network','none'),
         '--mount',f'type=bind,source={work},target=/work','--tmpfs','/tmp:rw,noexec,nosuid,size=256m','-w','/work']
    for k,v in inv.get('env',{}).items():cmd+=['-e',k+'='+v]
    cmd += ['--mount',f'type=bind,src={self.root / "tools"},dst=/opt/studio/tools,readonly',sandbox['image']]+inner
   else:
    # Host mode: the configured CLI runs directly on this workstation. It is only
    # reachable after an explicit sandbox.type='host' opt-in and a passing twelve
    # case admission report for the current profile. There is no OS level isolation,
    # so the child environment stays narrowed, arguments never pass through a shell
    # and provenance records 'host'. Do not point this at a CLI that can reach
    # unrelated directories. The studio interpreter is put first on PATH so the
    # documented render helper resolves to the environment that has its packages.
    exe=shutil.which(inv['cmd']);ensure(exe,'未找到本机可执行文件 '+str(inv['cmd'])+'，无法启用本机 Runner；请安装该 CLI 或把 invoke.cmd 写成绝对路径','configuration_required',400)
    for extra in ('APPDATA','LOCALAPPDATA','PROGRAMDATA','SYSTEMDRIVE'):
     if os.environ.get(extra):env[extra]=os.environ[extra]
    # The studio interpreter goes first so the documented render helper resolves to the
    # environment that has its packages. prependPath then adds machine specific tools,
    # for example a real bash for agents whose shell tool would otherwise pick the WSL
    # stub. It is additive, so a later PATH change on this machine is picked up.
    parts=[str(Path(sys.executable).parent)]+[str(p) for p in (inv.get('prependPath') or [])]
    env['PATH']=os.pathsep.join(parts+[env.get('PATH','')])
    cmd=[exe]+args
  timeout=float(task['limits'].get('timeout',profile['limits']['defaultTimeout']));maxturns=int(task['limits'].get('maxTurns',20));budget=float(task['limits'].get('budget',0));estimate=float(profile['limits'].get('costPerRunEstimate',0))
  if budget and estimate>budget:return {'status':'budget_exceeded','artifacts':[],'report':{'failureClass':'budget','notes':'Runner 预估成本超过本次预算'},'usage':{'wallTime':0,'turns':0,'cost':0},'runner':{'id':name,'version':profile['adapterVersion'],'invocation':self.safe_invocation(cmd)}}
  kwargs={'cwd':work,'env':env,'stdout':subprocess.PIPE,'stderr':subprocess.PIPE,'stdin':subprocess.DEVNULL,'text':True,'encoding':'utf-8','errors':'replace','bufsize':1,'shell':False}
  if os.name=='nt':kwargs['creationflags']=subprocess.CREATE_NEW_PROCESS_GROUP
  else:kwargs['start_new_session']=True
  try:proc=subprocess.Popen(cmd,**kwargs)
  except OSError as e:return {'status':'failed','artifacts':[],'report':{'failureClass':'cli_start','notes':str(e)},'usage':{'wallTime':time.monotonic()-start,'turns':0},'runner':{'id':name,'version':profile['adapterVersion'],'invocation':self.safe_invocation(cmd)}}
  q=queue.Queue();logs=[];errors=[];turns=0;cost=0;state=None;last_result=None;seen=set()
  def nested_events(value,depth=0):
   """An agent CLI runs the task inside its own shell tool and keeps the child's
   stdout inside its event stream. Recover those normalized events so turn and
   budget limits stay enforceable for agent adapters. Identical payloads are
   reported once because streamed partial messages repeat their own content."""
   if depth>6:return
   if isinstance(value,str):
    for candidate in value.splitlines():
     candidate=candidate.strip()
     if len(candidate)>2 and candidate[0]=='{' and candidate[-1]=='}':
      if candidate in seen:continue
      seen.add(candidate)
      try:yield json.loads(candidate)
      except (json.JSONDecodeError,TypeError):pass
   elif isinstance(value,dict):
    for item in value.values():yield from nested_events(item,depth+1)
   elif isinstance(value,list):
    for item in value:yield from nested_events(item,depth+1)
  def drain(pipe,label):
   for line in iter(pipe.readline,''):q.put((label,line))
   pipe.close()
  readers=[threading.Thread(target=drain,args=(proc.stdout,'stdout'),daemon=True),threading.Thread(target=drain,args=(proc.stderr,'stderr'),daemon=True)]
  for t in readers:t.start()
  try:
   while proc.poll() is None or not q.empty() or any(t.is_alive() for t in readers):
    check()
    if time.monotonic()-start>timeout:state='timeout';self.kill(proc);break
    try:label,line=q.get(timeout=.05)
    except queue.Empty:continue
    (logs if label=='stdout' else errors).append(line)
    if sum(map(len,logs))+sum(map(len,errors))>8*1024*1024:state='rejected';self.kill(proc);break
    try:event=json.loads(line)
    except (json.JSONDecodeError,TypeError):continue
    for item in [event,*(nested_events(event))]:
     if item.get('type') in ('turn_start','turn.started','tool_execution_start'):turns+=1
     if item.get('status') in ('ok','failed','timeout','budget_exceeded','rejected') and 'artifacts' in item:last_result=item
     message=item.get('message');usage=item.get('usage') or (message.get('usage') if isinstance(message,dict) else None) or {}
     cost=max(cost,float(usage.get('cost',{}).get('total',0) if isinstance(usage.get('cost'),dict) else usage.get('cost',0)))
     if turns>maxturns:state='rejected';self.kill(proc);break
     if budget and cost>budget:state='budget_exceeded';self.kill(proc);break
    if state:break
   try:proc.wait(timeout=5)
   except subprocess.TimeoutExpired:
    # Windows taskkill may fail to terminate the immediate process even when its
    # tree command completed. Normalize the timeout and reap the direct child.
    state=state or 'timeout';self.kill(proc)
    try:proc.wait(timeout=5)
    except subprocess.TimeoutExpired:
     proc.kill()
     try:proc.wait(timeout=2)
     except subprocess.TimeoutExpired:pass
  except Exception:
   self.kill(proc);raise
  finally:
   if container_name:
    try:subprocess.run(['docker','rm','-f',container_name],capture_output=True,timeout=15)
    except (OSError,subprocess.TimeoutExpired):pass
   for t in readers:t.join(timeout=1)
   # Original task contains credentials only on disk for this process; remove it.
   redacted=self.redact_task(task);taskfile.write_text(json.dumps(redacted,ensure_ascii=False,indent=2),encoding='utf-8')
   (work/'stdout.log').write_text(''.join(logs),encoding='utf-8');(work/'stderr.log').write_text(''.join(errors),encoding='utf-8')
  provenance={'id':name,'version':profile['adapterVersion'],'invocation':self.safe_invocation(cmd),'sandbox':'trusted_builtin' if mode=='builtin' else mode}
  result=last_result;remote=None
  if reportfile.exists():
   try:result=json.loads(reportfile.read_text(encoding='utf-8'))
   except json.JSONDecodeError:pass
  submitfile=work/'provider-submit.json'
  if submitfile.exists():
   try:
    remote=json.loads(submitfile.read_text(encoding='utf-8'))
    if isinstance(result,dict):result.setdefault('remote',remote)
   except (OSError,json.JSONDecodeError):pass
  if not isinstance(result,dict):result=None
  if state or proc.returncode or not result:
   failure={'status':state or 'failed','artifacts':[],'report':{'failureClass':'max_turns' if turns>maxturns else 'cli_error','notes':(''.join(errors)[-3000:] or 'Runner 没有返回合法 RunResult')},'usage':{'wallTime':round(time.monotonic()-start,3),'turns':turns,'cost':cost},'runner':provenance}
   if remote:failure['remote']=remote
   return failure
  if name!='subprocess':
   usage=result.setdefault('usage',{});raw=usage.get('cost',0);media_cost=float(raw.get('total',0) if isinstance(raw,dict) else raw);usage['mediaCost']=media_cost;usage['executionCost']=max(cost,estimate);usage['cost']=media_cost+max(cost,estimate);usage['costKnown']=bool(cost) and usage.get('costKnown',False)
  result['runner']=provenance;result.setdefault('usage',{}).update(wallTime=round(time.monotonic()-start,3),turns=max(turns,result.get('usage',{}).get('turns',0)))
  try:RunResult.model_validate(result)
  except Exception as e:result={'status':'failed','artifacts':[],'report':{'failureClass':'malformed_report','notes':'Runner 回执不是合法 RunResult：'+str(e)},'usage':result.get('usage',{}),'runner':provenance}
  try:
   if task.get('reportSchema'):jsonschema.validate(result,task['reportSchema'])
   for art in result.get('artifacts',[]):
    path=str(art['path'])
    if mode=='docker' and path.startswith('/work/'):path=str(work/path[len('/work/'):])
    p=Path(path).resolve();ensure(p.is_relative_to(work) and p.is_file(),'Runner 产物越界或不存在','path_escape',403)
    ensure(p.stat().st_size>=task['acceptance'].get('minBytes',1),'产物为空')
    ext=task['acceptance'].get('extensions',[]);ensure(not ext or p.suffix.lower() in ext,'产物格式与验收不符')
    art.update(path=str(p),size=p.stat().st_size,sha256=hashlib.sha256(p.read_bytes()).hexdigest())
   ensure(result['status']!='ok' or result.get('artifacts') or task['acceptance'].get('allowNoArtifacts'),'任务声称成功但没有产物')
  except Exception as e:result={'status':'rejected','artifacts':[],'report':{'failureClass':'acceptance','notes':str(e)},'usage':result.get('usage',{}),'runner':provenance}
  return result
 def safe_invocation(self,cmd):
  result=[];redact_next=False
  for s in cmd:
   if redact_next:result.append('<redacted>');redact_next=False;continue
   if s in ('--api-key','-e'):result.append(s);redact_next=True
   else:result.append(s[:400] if len(s)>400 else s)
  return result
 @staticmethod
 def kill(proc):
  if proc.poll() is not None:return
  try:
   if os.name=='nt':
    subprocess.run(['taskkill','/PID',str(proc.pid),'/T','/F'],capture_output=True,timeout=5)
    if proc.poll() is None:proc.kill()
   else:os.killpg(proc.pid,signal.SIGKILL)
  except (ProcessLookupError,OSError,subprocess.TimeoutExpired):proc.kill()
