"""Convert a shortdrama-director 1.2.x board.json into the readable v2 project files.

What carries over: entities, scenes, shots, dialogue, camera, transitions, beat tags and
the state changes the ledger understands (holders, wardrobe, injuries, open/closed,
props appearing or vanishing). What is dropped: per-line cut records, full state
snapshots, review lineage, units and grouping prose; v2 derives or no longer needs them.
"""
from __future__ import annotations

import collections
import json
import re
import shutil
from pathlib import Path

from .legacy_vocab import PLACES, VALUES
from .parse import parse_bible
from .resolve import time_key

WARDROBE = ('wardrobe', 'costume', 'outfit', 'clothing', 'dress')
INJURY = ('injury', 'wound', 'face')
HOLDER = ('holder',)
PLACE = ('place', 'position', 'location', 'contact')
OPEN = ('lid', 'open', 'door', 'form')
CROWD_WORDS = ('成员', '们', '众人', '人群', '手下', '小弟', '保镖们', '围观')
TAG_OF_EVENT = {'pressure': '冲突', 'counteraction': '反转', 'immediate_payoff': '爽点', 'payoff': '爽点',
                'key_visual': '高光', 'promised_payoff': '伏笔', 'setup': '伏笔', 'reversal': '反转', 'climax': '高潮'}
STYLE_DROP = ('16:9', '9:16', '横屏', '竖屏', '非血腥', '非性化', '不血腥', '无血腥')
NONE_VALUES = ('none', '', '无', '无人持有', 'null', '?')
META_WORDS = ('宣称', '声明', '不得', '禁止', '非教学', '不演', '不生成', '未证实', '不能当作', '不把', '不宣告', '不新增',
              '独立道具', '母资产', '母图', '沿用旧', '后期替换')
DRESSINGS = ('敷料', '纱布', '绷带', '创可贴', '膏药')


def _unmeta(text: str) -> str:
    """Drop clauses that talk to the author or the tool rather than describe what is seen."""
    text = str(text).replace('BGM', '背景音乐')
    parts = [p for p in re.split(r'[，,；;]', text) if p.strip() and not any(word in p for word in META_WORDS)]
    return '，'.join(p.strip() for p in parts)


def _load(path: Path) -> dict:
    data = json.loads(Path(path).read_text(encoding='utf-8-sig'))
    if 'scenes' not in data and isinstance(data.get('board'), dict):
        board = dict(data['board'])
        board['scenes'] = [data['scene']] if isinstance(data.get('scene'), dict) else []
        return board
    return data


def _say(value, field: str = '') -> str:
    """Translate an old English state code to Chinese where the old vocabulary knows it."""
    text = str(value)
    if field in VALUES and text in VALUES[field]:
        return VALUES[field][text]
    if text in PLACES:
        return PLACES[text]
    return text


def _label(text: str) -> str:
    label = re.sub(r'[\s，。、；：:,.;/\\|*?"<>（）()【】]', '', text)
    return label[:10] or '默认'


def _clean(text: str) -> str:
    return re.sub(r'。{2,}', '。', (text or '').strip()).strip()


def _split_title(title: str):
    match = re.match(r'^(.*?)\s*(EP\d+)\s*[｜|:：\-—]*\s*(.*)$', title or '', re.I)
    if match:
        return match.group(1).strip(' ｜|'), match.group(2).upper(), match.group(3).strip()
    return title or '', '', ''


def _style(style: str):
    parts = [p.strip() for p in re.split(r'[，,；;]', style or '') if p.strip()]
    keep = [p for p in parts if not any(word in p for word in STYLE_DROP)]
    notes = [p for p in parts if any(word in p for word in ('血腥', '性化'))]
    return '，'.join(keep), '；'.join(notes)


