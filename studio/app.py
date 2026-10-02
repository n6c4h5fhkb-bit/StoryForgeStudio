"""Single host, database, queue and two logically separate workspaces."""
from __future__ import annotations

import importlib
import importlib.util
import os
import sys
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse, RedirectResponse

from .core import Store, Jobs, DomainError, ensure, digest, uid
from .settings import Settings
from .migration import import_legacy

ROOT = Path(__file__).resolve().parents[1]


def package(name, path):
    if name not in sys.modules:
        spec = importlib.util.spec_from_file_location(name, path / '__init__.py', submodule_search_locations=[str(path)])
        module = importlib.util.module_from_spec(spec)
        sys.modules[name] = module
        spec.loader.exec_module(module)
    return importlib.import_module(name + '.main')


def create_app(data_dir=None):
    root = Path(data_dir or os.environ.get('STUDIO_DATA', ROOT / 'data')).resolve()
    legacy = [ROOT / 'system-a' / 'data', ROOT / 'system-b' / 'data']
    ensure(root not in (path.resolve() for path in legacy),'统一数据库不能直接写入旧 A/B 数据目录','data_directory',409)
    store = Store(root)
    if (data_dir is None and not os.environ.get('STUDIO_DATA')) or os.environ.get('STUDIO_MIGRATE_LEGACY') == '1':
        import_legacy(store, legacy)
    store.media_roots = [root / 'media', *(path / 'media' for path in legacy)]
    settings, jobs = Settings(root), Jobs(store)
    shared = {'store': store, 'settings': settings, 'jobs': jobs}
    embedded = os.environ.get('STUDIO_EMBEDDED')
    os.environ['STUDIO_EMBEDDED'] = '1'
    try:
        a = package('studio_a', ROOT / 'system-a' / 'app').create_app(root, shared=shared)
        b = package('studio_b', ROOT / 'system-b' / 'app').create_app(root, shared=shared)
    finally:
        if embedded is None:
            os.environ.pop('STUDIO_EMBEDDED', None)
        else:
            os.environ['STUDIO_EMBEDDED'] = embedded
    app = FastAPI(title='Story Studio · 剧本与制作', version='3.0.0')
    app.state.store = store
    app.state.workspaces = {'A': a, 'B': b}
    def import_story_to_a(production_id,package_data):
        production=store.get(production_id)
        claimed=package_data.get('project',{}).get('sourceId') or package_data.get('source',{}).get('projectId')
        source=store.get(claimed,required=False) if claimed else None
        if source and source.get('workspace')=='A':
            try:
                current=a.state.formats.source_package(source['id'])
                if current.get('versionFingerprint')!=package_data.get('versionFingerprint'):
                    source=None
            except DomainError:
                source=None
        else:
            source=None
        if not source:
            source=a.state.formats.import_source(package_data,production.get('presentationMode','fast_drama'))
        production.update(sourceProjectId=source['id'])
        store.put('project',production,production_id)
        return {'sourceProjectId':source['id'],'url':'/a/?project='+source['id'],'note':'旧交接稿已放入 A；在 A 采用呈现版本后再继续制作。'}
    b.state.service.story_bridge=import_story_to_a

    @app.exception_handler(DomainError)
    async def error(request, exc):
        return JSONResponse({'error': str(exc), 'code': exc.code, 'details': exc.details}, status_code=exc.status)

    @app.middleware('http')
    async def local_only(request: Request, call_next):
        from urllib.parse import urlparse
        ensure_host = request.headers.get('host', '').split(':')[0] in ('127.0.0.1', 'localhost', 'testserver', '[', '::1')
        origin = request.headers.get('origin')
        if not ensure_host or (origin and urlparse(origin).netloc != request.headers.get('host')):
            return JSONResponse({'error': '仅允许本机同来源访问'}, status_code=403)
        if request.method not in ('GET', 'HEAD', 'OPTIONS') and request.url.path.startswith(('/api/','/a/api/','/b/api/')) and request.headers.get('x-studio-client') != 'local-ui':
            return JSONResponse({'error': '缺少本地客户端请求标记'}, status_code=403)
        parts=request.url.path.strip('/').split('/')
        if len(parts)==5 and parts[0] in ('a','b') and parts[1:3]==['api','jobs'] and parts[4]=='resume':
            job=jobs.get(parts[3]);project=store.get(job['project'],required=False) if job.get('project') else None
            target='b' if (project or {}).get('workspace')=='B' else 'a'
            if target!=parts[0]:return RedirectResponse('/'+target+'/api/jobs/'+parts[3]+'/resume',status_code=307)
        return await call_next(request)

    @app.get('/')
    def home(workspace: str = 'A'):
        return RedirectResponse('/b/' if workspace.upper() == 'B' else '/a/')

    @app.get('/api/health')
    def health():
        return {'ok': True, 'system': 'SYSTEM AB', 'version': '3.0.0', 'workspaces': ['A', 'B']}

    @app.get('/api/workspaces')
    def workspaces():
        return {'A': '/a/', 'B': '/b/', 'database': 'shared', 'handoff': 'adopted_version'}

    @app.post('/api/handoff')
    def handoff(data: dict):
        source_id = data.get('projectId', '')
        project = store.get(source_id)
        ensure(project.get('workspace', 'A') == 'A', '请选择 A 的剧本项目')
        formats = a.state.formats
        selected = data.get('scriptVersionId') or project.get('activeScriptVersionId')
        ensure(selected, '先在 A 采用要制作的剧本版本', 'script_adoption_required', 409)
        script = store.get(selected)
        ensure(script['projectId'] == source_id and script.get('status') == 'adopted', '只交接已采用的正式版本', 'script_adoption_required', 409)
        package_data = formats.export_package(source_id, selected)
        target_id = data.get('productionProjectId')
        if target_id:
            target = store.get(target_id)
            ensure(target.get('workspace') == 'B' and target.get('sourceProjectId') == source_id and target.get('presentationMode') == script['mode'],
                   '制作分支不属于此作品与呈现方向', 'production_branch', 409)
        else:
            target = next((row for row in store.list(kind='project') if row.get('workspace') == 'B' and row.get('sourceProjectId') == source_id and row.get('presentationMode') == script['mode']), None)
            if not target:
                target = b.state.service.create({'title': project['title'], 'workflowVersion': 4, 'presentationMode': script['mode'],
                                                  'preset': {'cinema': 'cinema', 'series': 'series', 'fast_drama': 'vertical'}[script['mode']],
                                                  'aspectRatio': data.get('aspectRatio', '16:9')})['project']
                target.update(sourceProjectId=source_id, workspace='B')
                store.put('project', target, target['id'])
            target_id = target['id']
        service = b.state.service
        if target.get('sourceScriptVersionId') == selected:
            return {'projectId': target_id, 'scriptVersionId': selected, 'idempotent': True, 'url': '/b/?project=' + target_id}
        preview = service.script_import_plan(target_id, package_data)
        if preview['impacts'] and data.get('planHash') != preview['planHash']:
            return {'requiresChoice': True, 'preview': preview, 'projectId': target_id}
        result = service.import_script_package(target_id, package_data, plan_hash=preview['planHash'])
        return {**result, 'projectId': target_id, 'scriptVersionId': selected, 'url': '/b/?project=' + target_id}

    @app.post('/api/change-requests/{identifier}/apply')
    def change_request(identifier: str, data: dict):
        request = store.get(identifier)
        ensure(request.get('sourceProjectId') and request.get('status') == 'pending', '修改建议不存在或已处理')
        return {'projectId': request['sourceProjectId'], 'requestId': identifier, 'url': '/a/?project=' + request['sourceProjectId'] + '&changeRequest=' + identifier}

    @app.api_route('/api/{path:path}', methods=['GET','POST','PUT','PATCH','DELETE'])
    async def legacy_api(path:str, request:Request):
        # Native download links from older workbenches retain their workspace.
        from urllib.parse import urlparse
        referer=urlparse(request.headers.get('referer','')).path
        prefix='/b' if referer.startswith('/b/') else '/a'
        parts=path.split('/')
        if len(parts)>1 and parts[0]=='projects':
            project=store.get(parts[1],required=False)
            if project:prefix='/b' if project.get('workspace')=='B' else '/a'
        return RedirectResponse(prefix+'/api/'+path+('?' + request.url.query if request.url.query else ''),status_code=307)

    @app.get('/media/{path:path}')
    async def legacy_media(path:str, request:Request):
        project=store.get(path.split('/')[0],required=False)
        prefix='/b' if (project or {}).get('workspace')=='B' else '/a'
        return RedirectResponse(prefix+'/media/'+path,status_code=307)

    @app.get('/static/{path:path}')
    async def legacy_static(path:str, request:Request):
        from urllib.parse import urlparse
        prefix='/b' if urlparse(request.headers.get('referer','')).path.startswith('/b/') else '/a'
        return RedirectResponse(prefix+'/static/'+path,status_code=307)

    app.mount('/a', a)
    app.mount('/b', b)
    return app


app = create_app()
