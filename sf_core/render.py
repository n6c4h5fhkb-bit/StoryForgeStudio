"""Write one Seedance request in the shape the model reads: roles once, then time-coded shots.

Only what the camera should show and the actors should say goes in. Reasons, IDs,
workflow status, editorial handles and author notes stay in the plan files.
"""
from __future__ import annotations

import re

from .ledger import _mentions, condition_phrases, held_props
from .model import Project, UnitPlan
from .resolve import variant_of
from .textfmt import end_sentence, tidy

NO_WORDS = ('无', '否', '不要', '关', 'off', 'no', '')


def describe(name: str, project: Project, world: dict, variant: str) -> str:
    entity = project.entities[name]
    if entity.kind in ('character', 'crowd'):
        text = entity.looks.get(variant) or entity.identity or entity.name
        if entity.kind == 'crowd' and entity.count:
            text = f'{entity.count}人，{text}'
        extras = condition_phrases(world, name)
        return '，'.join([text.rstrip('。；;，'), *extras])
    if entity.kind == 'location':
        return (entity.states.get(variant) or entity.identity or entity.name).rstrip('。；;')
    text = entity.identity or entity.name
    if variant != '默认' and variant in entity.states:
        text = entity.states[variant]
    state = world.get('props', {}).get(name) or {}
    if state.get('condition') and state['condition'] not in text:
        text = f'{text}，{state["condition"]}'
    return text.rstrip('。；;')


def axis_for(axis: str, on_screen: list[str], project: Project) -> str:
    """Keep only the screen-side notes about people who are actually in this shot."""
    parts = [part.strip() for part in re.split(r'[，,；;、]', axis) if part.strip()]
    people = {alias: e.name for e in project.entities.values() if e.kind in ('character', 'crowd') for alias in e.names()}
    kept = []
    for part in parts:
        named = {name for alias, name in people.items() if alias in part}
        if not named or named & set(on_screen):
            kept.append(part)
    return '，'.join(kept)


DRESSINGS = ('敷料', '纱布', '绷带', '创可贴', '膏药', '护具')


def holding_phrase(person: str, prop: str, mode: str, world: dict) -> str:
    if mode != 'worn':
        return f'{person}手里拿着{prop}'
    place = (world.get('props', {}).get(prop) or {}).get('place', '')
    verb = '贴着' if any(word in prop for word in DRESSINGS) else '戴着'
    return f'{person}的{place}{verb}{prop}' if place and place not in ('身上', '手中') else f'{person}身上{verb}{prop}'


def _quote(text: str) -> str:
    text = text.strip()
    return text if text.startswith(('“', '"', '「')) else f'“{text}”'


def speech_text(line, on_screen: set, project: Project) -> str:
    entity = project.lookup(line.speaker)
    name = entity.name if entity else line.speaker
    paren = f'（{line.paren}）' if line.paren else ''
    if line.kind == 'inner':
        return f'{name}的内心独白（画外音，{name}不开口）：{_quote(line.text)}'
    if line.kind == 'narration':
        return f'旁白：{_quote(line.text)}' if project.series.narration_on else ''
    if line.offscreen or name not in on_screen:
        return f'画外传来{name}的声音{paren}：{_quote(line.text)}'
    return f'{name}{paren}：{_quote(line.text)}'


def render_unit(unit: UnitPlan, project: Project) -> str:
    series, cap = project.series, project.series.cap
    scene, defaults = unit.scene, unit.defaults
    first_world = unit.shots[0].world_start
    aspect = series.fmt.get('aspect', '16:9')
    style = series.style.rstrip('。；;')
    time = scene.time or ''
    if unit.shots[0].jump:
        time = f'{time}（{unit.shots[0].jump.rstrip("。")}）' if time else unit.shots[0].jump.rstrip('。')
    light = defaults.get('光线') or defaults.get('光') or ''
    header = '，'.join(p for p in (aspect, style) if p) + '。'
    header += '，'.join(p for p in (scene.location, time, light) if p) + '。'
    lines = [tidy(header)]
    token = cap.get('reference_token', '@图片{n}')
    for ref in unit.references:
        desc = describe(ref.entity, project, first_world, ref.variant)
        lines.append(tidy(f'{token.format(n=ref.slot)} 是{ref.entity}：{end_sentence(desc)}'))
    lines.append('')
    referenced = {ref.entity for ref in unit.references}
    introduced = set()
    axis = defaults.get('轴线') or defaults.get('站位') or ''
    has_speech = False
    for index, (plan, (a, b)) in enumerate(zip(unit.shots, unit.segments)):
        shot = plan.shot
        on_screen = {e.name for e in (project.lookup(n) for n in shot.who) if e}
        head = cap.get('segment_format', '{a}–{b}秒').format(a=a, b=b)
        head = '，'.join(p for p in (head, shot.size, shot.angle, shot.move) if p)
        if index == 0 and axis:
            side = axis_for(axis, [e.name for e in (project.lookup(n) for n in shot.who) if e], project)
            if side:
                head += f'，{side}'
        holding = []
        if index == 0:
            people = [e.name for e in (project.lookup(n) for n in shot.who) if e and e.kind == 'character']
            listed = {e.name for e in (project.lookup(n) for n in shot.who) if e and e.kind == 'prop'}
            for name in people:
                conditions = ''.join(condition_phrases(first_world, name))
                for prop, mode in held_props(first_world, name):
                    if prop not in listed or prop in _mentions(shot.action, project, kinds=('prop',)):
                        continue
                    if mode == 'worn' and any(w in prop for w in DRESSINGS) and any(w in conditions for w in DRESSINGS):
                        introduced.add(prop)      # the injury already says it; do not describe the bandage twice
                        continue
                    phrase = holding_phrase(name, prop, mode, first_world)
                    if prop not in referenced and prop not in introduced:
                        phrase += f'（{describe(prop, project, first_world, variant_of(prop, project, first_world, scene))}）'
                        introduced.add(prop)
                    holding.append(phrase)
        sentences = []
        for name in shot.who:
            entity = project.lookup(name)
            if entity and entity.kind != 'location' and entity.name not in referenced | introduced:
                variant = variant_of(entity.name, project, plan.world_start, scene)
                sentences.append(f'（{entity.name}：{describe(entity.name, project, plan.world_start, variant)}）')
                introduced.add(entity.name)
        sentences += holding
        if shot.action:
            sentences.append(shot.action)
        if shot.stage:
            sentences.append(shot.stage)
        body = ''.join(end_sentence(s) for s in sentences if s)
        speech = [speech_text(line, on_screen, project) for line in plan.lines if line.kind in ('speech', 'inner', 'narration')]
        speech = [s for s in speech if s]
        has_speech = has_speech or any(line.kind == 'speech' for line in plan.lines)
        lines.append(tidy(f'{head}：{body}{"".join(speech)}'))
    lines.append('')
    sound = (defaults.get('声音') or defaults.get('音效') or '').rstrip('。')
    if not series.native_audio:
        base = '只保留环境声，对白后期配音' + (f'，{sound}' if sound else '')
    elif sound and ('对白' in sound or '环境声' in sound):
        base = sound
    else:
        base = ('同期对白和环境声' if has_speech else '只有环境声') + (f'，{sound}' if sound else '')
    tail = [base]
    if series.music in NO_WORDS and '音乐' not in base:
        tail.append('无背景音乐')
    if series.subtitles in NO_WORDS and '字幕' not in base:
        tail.append('无字幕')
    lines.append(tidy('，'.join(tail) + '。'))
    return '\n'.join(lines).strip() + '\n'
