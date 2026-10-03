"""Continuity ledger: 【状态】 lines become typed events; replay gives the state at any line.

Authors only write changes. The ledger replays them in script order across the
whole series, so episode n+1 starts from episode n's end state automatically.
"""
from __future__ import annotations

import copy
import re
from dataclasses import dataclass, field

from .model import Issue, Project

VERBS = [
    ('hold', ['拿起', '拿着', '握住', '抓起', '捡起', '接过', '举起', '掏出', '取出', '抽出', '拔出', '提起', '端起', '抱起', '夺下', '夺过', '抢过']),
    ('give', ['交给', '递给', '扔给', '塞给', '还给', '递到', '交到']),
    ('put', ['放下', '放回', '放到', '扔下', '丢下', '扔掉', '丢掉', '插回', '留下', '松开']),
    ('place', ['放在', '位于', '留在', '摆在', '挂在', '落在', '掉在']),
    ('stow', ['收起', '藏起', '揣进', '装进', '塞进', '收好', '收进']),
    ('wear', ['戴上', '背起', '背上', '佩戴', '挎上', '系上', '披上']),
    ('unwear', ['摘下', '取下', '卸下', '解下']),
    ('dress', ['换上', '换成', '穿上', '换回', '改穿']),
    ('hurt', ['受伤', '负伤', '挂彩', '被打伤', '中刀', '中枪', '受了伤']),
    ('bandage', ['包扎', '贴上纱布', '缠上绷带', '上药']),
    ('heal', ['痊愈', '伤愈', '拆线', '恢复']),
    ('open', ['打开', '掀开', '拉开', '揭开']),
    ('close', ['关上', '合上', '盖上', '锁上']),
    ('break', ['毁坏', '折断', '摔碎', '碎裂', '损坏', '烧毁', '打碎', '断裂', '砸坏']),
    ('vanish', ['消失', '用掉', '消耗', '销毁', '用完', '吃掉', '喝掉']),
    ('appear', ['出现', '亮出', '现身']),
    ('die', ['死亡', '身亡', '断气', '死去']),
    ('faint', ['昏迷', '晕倒', '昏倒', '失去意识']),
    ('wake', ['醒来', '苏醒', '醒过来']),
    ('enter', ['进入', '来到', '走进', '赶到']),
    ('leave', ['离开', '走出', '退出']),
    ('learn', ['得知', '知道', '发现', '明白']),
]
VERB_TABLE = sorted(((verb, kind) for kind, verbs in VERBS for verb in verbs), key=lambda x: -len(x[0]))
APPEARANCE_KINDS = {'dress', 'hurt', 'bandage', 'heal', 'die', 'faint', 'wake'}


@dataclass
class Event:
    kind: str
    subject: str = ''
    obj: str = ''
    target: str = ''
    detail: str = ''
    offscreen: bool = False
    raw: str = ''
    where: str = ''


@dataclass
class Replay:
    before: dict = field(default_factory=dict)      # (episode, anchor) -> world before the line
    after: dict = field(default_factory=dict)       # (episode, anchor) -> world after the line and its state notes
    scene_start: dict = field(default_factory=dict) # (episode, scene id) -> world at the scene heading
    episode_start: dict = field(default_factory=dict)
    episode_end: dict = field(default_factory=dict)
    events: list = field(default_factory=list)      # (episode, scene, position, Event)


def initial_world(project: Project) -> dict:
    world = {'chars': {}, 'props': {}}
    for entity in project.entities.values():
        if entity.kind in ('character', 'crowd'):
            world['chars'][entity.name] = {'look': entity.default_look, 'conditions': {}, 'status': ''}
        elif entity.kind == 'prop':
            holder = project.lookup(entity.holder)
            world['props'][entity.name] = {'holder': holder.name if holder else None, 'place': entity.place,
                                           'mode': 'hand' if holder else '', 'open': None, 'condition': '', 'exists': True}
    return world


def _mentions(text: str, project: Project, kinds=None) -> list[str]:
    """Entity names mentioned in text, longest match first, in order of appearance."""
    names = []
    for entity in project.entities.values():
        if kinds and entity.kind not in kinds:
            continue
        for alias in entity.names():
            if alias:
                names.append((alias, entity.name))
    names.sort(key=lambda x: -len(x[0]))
    found, taken = [], []
    for alias, name in names:
        start = text.find(alias)
        while start >= 0:
            span = (start, start + len(alias))
            if not any(a < span[1] and span[0] < b for a, b in taken):
                taken.append(span)
                found.append((start, name))
                break
            start = text.find(alias, start + 1)
    return [name for _, name in sorted(found)]


