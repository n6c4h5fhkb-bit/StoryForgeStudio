"""Build an offline review package from docs and static source metadata only.

Never imports the apps, opens production databases, or reads user settings.
"""
from pathlib import Path
import ast
import datetime
import hashlib
import html
from html.parser import HTMLParser
import json
import re
import shutil
import subprocess
import zipfile

OUT = Path(__file__).resolve().parent
ROOT = OUT.parent.parent
DATE = '2026-09-29'

def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()

def source_record(path):
    raw = path.read_text(encoding='utf-8-sig')
    row = {'path': path.relative_to(ROOT).as_posix(), 'sha256': sha(path),
           'lines': len(raw.splitlines()), 'routes': [], 'symbols': [], 'documentKinds': []}
    if path.suffix != '.py':
        return row
    tree = ast.parse(raw)
    def walk(body, parents=()):
        for node in body:
            if isinstance(node, (ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef)):
                parts = parents + (node.name,)
                row['symbols'].append({'name': '.'.join(parts), 'line': node.lineno,
                                       'type': type(node).__name__})
                for deco in getattr(node, 'decorator_list', []):
                    if (isinstance(deco, ast.Call) and isinstance(deco.func, ast.Attribute)
                            and deco.func.attr in ('get','post','put','patch','delete')
                            and deco.args and isinstance(deco.args[0], ast.Constant)):
                        row['routes'].append({'method': deco.func.attr.upper(),
                            'path': deco.args[0].value, 'line': deco.lineno,
                            'handler': '.'.join(parts)})
                walk(node.body, parts)
    walk(tree.body)
    kinds = set()
    for node in ast.walk(tree):
        if (isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute)
                and node.func.attr == 'put' and node.args
                and isinstance(node.args[0], ast.Constant)
                and isinstance(node.args[0].value, str)
                and not node.args[0].value.startswith('/')):
            kinds.add(node.args[0].value)
    row['documentKinds'] = sorted(kinds)
    return row

records = []
for system in ('system-a', 'system-b'):
    for directory in ('app', 'static', 'tools', 'tests'):
        for path in sorted((ROOT / system / directory).rglob('*')):
            if path.is_file() and path.suffix in ('.py','.js','.css','.html') and '__pycache__' not in path.parts:
                records.append(source_record(path))
    for name in ('requirements.txt','MANIFEST.json'):
        records.append(source_record(ROOT / system / name))

manifests = {}
for system in ('system-a','system-b'):
    original = json.loads((ROOT/system/'MANIFEST.json').read_text(encoding='utf-8'))
    manifests[system] = {k: original.get(k) for k in ('release','edition','pythonMinimum','testCount',
        'paidProvidersLiveVerified','nativeWindowsVerified','browserVerified','handoffChecks')}

evidence_paths = [
    'system-a/docs/pytest-result.txt', 'system-b/docs/pytest-result.txt',
    '.validation/collaboration-a-tests.xml', '.validation/collaboration-b-tests.xml',
    '.validation/upgrade-20260927/browser-result.json', '.validation/upgrade-20260928/browser-result.json',
    '.validation/reader-smoke-results.json', '.validation/storyboard-copy/verification.json',
    '.validation/codex-system-b-b1ab6274/verification.json',
    '.validation/codex-result-binding-c2b6202d/verification.json',
    '.validation/collaboration-real-a-5c254b88/verification.json',
    '.validation/handoff-6c841e26c8784b57a62414bec6a3af18/result.json',
]
evidence = [{'path': value, 'exists': (ROOT/value).is_file(),
             **({'sha256': sha(ROOT/value)} if (ROOT/value).is_file() else {})} for value in evidence_paths]
recovery = next(r for r in records if r['path']=='system-b/app/production.py')
assert any(s['name']=='ProductionService.asset_render.recover_remote' for s in recovery['symbols'])
assert not any(s['name']=='ProductionService.recover_remote' for s in recovery['symbols'])
snapshot = {'format':'ABReviewSourceIndex-v1','snapshotDate':DATE,
    'generatedAt': datetime.datetime.now(datetime.timezone.utc).isoformat(),
    'method':'static AST and file SHA-256; apps not imported; production data not read',
    'releaseManifests':manifests, 'files':records, 'validationEvidenceIndex':evidence,
    'confirmedFinding': {'id':'R16','path':'system-b/app/production.py',
        'symbol':'ProductionService.asset_render.recover_remote',
        'evidence':'Nested in asset_render, not a ProductionService class method; route calls b.recover_remote.'}}
