#!/usr/bin/env python3
"""Standalone local launcher. Creates an isolated venv; no Node.js/database server.
Run `python launcher.py --help` for test, diagnosis and data directory options.
"""
from __future__ import annotations
import argparse,hashlib,json,os,shutil,subprocess,sys,threading,time,urllib.request,webbrowser
from pathlib import Path
ROOT=Path(__file__).resolve().parent
SYSTEM=ROOT.name[-1].upper() if ROOT.name.lower() in ('system-a','system-b') else 'B'
PORT=8788
def load_env():
    path=ROOT/'.env'
    if path.exists():
        for line in path.read_text(encoding='utf-8-sig').splitlines():
            if not line.strip() or line.lstrip().startswith('#') or '=' not in line:continue
            key,value=line.split('=',1);key=key.strip();value=value.strip().strip('"').strip("'")
            if key.startswith('STUDIO_'):os.environ.setdefault(key,value)

def main():
    if '--legacy' not in sys.argv and '--test' not in sys.argv and '--check' not in sys.argv:
        import runpy
        entry=ROOT.parent/'launcher.py'
        sys.argv=[str(entry),'--workspace',SYSTEM,*sys.argv[1:]]
        runpy.run_path(str(entry),run_name='__main__')
        return 0
    if '--legacy' in sys.argv:sys.argv.remove('--legacy')
    if sys.version_info<(3,11):raise SystemExit('Python 3.11 or newer is required. Install Python, then reopen this launcher.')
    parser=argparse.ArgumentParser(description='System '+SYSTEM+' independent local studio')
    parser.add_argument('--port',type=int,default=PORT);parser.add_argument('--data',type=Path)
    parser.add_argument('--no-browser',action='store_true');parser.add_argument('--no-install',action='store_true')
    parser.add_argument('--check',action='store_true',help='Print local diagnostics and exit')
    parser.add_argument('--test',action='store_true',help='Install development dependencies and run automated tests')
    args=parser.parse_args();load_env();os.environ['PYTHONUTF8']='1';os.environ['PYTHONIOENCODING']='utf-8'
    if args.data:os.environ['STUDIO_DATA']=str(args.data.resolve())
    envdir=ROOT/'.venv';python=envdir/('Scripts/python.exe' if os.name=='nt' else 'bin/python')
    if not python.exists():
        print('Creating isolated Python environment...',flush=True)
        subprocess.run([sys.executable,'-m','venv',str(envdir)],check=True,cwd=ROOT)
    req=ROOT/('requirements-dev.txt' if args.test else 'requirements.txt')
    fingerprint=hashlib.sha256(req.read_bytes()+(ROOT/'requirements.txt').read_bytes()).hexdigest()
    marker=envdir/('.dependencies-dev' if args.test else '.dependencies')
    if not args.no_install and (not marker.exists() or marker.read_text()!=fingerprint):
        print('Installing pinned dependencies (first launch requires internet)...',flush=True)
        subprocess.run([str(python),'-m','pip','install','--disable-pip-version-check','-r',str(req)],check=True,cwd=ROOT)
        marker.write_text(fingerprint)
    if args.check:
        code="import sys,fastapi,imageio_ffmpeg,shutil,json;print(json.dumps({'python':sys.version,'fastapi':fastapi.__version__,'ffmpeg':shutil.which('ffmpeg') or imageio_ffmpeg.get_ffmpeg_exe(),'ffprobe':shutil.which('ffprobe'),'docker':shutil.which('docker')},ensure_ascii=False,indent=2))"
        return subprocess.call([str(python),'-c',code],cwd=ROOT)
    if args.test:return subprocess.call([str(python),'-m','pytest','-q'],cwd=ROOT)
    url=f'http://127.0.0.1:{args.port}'
    try:
        with urllib.request.urlopen(url+'/api/health',timeout=1) as r:health=json.load(r)
        if health.get('system')=='SYSTEM '+SYSTEM:
            print('This studio is already running: '+url)
            if not args.no_browser:webbrowser.open(url)
            return 0
        raise SystemExit('Port is occupied. Use --port with another number.')
    except OSError:pass
    except ValueError:raise SystemExit('Port is occupied by another service. Use --port.')
    print('\nSYSTEM '+SYSTEM+' · '+url+'\nKeep this terminal open. Ctrl+C stops the server.\nData: '+os.environ.get('STUDIO_DATA',str(ROOT/'data'))+'\n',flush=True)
    proc=subprocess.Popen([str(python),'-m','uvicorn','app.main:app','--host','127.0.0.1','--port',str(args.port)],cwd=ROOT,env=os.environ.copy())
    def open_when_ready():
        for _ in range(120):
            if proc.poll() is not None:return
            try:
                with urllib.request.urlopen(url+'/api/health',timeout=1):pass
                webbrowser.open(url);return
            except OSError:time.sleep(.5)
    if not args.no_browser:threading.Thread(target=open_when_ready,daemon=True).start()
    try:return proc.wait()
    except KeyboardInterrupt:
        proc.terminate()
        try:proc.wait(timeout=10)
        except subprocess.TimeoutExpired:proc.kill();proc.wait()
        return 0
if __name__=='__main__':
    try:raise SystemExit(main())
    except subprocess.CalledProcessError as e:
        print('\nCommand failed. Check network/proxy and the error above. Retrying does not delete your projects.\n',file=sys.stderr)
        raise SystemExit(e.returncode)
