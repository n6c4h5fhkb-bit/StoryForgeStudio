"""Parsers for the authored Markdown files.

Every parser is lenient: it keeps going, records an Issue for anything it could
not understand, and never refuses to read a file. Validation happens in checks.
"""
from __future__ import annotations

import json
import re
from pathlib import Path

from .model import (KIND_NAMES, TAGS, Entity, Episode, Issue, Line, OutlineEpisode, Project, Scene,
                    Series, Shot, ShotScene)
from .textfmt import split_kv, split_list, strip_paren

PROFILE_DIR = Path(__file__).resolve().parent / 'profiles'
ANCHOR = re.compile(r'\s*\^(L\d+)\s*$')
TAG_LINE = re.compile(r'^【([^】]{1,8})】\s*(.*)$')
SPEAKER = re.compile(r'^([^\s：:（(【\[“"]{1,16})(?:[（(]([^）)]{1,12})[）)])?\s*[：:]\s*(.+)$')
INNER_MARKS = {'心声', '内心', '内心独白', '独白', 'OS', 'os'}
OFFSCREEN_MARKS = {'画外', '画外音', 'VO', 'V.O.', '电话', '电话里', '广播', '对讲机'}
TAG_KINDS = {'画面': 'action', '动作': 'action', '镜头': 'action', '音效': 'sfx', '声音': 'sfx', '状态': 'state',
             '时间跳转': 'jump', '转场': 'jump', '时间': 'jump', '备注': 'note', '注': 'note', '旁白': 'narration'}
SERIES_KEYS = {'片名': 'title', '标题': 'title', '剧名': 'title', '格式': 'format_name', '模型': 'model',
               '画风': 'style', '风格': 'style', '人脸': 'face', '语速': 'rate', '对白音频': 'audio', '音频': 'audio',
               '字幕': 'subtitles', '背景音乐': 'music', '配乐': 'music', '旁白': 'narration',
               '内容尺度': 'content', '内容': 'content'}
ANCHORED_KINDS = ('action', 'speech', 'inner', 'narration')


def read_text(path: Path) -> str:
    return Path(path).read_text(encoding='utf-8-sig')


def load_profiles():
    formats = json.loads((PROFILE_DIR / 'formats.json').read_text(encoding='utf-8'))
    caps = json.loads((PROFILE_DIR / 'capabilities.json').read_text(encoding='utf-8'))
    formats.pop('_note', None)
    caps.pop('_note', None)
    return formats, caps


def _match_profile(name: str, table: dict):
    wanted = (name or '').strip().lower()
    for key, value in table.items():
        if wanted == key.lower() or wanted in (alias.lower() for alias in value.get('aliases', [])):
            return key, value
    return None, None


def bullets(text: str):
    """Yield (lineno, key, value) for '- key：value' style lines."""
    for lineno, raw in enumerate(text.splitlines(), 1):
        line = raw.strip()
        if line.startswith(('- ', '* ', '+ ')):
            line = line[2:].strip()
        elif line.startswith('#') or not line:
            continue
        pair = split_kv(line)
        if pair and pair[0]:
            yield lineno, pair[0], pair[1]


def parse_series(path: Path, issues: list[Issue]) -> Series:
    series = Series()
    if path and Path(path).is_file():
        for lineno, key, value in bullets(read_text(path)):
            attr = SERIES_KEYS.get(key)
            if not attr:
                series.extra[key] = value
            elif attr == 'rate':
                try:
                    series.rate = float(re.sub(r'[^\d.]', '', value) or 0) or None
                except ValueError:
                    issues.append(Issue('warning', 'SERIES_RATE', f'series.md:{lineno}', f'语速「{value}」不是数字，已使用格式默认值'))
            else:
                setattr(series, attr, value)
    else:
        issues.append(Issue('warning', 'SERIES_MISSING', 'series.md', '缺少 series.md，使用默认：横屏剧集 + Seedance 2.0'))
    formats, caps = load_profiles()
    name, fmt = _match_profile(series.format_name, formats)
    if not fmt:
        issues.append(Issue('warning', 'FORMAT_UNKNOWN', 'series.md', f'未知格式「{series.format_name}」，改用横屏剧集；可选：{"、".join(formats)}'))
        name, fmt = '横屏剧集', formats['横屏剧集']
    series.format_name, series.fmt = name, fmt
    model, cap = _match_profile(series.model, caps)
    if not cap:
        issues.append(Issue('warning', 'MODEL_UNKNOWN', 'series.md', f'未知模型「{series.model}」，改用 seedance-2.0'))
        model, cap = 'seedance-2.0', caps['seedance-2.0']
    series.model, series.cap = model, cap
    return series


