"""Merge the review material into one self-contained readable document.

Reuse only pure renderer definitions; do not execute the package builder.
"""
import ast
from pathlib import Path
import hashlib
import html
import json
import re
import shutil
import subprocess
from html.parser import HTMLParser

ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / 'docs' / 'external-review-2026-09-29'
TARGET = ROOT / 'docs' / 'AB平台完整设计与外部评审文档-2026-09-29.md'

renderer_source = (SOURCE / 'build_review_package.py').read_text(encoding='utf-8')
tree = ast.parse(renderer_source)
definitions = []
for item in tree.body:
    if isinstance(item, (ast.FunctionDef, ast.ClassDef)) and item.name in {'inline', 'render_md', 'Inspector'}:
        definitions.append(item)
    elif isinstance(item, ast.Assign) and any(isinstance(t, ast.Name) and t.id in {'STYLE', 'SCRIPT'} for t in item.targets):
        definitions.append(item)
exec(compile(ast.Module(body=definitions, type_ignores=[]), '<pure-review-renderer>', 'exec'), globals())

def read(name):
    return (SOURCE / name).read_text(encoding='utf-8').strip()

def body(raw):
    return '\n'.join(raw.splitlines()[1:]).strip()

def adapt(raw):
    replacements = {
        '`04-代码与接口索引.md`、`05-代码快照索引.json`': '本文的「代码、接口与验证索引」和「代码快照与文件指纹」',
        '`03-外部评估任务书.md`': '本文的「外部评估任务书」',
        '`04-代码与接口索引.md`': '本文的「代码、接口与验证索引」',
        '`05-代码快照索引.json`': '本文的「代码快照与文件指纹」',
        'JSON 中保留文件指纹、符号、行号、路由和证据索引': '本文保留文件指纹、核心符号、行号、完整路由和证据索引',
        'SHA-256 见 JSON': 'SHA-256 见本文末尾文件指纹表',
        '同目录': '本文',
        '同包 HTML': '同内容的 HTML 阅读版',
        'Markdown 文件': '本 Markdown 文档',
        '本包': '本文',
        '本次文档工作': '原评审材料生成工作',
        '本次静态阅读': '原评审材料的静态阅读',
        '阅读 02 的全部设计、03 的评估要求、04/05 的源码索引和 06 的场景。': '阅读本文的详细设计、评估要求、源码索引、指纹表和场景示例。',
    }
    for old, new in replacements.items():
        raw = raw.replace(old, new)
    return raw

intro = '''# A/B 平台完整设计与外部评审文档

整合版本：1.0｜代码快照：2026-09-29｜用途：外部产品、AI 工程与架构评估

**这是一份可独立阅读和交给外部评估的完整文档。** 已整合原评审包的设计说明、评估任务书、代码与接口索引、关键场景、代码文件指纹和验证记录，无需再打开多个材料。

本文以代码快照的实际实现为准，区分已实现机制、产品目标、静态风险、已确认缺陷和未验证效果。整合没有修复业务代码，也没有新增模型或付费媒体调用；原评审材料的工程验证边界保持不变。

## 阅读顺序

| 部分 | 内容 | 评估用途 |
|---|---|---|
| 第一部分 | 评审说明与当前成熟度 | 快速理解目标、现状与边界 |
| 第二部分 | A/B 完整详细设计 | 流程、Agent 控制、会话、数据、连续性、缓存、费用、恢复、学习 |
| 第三部分 | 关键场景与任务轨迹 | 核对用户实际操作和数据流 |
| 第四部分 | 外部评估任务书 | 提问、优化交付模板和可复制评估提示词 |
| 第五部分 | 代码、接口与验证索引 | 定位实现、接口和现有验证材料 |
| 第六部分 | 代码快照与文件指纹 | 核对评估代码版本和文档来源 |

正文包含 Agent 会话树、完整流程和 16 项评审重点。代码索引是定位材料，不是完整源码；外部做代码级审计时需另行取得匹配指纹的源码。本文不包含生产数据库、小说全文、账号登录文件或 API 密钥。
'''

