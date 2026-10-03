"""Command line for authors and agents: sf <command> <project> [episodes...]."""
from __future__ import annotations

import argparse
import json
import shutil
import sys
from pathlib import Path

from . import VERSION
from .assets import write_assets
from .parse import assign_ids, episode_dirs, load_project
from .plan import plan_project, report_markdown, storyboard_markdown, write_episode

TEMPLATES = Path(__file__).resolve().parent / 'templates'
LEVEL = {'error': '错误', 'warning': '警告', 'info': '提示'}


def _print(text: str = ''):
    sys.stdout.write(text + '\n')


def _summary(plan, limit: int):
    m = plan.metrics
    _print(f'{plan.episode.id}：约 {m["edit_seconds"]:.0f} 秒 · {m["shots"]} 镜 · 平均镜长 {m["asl_seconds"]} 秒 · '
           f'{m["units"]} 个生成请求（共 {m["gen_seconds"]} 秒） · 提示词平均 {m["prompt_chars_mean"]} 字')
    counts = {level: sum(1 for i in plan.issues if i.level == level) for level in LEVEL}
    _print(f'  错误 {counts["error"]} · 警告 {counts["warning"]} · 提示 {counts["info"]}（全文见 derived/{plan.episode.id}/report.md）')
    shown = [i for i in plan.issues if i.level != 'info'][:limit]
    for issue in shown:
        _print(f'  - [{LEVEL[issue.level]}] {issue.code} {issue.where}：{issue.message}')
    hidden = counts['error'] + counts['warning'] - len(shown)
    if hidden > 0:
        _print(f'  ……另有 {hidden} 条，见报告')


def _project_issues(project):
    for issue in project.issues:
        if not issue.where.startswith('EP'):
            _print(f'[{LEVEL[issue.level]}] {issue.code} {issue.where}：{issue.message}')


def cmd_init(args):
    root = Path(args.project)
    root.mkdir(parents=True, exist_ok=True)
    created = []
    for name in ('series.md', 'bible.md', 'outline.md'):
        target = root / name
        if not target.exists():
            text = (TEMPLATES / name).read_text(encoding='utf-8')
            if name == 'series.md':
                text = text.replace('- 片名：', f'- 片名：{args.title or ""}').replace('- 格式：横屏剧集', f'- 格式：{args.format}')
            target.write_text(text, encoding='utf-8')
            created.append(name)
    episode = root / 'episodes' / 'EP01'
    episode.mkdir(parents=True, exist_ok=True)
    for name in ('script.md', 'shots.md'):
        if not (episode / name).exists():
            shutil.copyfile(TEMPLATES / name, episode / name)
            created.append(f'episodes/EP01/{name}')
    (root / 'assets' / 'images').mkdir(parents=True, exist_ok=True)
    (root / 'source').mkdir(exist_ok=True)
    _print(f'已创建：{"、".join(created) or "（文件都已存在，未改动）"}')
    return 0


def _episodes(project, wanted):
    return [e.upper() for e in wanted] if wanted else None


def cmd_ids(args):
    root = Path(args.project)
    total = 0
    for directory in episode_dirs(root):
        if args.episodes and directory.name.upper() not in {e.upper() for e in args.episodes}:
            continue
        script = directory / 'script.md'
        if script.is_file():
            added = assign_ids(script)
            total += added
            _print(f'{directory.name}：补了 {added} 个行号')
    return 0


def cmd_check(args, write_all=False):
    root = Path(args.project)
    for directory in episode_dirs(root):
        if args.episodes and directory.name.upper() not in {e.upper() for e in args.episodes}:
            continue
        if (directory / 'script.md').is_file():
            assign_ids(directory / 'script.md')
    project = load_project(root)
    _project_issues(project)
    plans = plan_project(project, _episodes(project, args.episodes))
    if not plans:
        _print('没有找到任何集（episodes/EP01/script.md）')
        return 1
    errors = 0
    for plan in plans:
        if write_all:
            write_episode(project, plan)
        else:
            out = root / 'derived' / plan.episode.id
            out.mkdir(parents=True, exist_ok=True)
            (out / 'report.md').write_text(report_markdown(project, plan), encoding='utf-8')
        _summary(plan, args.limit)
        errors += plan.metrics['errors']
    if write_all:
        _print('已写出：derived/<集>/storyboard.md、prompts/*.txt、requests.json、plan.json、report.md')
    return 1 if errors else 0