def _kind_of(heading: str) -> str | None:
    text = heading.strip().lower()
    for kind, names in KIND_NAMES.items():
        if any(text.startswith(name.lower()) for name in names):
            return kind
    return None


LOOK_KEY = re.compile(r'^(造型|服装|状态|版本)(?:\s*[（(]\s*(.+?)\s*[）)]|\s*[/·・]\s*(.+))?$')


def parse_bible(path: Path, issues: list[Issue]) -> dict[str, Entity]:
    entities: dict[str, Entity] = {}
    if not (path and Path(path).is_file()):
        issues.append(Issue('warning', 'BIBLE_MISSING', 'bible.md', '缺少 bible.md：人物、场景和道具都无法绑定参考图'))
        return entities
    kind, current = None, None
    for lineno, raw in enumerate(read_text(path).splitlines(), 1):
        line = raw.strip()
        where = f'bible.md:{lineno}'
        if line.startswith('# ') and not line.startswith('## '):
            kind, current = _kind_of(line[2:]), None
            if not kind:
                issues.append(Issue('warning', 'BIBLE_SECTION', where, f'无法识别的分区「{line[2:]}」；请用 人物 / 群演 / 场景 / 道具'))
        elif line.startswith('## '):
            name = line[3:].strip()
            if not kind:
                issues.append(Issue('warning', 'BIBLE_ORPHAN', where, f'「{name}」不在任何分区下，已忽略'))
                current = None
            elif name in entities:
                issues.append(Issue('warning', 'BIBLE_DUPLICATE', where, f'重复登记「{name}」，后面的内容合并到前面'))
                current = entities[name]
            else:
                current = entities[name] = Entity(name=name, kind=kind)
        elif line.startswith(('- ', '* ')) and current is not None:
            pair = split_kv(line[2:])
            if not pair:
                continue
            key, value = pair
            look = LOOK_KEY.match(key)
            if key in ('别名', '又名', '称呼'):
                current.aliases += [a for a in split_list(value) if a != current.name]
            elif key in ('身份', '外观', '布局', '描述', '长相', '外貌', '设定'):
                current.identity = (current.identity + '；' + value) if current.identity else value
            elif look:
                label = (look.group(2) or look.group(3) or '').strip() or '默认'
                if look.group(1) in ('状态', '版本') and current.kind in ('prop', 'location'):
                    current.states[label] = value
                else:
                    current.looks[label] = value
            elif key in ('标记', '特征', '印记'):
                current.marks = value
            elif key in ('声音', '嗓音', '音色'):
                current.voice = value
            elif key in ('人数', '数量'):
                digits = re.sub(r'\D', '', value)
                current.count = int(digits) if digits else None
            elif key in ('持有', '初始持有', '持有者'):
                current.holder = value
            elif key in ('位置', '初始位置', '初始', '放在'):
                current.place = value
            elif key in ('参考图', '出图'):
                current.extra['参考图'] = value
            else:
                current.extra[key] = value
    return entities


def parse_outline(path: Path, issues: list[Issue]) -> list[OutlineEpisode]:
    rows: list[OutlineEpisode] = []
    if not (path and Path(path).is_file()):
        return rows
    current = None
    for raw in read_text(path).splitlines():
        line = raw.strip()
        match = re.match(r'^##\s+(EP\d+)\s*(.*)$', line, re.I)
        if match:
            current = OutlineEpisode(id=match.group(1).upper(), title=match.group(2).strip(' ：:-—'))
            rows.append(current)
        elif current and line.startswith(('- ', '* ')):
            pair = split_kv(line[2:])
            if pair:
                current.fields[pair[0]] = pair[1]
    return rows


def parse_heading(text: str, lineno: int) -> Scene:
    parts = [p.strip() for p in re.split(r'\s*[·・|｜/]\s*', text) if p.strip()]
    first = parts[0].split(None, 1) if parts else ['场']
    scene = Scene(id=first[0], heading=text.strip(), lineno=lineno)
    rest = parts[1:]
    scene.location = first[1].strip() if len(first) > 1 else (rest.pop(0) if rest else '')
    for part in rest:
        if re.match(r'^(第.{1,4}[天日]|D\d+|Day\s*\d+)$', part, re.I):
            scene.day = part
        elif not scene.time:
            scene.time = part
    return scene


