"""Portable reading copies; no network requests and no model calls."""
from __future__ import annotations
import base64
from html import escape
from pathlib import Path
from studio.directing_reading import intent_html, direction_html, shot_html


def text(value):
    return escape(str(value or '')).replace('\n', '<br>')


def prose(body, names):
    def dialogue(row):
        identifier=row.get('speakerId',row.get('character','人物'))
        who = names.get(identifier,identifier)
        return f'<div class="dialogue"><strong>{text(who)}</strong><p>{text(row.get("text"))}</p></div>'
    if body.get('blocks'):
        return ''.join(dialogue(row) if row.get('type') == 'dialogue' else f'<p>{text(row.get("text") or row.get("action"))}</p>' for row in body['blocks'])
    parts = [f'<p>{text(body[k])}</p>' for k in ('sceneHeading','logline','synopsis','summary','action') if body.get(k)]
    parts += [dialogue(row) for row in body.get('dialogue', [])]
    if not body.get('dialogue'):
        parts += [f'<p>{text(row.get("action") or row.get("text"))}</p>' for row in body.get('beats', [])]
    return ''.join(parts) or '<p class="muted">正文尚未完成。</p>'


def embedded_image(render, files, store):
    if store is None:
        return ''
    f = next((f for f in files if f.get('id') == render.get('fileId') or f.get('url') == render.get('url')), None)
    if not f:
        return ''
    path = Path(f['path']).resolve()
    types = {'.png':'image/png','.jpg':'image/jpeg','.jpeg':'image/jpeg','.webp':'image/webp'}
    if not any(path.is_relative_to(Path(root).resolve()) for root in getattr(store,'media_roots',[store.root/'media'])) or not path.is_file() or path.suffix.lower() not in types:
        return ''
    return 'data:'+types[path.suffix.lower()]+';base64,'+base64.b64encode(path.read_bytes()).decode()


