#!/usr/bin/env python3
"""Start one local application containing A and B; original entry points delegate here."""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import subprocess
import sys
import threading
import time
import urllib.request
import webbrowser
from pathlib import Path

ROOT = Path(__file__).resolve().parent

def load_env():
    for directory in (ROOT,ROOT/'system-a',ROOT/'system-b'):
        path=directory/'.env'
        if not path.is_file():continue
        for line in path.read_text(encoding='utf-8-sig').splitlines():
            if not line.strip() or line.lstrip().startswith('#') or '=' not in line:continue
            key,value=line.split('=',1);key=key.strip();value=value.strip().strip('"').strip("'")
            if key.startswith('STUDIO_') and (directory==ROOT or key!='STUDIO_DATA'):os.environ.setdefault(key,value)


def main():
    if sys.version_info < (3, 11):
        raise SystemExit('需要 Python 3.11 或更新版本。')
    parser = argparse.ArgumentParser(description='A 剧本 + B 导演与制作 · 统一工作室')
    parser.add_argument('--port', type=int, default=8787)
    parser.add_argument('--workspace', choices=['A', 'B'], default='A')
    parser.add_argument('--data', type=Path)
    parser.add_argument('--no-browser', action='store_true')
    parser.add_argument('--no-install', action='store_true')
    args = parser.parse_args()
    load_env()
    os.environ['PYTHONUTF8'] = '1'
    os.environ['PYTHONIOENCODING'] = 'utf-8'
    if args.data:
        os.environ['STUDIO_DATA'] = str(args.data.resolve())
    if os.environ.get('STUDIO_DATA') and Path(os.environ['STUDIO_DATA']).resolve() in ((ROOT/'system-a/data').resolve(),(ROOT/'system-b/data').resolve()):
        raise SystemExit('统一数据库不能直接写入旧 A/B 数据目录。请取消旧 STUDIO_DATA 设置，或用 --data 指定新的独立目录。')
    origin = f'http://127.0.0.1:{args.port}'
    destination = origin + ('/b/' if args.workspace == 'B' else '/a/')
    for port in dict.fromkeys([args.port,8787,8788]):
        try:
            with urllib.request.urlopen(f'http://127.0.0.1:{port}/api/health',timeout=1) as response:health=json.load(response)
        except (OSError,ValueError):continue
        if port==args.port and health.get('system')=='SYSTEM AB':
            print('统一工作室已在运行：'+destination,flush=True)
            if not args.no_browser:webbrowser.open(destination)
            return 0
        if health.get('system') in ('SYSTEM A','SYSTEM B','SYSTEM AB'):
            raise SystemExit('旧服务或另一统一工作室仍在运行。请关闭旧 A/B 服务终端后重新启动；项目和素材保留。')
    envdir = ROOT / 'system-b' / '.venv'
    interpreter = envdir / ('Scripts/python.exe' if os.name == 'nt' else 'bin/python')
    if not interpreter.is_file():
        envdir = ROOT / 'system-a' / '.venv'
        interpreter = envdir / ('Scripts/python.exe' if os.name == 'nt' else 'bin/python')
    if not interpreter.is_file():
        subprocess.run([sys.executable, '-m', 'venv', str(envdir)], check=True, cwd=ROOT)
    requirements = ROOT / 'system-b' / 'requirements.txt'
    fingerprint = hashlib.sha256(requirements.read_bytes()).hexdigest()
    marker = envdir / '.unified-dependencies'
    previous_marker=envdir/'.dependencies'
    installed=any(path.is_file() and path.read_text().strip()==fingerprint for path in (marker,previous_marker))
    if not args.no_install and not installed:
        subprocess.run([str(interpreter), '-m', 'pip', 'install', '--disable-pip-version-check', '-r', str(requirements)], check=True, cwd=ROOT)
        marker.write_text(fingerprint)
    print('统一工作室：' + destination + '\nA/B 共用数据库；首次启动会保留原库并导入历史记录。', flush=True)
    server = subprocess.Popen([str(interpreter), '-m', 'uvicorn', 'studio.app:app', '--host', '127.0.0.1', '--port', str(args.port)], cwd=ROOT, env=os.environ.copy())
    def open_when_ready():
        for _ in range(120):
            if server.poll() is not None:
                return
            try:
                with urllib.request.urlopen(origin + '/api/health', timeout=1):
                    pass
                webbrowser.open(destination)
                return
            except OSError:
                time.sleep(.5)
    if not args.no_browser:
        threading.Thread(target=open_when_ready, daemon=True).start()
    try:
        return server.wait()
    except KeyboardInterrupt:
        server.terminate()
        try:
            server.wait(timeout=10)
        except subprocess.TimeoutExpired:
            server.kill()
        return 0


if __name__ == '__main__':
    raise SystemExit(main())