def classify(text: str):
    """Return (kind, speaker, paren, offscreen, body) for one script line without its anchor."""
    tag = TAG_LINE.match(text)
    if tag:
        label, body = tag.group(1).strip(), tag.group(2).strip()
        return TAG_KINDS.get(label, 'action'), ('旁白' if label == '旁白' else ''), '', False, body
    speaker = SPEAKER.match(text)
    if speaker:
        name, mod, body = speaker.group(1).strip(), (speaker.group(2) or '').strip(), speaker.group(3).strip()
        if name == '旁白':
            return 'narration', '旁白', '', False, body
        kind, offscreen, paren = 'speech', False, ''
        lead, rest = strip_paren(body)
        for mark in (mod, lead):
            if not mark:
                continue
            if mark in INNER_MARKS:
                kind = 'inner'
            elif mark in OFFSCREEN_MARKS:
                offscreen = True
                paren = mark if mark in ('电话', '电话里', '广播', '对讲机') else paren
            else:
                paren = mark if not paren else paren + '，' + mark
        return kind, name, paren, offscreen, (rest if lead else body)
    return 'action', '', '', False, text


def parse_script(path: Path, episode_id: str, issues: list[Issue]) -> Episode:
    episode = Episode(id=episode_id, script_path=Path(path))
    scene = None
    seen: dict[str, int] = {}
    for lineno, raw in enumerate(read_text(path).splitlines(), 1):
        text = raw.strip()
        where = f'{episode_id}/script.md:{lineno}'
        if not text or text.startswith('<!--') or text.startswith('>'):
            continue
        if text.startswith('# ') and not text.startswith('## '):
            episode.title = re.sub(r'^EP\d+\s*', '', text[2:], flags=re.I).strip()
            continue
        if text.startswith('## '):
            scene = parse_heading(text[3:], lineno)
            if any(s.id == scene.id for s in episode.scenes):
                issues.append(Issue('error', 'SCENE_DUPLICATE', where, f'场次编号「{scene.id}」重复'))
            episode.scenes.append(scene)
            continue
        if scene is None:
            scene = Scene(id='场1', heading='（未写场次标题）', lineno=lineno)
            episode.scenes.append(scene)
            issues.append(Issue('warning', 'SCENE_MISSING', where, '第一行内容之前没有场次标题（## 场1 地点 · 时间）'))
        anchor = ''
        match = ANCHOR.search(text)
        if match:
            anchor, text = match.group(1), text[:match.start()].rstrip()
        kind, speaker, paren, offscreen, body = classify(text)
        if not TAG_LINE.match(text) and not SPEAKER.match(text):
            issues.append(Issue('info', 'LINE_UNMARKED', where, '没有【画面】等标记的行按画面处理'))
        if anchor:
            if anchor in seen:
                issues.append(Issue('error', 'ANCHOR_DUPLICATE', where, f'行号 {anchor} 与第 {seen[anchor]} 行重复'))
            seen[anchor] = lineno
        scene.lines.append(Line(kind=kind, text=body, speaker=speaker, paren=paren, offscreen=offscreen,
                                anchor=anchor, lineno=lineno, scene=scene.id))
    return episode


def assign_ids(path: Path) -> int:
    """Append ^Lnnn anchors to action and spoken lines that lack one. Returns the number added."""
    lines = read_text(path).splitlines()
    numbers = [int(m.group(1)[1:]) for raw in lines for m in [ANCHOR.search(raw.strip())] if m]
    next_number = max(numbers, default=0) + 1
    added, out = 0, []
    for raw in lines:
        text = raw.strip()
        needs = (text and not text.startswith(('#', '<!--', '>')) and not ANCHOR.search(text)
                 and classify(text)[0] in ANCHORED_KINDS)
        if needs:
            raw = raw.rstrip() + f' ^L{next_number:03d}'
            next_number += 1
            added += 1
        out.append(raw)
    if added:
        Path(path).write_text('\n'.join(out) + '\n', encoding='utf-8')
    return added


SHOT_KEYS = {'时长': 'duration', '秒': 'duration', '运镜': 'move', '镜头运动': 'move', '角度': 'angle', '机位': 'angle',
             '转场': 'transition', '舞台': 'stage', '调度': 'stage', '备注': 'note', '标签': 'tags'}


def _transition(value: str) -> str:
    if any(word in value for word in ('省略', '跳', '过了', '之后', '稍后')):
        return '省略'
    if any(word in value for word in ('重置', '新空间', '切到', '另一')):
        return '重置'
    return ''