def _strip_names(text: str, project: Project, names) -> str:
    for name in names:
        entity = project.entities.get(name)
        for alias in (entity.names() if entity else [name]):
            text = text.replace(alias, '')
    return text.strip(' ，,、：:')


def parse_event(text: str, project: Project, where: str = ''):
    """Parse one 【状态】 line. Returns (Event | None, warning message | '')."""
    raw = text.strip()
    note = ''
    match = re.search(r'[（(]([^（）()]*)[）)]\s*$', raw)
    body = raw
    if match:
        note, body = match.group(1), raw[:match.start()].strip()
    offscreen = '画外' in note
    extra = '' if offscreen else note
    main, detail = body, ''
    split = re.search(r'[：:]', body)
    if split:
        main, detail = body[:split.start()].strip(), body[split.end():].strip()
    compact = re.sub(r'\s+', '', main)
    hit = None
    for verb, kind in VERB_TABLE:
        position = compact.find(verb)
        if position > 0:
            if hit is None or position < hit[0] or (position == hit[0] and len(verb) > len(hit[1])):
                hit = (position, verb, kind)
    if not hit:
        return None, f'无法识别的状态行「{raw}」：请用「主体 动词 对象：细节」，如「李树 拿起 铁棍：右手」'
    position, verb, kind = hit
    subject_text, rest = compact[:position], compact[position + len(verb):]
    pre_object = ''
    if '把' in subject_text:
        subject_text, pre_object = subject_text.split('把', 1)
    event = Event(kind=kind, detail=detail, offscreen=offscreen, raw=raw, where=where)
    subject_entity = project.lookup(subject_text) or next(
        (project.entities[n] for n in _mentions(subject_text, project)), None)
    event.subject = subject_entity.name if subject_entity else subject_text
    others = _mentions(pre_object + rest + ' ' + detail, project)
    props = [n for n in others if project.entities[n].kind == 'prop']
    people = [n for n in others if project.entities[n].kind in ('character', 'crowd')]
    if kind in ('hold', 'give', 'put', 'stow', 'wear', 'unwear'):
        event.obj = props[0] if props else (pre_object or _strip_names(rest, project, people))
        if kind == 'give':
            event.target = people[0] if people else ''
        if kind == 'put' and not detail:
            event.detail = _strip_names(rest, project, props)
        event.detail = event.detail or extra
    elif kind == 'place':
        prop = subject_entity.name if subject_entity and subject_entity.kind == 'prop' else (props[0] if props else '')
        event.obj, event.subject = prop, ''
        if not detail:
            event.detail = _strip_names(rest, project, props)
    elif kind in ('open', 'close', 'break', 'vanish', 'appear'):
        if subject_entity and subject_entity.kind == 'prop':
            event.obj = subject_entity.name
        else:
            event.obj = props[0] if props else _strip_names(rest, project, people)
        if kind == 'appear' and not detail:
            event.detail = _strip_names(rest, project, props)
    elif kind == 'dress':
        event.obj = (detail or _strip_names(rest, project, [])).strip()
    elif kind in ('hurt', 'bandage', 'heal'):
        event.detail = (detail or rest) + (f'（{extra}）' if extra else '')
    elif kind in ('enter', 'leave', 'learn'):
        event.obj = detail or rest
    warning = ''
    if kind not in ('place', 'open', 'close', 'break', 'vanish', 'appear') and not subject_entity:
        warning = f'状态行「{raw}」的主体「{subject_text}」不在 bible.md'
    elif kind in ('hold', 'give', 'put', 'stow', 'wear', 'unwear', 'place') and event.obj not in project.entities:
        warning = f'状态行「{raw}」的道具「{event.obj}」不在 bible.md 道具表'
    return event, warning


def _injury(detail: str):
    detail = detail.strip()
    match = re.match(r'^([^，,（(：:]+)[，,（(：:]?\s*(.*?)[）)]?$', detail)
    if not match:
        return detail or '身上', ''
    return match.group(1).strip() or '身上', match.group(2).strip(' ，,')