(OUT/'05-代码快照索引.json').write_text(json.dumps(snapshot,ensure_ascii=False,indent=2),encoding='utf-8')

key_names = {
    'core.py':'数据、审计、任务、幂等和缓存', 'main.py':'HTTP 路由与服务组装',
    'http.py':'本机访问、Jobs、SSE、文件与备份', 'models.py':'数据／输出模型',
    'settings.py':'角色配置、价格和运行设置', 'llm.py':'模型请求、用量、结果缓存和并发',
    'codex_cli.py':'持久会话、增量传输、上一输出和 CLI 权限',
    'call_queue.py':'同账号跨进程 FIFO 队列', 'process_tree.py':'Windows 进程树与存活检查',
    'experience.py':'反馈、经验、应用、验证和包交换',
    'creative_review.py':'独立复核、有界生成和 JSON Patch',
    'story_contract.py':'正文、事件回放、状态、播放顺序和覆盖',
    'story.py':'原创节点与采用流程', 'story_review.py':'原创独立审查',
    'novel.py':'原文索引、范围改编、全书深读与续写', 'ideation.py':'AI 选题入口',
    'interchange.py':'SceneExport v4 导出', 'shooting.py':'B 转换、导演、素材和生成单元',
    'production.py':'制作对象、影响、单镜媒体与兼容流程',
    'workflow.py':'旧阶段候选兼容', 'cinema.py':'镜头规则、提示词编译和 render key',
    'runner.py':'TaskSpec 执行、隔离、资格、结果验收', 'gates.py':'真实文件与观察检查',
    'assembly.py':'粗剪与装配', 'qualification.py':'第三方 Runner 资格',
    'reading_export.py':'可读文档导出', 'render.py':'媒体 Provider 和 Dreamina 提交／查询',
}
lines = ['# 代码、接口与验证索引','',f'静态快照日期：{DATE}。本索引由 AST 解析生成，没有导入应用或读取生产数据库。',
    '', '路径相对于 StorySystems 根目录。行号供定位，SHA-256 见 JSON；代码修改后行号可能变化。',
    '', '## 1. 核心文件与职责','', '| 平台 | 文件 | 职责 |', '|---|---|---|']
for row in records:
    parts=row['path'].split('/')
    if parts[1]=='app' and parts[-1] in key_names or row['path']=='system-b/tools/render.py':
        lines.append(f"| {parts[0]} | `{row['path']}` | {key_names.get(parts[-1],'')} |")
lines += ['', '## 2. 核心方法定位', '', '| 文件 | 方法 | 行号 |', '|---|---|---|']
wanted = {'context','next_step','advance','generate','adopt','propose','analyze_all','read','chapter_index',
    'scene_export','propose_shooting','adopt_shooting','shooting_adoption_plan','key_scene_roles',
    'advance_creative','creative_snapshot','propose_director','prepare_event_assets','event_manifest',
    'observed_adoption','plan_generation_tasks','execute_generation_tasks','generation_dry_run',
    'change_plan','apply_impact','render','select_render','recover_remote','json','request','packet','prepare',
    '_claim','_request','acquire','applicable','guidance','validate','export_pack','import_pack',
    'generate_reviewed','review_candidate','review_candidates','replay','check_world','validate_shot_coverage',
    'inspect','execute','dreamina','dreamina_remote','create_app'}
for row in records:
    if '/app/' in row['path'] or row['path']=='system-b/tools/render.py':
        for symbol in row['symbols']:
            if symbol['name'].split('.')[-1] in wanted:
                lines.append(f"| `{row['path']}` | `{symbol['name']}` | {symbol['line']} |")