def _extra_tokens(field: str) -> list[str]:
    """Split an optional field into tags and key=value pairs; values may contain commas."""
    tokens: list[str] = []
    for word in field.split():
        if '=' in word or '＝' in word:
            tokens.append(word)
        elif tokens and ('=' in tokens[-1] or '＝' in tokens[-1]):
            tokens[-1] += ' ' + word
        else:
            tokens += [t for t in re.split(r'\s*[,，、]\s*', word) if t]
    return tokens


def expand_refs(text: str, order: list[str]) -> list[str]:
    refs = []
    for token in re.split(r'[\s,，、;；]+', (text or '').strip()):
        if not token or token in ('-', '—', '无'):
            continue
        span = re.match(r'^(L\d+)\s*[-~～至]\s*(L\d+)$', token)
        if span and span.group(1) in order and span.group(2) in order:
            a, b = order.index(span.group(1)), order.index(span.group(2))
            refs += order[min(a, b):max(a, b) + 1]
        else:
            refs.append(token)
    return refs


def parse_shots(path: Path, episode: Episode, issues: list[Issue]):
    order = [line.anchor for scene in episode.scenes for line in scene.lines if line.anchor]
    current = None
    for lineno, raw in enumerate(read_text(path).splitlines(), 1):
        text = raw.strip()
        where = f'{episode.id}/shots.md:{lineno}'
        if text.startswith('## '):
            current = ShotScene(id=text[3:].split()[0])
            episode.shot_scenes.append(current)
        elif text.startswith('默认') and current is not None:
            pair = split_kv(text)
            for item in re.split(r'[；;]', pair[1] if pair else ''):
                kv = re.split(r'\s*[=＝：:]\s*', item.strip(), maxsplit=1)
                if len(kv) == 2 and kv[0]:
                    current.defaults[kv[0]] = kv[1]
        elif text.startswith(('- ', '* ')) and '|' in text:
            if current is None:
                issues.append(Issue('error', 'SHOT_NO_SCENE', where, '镜头行之前没有「## 场次」标题'))
                continue
            fields = [f.strip() for f in text[2:].split('|')]
            if len(fields) < 5:
                issues.append(Issue('error', 'SHOT_FIELDS', where, '镜头行至少需要 5 栏：镜号 | 景别 | 人物 | 台词行号 | 画面'))
                fields += [''] * (5 - len(fields))
            shot = Shot(id=fields[0], scene=current.id, size=fields[1], who=split_list(fields[2]),
                        lines=expand_refs(fields[3], order), action=fields[4], lineno=lineno)
            for extra in fields[5:]:
                for token in _extra_tokens(extra):
                    kv = re.split(r'\s*[=＝]\s*', token, maxsplit=1)
                    if len(kv) == 2:
                        key = SHOT_KEYS.get(kv[0])
                        if key == 'duration':
                            try:
                                shot.duration = float(re.sub(r'[^\d.]', '', kv[1]))
                            except ValueError:
                                issues.append(Issue('warning', 'SHOT_DURATION', where, f'时长「{kv[1]}」不是数字'))
                        elif key == 'transition':
                            shot.transition = _transition(kv[1])
                        elif key == 'tags':
                            shot.tags += split_list(kv[1])
                        elif key:
                            setattr(shot, key, kv[1])
                        else:
                            issues.append(Issue('info', 'SHOT_KEY', where, f'未知字段「{kv[0]}」已忽略'))
                    elif token in TAGS:
                        shot.tags.append(token)
                    else:
                        shot.note = (shot.note + ' ' + token).strip()
            current.shots.append(shot)


def episode_dirs(root: Path) -> list[Path]:
    base = Path(root) / 'episodes'
    if not base.is_dir():
        return []
    dirs = [p for p in base.iterdir() if p.is_dir() and re.match(r'^EP\d+$', p.name, re.I)]
    return sorted(dirs, key=lambda p: int(re.sub(r'\D', '', p.name)))


def load_project(root: Path) -> Project:
    root = Path(root)
    issues: list[Issue] = []
    series = parse_series(root / 'series.md', issues)
    entities = parse_bible(root / 'bible.md', issues)
    outline = parse_outline(root / 'outline.md', issues)
    episodes = []
    for directory in episode_dirs(root):
        script = directory / 'script.md'
        if not script.is_file():
            issues.append(Issue('warning', 'SCRIPT_MISSING', directory.name, '没有 script.md'))
            continue
        episode = parse_script(script, directory.name.upper(), issues)
        shots = directory / 'shots.md'
        if shots.is_file():
            episode.shots_path = shots
            parse_shots(shots, episode, issues)
        episodes.append(episode)
    return Project(root=root, series=series, entities=entities, outline=outline, episodes=episodes, issues=issues)