overview_raw = read('01-评审包说明.md')
overview = overview_raw[overview_raw.index('## 平台一句话分工'):]
overview = overview.replace('这里没有把问题悄悄修掉再描述成已有能力，以便外部评估拿到真实现状。', '这些问题保持为代码快照的真实现状，供外部评审。')
overview = overview.replace('本包中的 R 编号和建议只是评审内容，没有更改业务实现。', '本文中的 R 编号和建议只是评审内容，没有更改业务实现。')
main_raw = read('02-AB详细设计文档.md')
main = main_raw[main_raw.index('## 1. 产品目标'):]
main = main.replace('本报告来自当前源码静态阅读', '本报告来自 2026-09-29 代码快照的静态阅读')
main = main.replace('同包 HTML 可离线阅读、搜索和浏览器打印；Markdown 适合直接交给外部 AI。', '同内容的 HTML 阅读版可离线阅读、搜索和浏览器打印；本 Markdown 文档适合直接交给外部 AI。')

sections = [
    ('第一部分：评审说明与当前成熟度', overview),
    ('第二部分：A/B 完整详细设计', main),
    ('第三部分：关键场景与任务轨迹', body(read('06-关键场景与任务轨迹.md'))),
    ('第四部分：外部评估任务书', body(read('03-外部评估任务书.md'))),
    ('第五部分：代码、接口与验证索引', body(read('04-代码与接口索引.md'))),
]

chunks = [intro.strip()]
for title, content in sections:
    content = adapt(content)
    # Parts are h2; preserve source sections and subsections as h3/h4.
    content = re.sub(r'^(#{2,5}) ', lambda m: '#' + m.group(1) + ' ', content, flags=re.M)
    chunks.append('## ' + title + '\n\n' + content)

snapshot = json.loads(read('05-代码快照索引.json'))
qa = json.loads(read('07-文档检查记录.json'))
appendix = [
    '## 第六部分：代码快照与文件指纹', '',
    '原机器索引中的文件指纹、发布元数据、确认缺陷和文档检查结果在这里转换为可读表格。核心方法和完整 API 已包含在第五部分，避免再粘贴大量重复的 JSON。', '',
    '### 1. 快照元数据', '',
    '| 项目 | 值 |', '|---|---|',
    '| 代码索引格式 | `' + snapshot['format'] + '` |',
    '| 快照日期 | ' + snapshot['snapshotDate'] + ' |',
    '| 原索引生成时间（UTC） | ' + snapshot['generatedAt'] + ' |',
    '| 索引文件数 | ' + str(len(snapshot['files'])) + ' |',
    '| 接口记录数 | ' + str(sum(len(r['routes']) for r in snapshot['files'])) + ' |',
    '| 采集方法 | 静态 AST、文件 SHA-256；不导入应用，不读取生产数据库 |', '',
    '### 2. 发布清单记录', '',
    '| 平台 | 版本 | Python 最低版本 | 测试数 | 付费 Provider 完整实测 | 历史浏览器标签 |',
    '|---|---|---|---|---|---|',
]
for system, item in snapshot['releaseManifests'].items():
    appendix.append('| ' + system + ' | ' + str(item['release']) + ' | ' + str(item['pythonMinimum'])
        + ' | ' + str(item['testCount']) + ' | ' + str(item['paidProvidersLiveVerified']).lower()
        + ' | ' + str(item['browserVerified']) + ' |')
appendix += ['', '这些值来自原发布清单，不能解释为整合文档时重新运行的测试。原测试结果文件还包含旧版本计数，详见第五部分。', '',
    '### 3. 已确认的恢复入口缺陷', '',
    '| 字段 | 内容 |', '|---|---|',
    '| 编号 | R16 |',
    '| 文件 | `' + snapshot['confirmedFinding']['path'] + '` |',
    '| AST 符号 | `' + snapshot['confirmedFinding']['symbol'] + '` |',
    '| 证据 | recover_remote 嵌套在 asset_render 内，不是 ProductionService 类方法；路由调用 b.recover_remote。 |', '',
    '### 4. 源文件 SHA-256', '',
    '路径相对于 StorySystems 根目录；指纹标识原评审索引记录的文件内容。此表没有复制源代码、配置密钥或生产数据。', '',
    '| 文件 | 行数 | SHA-256 |', '|---|---|---|',
]
for row in snapshot['files']:
    appendix.append('| `' + row['path'] + '` | ' + str(row['lines']) + ' | `' + row['sha256'] + '` |')
