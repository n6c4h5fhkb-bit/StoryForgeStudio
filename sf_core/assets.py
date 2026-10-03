"""List the reference images the planned units need, with an image prompt for each.

Masters are generated from text; every other look, time of day or prop state is an
edit of its master, so identity stays the same across variants.
"""
from __future__ import annotations

import json
from pathlib import Path

from .model import Project
from .resolve import find_image, time_key

KIND_ORDER = {'character': 0, 'crowd': 1, 'location': 2, 'prop': 3}
KIND_LABEL = {'character': '人物', 'crowd': '群演', 'location': '场景', 'prop': '道具'}
TIME_LIGHT = {'日': '白天自然光', '夜': '夜晚，室内外灯光照明', '晨': '清晨柔和的光', '黄昏': '黄昏暖色斜光'}
LAYOUT_NOTE = '版式是起点假设：先用一个角色在视频里做冒烟测试，确认能上传、能保持身份，再批量出图。'


def _master_variant(entity, used: list[str]) -> str:
    if entity.kind in ('character', 'crowd'):
        return entity.default_look or (used[0] if used else '默认')
    if entity.kind == 'location':
        return '日' if '日' in used else (used[0] if used else '日')
    return '默认'


def image_prompt(project: Project, entity, variant: str, master: str) -> str:
    style = project.series.style.rstrip('。')
    aspect = project.series.fmt.get('aspect', '16:9')
    if variant != master:
        if entity.kind in ('character', 'crowd'):
            change = entity.looks.get(variant) or variant
            return (f'以参考图里的{entity.name}为准：同一张脸、同一发型、同一体型，画风和版式不变，'
                    f'只把服装换成：{change}。其他保持不变。')
        if entity.kind == 'location':
            light = entity.states.get(variant) or TIME_LIGHT.get(variant, variant)
            return f'以参考图里的{entity.name}为准：同一空间结构、同样陈设和机位，只把时间改成{variant}：{light}。'
        change = entity.states.get(variant) or variant
        return f'以参考图里的{entity.name}为准：同一物件，只改成：{change}。'
    if entity.kind == 'character':
        look = entity.looks.get(variant) or ''
        return (f'{style}。角色设定图，浅灰色纯背景，同一个人物的正面、侧面、背面三视图，全身站立，头部完整入画，'
                f'旁边加一张正面半身特写。{entity.identity.rstrip("。")}。'
                + (f'服装：{look.rstrip("。")}。' if look else '')
                + '自然中性表情，双手自然下垂，空手，不拿道具。画面里只有这一个人物，没有文字、标注和水印。')
    if entity.kind == 'crowd':
        look = entity.looks.get(variant) or entity.identity
        count = f'{entity.count}名' if entity.count else '几名'
        return (f'{style}。群演设定图，浅灰色纯背景，{count}{entity.name}并排全身站立，{look.rstrip("。")}，'
                '统一造型，表情中性，没有文字和水印。')
    if entity.kind == 'location':
        light = TIME_LIGHT.get(variant, variant)
        return (f'{style}。场景设定图，{aspect}画面，约45度俯视的完整空间全景，画面中没有人物。'
                f'{entity.identity.rstrip("。")}。{light}。没有文字和水印。')
    return (f'{style}。道具设定图，浅灰色纯背景，同一件{entity.name}的正面、侧面、背面和45度俯视四个角度，2×2排列，'
            f'画面里没有手和人物。{entity.identity.rstrip("。")}。没有文字和水印。')


def requirements(project: Project, plans) -> list[dict]:
    used: dict[tuple[str, str], list[str]] = {}
    for plan in plans:
        for unit in plan.units:
            for ref in unit.references:
                used.setdefault((ref.entity, ref.variant), []).append(f'{plan.episode.id}/{unit.id}')
    by_entity: dict[str, list[str]] = {}
    for name, variant in used:
        by_entity.setdefault(name, []).append(variant)
    rows = []
    for name, variants in by_entity.items():
        entity = project.entities[name]
        master = _master_variant(entity, variants)
        for variant in [master] + sorted(v for v in variants if v != master):
            image = find_image(project.root, name, variant)
            cli = project.series.cap.get('cli', {})
            ratio = '1:1' if entity.kind == 'prop' else project.series.fmt.get('aspect', '16:9') if entity.kind == 'location' else '16:9'
            prompt = image_prompt(project, entity, variant, master)
            target = f'assets/images/{name}/{variant}.png'
            parent = None if variant == master else f'assets/images/{name}/{master}.png'
            command = [cli.get('executable', 'dreamina'),
                       cli.get('image_edit_command', 'image2image') if parent else cli.get('image_text_command', 'text2image')]
            if parent:
                command += ['--images', parent]
            command += ['--prompt', prompt, '--ratio', ratio, '--resolution_type', cli.get('image_resolution', '2k'),
                        '--model_version', cli.get('image_model_version', '5.0'), '--generate_num', '1']
            rows.append({'entity': name, 'kind': entity.kind, 'variant': variant, 'master': variant == master,
                         'parent': parent, 'used_in': used.get((name, variant), []), 'file': target,
                         'exists': bool(image), 'ratio': ratio, 'prompt': prompt, 'command': command})
    rows.sort(key=lambda r: (KIND_ORDER.get(r['kind'], 9), r['entity'], not r['master'], r['variant']))
    return rows


def assets_markdown(project: Project, rows: list[dict]) -> str:
    missing = sum(1 for r in rows if not r['exists'])
    out = ['# 参考图清单', '', '> 由 `sf assets` 生成。图片存到「保存为」路径后重新运行 `sf plan`，提示词里的 @图片 会自动对上文件。',
           f'> {LAYOUT_NOTE}', '', f'共 {len(rows)} 张，缺 {missing} 张。人脸设置：{project.series.face}。', '']
    current = None
    for row in rows:
        if row['kind'] != current:
            current = row['kind']
            out += [f'## {KIND_LABEL.get(current, current)}', '']
        status = '已有' if row['exists'] else '缺图'
        base = '母图' if row['master'] else f'子图（以 {row["parent"]} 为参考修改）'
        out += [f'### {row["entity"]}／{row["variant"]}（{status}，{base}）', '',
                f'- 保存为：`{row["file"]}`',
                f'- 比例：{row["ratio"]}',
                f'- 用于：{"、".join(row["used_in"]) or "—"}', '', '```', row['prompt'], '```', '']
    return '\n'.join(out)


def write_assets(project: Project, plans) -> Path:
    rows = requirements(project, plans)
    out = project.root / 'derived'
    out.mkdir(parents=True, exist_ok=True)
    (out / 'assets.json').write_text(json.dumps(rows, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    (out / 'assets.md').write_text(assets_markdown(project, rows), encoding='utf-8')
    return out / 'assets.md'
