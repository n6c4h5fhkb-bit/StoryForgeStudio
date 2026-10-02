from __future__ import annotations
import copy,time
from concurrent.futures import ThreadPoolExecutor
from .core import uid,now,digest,ensure

def behavioral_hash(profile):return digest({k:v for k,v in profile.items() if k!='enabled'})
class Qualification:
 """Twelve fixed admission groups. No fake certification from declared abilities.
 External runners execute the fixture through their actual CLI in Docker. Some
 adapters may need event normalization before passing turn/budget tests.
 """
 def __init__(self,registry):self.r=registry;self.s=registry.s
 def run(self,id,progress=lambda *_:None,check=lambda:None):
  profile=self.r.profiles()[id];groups=[('正常产物','normal','ok'),('中文路径产物','unicode','ok'),('自愈回执一','heal1','ok'),('自愈回执二','heal2','ok'),('主动拒绝任务','reject','rejected'),('非零退出归一化','cli_error','failed'),('损坏回执归一化','malformed','failed'),('超时中止','timeout','timeout'),('预算中止','budget','budget_exceeded'),('轮次中止','turns','rejected'),('越界产物拦截','escape','rejected'),('八路并发稳定性','concurrent','ok')];results=[];suiteid=uid('suite')
  def test(case,index):
   check();taskid=uid('qtask');work=self.s.root/'qualification'/suiteid/(str(index)+'-'+taskid);work.mkdir(parents=True,exist_ok=True)
   task={'taskId':taskid,'role':'operator','stage':'TEST','task':'qualification','objective':'验收任务：仅执行 python /opt/studio/tools/qualification_fixture.py /work/task.json。不要修复故意制造的失败，不篡改返回状态。保持 fixture 的 stdout 事件流与 report.json 原样。','inputs':{'case':case,'prompt':'identity freeze exact','freezeStrings':['identity freeze exact']},'tools':['read_task','write_report'],'workdir':str(work.resolve()),'acceptance':{'minBytes':10,'extensions':['.png'],'allowNoArtifacts':case=='reject'},'limits':{'maxTurns':2 if case=='turns' else 50,'timeout':1.5 if case=='timeout' else 120,'budget':1 if case=='budget' else 10},'reportSchema':{}}
   return self.r.run_process(task,profile,check,qualification=True)
  for i,(label,case,expected) in enumerate(groups):
   start=time.monotonic();check()
   try:
    if case=='concurrent':
     with ThreadPoolExecutor(max_workers=8) as pool:outputs=list(pool.map(lambda j:test('normal',str(i)+'-'+str(j)),range(8)))
     passed=all(x['status']=='ok' for x in outputs);result={'statuses':[x['status'] for x in outputs]}
    else:
     result=test(case,i);passed=result['status']==expected
     if case.startswith('heal'):passed=passed and result.get('report',{}).get('actualPrompt')!='identity freeze exact'
    record={'name':label,'case':case,'passed':passed,'expected':expected,'result':result,'wallTime':round(time.monotonic()-start,3)}
   except Exception as e:record={'name':label,'case':case,'passed':False,'expected':expected,'error':str(e)}
   results.append(record);progress((i+1)/len(groups),f'Runner 验收 {i+1}/12：{label}')
  report={'id':'qualification_'+id,'runnerId':id,'suiteId':suiteid,'profileHash':behavioral_hash(profile),'passed':all(x['passed'] for x in results),'results':results,'createdAt':now(),'environment':'真实本地子进程' if id=='subprocess' else '实际 Agent CLI / Docker','note':'通过只代表本次配置下的验收；未验证真实收费模型渲染质量。'};self.s.put('qualification',report,'__system__');self.s.audit('__system__','runner_qualified',[id],{'passed':report['passed'],'suiteId':suiteid});return report
