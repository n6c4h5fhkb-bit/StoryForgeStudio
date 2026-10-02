"""Measure shortdrama-director boards and video prompts.

Read-only. Prints the metrics used in docs/PLATFORM_SKILL_JOINT_REVIEW_2026_10_02.en.md
so the same numbers can be recomputed on any project before and after a redesign.

    python tools/skill_board_metrics.py board.json [more boards...]
    python tools/skill_board_metrics.py --prompt U01.PLAN.txt [more prompts...]
    python tools/skill_board_metrics.py --json board.json

A board file may be a native board, or a test fixture that wraps
{"board": {...}, "scene": {...}}.
"""
from __future__ import annotations

import argparse
import collections
import json
import re
import statistics
import sys
from pathlib import Path

PUNCT = re.compile(r'[\s，。！？、；：“”‘’…—,.!?;:"\'()（）《》]')
ASCII_CODE = re.compile(r'[A-Za-z][A-Za-z0-9_]{2,}')
# Phrases that address the author or the workflow rather than the video model.
META_PHRASES = ['剪辑余量', '参考计划', '尚未物化', '上传参考图', '切镜依据', '随后切镜', '不提前表演',
                '伤未宣称', '本镜约第', '起始组合', '结束组合', '补充状态', '__母图__', '__子图__', '@1）']
BOILERPLATE_FIELDS = ('blocking', 'lighting', 'sound', 'emotion', 'cut_reason')


def size(value):
    return len(json.dumps(value, ensure_ascii=False, separators=(',', ':')))


def load_board(path):
    data = json.loads(Path(path).read_text(encoding='utf-8-sig'))
    if 'scenes' not in data and isinstance(data.get('board'), dict):
        board = dict(data['board'])
        board['scenes'] = [data['scene']] if isinstance(data.get('scene'), dict) else data['board'].get('scenes', [])
        return board
    return data


def board_metrics(board):
    scenes = board.get('scenes', [])
    shots = [shot for scene in scenes for shot in scene.get('shots', [])]
    units = [unit for scene in scenes for unit in scene.get('units', [])]
    total = size(board)
    out = {'chars': total, 'scenes': len(scenes), 'shots': len(shots), 'units': len(units),
           'cut_records': len(board.get('cuts', [])), 'cut_chars': size(board.get('cuts', []))}
    if not shots:
        return out
    state_chars = sum(size(s.get('start_state', {})) + size(s.get('end_state', {})) for s in shots)
    keys = [len(s.get('start_state', {})) for s in shots]
    relevant, unchanged = [], 0
    for s in shots:
        start, end = s.get('start_state', {}), s.get('end_state', {})
        visible = set(s.get('visible_entities', []))
        relevant.append(sum(1 for k in start if k.split('.')[0] in visible))
        unchanged += all(start.get(k) == end.get(k) for k in set(start) | set(end))
    values = [v for s in shots for v in s.get('start_state', {}).values() if isinstance(v, str)]
    out.update(state_chars=state_chars, state_share=round(state_chars / total, 3),
               derivable_or_bookkeeping_share=round((state_chars + out['cut_chars']) / total, 3),
               state_keys_per_shot=round(statistics.mean(keys), 1),
               visible_key_share=round(statistics.mean(relevant) / max(statistics.mean(keys), 1e-9), 3),
               shots_without_change=unchanged,
               ascii_coded_values=sum(1 for v in values if re.fullmatch(r'[A-Za-z0-9_ \-]+', v)),
               state_values=len(values))
    out['identical_text'] = {
        'intent==visual': sum(1 for s in shots if s.get('intent') and s.get('intent') == s.get('visual')),
        'visual==composition': sum(1 for s in shots if s.get('visual') and s.get('visual') == (s.get('camera') or {}).get('composition')),
        'visual==blocking': sum(1 for s in shots if s.get('visual') and s.get('visual') == s.get('blocking'))}
    out['distinct_values'] = {f: len({s.get(f) for s in shots if s.get(f) is not None}) for f in BOILERPLATE_FIELDS}
    durations = [s['duration_ms'] for s in shots if isinstance(s.get('duration_ms'), int)]
    if durations:
        out.update(edited_s=sum(durations) / 1000, asl_s=round(statistics.mean(durations) / 1000, 2),
                   shot_seconds_histogram=dict(sorted(collections.Counter(d // 1000 for d in durations).items())),
                   shots_under_3s=sum(1 for d in durations if d < 3000))
    rates, placeholders = [], 0
    for s in shots:
        for line in s.get('dialogue', []):
            span = (line.get('end_ms', 0) - line.get('start_ms', 0)) / 1000
            chars = len(PUNCT.sub('', line.get('text', '')))
            if span > 0:
                rates.append(chars / span)
            placeholders += line.get('start_ms') == 200 and line.get('end_ms') == s.get('duration_ms', 0) - 200
    if rates:
        out.update(dialogue_lines=len(rates), dialogue_chars_per_s=round(statistics.mean(rates), 2),
                   placeholder_windows=placeholders,
                   declared_chars_per_s=(board.get('project') or {}).get('zh_chars_per_second'))
    if units:
        per_unit = [len(u.get('shot_ids', [])) for u in units]
        out.update(shots_per_unit=round(statistics.mean(per_unit), 2),
                   single_shot_units=sum(1 for n in per_unit if n == 1),
                   render_s_mean=round(statistics.mean(u.get('render_ms', 0) for u in units) / 1000, 2))
    return out


def prompt_metrics(text):
    lines = text.splitlines()
    state = sum(len(l) for l in lines if l.startswith(('开始：', '结束：', '开镜时', '本镜收束时', '全段保持')) or '组合：' in l)
    return {'chars': len(text), 'lines': len(lines), 'state_line_share': round(state / max(len(text), 1), 3),
            'ascii_tokens': sorted(set(ASCII_CODE.findall(text))),
            'meta_phrases': [p for p in META_PHRASES if p in text], 'double_periods': text.count('。。')}


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument('files', nargs='+')
    parser.add_argument('--prompt', action='store_true', help='treat files as compiled prompt text')
    parser.add_argument('--json', action='store_true', help='print JSON instead of a readable listing')
    args = parser.parse_args(argv)
    results = {}
    for name in args.files:
        if args.prompt:
            results[name] = prompt_metrics(Path(name).read_text(encoding='utf-8-sig'))
        else:
            results[name] = board_metrics(load_board(name))
    if args.json:
        sys.stdout.write(json.dumps(results, ensure_ascii=False, indent=2) + '\n')
        return 0
    for name, metrics in results.items():
        sys.stdout.write(name + '\n')
        for key, value in metrics.items():
            sys.stdout.write(f'  {key}: {json.dumps(value, ensure_ascii=False)}\n')
    return 0


if __name__ == '__main__':
    if hasattr(sys.stdout, 'reconfigure'):
        sys.stdout.reconfigure(encoding='utf-8')
    raise SystemExit(main())
