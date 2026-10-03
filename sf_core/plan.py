"""Turn an authored episode into units, references, prompts, reports and a request kit."""
from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
from pathlib import Path

from . import VERSION
from .checks import check_carryover, check_format, check_script, check_shots
from .ledger import Replay, appearance, replay
from .lint import author_words, lint_prompt
from .model import Episode, Issue, Project, ShotPlan, UnitPlan
from .pack import gen_seconds, pack_scene, segment_bounds
from .render import render_unit
from .resolve import bind, candidates
from .timing import SPOKEN, shot_seconds
from .textfmt import spoken_chars


@dataclass
class EpisodePlan:
    episode: Episode
    shots: list[ShotPlan] = field(default_factory=list)
    units: list[UnitPlan] = field(default_factory=list)
    issues: list[Issue] = field(default_factory=list)
    metrics: dict = field(default_factory=dict)


def _shot_plans(project: Project, episode: Episode, rp: Replay, issues: list[Issue]) -> dict[str, list[ShotPlan]]:
    index = episode.line_index()
    by_scene: dict[str, list[ShotPlan]] = {}
    for shot_scene in episode.shot_scenes:
        scene = episode.scene(shot_scene.id)
        if not scene:
            continue
        position = {line.anchor: i for i, line in enumerate(scene.lines) if line.anchor}
        jumps = [(i, line.text) for i, line in enumerate(scene.lines) if line.kind == 'jump']
        world = rp.scene_start.get((episode.id, scene.id), {})
        last_index = -1
        plans = []
        for shot in shot_scene.shots:
            lines = [index[a] for a in shot.lines if a in index]
            ordered = sorted((l for l in lines if l.anchor in position), key=lambda l: position[l.anchor])
            if not shot.action:
                shot.action = '；'.join(l.text for l in ordered if l.kind == 'action')
            plan = ShotPlan(shot=shot, lines=[l for l in lines if l.kind in SPOKEN],
                            duration=shot_seconds(shot, lines, project.series))
            if ordered:
                first, last = position[ordered[0].anchor], position[ordered[-1].anchor]
                plan.world_start = rp.before.get((episode.id, ordered[0].anchor), world)
                plan.world_end = rp.after.get((episode.id, ordered[-1].anchor), plan.world_start)
                between = [text for i, text in jumps if last_index < i < first]
                if between:
                    plan.jump = between[-1]
                    shot.transition = shot.transition or '省略'
                last_index = max(last_index, last)
            else:
                plan.world_start = plan.world_end = world
            world = plan.world_end
            plans.append(plan)
        by_scene[scene.id] = plans
    return by_scene


def build_episode(project: Project, episode: Episode, rp: Replay) -> EpisodePlan:
    result = EpisodePlan(episode=episode)
    issues = result.issues
    issues += check_script(project, episode) + check_shots(project, episode)
    issues += check_carryover(project, episode, rp.scene_start)
    issues += [i for i in project.issues if i.where.startswith(episode.id + '/')]
    by_scene = _shot_plans(project, episode, rp, issues)
    cap = project.series.cap
    clock = 0.0
    for shot_scene in episode.shot_scenes:
        for plan in by_scene.get(shot_scene.id, []):
            plan.start = round(clock, 1)
            clock += plan.duration
            result.shots.append(plan)
    allowed = author_words(project.series.style, *(e.identity + ' ' + ' '.join(e.looks.values()) + ' ' + e.name
                                                     for e in project.entities.values()),
                           *(line.text for scene in episode.scenes for line in scene.lines),
                           *(s.action + ' ' + s.size + ' ' + s.move + ' ' + s.stage for s in episode.all_shots()),
                           *(' '.join(ss.defaults.values()) for ss in episode.shot_scenes))
    for scene_number, scene in enumerate(episode.scenes, 1):
        plans = by_scene.get(scene.id)
        if not plans:
            continue
        shot_scene = next(s for s in episode.shot_scenes if s.id == scene.id)

        def valid(start, end, plans=plans):
            base = plans[start].world_start
            for m in range(start + 1, end):
                if plans[m].shot.transition in ('省略', '重置'):
                    return False
                for name in plans[m].shot.who:
                    entity = project.lookup(name)
                    if entity and entity.kind in ('character', 'crowd') and \
                            appearance(plans[m].world_start, entity.name) != appearance(base, entity.name):
                        return False
            return True

        spans = pack_scene([p.duration for p in plans], cap,
                           lambda a, b, plans=plans: len(candidates(plans[a:b], scene, project)), valid)
        for k, (a, b) in enumerate(spans, 1):
            unit_plans = plans[a:b]
            unit = UnitPlan(id=f'U{scene_number:02d}-{k}', scene=scene, defaults=shot_scene.defaults,
                            shots=unit_plans, gen_seconds=gen_seconds(sum(p.duration for p in unit_plans), cap))
            if unit.gen_seconds > cap['unit_seconds'][1]:
                issues.append(Issue('error', 'UNIT_TOO_LONG', unit.id,
                                    f'{unit_plans[0].shot.id} 单镜就要 {unit.gen_seconds} 秒，超过模型上限 {cap["unit_seconds"][1]} 秒；拆成两镜'))
            unit.references, unit.text_only = bind(unit_plans, scene, project)
            if unit.text_only:
                issues.append(Issue('info', 'REF_TEXT_ONLY', unit.id,
                                    f'参考图名额已满，这些只用文字描述：{"、".join(unit.text_only)}'))
            unit.segments = segment_bounds([p.duration for p in unit_plans], unit.gen_seconds)
            unit.prompt = render_unit(unit, project)
            issues += lint_prompt(unit.prompt, unit.id, cap, allowed)
            result.units.append(unit)
    issues += check_format(project, episode, result.shots)
    result.metrics = metrics(project, result)
    return result