lines += ['', '## 3. 确认的恢复入口连接缺陷', '',
    '`system-b/app/production.py` 的 AST 中存在 `ProductionService.asset_render.recover_remote`，不存在 `ProductionService.recover_remote`。路由请求仍调用后者。此证据证明方法归属错误；本次没有提交真实付费媒体复现。',
    '', '## 4. 完整 API 路由', '',
    'A/B 各自的 `http.py` 注册同一组基础接口。表中按源码展开，会列出两个平台的共同接口。HTTP 方法、路径存在不代表业务已通过端到端验收。',
    '', '| 平台 | 方法 | 路径 | 文件:行 |', '|---|---|---|---|']
for row in records:
    if row['path'].endswith(('/app/main.py','/app/http.py')):
        for route in row['routes']:
            lines.append(f"| {row['path'].split('/')[0]} | {route['method']} | `{route['path']}` | `{row['path']}:{route['line']}` |")
lines += ['', '## 5. 持久化 document kind 索引', '',
    '下面从字面量 `Store.put(kind,...)` 提取，不保证包含动态 kind，也不表示每个 kind 都有正式 schema。', '']
for system in ('system-a','system-b'):
    kinds=sorted({k for row in records if row['path'].startswith(system+'/app/') for k in row['documentKinds']})
    lines += [f'### {system}', '', ', '.join('`'+k+'`' for k in kinds), '']
lines += ['## 6. 自动化与验证材料', '',
    '当前 MANIFEST 记录 A 164、B 218 项测试；旧 docs/pytest-result.txt 分别为 157、216，旧 collaboration XML 又属于更早一轮。它们是不同版本的历史证据，本次没有重跑全套业务测试。',
    '', '| 材料 | 当前存在 |', '|---|---|']
for item in evidence:
    lines.append(f"| `{item['path']}` | {'是' if item['exists'] else '否／路径历史遗留'} |")
lines += ['', '### 测试文件入口', '']
for system in ('system-a','system-b'):
    lines += [f'#### {system}', '']
    for row in records:
        if row['path'].startswith(system+'/tests/') and row['path'].endswith('.py'):
            count=sum(s['name'].split('.')[-1].startswith('test_') for s in row['symbols'])
            lines.append(f"- `{row['path']}`：静态测试函数 {count} 个（参数化后用例数可能不同）。")
    lines.append('')
lines += ['## 7. 代码快照范围', '',
    f"索引覆盖 {len(records)} 个 app/static/tools/tests 与发布配置源文件。未包含 data、登录目录、用户正文、生产媒体、settings.json 或 .env。", '',
    'JSON 中保留文件指纹、符号、行号、路由和证据索引，可在外部持有源码时复核。发布清单的验证标签不自动提升为本次真实媒体证据。', '']
(OUT/'04-代码与接口索引.md').write_text('\n'.join(lines),encoding='utf-8')

def inline(value):
    value=html.escape(value)
    tokens=[]
    def code(match):
        tokens.append('<code>'+match.group(1)+'</code>')
        return '\x00'+str(len(tokens)-1)+'\x00'
    value=re.sub(r'`([^`]+)`',code,value)
    value=re.sub(r'\*\*([^*]+)\*\*',r'<strong>\1</strong>',value)
    def link(match):
        href=html.unescape(match.group(2))
        if href.endswith('.md'): href=href[:-3]+'.html'
        if re.match(r'^(javascript|data):',href,re.I): return match.group(1)
        return '<a href="'+html.escape(href,quote=True)+'">'+match.group(1)+'</a>'
    value=re.sub(r'\[([^\]]+)\]\(([^)]+)\)',link,value)
    return re.sub(r'\x00(\d+)\x00',lambda m:tokens[int(m.group(1))],value)