def import_board(board_path: Path, root: Path, episode: str = '', keep_durations: bool = False, assets: Path | None = None) -> str:
    board = _load(board_path)
    project = board.get('project', {})
    series_title, title_ep, episode_title = _split_title(project.get('title', ''))
    episode = (episode or title_ep or 'EP01').upper()
    entities = {e['id']: e for e in board.get('entities', [])}
    names = {eid: e.get('name') or eid for eid, e in entities.items()}
    scenes = board.get('scenes', [])
    shots = [shot for scene in scenes for shot in scene.get('shots', [])]
    stats = collections.Counter()
    dropped = collections.Counter()

    # --- looks: every distinct wardrobe value a character has, in order of appearance
    looks: dict[str, dict[str, str]] = collections.defaultdict(dict)
    first_state = scenes[0].get('initial_state', {}) if scenes else {}
    states_in_order = [first_state] + [s for shot in shots for s in (shot.get('start_state', {}), shot.get('end_state', {}))]
    for state in states_in_order:
        for key, value in state.items():
            eid, _, field = key.partition('.')
            if field in WARDROBE and eid in entities and str(value) not in NONE_VALUES:
                text = _say(value, field)
                looks[eid].setdefault(_label(text), text)

    def is_crowd(eid):
        name = names.get(eid, '')
        return entities[eid].get('kind') == 'character' and any(word in name for word in CROWD_WORDS)

    # --- bible.md, as one block per entity so later episodes can append new ones
    blocks: list[tuple[str, str, list[str]]] = []
    for eid, e in entities.items():
        if e.get('kind') == 'character' and not is_crowd(eid):
            lines = [f'- 身份：{_unmeta(_clean(e.get("visual_anchor", "")))}']
            lines += [f'- 造型（{label}）：{text}' for label, text in looks.get(eid, {}).items()]
            if e.get('hard_facts'):
                lines.append(f'- 备注：{"；".join(e["hard_facts"])}')
            blocks.append(('人物', names[eid], lines))
    for eid in entities:
        if is_crowd(eid):
            blocks.append(('群演', names[eid], [f'- 造型：{_unmeta(_clean(entities[eid].get("visual_anchor", "")))}']))
    for eid, e in entities.items():
        if e.get('kind') == 'location':
            blocks.append(('场景', names[eid], [f'- 布局：{_unmeta(_clean(e.get("visual_anchor", "")))}']))
    for eid, e in entities.items():
        if e.get('kind') == 'prop':
            lines = [f'- 外观：{_unmeta(_clean(e.get("visual_anchor", "")))}']
            holder = first_state.get(f'{eid}.holder')
            if holder in entities and entities[holder].get('kind') == 'character' and first_state.get(f'{eid}.mode') != 'worn':
                lines.append(f'- 持有：{names[holder]}')
            if any(word in names[eid] for word in DRESSINGS):
                lines.append('- 参考图：否')
            blocks.append(('道具', names[eid], lines))

    # --- tags from the old dramatic audit
    tags: dict[str, list[str]] = collections.defaultdict(list)
    for beat in board.get('beats', []):
        for event in (beat.get('drama') or {}).get('events', []):
            tag = TAG_OF_EVENT.get(event.get('kind'))
            if tag and event.get('shot_id'):
                tags[event['shot_id']].append(tag)
    design = board.get('story_design') or {}
    opening = ((design.get('opening') or {}).get('candidates') or [{}])[0]
    beat_first_shot = {}
    for shot in shots:
        for beat_id in shot.get('beat_ids', []):
            beat_first_shot.setdefault(beat_id, shot['id'])
    if opening.get('beat_id') in beat_first_shot:
        tags[beat_first_shot[opening['beat_id']]].insert(0, '钩子')
    elif shots:
        tags[shots[0]['id']].insert(0, '钩子')
    for shot_id in ((design.get('ending') or {}).get('shot_ids') or [shots[-1]['id']] if shots else []):
        tags[shot_id].append('卡点')

    # --- script.md and shots.md
    script = [f'# {episode} {episode_title}'.rstrip(), '']
    shot_lines = [f'# {episode} 分镜', '']
    counter = [0]

    def anchor():
        counter[0] += 1
        return f'^L{counter[0]:03d}'

    def state_lines(before: dict, after: dict, offscreen: bool) -> list[str]:
        out = []
        note = '（画外）' if offscreen else ''
        for key in after:
            if before.get(key) == after.get(key):
                continue
            eid, _, field = key.partition('.')
            if eid not in entities:
                continue
            who, new = names[eid], after[key]
            kind = entities[eid].get('kind')
            if kind == 'prop' and field in HOLDER:
                place = next((after.get(f'{eid}.{f}') for f in PLACE if after.get(f'{eid}.{f}')), '')
                place = _say(place, 'place') if place else ''
                verb = '戴上' if after.get(f'{eid}.mode') == 'worn' else '拿起'
                if new in entities and entities[new].get('kind') == 'character':
                    out.append(f'【状态】{names[new]} {verb} {who}' + (f'：{place}' if place and place not in NONE_VALUES else '') + note)
                elif str(new) in NONE_VALUES:
                    out.append(f'【状态】{who} 放在：{place or "原处"}{note}')
                else:
                    out.append(f'【备注】{who}持有：{_say(new)}')
                stats['state_converted'] += 1
            elif kind == 'character' and field in WARDROBE and str(new) not in NONE_VALUES:
                out.append(f'【状态】{who} 换上 {_label(_say(new, field))}{note}')
                stats['state_converted'] += 1
            elif kind == 'character' and field in INJURY:
                if str(new) in NONE_VALUES or '痊愈' in str(new):
                    out.append(f'【状态】{who} 痊愈：伤情{note}')
                elif _unmeta(_say(new, field)):
                    out.append(f'【状态】{who} 受伤：伤情（{_unmeta(_say(new, field))}）{note}')
                stats['state_converted'] += 1
            elif kind == 'prop' and field in OPEN and str(new) in ('open', 'opened', '开启', '打开', '开'):
                out.append(f'【状态】{who} 打开{note}')
                stats['state_converted'] += 1
            elif kind == 'prop' and field in OPEN and str(new) in ('closed', '关闭', '合上', '关'):
                out.append(f'【状态】{who} 关上{note}')
                stats['state_converted'] += 1
            elif kind == 'prop' and field == 'count' and str(new) in ('0', 'absent'):
                out.append(f'【状态】{who} 消失{note}')
                stats['state_converted'] += 1
            else:
                dropped[field] += 1
        return out

    previous_end = dict(first_state)
    first_scene = True
    previous_time = '日'
    for number, scene in enumerate(scenes, 1):
        location = names.get(scene.get('location_id'), scene.get('location_id', ''))
        time_text = scene.get('time_domain', '')
        key = time_key(time_text)
        if key == time_text and key not in ('日', '夜', '晨', '黄昏'):
            key = previous_time
        previous_time = key
        script.append(f'## 场{number} {location} · {key}')
        if time_text and time_text != key:
            script.append(f'【备注】时间：{time_text}')
        if scene.get('space'):
            script.append(f'【备注】空间：{_clean(scene["space"])}')
        initial = scene.get('initial_state', {})
        if first_scene:
            for key, value in initial.items():
                eid, _, field = key.partition('.')
                if eid in entities and entities[eid].get('kind') == 'character' and field in INJURY and str(value) not in NONE_VALUES:
                    script.append(f'【状态】{names[eid]} 受伤：伤情（{_unmeta(_say(value, field))}）（画外）')
                    stats['state_converted'] += 1
                elif eid in entities and entities[eid].get('kind') == 'prop' and field == 'holder' and value in entities \
                        and initial.get(f'{eid}.mode') == 'worn':
                    contact = initial.get(f'{eid}.contact') or initial.get(f'{eid}.place') or ''
                    script.append(f'【状态】{names[value]} 戴上 {names[eid]}' + (f'：{_say(contact, "contact")}' if contact else '') + '（画外）')
                    stats['state_converted'] += 1
            first_scene = False
        else:
            script += state_lines(previous_end, initial, offscreen=True)
        lighting = collections.Counter(_unmeta(_clean(s.get('lighting', ''))) for s in scene.get('shots', []) if s.get('lighting'))
        sound = collections.Counter(_unmeta(_clean(s.get('sound', ''))) for s in scene.get('shots', []) if s.get('sound'))
        defaults = []
        if lighting:
            defaults.append(f'光线={lighting.most_common(1)[0][0].rstrip("。")}')
        if sound:
            defaults.append(f'声音={sound.most_common(1)[0][0].rstrip("。")}')
        shot_lines += [f'## 场{number}', '默认：' + '；'.join(defaults) if defaults else '', '']
        last_visual = None
        previous_end = dict(initial) if initial else previous_end
        for index, shot in enumerate(scene.get('shots', [])):
            refs = []
            transition = (shot.get('transition_in') or {})
            if index > 0 and transition.get('kind') in ('ellipsis', 'reset'):
                script.append('【时间跳转】稍后')
                if transition.get('reason'):
                    script.append(f'【备注】跳转：{_clean(transition["reason"])}')
            start = shot.get('start_state', {})
            script += state_lines(previous_end, start, offscreen=True)
            visual = _unmeta(_clean(shot.get('visual') or shot.get('intent') or ''))
            if visual and visual != last_visual:
                mark = anchor()
                script.append(f'【画面】{visual} {mark}')
                refs.append(mark[1:])
                last_visual = visual
            for line in shot.get('dialogue', []):
                speaker = names.get(line.get('speaker_id'), line.get('speaker_id', '旁白'))
                mark = anchor()
                script.append(f'{speaker}：{_clean(line.get("text", ""))} {mark}')
                refs.append(mark[1:])
                stats['dialogue'] += 1
            script += state_lines(start, shot.get('end_state', {}), offscreen=False)
            previous_end = shot.get('end_state', start)
            camera = shot.get('camera') or {}
            who = [names[e] for e in shot.get('visible_entities', []) if e in entities and entities[e].get('kind') != 'location']
            extras = list(dict.fromkeys(tags.get(shot['id'], [])))
            composition = _clean(camera.get('composition', ''))
            if composition and composition != visual and len(composition) <= 40:
                extras.append(f'舞台={composition.rstrip("。")}')
            if camera.get('angle') and camera['angle'] not in ('平视', 'eye-level', 'eye level'):
                extras.append(f'角度={camera["angle"]}')
            if camera.get('movement') and camera['movement'] not in ('固定', 'static'):
                extras.append(f'运镜={camera["movement"]}')
            if keep_durations and shot.get('duration_ms'):
                extras.append(f'时长={shot["duration_ms"] / 1000:g}')
            fields = [shot['id'], camera.get('size', ''), '、'.join(who) or '—', ','.join(refs) or '—',
                      (visual or '—').rstrip('。').replace('|', '／')] + extras
            shot_lines.append('- ' + ' | '.join(fields))
            stats['shots'] += 1
        script.append('')
        shot_lines.append('')

    # --- series.md and outline.md
    style, content = _style(project.get('style', ''))
    series = ['# 系列设定', '', f'- 片名：{series_title or project.get("title", "")}',
              f'- 格式：{"横屏剧集" if project.get("aspect_ratio", "16:9") == "16:9" else "竖屏短剧"}',
              '- 模型：seedance-2.0', f'- 画风：{style}', '- 人脸：待测试',
              f'- 语速：{project.get("zh_chars_per_second") or 5}',
              f'- 旁白：{"有" if project.get("voiceover") else "无"}',
              f'- 字幕：{"有" if project.get("subtitles") else "无"}',
              f'- 背景音乐：{"有" if project.get("music_in_generation") else "无"}']
    if content:
        series.append(f'- 内容尺度：{content}')
    outline = ['# 大纲', '', f'## {episode} {episode_title}'.rstrip()]
    if opening.get('hook'):
        outline.append(f'- 钩子：{opening["hook"]}')
    for beat in board.get('beats', []):
        if beat.get('summary'):
            outline.append(f'- 推进：{beat["summary"]}')
    ending = design.get('ending') or {}
    if ending.get('next_step') or ending.get('effect'):
        outline.append(f'- 卡点：{ending.get("next_step") or ending.get("effect")}')
    if project.get('directing_intent'):
        outline.append(f'- 导演意图：{project["directing_intent"]}')
    for sub in board.get('subplots', []):
        outline.append(f'- 支线：{sub.get("name", "")}（{sub.get("decision", "")}；{sub.get("due", "")}）')

    # --- write
    root = Path(root)
    folder = root / 'episodes' / episode
    folder.mkdir(parents=True, exist_ok=True)
    (root / 'assets' / 'images').mkdir(parents=True, exist_ok=True)
    for path, lines in ((root / 'series.md', series), (root / 'outline.md', outline)):
        if not path.exists():
            path.write_text('\n'.join(lines).rstrip() + '\n', encoding='utf-8')
    bible_path = root / 'bible.md'
    known = set(parse_bible(bible_path, []).keys()) if bible_path.exists() else set()
    fresh = [block for block in blocks if block[1] not in known]
    if fresh:
        out = [bible_path.read_text(encoding='utf-8').rstrip(), ''] if bible_path.exists() else []
        for heading in ('人物', '群演', '场景', '道具'):
            group = [block for block in fresh if block[0] == heading]
            if group:
                out += [f'# {heading}', '']
                for _, name, lines in group:
                    out += [f'## {name}', *lines, '']
        bible_path.write_text('\n'.join(out).rstrip() + '\n', encoding='utf-8')
        stats['bible_added'] = len(fresh)
    (folder / 'script.md').write_text('\n'.join(script).rstrip() + '\n', encoding='utf-8')
    (folder / 'shots.md').write_text('\n'.join(l for l in shot_lines).rstrip() + '\n', encoding='utf-8')
    legacy = root / 'legacy' / episode
    legacy.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(board_path, legacy / Path(board_path).name)
    if assets and Path(assets).is_file():
        shutil.copyfile(assets, legacy / Path(assets).name)
    report = [f'# {episode} 旧版转换说明', '',
              f'- 来源：{Path(board_path).name}（shortdrama-director 1.2.x）',
              f'- 场次 {len(scenes)} · 镜头 {stats["shots"]} · 台词 {stats["dialogue"]} · 转成【状态】的变化 {stats["state_converted"]}'
              f' · bible.md 新增 {stats["bible_added"]} 条',
              f'- 未转换（v2 自动推导或不再需要）：逐行删改记录 {len(board.get("cuts", []))} 条、完整状态快照、旧生成单元 '
              f'{sum(len(s.get("units", [])) for s in scenes)} 个及分组说明、审查记录',
              '- 旧版每镜时长' + ('已保留（时长=）' if keep_durations else '未保留，改按台词和动作重新估算；要保留请加 --keep-durations'),
              '- 时间跳转的原因和场景空间说明保留为【备注】，不会进入提示词',
              '- 角色造型取自旧状态里的服装值；只有一个造型的人物用旧的外观描述']
    if dropped:
        report.append('- 没有对应 v2 状态的旧字段（多为站位、姿态和表演，应写在画面动作里）：'
                      + '、'.join(f'{field}×{count}' for field, count in dropped.most_common()))
    report.append('')
    (legacy / 'conversion.md').write_text('\n'.join(report), encoding='utf-8')
    return '\n'.join(report)
