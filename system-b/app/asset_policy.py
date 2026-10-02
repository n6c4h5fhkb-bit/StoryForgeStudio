"""Stable neutral identities, limited appearance variants and separate shot states."""
from __future__ import annotations

import hashlib
from pathlib import Path
from .core import canonical, digest

VERSION = 'neutral-asset-policy-v1'
APPEARANCE_KEYS = {'wardrobe', 'outfit', 'costume', 'clothing', 'hairstyle', 'hair', 'age', 'injury', 'wound', 'damage', 'damaged',
                   'cleanliness', 'dirt', 'structure', 'shape', 'material', 'timeOfDay', 'time_of_day', 'dayNight',
                   '服装', '衣装', '发型', '年龄', '伤势', '污迹', '结构', '材质', '日夜'}
SHOT_KEYS = {'pos', 'position', 'holder', 'owner', 'expression', 'emotion', 'pose', 'facing', 'hand', 'hands', 'lid', 'open',
             'closed', 'quantity', 'count', 'contents', '@contents', 'contentsKnown', 'visibleTo', 'active', 'consumed', 'destroyed',
             '汗', '表情', '姿势', '持有者', '开合', '数量'}

RULES = [
    '人物母图保持正常中性表情和自然姿态，默认空手；保留原文规定的服装、伤势与污迹。笑怒、姿态、握持、佩戴和拿放写在镜头表演及状态中。',
    '人物与可独立操作、佩戴、转交的道具分别建立母资产；普通服装和固定造型不机械拆分。',
    '场景母图交代完整布局和固定陈设，默认空场；人物及临时道具由镜头组合。道具母图单独展示，不夹带持有者。',
    '先复用资产。表情、开合、满空、换手或落点变化不自动增加子图；显著且需要视觉参考的外观变化才派生。',
    '母图给完整独立提示词；子图附具体直接上级图片，只写本次修改、与母版区别和保持不变项，不能从零重新描述身份。',
    '镜头状态仍须完整记录。隐藏与画外不等于物体消失，实际采用区间末态与计划末态分别保存。',
]


def guidance(settings=None):
    configured = (settings.read().get('directorSkillPath') if settings else None)
    root = Path(configured) if configured else Path.home() / '.agents' / 'skills' / 'shortdrama-director'
    if root.name.lower() == 'skill.md':
        root = root.parent
    sources, excerpts = [], []
    card = root / 'references' / '09-assets.md'
    if card.is_file():
        content = card.read_text(encoding='utf-8-sig')
        sources.append({'name': 'shortdrama-director/09-assets', 'sha256': hashlib.sha256(content.encode()).hexdigest()})
        # Selected reference data, not an entire instruction file or tool permission.
        for heading in ('## 先判断资产本体', '## 母子命名', '## 人物与独立道具'):
            start = content.find(heading)
            if start < 0:
                continue
            end = content.find('\n## ', start + len(heading))
            excerpts.append(content[start:end if end >= 0 else len(content)][:2600])
    package = {'version': VERSION, 'rules': RULES, 'sources': sources, 'referenceData': excerpts,
               'scope': 'asset_design_and_continuity', 'authority': 'reference_data_only'}
    package['revisionHash'] = digest(package)
    return package


def appearance(spec, state):
    declared = set(spec.get('imageStateKeys', []))
    keys = (set(spec.get('visualStateKeys', [])) & APPEARANCE_KEYS) | declared
    return {key: state[key] for key in sorted(keys - SHOT_KEYS) if key in state and not (isinstance(state[key], dict) and state[key].get('unknown'))}


def image_needed(spec, claims, baseline):
    selected = appearance(spec, claims)
    return bool(selected and any(value != baseline.get(key) for key, value in selected.items()))


def mother_brief(kind):
    return {
        'character': 'Character identity reference sheet, 2x2 layout. Upper row: front and side head closeups, head top to collarbone. Lower row: front and back body views, shoulders to feet. Same identity and costume in all views. Normal neutral expression, relaxed brows, naturally closed lips, stable natural pose, empty hands. No independently held or worn props. Preserve declared dirt, wounds and costume; do not heal, wash, beautify or change identity.',
        'prop': 'Independent prop reference sheet, 2x2 front, side, back and 45-degree overhead views. Same object, proportions, material and structure. No person, owner, hands or feet. Simple opening structures may have an auxiliary structural view; do not embed unrelated contents.',
        'location': 'Environment master reference, 16:9, wide high-angle view around 45-65 degrees showing the full room or site, entrances, spatial layout and fixed furnishings. Empty of actors and temporary story props. Preserve established fixed layout and architecture.',
    }[kind]


def child_brief(asset, variant, parent):
    if variant.get('referenceType') == 'appearance_variant':
        parent_appearance = parent.get('appearanceClaims', asset.get('baselineAppearance', {}))
        changes = {key: value for key, value in variant.get('appearanceClaims', {}).items()
                   if value != parent_appearance.get(key)}
        delta = canonical(changes)
    elif variant.get('referenceType') == 'shot_state':
        physical={'lid','open','closed','damage','damaged','@contents','contents','开合','损坏','内容物'}
        delta = canonical({key:value for key,value in variant.get('claims',{}).items() if key in physical})
    else:
        delta = variant.get('deltaString') or canonical(variant.get('appearanceClaims', variant.get('claims', {})))
    return '\n'.join([
        'Edit the attached direct-parent reference image of ' + asset['name'] + '.',
        'Direct parent: ' + str(parent.get('name', parent['id'])) + ' @ revision ' + str(parent.get('_version', 1)) + '.',
        'Change only: ' + delta,
        'Preserve the same identity, proportions, unaffected costume and injury, artistic style, material, layout and view arrangement from the parent. Do not redesign the subject, add independent props or change unrelated areas.',
        'Keep normal neutral expression for character reference views. This is an asset reference, not a scene performance.',
    ])