def render_md(raw):
    output=[]; headings=[]; rows=raw.splitlines(); i=0; n=0
    while i<len(rows):
        line=rows[i]
        if not line.strip(): i+=1; continue
        if line.startswith('```'):
            lang=line[3:].strip(); i+=1; code=[]
            while i<len(rows) and not rows[i].startswith('```'):
                code.append(rows[i]); i+=1
            output.append('<pre><code data-language="'+html.escape(lang)+'">'+html.escape('\n'.join(code))+'</code></pre>'); i+=1; continue
        match=re.match(r'^(#{1,6}) (.+)$',line)
        if match:
            n+=1; level=len(match[1]); identifier='section-'+str(n)
            headings.append((level,identifier,match[2]))
            output.append(f'<h{level} id="{identifier}">{inline(match[2])}</h{level}>'); i+=1; continue
        if line.startswith('|') and i+1<len(rows) and re.match(r'^\|[\s:|\-]+\|$',rows[i+1]):
            headers=[c.strip() for c in line.strip().strip('|').split('|')]; i+=2; body=[]
            while i<len(rows) and rows[i].startswith('|'):
                cells=[c.strip() for c in rows[i].strip().strip('|').split('|')]
                body.append('<tr>'+''.join('<td>'+inline(c)+'</td>' for c in cells)+'</tr>'); i+=1
            output.append('<div class="table-wrap"><table><thead><tr>'+''.join('<th>'+inline(c)+'</th>' for c in headers)+'</tr></thead><tbody>'+''.join(body)+'</tbody></table></div>'); continue
        if re.match(r'^(- |\d+\. )',line):
            ordered=bool(re.match(r'^\d+\. ',line)); tag='ol' if ordered else 'ul'; items=[]
            while i<len(rows) and re.match(r'^(- |\d+\. )',rows[i]):
                items.append('<li>'+inline(re.sub(r'^(- |\d+\. )','',rows[i]))+'</li>'); i+=1
            output.append('<'+tag+'>'+''.join(items)+'</'+tag+'>'); continue
        para=[line]; i+=1
        while i<len(rows) and rows[i].strip() and not re.match(r'^(#|```|\||- |\d+\. )',rows[i]):
            para.append(rows[i]); i+=1
        output.append('<p>'+inline('\n'.join(para))+'</p>')
    return '\n'.join(output), headings