def cmd_plan(args):
    return cmd_check(args, write_all=True)


def cmd_assets(args):
    root = Path(args.project)
    project = load_project(root)
    plans = plan_project(project, _episodes(project, args.episodes))
    path = write_assets(project, plans)
    rows = json.loads((path.parent / 'assets.json').read_text(encoding='utf-8'))
    _print(f'参考图 {len(rows)} 张，缺 {sum(1 for r in rows if not r["exists"])} 张 → {path.relative_to(root).as_posix()}')
    return 0


def cmd_show(args):
    project = load_project(Path(args.project))
    plans = plan_project(project, [args.episode])
    if not plans:
        _print(f'找不到 {args.episode}')
        return 1
    plan = plans[0]
    if args.unit:
        unit = next((u for u in plan.units if u.id.upper() == args.unit.upper()), None)
        if not unit:
            _print(f'找不到请求 {args.unit}；有：{"、".join(u.id for u in plan.units)}')
            return 1
        _print(unit.prompt)
        return 0
    _print(storyboard_markdown(project, plan))
    return 0


def cmd_import_legacy(args):
    from .legacy import import_board
    report = import_board(Path(args.board), Path(args.project), episode=args.episode,
                          keep_durations=args.keep_durations, assets=Path(args.assets) if args.assets else None)
    _print(report)
    return 0


def cmd_doctor(args):
    _print(f'sf_core {VERSION} · Python {sys.version.split()[0]}')
    if args.project:
        project = load_project(Path(args.project))
        cap = project.series.cap
        _print(f'格式：{project.series.format_name} {project.series.fmt.get("aspect")} · 模型：{cap.get("label")} '
               f'（{cap.get("unit_seconds")} 秒整数，参考图上限 {cap.get("images_max")}，稳定 {cap.get("images_reliable")}；'
               f'实测校准：{cap.get("calibrated") or "尚未"}）')
        _print(f'人物/群演/场景/道具：{sum(1 for e in project.entities.values() if e.kind == "character")}/'
               f'{sum(1 for e in project.entities.values() if e.kind == "crowd")}/'
               f'{sum(1 for e in project.entities.values() if e.kind == "location")}/'
               f'{sum(1 for e in project.entities.values() if e.kind == "prop")} · 集数：{len(project.episodes)}')
        _project_issues(project)
    return 0


def main(argv=None):
    if hasattr(sys.stdout, 'reconfigure'):
        sys.stdout.reconfigure(encoding='utf-8')
    parser = argparse.ArgumentParser(prog='sf', description='shortdrama-director 2：小说改编短剧的分镜与 Seedance 提示词工具')
    sub = parser.add_subparsers(dest='command', required=True)
    p = sub.add_parser('init', help='新建系列目录和模板')
    p.add_argument('project'); p.add_argument('--title', default=''); p.add_argument('--format', default='横屏剧集')
    p.set_defaults(func=cmd_init)
    for name, func, text in (('ids', cmd_ids, '给台词和画面行补行号'), ('check', cmd_check, '检查，只写报告'),
                             ('plan', cmd_plan, '生成请求、提示词、分镜表和报告'), ('assets', cmd_assets, '列出参考图和出图提示词')):
        p = sub.add_parser(name, help=text)
        p.add_argument('project'); p.add_argument('episodes', nargs='*')
        p.add_argument('--limit', type=int, default=12, help='屏幕上最多显示几条问题')
        p.set_defaults(func=func)
    p = sub.add_parser('show', help='显示分镜表或某个请求的提示词')
    p.add_argument('project'); p.add_argument('episode'); p.add_argument('--unit')
    p.set_defaults(func=cmd_show)
    p = sub.add_parser('import-legacy', help='把旧版（1.2.x）board.json 转成新格式')
    p.add_argument('board'); p.add_argument('project'); p.add_argument('--episode', default='')
    p.add_argument('--keep-durations', action='store_true', help='保留旧版每镜时长，不按台词重新估算')
    p.add_argument('--assets', help='旧版资产登记 JSON（可选）')
    p.set_defaults(func=cmd_import_legacy)
    p = sub.add_parser('doctor', help='版本、格式和模型能力')
    p.add_argument('project', nargs='?')
    p.set_defaults(func=cmd_doctor)
    args = parser.parse_args(argv)
    return args.func(args)


if __name__ == '__main__':
    raise SystemExit(main())