appendix += ['', '### 5. 原文档结构检查记录', '',
    '| 检查 | 结果 |', '|---|---|']
for key, value in qa['checks'].items():
    appendix.append('| `' + key + '` | ' + ('通过' if value else '未通过') + ' |')
appendix += ['', '此记录仅证明原文档结构、链接和脚本语法检查，不代表重新运行业务测试、浏览器截图或付费媒体验收。', '',
    '### 6. 整合材料来源指纹', '',
    '这些是构成本整合文档的原材料指纹，便于核对；阅读和评估本文无需打开它们。', '',
    '| 原材料 | SHA-256 |', '|---|---|']
sources = ['01-评审包说明.md','02-AB详细设计文档.md','03-外部评估任务书.md',
           '04-代码与接口索引.md','05-代码快照索引.json','06-关键场景与任务轨迹.md','07-文档检查记录.json']
for name in sources:
    appendix.append('| `' + name + '` | `' + hashlib.sha256((SOURCE/name).read_bytes()).hexdigest() + '` |')
chunks.append('\n'.join(appendix))
raw = '\n\n'.join(chunks).strip() + '\n'

# Remove the remaining old multi-file instruction, keeping everything self-contained.
raw = raw.replace('请先区分当前代码实现、此前产品目标和真实验收证据。阅读本文的详细设计、评估要求、源码索引、指纹表和场景示例。索引不包含完整源码；无法由现有材料确认的地方请标注需代码或试跑，不要编造。',
    '请先区分当前代码实现、此前产品目标和真实验收证据。完整阅读本文的详细设计、评估要求、源码索引、指纹表和场景示例。索引不包含完整源码；无法由现有材料确认的地方请标注需代码或试跑，不要编造。')
assert raw.count('```') % 2 == 0
assert len(re.findall(r'^# ', raw, re.M)) == 1
assert all(title in raw for title, _ in sections)
assert all(f'| R{i:02d} ' in raw for i in range(1, 17))
assert len(re.findall(r'\| (?:system-a|system-b) \| (?:GET|POST|PUT|PATCH|DELETE) \|', raw)) == 165
TARGET.write_text(raw, encoding='utf-8')

body_html, headings = render_md(raw)
toc = ''.join('<a class="' + ('sub' if level >= 3 else '') + '" href="#' + identifier + '">' + html.escape(text) + '</a>'
              for level, identifier, text in headings if level in (2, 3))
page = '<!doctype html><html lang="zh-CN"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>A/B 平台完整设计与外部评审文档</title><style>' + STYLE + '</style></head><body><header><a href="#section-1">A/B 完整设计与评审 · 单文档</a><small>2026-09-29 代码快照</small><div><input id="search" aria-label="搜索文档" placeholder="搜索 · 回车下一处"><button id="next">下一处</button> <span class="search-status" id="search-status"></span> <button id="print">打印 / 保存 PDF</button></div></header><div class="layout"><aside aria-label="目录">' + toc + '</aside><main>' + body_html + '<footer>所有设计、评估要求、场景和索引已整合于本文件；业务和媒体验证边界保持原样。</footer></main></div><script>' + SCRIPT + '</script></body></html>'
TARGET.with_suffix('.html').write_text(page, encoding='utf-8')
parser = Inspector()
parser.feed(page)
assert not parser.duplicates
assert all(link.startswith('#') and link[1:] in parser.ids for link in parser.links), parser.links
assert '\x00' not in page
assert not re.search(r'<(?:script|link|img)[^>]+(?:src|href)=', page)
node = shutil.which('node')
if node:
    subprocess.run([node, '--check', '-'], input=SCRIPT, text=True, capture_output=True, check=True)