STYLE='''
:root{color-scheme:light;--ink:#24333a;--muted:#67767b;--accent:#215b5b;--paper:#fff;--line:#dce5e6}
*{box-sizing:border-box}body{margin:0;background:#f3f6f6;color:var(--ink);font-family:"Microsoft YaHei","PingFang SC",sans-serif;font-size:15px;line-height:1.85}a{color:var(--accent);text-underline-offset:3px}
header{position:sticky;top:0;z-index:3;background:#173c42;color:#fff;padding:12px 24px;display:flex;gap:18px;align-items:center;justify-content:space-between}header a{color:#fff;text-decoration:none}header small{opacity:.75}button{border:1px solid #94b6b8;background:transparent;color:inherit;border-radius:6px;padding:7px 12px;cursor:pointer}header input{border:1px solid #729b9f;border-radius:5px;padding:7px;background:#fff;color:#24333a;width:190px}
.layout{max-width:1510px;margin:auto;display:grid;grid-template-columns:270px minmax(0,1fr);gap:24px;padding:26px}aside{position:sticky;top:80px;align-self:start;max-height:calc(100vh - 108px);overflow:auto;padding:10px 10px 18px;font-size:13px}aside a{display:block;text-decoration:none;padding:5px 7px;line-height:1.55;border-left:2px solid transparent}aside a:hover{background:#e2eded;border-color:var(--accent)}aside .sub{padding-left:20px;font-size:12px;color:var(--muted)}main{background:var(--paper);padding:38px 44px;min-width:0;border:1px solid var(--line);border-radius:9px}
h1{font-size:29px;line-height:1.4;margin:0 0 20px}h2{font-size:22px;border-top:1px solid var(--line);padding-top:28px;margin:34px 0 16px;scroll-margin-top:85px}h3{font-size:17px;margin-top:25px;scroll-margin-top:85px}h4{font-size:15px}p{margin:13px 0}strong{color:#153c43}code{font-family:Consolas,monospace;font-size:12.5px;overflow-wrap:anywhere;background:#eff4f5;padding:2px 4px;border-radius:3px}pre{white-space:pre;overflow:auto;background:#eef4f4;border-left:3px solid #609594;padding:18px;line-height:1.7}pre code{background:none;padding:0;overflow-wrap:normal}.table-wrap{max-width:100%;overflow:auto;margin:18px 0}table{border-collapse:collapse;width:100%;font-size:13px;line-height:1.7}th,td{text-align:left;padding:10px 12px;border:1px solid var(--line);vertical-align:top}th{background:#e7f0f0;color:#244d52}tr:nth-child(even) td{background:#fafcfc}li{margin:6px 0}footer{color:var(--muted);font-size:12px;margin-top:35px;border-top:1px solid var(--line);padding-top:15px}.search-status{font-size:12px;min-width:70px}.highlight{background:#fff0ba;border-radius:4px;outline:2px solid #fff0ba}
@media(max-width:900px){.layout{grid-template-columns:1fr;padding:12px}aside{position:static;max-height:220px;border:1px solid var(--line);border-radius:6px}main{padding:24px 18px}header{padding:10px 12px;flex-wrap:wrap;gap:8px}header small{display:none}header input{width:145px}h1{font-size:24px}pre{font-size:12px}th,td{min-width:110px}}
@media print{body{background:#fff;font-size:10pt;line-height:1.65}header,aside,.search-status{display:none}.layout{display:block;padding:0}main{padding:0;border:none}h1{font-size:22pt}h2{font-size:16pt;break-after:avoid}h3{break-after:avoid}table{font-size:9pt}thead{display:table-header-group}tr{break-inside:avoid}.table-wrap{overflow:visible}pre{white-space:pre-wrap;overflow:visible;font-size:8.5pt;break-inside:avoid}code{font-size:9pt}.highlight{background:none;outline:none}@page{size:A4;margin:17mm}}
'''
SCRIPT='''
const field=document.getElementById('search');const status=document.getElementById('search-status');let hits=[],cursor=-1;
function clearHits(){document.querySelectorAll('.highlight').forEach(x=>x.classList.remove('highlight'));hits=[];cursor=-1}
field.addEventListener('input',()=>{clearHits();const q=field.value.trim().toLocaleLowerCase();if(!q){status.textContent='';return}hits=[...document.querySelectorAll('main h2,main h3,main p,main li,main td,main pre')].filter(x=>x.textContent.toLocaleLowerCase().includes(q));status.textContent=hits.length+' 处匹配'});
function nextHit(){if(!hits.length)return;hits.forEach(x=>x.classList.remove('highlight'));cursor=(cursor+1)%hits.length;const target=hits[cursor];target.classList.add('highlight');target.scrollIntoView({behavior:'smooth',block:'center'});status.textContent=(cursor+1)+' / '+hits.length}
field.addEventListener('keydown',e=>{if(e.key==='Enter')nextHit()});document.getElementById('next').addEventListener('click',nextHit);document.getElementById('print').addEventListener('click',()=>window.print());
'''
for path in sorted(OUT.glob('*.md')):
    raw=path.read_text(encoding='utf-8'); body, headings=render_md(raw)
    title=headings[0][2]
    toc=''.join('<a class="'+('sub' if level>=3 else '')+'" href="#'+identifier+'">'+html.escape(text)+'</a>' for level,identifier,text in headings if level in (2,3))
    page='<!doctype html><html lang="zh-CN"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>'+html.escape(title)+'</title><style>'+STYLE+'</style></head><body><header><a href="00-阅读入口.html">A/B 外部评审 · 2026-09-29</a><small>当前实现 / 待完善能力 / 验证边界</small><div><input id="search" aria-label="搜索文档" placeholder="搜索 · 回车下一处"><button id="next">下一处</button> <span class="search-status" id="search-status"></span> <button id="print">打印 / 保存 PDF</button></div></header><div class="layout"><aside aria-label="目录">'+toc+'</aside><main>'+body+'<footer>来源：'+html.escape(path.name)+' · 静态代码快照；真实文字、媒体和学习效果需分别验收。</footer></main></div><script>'+SCRIPT+'</script></body></html>'
    path.with_suffix('.html').write_text(page,encoding='utf-8')

cards=[]
for path in sorted(OUT.glob('*.md')):
    title=path.read_text(encoding='utf-8').splitlines()[0].lstrip('# ')
    cards.append('<li><a href="'+html.escape(path.with_suffix('.html').name,quote=True)+'">'+html.escape(title)+'</a> · <a href="'+html.escape(path.name,quote=True)+'">Markdown</a></li>')
