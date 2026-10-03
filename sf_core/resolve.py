"""Choose which reference images a generation unit uploads, in priority order.

Speaking characters first, then other people on screen, the set, props in play,
crowds, and props that are only mentioned. Anything beyond the reliable budget is
described in text instead of taking a slot.
"""
from __future__ import annotations

import hashlib
from pathlib import Path

from .ledger import _mentions
from .model import Project, Reference, ShotPlan

IMAGE_EXTENSIONS = ('.png', '.jpg', '.jpeg', '.webp')


def time_key(time: str) -> str:
    text = time or ''
    if any(word in text for word in ('黄昏', '傍晚', '日落', '夕阳', '薄暮')):
        return '黄昏'
    if any(word in text for word in ('凌晨', '拂晓', '黎明', '清晨', '早晨', '晨')):
        return '晨'
    if any(word in text for word in ('夜', '更', '晚')):
        return '夜'
    if any(word in text for word in ('日', '白天', '午', '早上', '上午', '下午')):
        return '日'
    return text or '日'


def candidates(plans: list[ShotPlan], scene, project: Project) -> list[str]:
    on_screen, crowds, props_in_play = [], [], []
    for plan in plans:
        for name in plan.shot.who:
            entity = project.lookup(name)
            if not entity:
                continue
            bucket = {'character': on_screen, 'crowd': crowds, 'prop': props_in_play}.get(entity.kind)
            if bucket is not None and entity.name not in bucket:
                bucket.append(entity.name)
    speakers = []
    for plan in plans:
        for line in plan.lines:
            entity = project.lookup(line.speaker)
            if (line.kind == 'speech' and not line.offscreen and entity and entity.name in on_screen
                    and entity.name not in speakers):
                speakers.append(entity.name)
    mentioned = []
    for plan in plans:
        for name in _mentions(plan.shot.action, project, kinds=('prop',)):
            if name not in props_in_play and name not in mentioned:
                mentioned.append(name)
    location = project.lookup(scene.location)
    ranked = speakers + [n for n in on_screen if n not in speakers]
    if location:
        ranked.append(location.name)
    ranked += props_in_play + crowds + mentioned
    return ranked


def variant_of(name: str, project: Project, world: dict, scene) -> str:
    entity = project.entities[name]
    if entity.kind in ('character', 'crowd'):
        person = world.get('chars', {}).get(name) or {}
        return person.get('look') or entity.default_look or '默认'
    if entity.kind == 'location':
        key = time_key(scene.time)
        return key if not entity.states or key in entity.states else next(iter(entity.states))
    state = world.get('props', {}).get(name) or {}
    for label in entity.states:
        if (state.get('open') is True and label in ('打开', '开着', '开启')) or \
           (state.get('open') is False and label in ('关闭', '关着', '合上')) or \
           (state.get('condition') and label in state.get('condition', '')):
            return label
    return '默认'


def find_image(root: Path, name: str, variant: str):
    for folder in (root / 'assets' / 'images' / name,):
        for ext in IMAGE_EXTENSIONS:
            path = folder / f'{variant}{ext}'
            if path.is_file():
                return path
    for ext in IMAGE_EXTENSIONS:
        path = root / 'assets' / 'images' / f'{name}-{variant}{ext}'
        if path.is_file():
            return path
    return None


def bind(plans: list[ShotPlan], scene, project: Project):
    """Return (references, text_only) for one unit."""
    ranked = candidates(plans, scene, project)
    budget = project.series.cap.get('images_reliable', 6)
    world = plans[0].world_start if plans else {}
    references, text_only = [], []
    for name in ranked:
        wanted = project.entities[name].extra.get('参考图', '')
        if len(references) >= budget or wanted in ('否', '不需要', '无', '不用', '文字'):
            text_only.append(name)
            continue
        variant = variant_of(name, project, world, scene)
        image = find_image(project.root, name, variant)
        reference = Reference(slot=len(references) + 1, entity=name, kind=project.entities[name].kind, variant=variant)
        if image:
            reference.file = image.relative_to(project.root).as_posix()
            reference.sha256 = hashlib.sha256(image.read_bytes()).hexdigest()
        references.append(reference)
    return references, text_only
