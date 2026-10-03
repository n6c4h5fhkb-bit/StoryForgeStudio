"""Advisory checks. They report; they never stop a file from being saved or planned."""
from __future__ import annotations

from .model import TAGS, TURN_TAGS, Episode, Issue, Project, ShotPlan
from .textfmt import spoken_chars

SPOKEN = ('speech', 'inner', 'narration')


def check_script(project: Project, episode: Episode) -> list[Issue]:
    issues = []
    for scene in episode.scenes:
        where = f'{episode.id}/script.md:{scene.lineno}'
        if scene.location and not project.lookup(scene.location):
            issues.append(Issue('warning', 'LOCATION_UNKNOWN', where, f'场景「{scene.location}」不在 bible.md 的场景表'))
        if not scene.location:
            issues.append(Issue('warning', 'LOCATION_MISSING', where, f'{scene.id} 的标题没写地点（## 场1 地点 · 时间）'))
        for line in scene.lines:
            at = f'{episode.id}/script.md:{line.lineno}'
            if line.kind in SPOKEN and not line.anchor:
                issues.append(Issue('warning', 'ANCHOR_MISSING', at, '这句还没有行号；运行 sf ids 自动补上'))
            if line.kind in ('speech', 'inner') and not project.lookup(line.speaker):
                issues.append(Issue('warning', 'SPEAKER_UNKNOWN', at, f'说话人「{line.speaker}」不在 bible.md'))
            if line.kind in SPOKEN and spoken_chars(line.text) > 40:
                issues.append(Issue('info', 'LONG_LINE', at, f'这句台词约 {int(spoken_chars(line.text))} 字，短剧里通常拆成两句或两镜'))
    return issues


def check_shots(project: Project, episode: Episode) -> list[Issue]:
    issues = []
    if not episode.shot_scenes:
        issues.append(Issue('warning', 'SHOTS_MISSING', f'{episode.id}/shots.md', '还没有分镜（shots.md），无法生成请求'))
        return issues
    index = episode.line_index()
    order = [line.anchor for scene in episode.scenes for line in scene.lines if line.anchor]
    covered: dict[str, list[str]] = {}
    seen_ids = set()
    for shot_scene in episode.shot_scenes:
        scene = episode.scene(shot_scene.id)
        if not scene:
            issues.append(Issue('error', 'SHOT_SCENE_UNKNOWN', f'{episode.id}/shots.md', f'分镜里的「{shot_scene.id}」在 script.md 没有对应场次'))
            continue
        last_position = -1
        for shot in shot_scene.shots:
            where = f'{episode.id}/shots.md:{shot.lineno} {shot.id}'
            if shot.id in seen_ids:
                issues.append(Issue('error', 'SHOT_ID_DUPLICATE', where, f'镜号 {shot.id} 重复'))
            seen_ids.add(shot.id)
            for name in shot.who:
                if not project.lookup(name):
                    issues.append(Issue('warning', 'WHO_UNKNOWN', where, f'「{name}」不在 bible.md'))
            for anchor in shot.lines:
                line = index.get(anchor)
                if not line:
                    issues.append(Issue('error', 'SHOT_LINE_UNKNOWN', where, f'行号 {anchor} 在 script.md 里不存在'))
                    continue
                if line.scene != shot_scene.id:
                    issues.append(Issue('warning', 'SHOT_LINE_SCENE', where, f'{anchor} 属于 {line.scene}，不在 {shot_scene.id}'))
                covered.setdefault(anchor, []).append(shot.id)
                position = order.index(anchor)
                if position < last_position:
                    issues.append(Issue('info', 'LINE_ORDER', where, f'{anchor} 早于前一镜的台词；如果是倒叙或插叙可以忽略'))
                last_position = max(last_position, position)
            if not shot.action and not shot.lines:
                issues.append(Issue('warning', 'SHOT_EMPTY', where, '这一镜既没有画面也没有台词'))
    for scene in episode.scenes:
        for line in scene.lines:
            if line.kind in SPOKEN and line.anchor and line.anchor not in covered:
                issues.append(Issue('warning', 'LINE_UNCOVERED', f'{episode.id}/script.md:{line.lineno}',
                                    f'{line.anchor}「{line.text[:16]}」没有分到任何镜头'))
    for anchor, shots in covered.items():
        if len(shots) > 1 and index.get(anchor) and index[anchor].kind in SPOKEN:
            issues.append(Issue('warning', 'LINE_DUPLICATE', f'{episode.id}/shots.md', f'{anchor} 同时出现在 {"、".join(shots)}'))
    return issues