def metrics(project: Project, plan: EpisodePlan) -> dict:
    shots, units = plan.shots, plan.units
    total = round(sum(p.duration for p in shots), 1)
    histogram: dict[int, int] = {}
    for p in shots:
        histogram[int(p.duration)] = histogram.get(int(p.duration), 0) + 1
    spoken = [line for p in shots for line in p.lines]
    prompt_sizes = [len(u.prompt) for u in units]
    return {
        'edit_seconds': total,
        'shots': len(shots),
        'asl_seconds': round(total / len(shots), 2) if shots else 0,
        'shots_under_3s': sum(1 for p in shots if p.duration < 3),
        'shot_seconds_histogram': dict(sorted(histogram.items())),
        'units': len(units),
        'gen_seconds': sum(u.gen_seconds for u in units),
        'single_shot_units': sum(1 for u in units if len(u.shots) == 1),
        'shots_per_unit': round(len(shots) / len(units), 2) if units else 0,
        'references_per_unit': round(sum(len(u.references) for u in units) / len(units), 2) if units else 0,
        'reference_images_missing': sum(1 for u in units for r in u.references if not r.file),
        'spoken_lines': len(spoken),
        'spoken_chars': int(sum(spoken_chars(line.text) for line in spoken)),
        'prompt_chars_mean': round(sum(prompt_sizes) / len(prompt_sizes)) if prompt_sizes else 0,
        'prompt_chars_max': max(prompt_sizes, default=0),
        'errors': sum(1 for i in plan.issues if i.level == 'error'),
        'warnings': sum(1 for i in plan.issues if i.level == 'warning'),
    }


def plan_project(project: Project, episode_ids=None) -> list[EpisodePlan]:
    rp = replay(project)
    wanted = {e.upper() for e in episode_ids} if episode_ids else None
    plans = []
    for episode in project.episodes:
        if wanted and episode.id not in wanted:
            continue
        plans.append(build_episode(project, episode, rp))
    return plans


def _clock(seconds: float) -> str:
    return f'{int(seconds // 60)}:{seconds % 60:04.1f}'


def storyboard_markdown(project: Project, plan: EpisodePlan) -> str:
    m = plan.metrics
    episode = plan.episode
    out = [f'# {episode.id} {episode.title}'.rstrip() + ' 分镜表',
           '',
           '> 由 `sf plan` 生成。要改内容，请改 script.md / shots.md 后重新生成，不要手改本文件。',
           '',
           f'约 {m["edit_seconds"]:.0f} 秒 · {m["shots"]} 镜 · 平均镜长 {m["asl_seconds"]} 秒 · '
           f'{m["units"]} 个生成请求，共 {m["gen_seconds"]} 秒',
           '']
    unit_of = {p.shot.id: u for u in plan.units for p in u.shots}
    for scene in episode.scenes:
        rows = [p for p in plan.shots if p.shot.scene == scene.id]
        if not rows:
            continue
        out += [f'## {scene.heading}', '', '| 请求 | 时间 | 镜 | 景别 | 人物 | 画面 | 台词 | 标记 |', '|---|---|---|---|---|---|---|---|']
        for p in rows:
            unit = unit_of.get(p.shot.id)
            label = f'{unit.id}（{unit.gen_seconds}秒）' if unit and unit.shots[0] is p else ''
            speech = ' / '.join(f'{(l.speaker or "旁白")}：{l.text}' for l in p.lines)
            cells = [label, f'{_clock(p.start)}–{_clock(p.start + p.duration)}', p.shot.id, p.shot.size,
                     '、'.join(p.shot.who), p.shot.action, speech, '、'.join(p.shot.tags)]
            out.append('| ' + ' | '.join(c.replace('|', '／').replace('\n', ' ') for c in cells) + ' |')
        out.append('')
    out += ['## 参考图', '', '| 请求 | 图片 | 对应 | 文件 |', '|---|---|---|---|']
    for unit in plan.units:
        for ref in unit.references:
            out.append(f'| {unit.id} | 图片{ref.slot} | {ref.entity}／{ref.variant} | {ref.file or "缺图：assets/images/" + ref.entity + "/" + ref.variant + ".png"} |')
    out.append('')
    return '\n'.join(out)


