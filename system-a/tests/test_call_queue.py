import json
from pathlib import Path
import subprocess
import sys
import time

from app.call_queue import AccountQueue


def spawn(home, result, mode='normal', duration=.4):
    return subprocess.Popen([sys.executable,str(Path(__file__).parent/'fixtures'/'queue_worker.py'),str(home),str(result),mode,str(duration)],
        stdout=subprocess.PIPE,stderr=subprocess.PIPE,creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0))


def wait_until(predicate):
    deadline=time.monotonic()+8
    while not predicate():
        assert time.monotonic()<deadline,'worker did not reach expected state'
        time.sleep(.02)


def finish(process, code=0):
    try:
        out,err=process.communicate(timeout=8)
        assert process.returncode==code,(out,err)
    finally:
        if process.poll() is None:process.kill();process.wait()


def test_independent_studio_processes_share_fifo_without_overlapping_inference(tmp_path):
    home=tmp_path/'account';one=tmp_path/'a.json';two=tmp_path/'b.json';three=tmp_path/'c.json'
    first=spawn(home,one,duration=.6)
    wait_until(lambda:one.with_suffix('.entered').exists())
    second=spawn(home,two)
    queue=AccountQueue(home)
    def waiting():
        with queue.connect() as conn:return conn.execute("SELECT count(*) FROM tickets WHERE state='waiting'").fetchone()[0]>=1
    wait_until(waiting)
    third=spawn(home,three)
    for process in (first,second,third):finish(process)
    a,b,c=[json.loads(p.read_text()) for p in (one,two,three)]
    assert a['end']<=b['start'] and b['end']<=c['start']
    assert b['queueWaitSeconds']>0 and b['accountConcurrency']==1
    with queue.connect() as conn:assert conn.execute('SELECT count(*) FROM tickets').fetchone()[0]==0


def test_cancel_while_queued_removes_ticket_without_entering(tmp_path):
    home=tmp_path/'account';result=tmp_path/'cancelled.json';queue=AccountQueue(home)
    with queue.acquire():
        process=spawn(home,result)
        def waiting():
            with queue.connect() as conn:return conn.execute('SELECT count(*) FROM tickets').fetchone()[0]==2
        wait_until(waiting);result.with_suffix('.cancel').write_text('cancel')
        finish(process)
        assert json.loads(result.read_text())['error']=='cancelled'
        assert not result.with_suffix('.entered').exists()
    with queue.connect() as conn:assert conn.execute('SELECT count(*) FROM tickets').fetchone()[0]==0


def test_owner_crash_releases_account_for_another_process(tmp_path):
    home=tmp_path/'account';crashed=tmp_path/'crashed.json';next_result=tmp_path/'next.json'
    process=spawn(home,crashed,'crash');finish(process,23)
    next_process=spawn(home,next_result);finish(next_process)
    assert json.loads(next_result.read_text())['queueWaitSeconds']<2


def test_separate_homes_do_not_block_each_other(tmp_path):
    with AccountQueue(tmp_path/'a').acquire():
        result=tmp_path/'b.json';process=spawn(tmp_path/'b',result);finish(process)
        assert json.loads(result.read_text())['queueWaitSeconds']<1