def export_reading(data, system, store=None):
    project = data['project']; parts = []; outline = []
    active=store.get(project.get('activeScriptVersionId',''),required=False) if store and project.get('activeScriptVersionId') else None
    if system=='A' and active and active.get('status')=='adopted':
        doc=active['payload'];project={**project,'canon':{**project.get('canon',{}),'entities':[{'id':identifier,**entity} for identifier,entity in doc['continuity']['entities'].items()]}}
        data={**data,'nodes':[{'id':row['id'],'title':row.get('title','场次'),'level':'scene','status':'accepted','generationComplete':True,'body':{'blocks':row['blocks']}} for row in doc['scenes']]}
    if system == 'A':
        names = {e['id']:e.get('name',e['id']) for e in project.get('canon',{}).get('entities',[])}
        nodes = [n for n in data['nodes'] if n['status'] != 'archived']
        rows = [n for n in nodes if n['level']=='scene'] or [n for n in nodes if not n.get('parentId')]
        for i, row in enumerate(rows):
            script = next((n for n in nodes if n.get('parentId')==row['id'] and n['level']=='script' and n.get('generationComplete')), row)
            title = f'{i+1:02d} · {row["title"]}'
            outline.append(f'<a href="#scene-{i}">{text(title)}</a>')
            content = prose(script.get('body',{}),names) if script.get('generationComplete') else f'<p>{text(row.get("contract",{}).get("summary"))}</p><p class="muted">已选方案 · 正文待展开</p>'
            parts.append(f'<article id="scene-{i}"><h2>{text(title)}</h2>{content}</article>')
        if not rows:
            parts.append(f'<article><h2>故事种子</h2><p>{text(project.get("seed"))}</p></article>')
    else:
        scenes={row['id']:row for row in data['scenes'] if row['status']!='archived'}
        script=next((row for row in [*data.get('adopted_scripts',[]),*data.get('shooting_scripts',[])] if row['id']==(project.get('activeScriptId') or project.get('activeShootingId'))),None)
        ranks={item['id']:index for index,item in enumerate((script or {}).get('payload',{}).get('presentationPlan',[]))}
        groups=[]
        if ranks:
            for shot in sorted((shot for shot in data['shots'] if shot['status']!='archived' and shot['sceneId'] in scenes),key=lambda shot:(ranks.get(shot.get('presentationId'),1e9),shot['order'])):
                if groups and groups[-1][0]['id']==shot['sceneId']:groups[-1][1].append(shot)
                else:groups.append((scenes[shot['sceneId']],[shot]))
        else:groups=[(row,sorted((shot for shot in data['shots'] if shot['sceneId']==row['id'] and shot['status']!='archived'),key=lambda shot:shot['order'])) for row in sorted(scenes.values(),key=lambda row:row.get('order',0))]
        for i,(row,local_shots) in enumerate(groups):
            title=f'{i+1:02d} · {row["title"]}';outline.append(f'<a href="#scene-{i}">{text(title)}</a>'); shots=[]
            for shot in local_shots:
                options=[r for r in data['renders'] if r.get('shotId')==shot['id'] and r.get('kind')=='keyframe' and r.get('freshness')!='broken']
                render=next((r for r in options if r.get('selected')), options[-1] if options else {})
                src=embedded_image(render,data.get('files',[]),store)
                visual=f'<img alt="镜头画面" src="{src}">' if src else '<div class="placeholder">文字分镜 · 尚无画面</div>'
                label='演示测试图' if render.get('demo') else '未终选图片' if render and not render.get('selected') else ''
                shots.append(f'<section class="shot"><header>镜 {shot["order"]+1:02d} · {text(shot.get("shotSize"))} · {text(shot.get("angle"))} · {float(shot.get("duration",0)):.1f} 秒</header>{visual}<div><small>{label}</small><p>{text(shot.get("actionLine"))}</p>{shot_html(shot)}<p class="muted">{text("；".join(shot.get("informationPayload",[])))}</p></div></section>')
            direction=next((d for d in data.get('directions',[]) if d.get('sceneId')==row['id'] and d.get('status')!='archived'),{})
            entities=(script or {}).get('payload',{}).get('continuity',{}).get('entities',{});names={identifier:entity.get('name',identifier) for identifier,entity in entities.items()}
            parts.append(f'<article id="scene-{i}"><h2>{text(title)}</h2><p>{text(row.get("presentation") or row.get("sourceText"))}</p>{intent_html(row.get("sceneIntent"),names)}{direction_html(direction.get("directingPlan"))}<div class="board">{"".join(shots)}</div></article>')
        if not parts:
            parts.append(f'<article><h2>原稿</h2><p>{text(project.get("source"))}</p></article>')
    css='''*{box-sizing:border-box}body{margin:0;background:#f4f3ee;color:#28362f;font:18px/1.9 "Microsoft YaHei",sans-serif}main{max-width:1080px;margin:40px auto;padding:0 24px}h1{font-size:30px}h2{font-size:22px}nav{display:flex;gap:14px;flex-wrap:wrap;margin:24px 0}a{color:#34533f}article{background:#fffefa;border:1px solid #d8dfd5;border-radius:8px;margin:24px 0;padding:32px;overflow-wrap:anywhere}.muted,small{color:#657269;font-size:14px}.dialogue{max-width:28em;margin:30px auto}.dialogue strong{display:block;text-align:center}.board{display:grid;grid-template-columns:1fr 1fr;gap:20px}.shot{border:1px solid #d8dfd5;break-inside:avoid}.shot header,.shot>div:not(.placeholder){padding:14px}.shot header{font-size:14px}.shot img{display:block;width:100%;aspect-ratio:16/9;object-fit:contain}.placeholder{aspect-ratio:16/9;display:grid;place-items:center;background:#e7eee3;font-size:14px}@media(max-width:650px){main{padding:0 14px}.board{grid-template-columns:1fr}article{padding:22px}}@media print{body{background:white;font-size:12pt}nav{display:none}main{margin:0;max-width:none}article{border:0;padding:0;break-before:page}.shot{break-inside:avoid}}'''
    return f'<!doctype html><html lang="zh-CN"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>{text(project["title"])}</title><style>{css}</style><main><h1>{text(project["title"])}</h1><p class="muted">System {system} · 已选作品阅读副本 · 可离线打开及打印为 PDF</p><nav>{"".join(outline)}</nav>{"".join(parts)}</main></html>'