def report_markdown(project: Project, plan: EpisodePlan) -> str:
    m = plan.metrics
    fmt = project.series.fmt
    out = [f'# {plan.episode.id} 检查报告', '',
           f'格式：{project.series.format_name}（{fmt.get("aspect")}，每集 {fmt.get("episode_seconds")} 秒，平均镜长 {fmt.get("asl_seconds")} 秒）'
           f' · 模型：{project.series.cap.get("label", project.series.model)}', '',
           '| 指标 | 数值 |', '|---|---|']
    labels = {'edit_seconds': '成片时长（秒）', 'shots': '镜头数', 'asl_seconds': '平均镜长（秒）', 'shots_under_3s': '3 秒以下镜头',
              'shot_seconds_histogram': '镜长分布（秒: 镜数）', 'units': '生成请求数', 'gen_seconds': '生成总秒数',
              'single_shot_units': '单镜请求', 'shots_per_unit': '每请求镜数', 'references_per_unit': '每请求参考图',
              'reference_images_missing': '缺少的参考图', 'spoken_lines': '台词句数', 'spoken_chars': '台词字数',
              'prompt_chars_mean': '提示词平均字数', 'prompt_chars_max': '提示词最长字数', 'errors': '错误', 'warnings': '警告'}
    for key, label in labels.items():
        out.append(f'| {label} | {json.dumps(m.get(key), ensure_ascii=False)} |')
    for level, title in (('error', '错误（会导致请求无效）'), ('warning', '建议处理'), ('info', '提示')):
        rows = [i for i in plan.issues if i.level == level]
        if rows:
            out += ['', f'## {title}', '']
            out += [f'- `{i.code}` {i.where}：{i.message}' for i in rows]
    out.append('')
    return '\n'.join(out)


def requests_json(project: Project, plan: EpisodePlan) -> list[dict]:
    cap = project.series.cap
    cli = cap.get('cli', {})
    ratio = project.series.fmt.get('aspect', '16:9')
    rows = []
    for unit in plan.units:
        images = [ref.file for ref in unit.references]
        command = [cli.get('executable', 'dreamina'), cli.get('video_command', 'multimodal2video')]
        for ref in unit.references:
            command += ['--image', ref.file or f'assets/images/{ref.entity}/{ref.variant}.png']
        command += ['--prompt', unit.prompt.strip(), '--duration', str(unit.gen_seconds), '--ratio', ratio,
                    '--video_resolution', cli.get('video_resolution', '720p'), '--model_version', cli.get('model_version', 'seedance2.0fast')]
        rows.append({'unit': unit.id, 'scene': unit.scene.id, 'shots': [p.shot.id for p in unit.shots],
                     'seconds': unit.gen_seconds, 'ratio': ratio, 'prompt_file': f'prompts/{unit.id}.txt',
                     'images': images, 'missing_images': [f'{r.entity}/{r.variant}' for r in unit.references if not r.file],
                     'ready': all(images) and not any(i.level == 'error' and i.where == unit.id for i in plan.issues),
                     'command': command})
    return rows


def plan_json(project: Project, plan: EpisodePlan) -> dict:
    return {
        'sf_core': VERSION,
        'format': project.series.format_name,
        'model': project.series.model,
        'episode': plan.episode.id,
        'metrics': plan.metrics,
        'shots': [{'id': p.shot.id, 'scene': p.shot.scene, 'start': p.start, 'duration': p.duration,
                   'lines': p.shot.lines, 'tags': p.shot.tags} for p in plan.shots],
        'units': [{'id': u.id, 'scene': u.scene.id, 'shots': [p.shot.id for p in u.shots], 'gen_seconds': u.gen_seconds,
                   'edit_seconds': u.edit_seconds, 'segments': [list(s) for s in u.segments],
                   'references': [{'slot': r.slot, 'entity': r.entity, 'kind': r.kind, 'variant': r.variant,
                                   'file': r.file or None, 'sha256': r.sha256 or None} for r in u.references],
                   'text_only': u.text_only, 'prompt_file': f'prompts/{u.id}.txt',
                   'prompt_sha256': hashlib.sha256(u.prompt.encode('utf-8')).hexdigest(), 'prompt_chars': len(u.prompt)}
                  for u in plan.units],
        'issues': [i.as_dict() for i in plan.issues],
    }


def write_episode(project: Project, plan: EpisodePlan) -> Path:
    out = project.root / 'derived' / plan.episode.id
    prompts = out / 'prompts'
    prompts.mkdir(parents=True, exist_ok=True)
    keep = {f'{u.id}.txt' for u in plan.units}
    for stale in prompts.glob('*.txt'):
        if stale.name not in keep:
            stale.unlink()
    for unit in plan.units:
        path = prompts / f'{unit.id}.txt'
        if not path.is_file() or path.read_text(encoding='utf-8') != unit.prompt:
            path.write_text(unit.prompt, encoding='utf-8')
    (out / 'plan.json').write_text(json.dumps(plan_json(project, plan), ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    (out / 'requests.json').write_text(json.dumps(requests_json(project, plan), ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    (out / 'storyboard.md').write_text(storyboard_markdown(project, plan), encoding='utf-8')
    (out / 'report.md').write_text(report_markdown(project, plan), encoding='utf-8')
    return out