def apply_event(world: dict, event: Event, project: Project, issues: list[Issue]):
    chars, props = world['chars'], world['props']
    if event.kind in ('hold', 'give', 'put', 'stow', 'wear', 'unwear', 'place', 'open', 'close', 'break', 'vanish', 'appear'):
        prop = props.get(event.obj)
        if prop is None:
            return
        if event.kind == 'hold':
            prop.update(holder=event.subject, mode='hand', place=event.detail or '手中', exists=True)
        elif event.kind == 'give':
            prop.update(holder=event.target or None, mode='hand', place='手中', exists=True)
        elif event.kind in ('put', 'place'):
            prop.update(holder=None, mode='', place=event.detail or prop.get('place', ''), exists=True)
        elif event.kind == 'stow':
            prop.update(holder=event.subject, mode='hidden', place=event.detail or '身上')
        elif event.kind == 'wear':
            prop.update(holder=event.subject, mode='worn', place=event.detail or '身上')
        elif event.kind == 'unwear':
            prop.update(mode='hand', place=event.detail or '手中')
        elif event.kind in ('open', 'close'):
            prop['open'] = event.kind == 'open'
        elif event.kind == 'break':
            prop['condition'] = event.detail or '损坏'
        elif event.kind == 'vanish':
            prop.update(exists=False, holder=None, mode='')
        elif event.kind == 'appear':
            prop.update(exists=True, place=event.detail or prop.get('place', ''))
        return
    person = chars.get(event.subject)
    if person is None:
        return
    if event.kind == 'dress':
        entity = project.entities.get(event.subject)
        looks = list(entity.looks) if entity else []
        chosen = next((name for name in looks if name and name in event.obj), None)
        if not chosen:
            if event.obj:
                issues.append(Issue('warning', 'LOOK_UNKNOWN', event.where,
                                    f'「{event.subject}」没有登记造型「{event.obj}」；请在 bible.md 加「造型（{event.obj}）」'))
            chosen = event.obj or person['look']
        person['look'] = chosen
    elif event.kind in ('hurt', 'bandage'):
        part, desc = _injury(event.detail)
        if event.kind == 'bandage' and not desc:
            desc = '包扎着'
        person['conditions'][part] = desc
    elif event.kind == 'heal':
        part, _ = _injury(event.detail)
        if event.detail and part in person['conditions']:
            person['conditions'].pop(part)
        elif not event.detail:
            person['conditions'].clear()
    elif event.kind == 'die':
        person['status'] = '死亡'
    elif event.kind == 'faint':
        person['status'] = '昏迷'
    elif event.kind == 'wake':
        person['status'] = ''


def replay(project: Project) -> Replay:
    result = Replay()
    world = initial_world(project)
    for episode in project.episodes:
        result.episode_start[episode.id] = copy.deepcopy(world)
        last_anchor = None
        for scene in episode.scenes:
            snapshot = copy.deepcopy(world)
            result.scene_start[(episode.id, scene.id)] = snapshot
            if last_anchor:
                result.after[(episode.id, last_anchor)] = snapshot
            for index, line in enumerate(scene.lines):
                if line.kind == 'state':
                    where = f'{episode.id}/script.md:{line.lineno}'
                    event, warning = parse_event(line.text, project, where)
                    if warning:
                        project.issues.append(Issue('warning', 'STATE_UNPARSED' if event is None else 'STATE_ENTITY', where, warning))
                    if event:
                        apply_event(world, event, project, project.issues)
                        result.events.append((episode.id, scene.id, index, event))
                elif line.anchor:
                    snapshot = copy.deepcopy(world)
                    result.before[(episode.id, line.anchor)] = snapshot
                    if last_anchor:
                        result.after[(episode.id, last_anchor)] = snapshot
                    last_anchor = line.anchor
        if last_anchor:
            result.after[(episode.id, last_anchor)] = copy.deepcopy(world)
        result.episode_end[episode.id] = copy.deepcopy(world)
    return result


def appearance(world: dict, name: str) -> tuple:
    """What a camera would see changing on a character: look, injuries, status."""
    person = world['chars'].get(name)
    if not person:
        return ()
    return (person['look'], tuple(sorted(person['conditions'].items())), person['status'])


def held_props(world: dict, name: str) -> list[tuple[str, str]]:
    """Visible props a character is holding or wearing: [(prop, mode)]."""
    return [(prop, state['mode']) for prop, state in world['props'].items()
            if state['holder'] == name and state['exists'] and state['mode'] in ('hand', 'worn')]


SUMMARY_PARTS = ('伤情', '伤势', '状况', '情况', '外伤')
CONDITION_WORDS = ('伤', '肿', '瘸', '跛', '血', '疤', '敷料', '纱布', '绷带', '淤', '青', '包扎', '石膏')


def condition_phrase(part: str, desc: str) -> str:
    if part in SUMMARY_PARTS:
        return desc or part
    if desc:
        return f'{part}{desc}'
    return part if any(word in part for word in CONDITION_WORDS) else f'{part}有伤'


def condition_phrases(world: dict, name: str) -> list[str]:
    person = world['chars'].get(name) or {}
    phrases = [condition_phrase(part, desc) for part, desc in (person.get('conditions') or {}).items()]
    if person.get('status'):
        phrases.append(person['status'])
    return phrases