print(json.dumps({'markdown': str(TARGET), 'html': str(TARGET.with_suffix('.html')),
    'characters': len(raw), 'lines': len(raw.splitlines()), 'headings': len(headings),
    'routes': 165, 'risks': 16, 'sourceFingerprints': len(snapshot['files']),
    'checks': 'single heading, sections and scenarios present, all routes and risks retained, self-contained HTML, anchor and script syntax checks passed'}, ensure_ascii=False))

# English narrative is translated as prose; identical code/API/hash data is
# appended from the same snapshot rather than translated as identifiers.
ENGLISH = ROOT / 'docs' / 'AB-platform-complete-design-and-external-review-2026-09-29.en.md'
marker = '<!-- TECHNICAL APPENDICES -->'
english_prefix = ENGLISH.read_text(encoding='utf-8').split(marker)[0].rstrip()
responsibilities = {
    'core.py': 'Persistence, audit, jobs, idempotency, and caching',
    'main.py': 'HTTP routes and service composition',
    'http.py': 'Local access guard, jobs, SSE, files, and backups',
    'models.py': 'Data and output models',
    'settings.py': 'Role configuration, prices, and runtime settings',
    'llm.py': 'Model requests, usage, result cache, and concurrency',
    'codex_cli.py': 'Persistent sessions, deltas, preceding-output binding, CLI permissions',
    'call_queue.py': 'Cross-process FIFO for one account',
    'process_tree.py': 'Windows process trees and liveness',
    'experience.py': 'Feedback, scoped rules, applications, validation, and exchange',
    'creative_review.py': 'Independent review, bounded generation, JSON Patch',
    'story_contract.py': 'Blocks, event replay, states, presentation, and coverage',
    'story.py': 'Original story nodes and adoption',
    'story_review.py': 'Independent original-story review',
    'novel.py': 'Indexing, selected adaptation, whole-book reading, continuation',
    'ideation.py': 'AI concept entry',
    'interchange.py': 'SceneExport v4 export',
    'shooting.py': 'B adaptation, direction, assets, and generation units',
    'production.py': 'Production objects, impact, single-shot media, legacy workflows',
    'workflow.py': 'Legacy staged proposal compatibility',
    'cinema.py': 'Shot rules, prompt compilation, and render keys',
    'runner.py': 'Task execution, isolation, qualification, output acceptance',
    'gates.py': 'Actual-file inspection and observations',
    'assembly.py': 'Rough cuts and assembly',
    'qualification.py': 'Third-party runner qualification',
    'reading_export.py': 'Readable exports',
    'render.py': 'Media providers and Dreamina submission/query',
}
index = ['## Part V: Code, API, and evidence index', '',
    'Snapshot: September 29, 2026. AST-derived metadata; no application import or production database access. Paths are relative to StorySystems. Line numbers locate the snapshot; hashes appear in Part VI.', '',
    '### 1. Core files and responsibilities', '',
    '| Platform | File | Responsibility |', '|---|---|---|']
for row in snapshot['files']:
    parts = row['path'].split('/')
    if parts[1] == 'app' and parts[-1] in responsibilities or row['path'] == 'system-b/tools/render.py':
        index.append('| ' + parts[0] + ' | `' + row['path'] + '` | ' + responsibilities[parts[-1]] + ' |')
index += ['', '### 2. Core method locations', '', '| File | Symbol | Line |', '|---|---|---|']
method_section = read('04-代码与接口索引.md').split('## 2. 核心方法定位')[1].split('## 3.')[0]
for line in method_section.splitlines():
    if line.startswith('| `'):
        index.append(line)
index += ['', '### 3. Confirmed recovery endpoint defect', '',
    'The production.py AST contains `ProductionService.asset_render.recover_remote`, not `ProductionService.recover_remote`. The route calls the latter. This confirms incorrect method ownership; no paid-media reproduction was initiated.', '',
    '### 4. Complete API route catalogue', '',
    'Each platform registers the common http.py endpoints. Both copies are listed. Endpoint existence does not establish end-to-end acceptance.', '',
    '| Platform | Method | Path | File:line |', '|---|---|---|---|']