home='<!doctype html><html lang="zh-CN"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>A/B 外部评审阅读入口</title><style>'+STYLE+'</style></head><body><header>A/B 精品创作平台 · 外部评审</header><div class="layout" style="display:block;max-width:1080px"><main><h1>当前设计与外部评审包</h1><p>2026-09-29 代码快照。包含流程、Agent 控制与会话树、版本和缓存、素材连续性、费用恢复、自我改进，以及 16 项明确的评审重点。</p><p>先读详细设计，再按评估任务书审查。当前实现和完整目标的缺口均已标明；演示／结构测试不代表真实成片验收。</p><ol>'+''.join(cards)+'</ol><p><a href="05-代码快照索引.json">机器可读代码指纹、符号、接口与证据索引</a></p><p>本包不含生产数据库、用户小说全文、登录凭据或 API 密钥。HTML 完全离线，可使用页面搜索和浏览器打印功能。</p></main></div></body></html>'
(OUT/'00-阅读入口.html').write_text(home,encoding='utf-8')

class Inspector(HTMLParser):
    def __init__(self): super().__init__();self.ids=set();self.links=[];self.duplicates=[]
    def handle_starttag(self,tag,attrs):
        values=dict(attrs)
        if 'id' in values:
            if values['id'] in self.ids:self.duplicates.append(values['id'])
            self.ids.add(values['id'])
        if tag=='a' and 'href' in values:self.links.append(values['href'])

issues=[]; html_checks=[]
for path in sorted(OUT.glob('*.html')):
    parser=Inspector();raw=path.read_text(encoding='utf-8');parser.feed(raw)
    if parser.duplicates:issues.append((path.name,'duplicate ids',parser.duplicates))
    for href in parser.links:
        if href.startswith('#'):
            if href[1:] not in parser.ids:issues.append((path.name,'missing anchor',href))
        elif not re.match(r'^[a-z]+:',href,re.I):
            if not (OUT/href.split('#')[0]).is_file():issues.append((path.name,'missing file',href))
    if '\x00' in raw:issues.append((path.name,'unresolved inline token'))
    html_checks.append({'path':path.name,'bytes':path.stat().st_size,'anchors':len(parser.ids),'links':len(parser.links)})
assert not issues, issues
md_checks=[]
for path in sorted(OUT.glob('*.md')):
    raw=path.read_text(encoding='utf-8')
    assert raw.count('```')%2==0,path
    md_checks.append({'path':path.name,'characters':len(raw),'lines':len(raw.splitlines())})
quality={'format':'ABReviewDocumentQA-v1','date':DATE,'sourceFiles':len(records),
    'routes':sum(len(r['routes']) for r in records),'markdown':md_checks,'html':html_checks,
    'checks':{'balancedCodeFences':True,'uniqueHtmlIds':True,'internalAnchorsResolve':True,
        'localLinksResolve':True,'noExternalRuntimeAssets':True,'confirmedRecoveryAstFinding':True},
    'limits':'Document structural QA only. No new business test suite, browser screenshot or paid media validation.'}
node = shutil.which('node')
if node:
    subprocess.run([node,'--check','-'],input=SCRIPT,text=True,capture_output=True,check=True)
    quality['checks']['htmlJavaScriptSyntax'] = True
(OUT/'07-文档检查记录.json').write_text(json.dumps(quality,ensure_ascii=False,indent=2),encoding='utf-8')

archive_path=OUT.parent/'AB平台设计与外部评审包-2026-09-29.zip'
with zipfile.ZipFile(archive_path,'w',zipfile.ZIP_DEFLATED) as archive:
    for path in sorted(OUT.iterdir()):
        if path.is_file() and path.suffix in ('.md','.html','.json','.py'):
            archive.write(path,'AB平台外部评审/'+path.name)
with zipfile.ZipFile(archive_path) as archive:
    assert archive.testzip() is None
print(json.dumps({'archive':str(archive_path),'archiveBytes':archive_path.stat().st_size,
    'files':len(list(OUT.iterdir())),'sourceFiles':len(records),'routes':quality['routes'],
    'markdown':md_checks,'qa':'passed'},ensure_ascii=False))