def check_format(project: Project, episode: Episode, plans: list[ShotPlan]) -> list[Issue]:
    issues = []
    fmt = project.series.fmt
    if not plans:
        return issues
    where = f'{episode.id}'
    total = round(sum(p.duration for p in plans), 1)
    low, high = fmt.get('episode_seconds', [0, 10 ** 6])
    if not low <= total <= high:
        issues.append(Issue('warning', 'EP_LENGTH', where, f'本集约 {total:.0f} 秒，{project.series.format_name}建议 {low}–{high} 秒'))
    asl = total / len(plans)
    a_low, a_high = fmt.get('asl_seconds', [0, 10 ** 6])
    if not a_low <= asl <= a_high:
        issues.append(Issue('warning', 'ASL', where, f'平均镜长 {asl:.1f} 秒，建议 {a_low}–{a_high} 秒'))
    longest = fmt.get('max_shot_seconds', 10 ** 6)
    for p in plans:
        if p.duration > longest:
            issues.append(Issue('warning', 'SHOT_LONG', f'{episode.id} {p.shot.id}', f'{p.shot.id} 约 {p.duration} 秒，超过 {longest} 秒；拆镜或加反应镜头'))
    tagged = [(p.start, p.start + p.duration, tag, p.shot.id) for p in plans for tag in p.shot.tags if tag in TAGS]
    hooks = [t for t in tagged if t[2] == '钩子']
    if not hooks:
        issues.append(Issue('warning', 'HOOK_MISSING', where, '没有标「钩子」的镜头；开场钩子是留存的第一道门'))
    elif hooks[0][0] > fmt.get('hook_seconds', 7):
        issues.append(Issue('warning', 'HOOK_LATE', where, f'第一个钩子在 {hooks[0][0]:.0f} 秒（{hooks[0][3]}），建议 {fmt.get("hook_seconds")} 秒内'))
    turns = [t for t in tagged if t[2] in TURN_TAGS]
    if not turns or turns[0][0] > fmt.get('first_turn_seconds', 20):
        when = f'在 {turns[0][0]:.0f} 秒' if turns else '没有标出'
        issues.append(Issue('warning', 'TURN_LATE', where, f'第一个冲突/反转/爽点{when}，建议 {fmt.get("first_turn_seconds")} 秒内'))
    beats = sorted(t[0] for t in tagged if t[2] != '伏笔')
    gap_limit = fmt.get('max_beat_gap_seconds', 30)
    points = [0.0] + beats + [total]
    for a, b in zip(points, points[1:]):
        if b - a > gap_limit:
            issues.append(Issue('warning', 'BEAT_GAP', where, f'{a:.0f}–{b:.0f} 秒之间 {b - a:.0f} 秒没有标记的戏剧节点（钩子/冲突/反转/爽点），建议不超过 {gap_limit} 秒'))
    cliffs = [t for t in tagged if t[2] == '卡点']
    if not cliffs or cliffs[-1][1] < total - fmt.get('cliff_window_seconds', 20):
        issues.append(Issue('warning', 'CLIFF_MISSING', where, '结尾没有标「卡点」的镜头；每集要留下一个让人点下一集的问题'))
    return issues


def check_carryover(project: Project, episode: Episode, scene_start: dict) -> list[Issue]:
    """Flag props that the ledger still puts in someone's hand when a scene never mentions them."""
    issues = []
    for scene in episode.scenes:
        world = scene_start.get((episode.id, scene.id))
        if not world:
            continue
        text = ' '.join(line.text for line in scene.lines)
        shots = [s for ss in episode.shot_scenes if ss.id == scene.id for s in ss.shots]
        text += ' ' + ' '.join(s.action + ' ' + ' '.join(s.who) for s in shots)
        for prop, state in world['props'].items():
            holder = state.get('holder')
            if not holder or state.get('mode') != 'hand' or not state.get('exists'):
                continue
            entity = project.entities.get(prop)
            names = entity.names() if entity else [prop]
            if holder in text and not any(name in text for name in names):
                issues.append(Issue('info', 'HELD_CARRYOVER', f'{episode.id}/script.md:{scene.lineno}',
                                    f'进入{scene.id}时，按之前的状态{holder}手里还拿着{prop}；如果已经放下，'
                                    f'在前面补一行「【状态】{holder} 放下 {prop}：地点」'))
    return issues