for row in snapshot['files']:
    if row['path'].endswith(('/app/main.py', '/app/http.py')):
        for route in row['routes']:
            index.append('| ' + row['path'].split('/')[0] + ' | ' + route['method'] + ' | `' + route['path']
                + '` | `' + row['path'] + ':' + str(route['line']) + '` |')
index += ['', '### 5. Persistent document kinds', '',
    'Extracted from literal Store.put(kind,...) calls. Dynamic kinds may be omitted; listing does not establish a formal schema.', '']
for system in ('system-a', 'system-b'):
    kinds = sorted({k for row in snapshot['files'] if row['path'].startswith(system + '/app/') for k in row['documentKinds']})
    index += ['#### ' + system, '', ', '.join('`' + k + '`' for k in kinds), '']
index += ['### 6. Tests and evidence', '',
    'Current manifests record A:164 and B:218 tests. Older docs/pytest-result.txt reports contain 157 and 216 respectively; collaboration XML belongs to an earlier run. These are different historical versions, not a newly rerun full suite.', '',
    '| Evidence | Available in original workspace |', '|---|---|']
for item in snapshot['validationEvidenceIndex']:
    index.append('| `' + item['path'] + '` | ' + ('Yes' if item['exists'] else 'No / historical path') + ' |')
index += ['', '#### Test-file entry points', '']
for system in ('system-a', 'system-b'):
    index += ['##### ' + system, '']
    for row in snapshot['files']:
        if row['path'].startswith(system + '/tests/') and row['path'].endswith('.py'):
            count = sum(s['name'].split('.')[-1].startswith('test_') for s in row['symbols'])
            index.append('- `' + row['path'] + '`: ' + str(count) + ' statically identified test functions; parametrized case counts can differ.')
    index.append('')
index += ['### 7. Snapshot scope', '',
    'The index covers ' + str(len(snapshot['files'])) + ' app/static/tools/tests and release/configuration source files. It excludes data, login files, private text, production media, settings.json, and .env.', '',
    'Source fingerprints, core symbols, lines, routes, and evidence locations support external source verification. Manifest labels are not automatically evidence of real paid-media acceptance.', '']

english_appendix = ['## Part VI: Snapshot metadata and source fingerprints', '',
    'Machine-index fingerprints, release metadata, the confirmed defect, and document checks are represented as readable tables. Core methods and complete endpoints appear in Part V without a repeated JSON dump.', '',
    '### 1. Snapshot metadata', '', '| Item | Value |', '|---|---|',
    '| Index format | `' + snapshot['format'] + '` |',
    '| Snapshot date | ' + snapshot['snapshotDate'] + ' |',
    '| Original generation time (UTC) | ' + snapshot['generatedAt'] + ' |',
    '| Indexed files | ' + str(len(snapshot['files'])) + ' |',
    '| Route records | ' + str(sum(len(r['routes']) for r in snapshot['files'])) + ' |',
    '| Method | Static AST and file SHA-256; applications not imported; production data not read |', '',
    '### 2. Release manifest records', '',
    '| Platform | Release | Minimum Python | Tests | Complete paid-provider verification | Historical browser label |',
    '|---|---|---|---|---|---|']
for system, item in snapshot['releaseManifests'].items():
    english_appendix.append('| ' + system + ' | ' + str(item['release']) + ' | ' + str(item['pythonMinimum'])
        + ' | ' + str(item['testCount']) + ' | ' + str(item['paidProvidersLiveVerified']).lower()
        + ' | ' + str(item['browserVerified']) + ' |')
english_appendix += ['', 'These are original manifest values, not tests rerun during consolidation/translation. Older report counts remain historical evidence.', '',
    '### 3. Confirmed recovery defect', '', '| Field | Value |', '|---|---|',
    '| ID | R16 |', '| File | `' + snapshot['confirmedFinding']['path'] + '` |',
    '| AST symbol | `' + snapshot['confirmedFinding']['symbol'] + '` |',
    '| Evidence | recover_remote is nested inside asset_render, not a ProductionService method; the route calls b.recover_remote. |', '',
    '### 4. Source-file SHA-256', '',
    'Paths are relative to StorySystems. Hashes identify source content in the original review index, without including the code, secrets, or production data itself.', '',
    '| File | Lines | SHA-256 |', '|---|---|---|']
for row in snapshot['files']:
    english_appendix.append('| `' + row['path'] + '` | ' + str(row['lines']) + ' | `' + row['sha256'] + '` |')
english_appendix += ['', '### 5. Original document checks', '', '| Check | Result |', '|---|---|']
for key, value in qa['checks'].items():
    english_appendix.append('| `' + key + '` | ' + ('Passed' if value else 'Not passed') + ' |')
english_appendix += ['', 'These checks concern document structure, links, and script syntax. They are not new business suites, screenshot inspections, or paid-media tests.', '',
    '### 6. Source-material fingerprints', '',
    'Original filenames are retained as provenance identifiers. This document is independently readable; opening those files is not required.', '',
    '| Original material | SHA-256 |', '|---|---|']
for name in sources:
    english_appendix.append('| `' + name + '` | `' + hashlib.sha256((SOURCE / name).read_bytes()).hexdigest() + '` |')
english_raw = english_prefix + '\n\n' + marker + '\n\n' + '\n'.join(index) + '\n\n' + '\n'.join(english_appendix) + '\n'
assert english_raw.count('```') % 2 == 0
assert len(re.findall(r'^# ', english_raw, re.M)) == 1
assert all('| R' + f'{i:02d}' + ' ' in english_raw for i in range(1, 17))
assert len(re.findall(r'\| (?:system-a|system-b) \| (?:GET|POST|PUT|PATCH|DELETE) \|', english_raw)) == 165
english_routes = re.findall(r'\| (system-[ab]) \| (GET|POST|PUT|PATCH|DELETE) \| `([^`]+)` \|', english_raw)
chinese_routes = re.findall(r'\| (system-[ab]) \| (GET|POST|PUT|PATCH|DELETE) \| `([^`]+)` \|', raw)
assert english_routes == chinese_routes
assert re.findall(r'`([0-9a-f]{64})`', english_raw) == re.findall(r'`([0-9a-f]{64})`', raw)
ENGLISH.write_text(english_raw, encoding='utf-8')
english_body, english_headings = render_md(english_raw)
english_toc = ''.join('<a class="' + ('sub' if level >= 3 else '') + '" href="#' + identifier + '">' + html.escape(text) + '</a>'
    for level, identifier, text in english_headings if level in (2, 3))
english_script = SCRIPT.replace("+' 处匹配'", "+' matches'")
english_page = '<!doctype html><html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>A/B Platforms: Complete Design and External Review</title><style>' + STYLE + '</style></head><body><header><a href="#section-1">A/B Complete Design and Review</a><small>September 29, 2026 snapshot</small><div><input id="search" aria-label="Search document" placeholder="Search; Enter for next"><button id="next">Next</button> <span class="search-status" id="search-status"></span> <button id="print">Print / Save PDF</button></div></header><div class="layout"><aside aria-label="Contents">' + english_toc + '</aside><main>' + english_body + '<footer>Self-contained English edition. Business, text, media, and learning evidence remain separately qualified.</footer></main></div><script>' + english_script + '</script></body></html>'
ENGLISH.with_suffix('.html').write_text(english_page, encoding='utf-8')
english_parser = Inspector()
english_parser.feed(english_page)
assert not english_parser.duplicates
assert all(link.startswith('#') and link[1:] in english_parser.ids for link in english_parser.links)
assert not re.search(r'<(?:script|link|img)[^>]+(?:src|href)=', english_page)
assert '\x00' not in english_page
if node:
    subprocess.run([node, '--check', '-'], input=english_script, text=True, capture_output=True, check=True)
print(json.dumps({'englishMarkdown': str(ENGLISH), 'englishHtml': str(ENGLISH.with_suffix('.html')),
    'englishCharacters': len(english_raw), 'englishWords': len(english_raw.split()), 'englishLines': len(english_raw.splitlines()),
    'bilingualChecks': 'All 165 API records and all source/material fingerprints match. Both documents contain all 16 risks and six parts. Offline HTML anchors and JavaScript syntax valid.'}, ensure_ascii=False))
