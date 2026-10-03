"""Tests for the shared kernel. Run from the repository root: python -m unittest discover -s sf_core/tests"""
from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from sf_core.ledger import parse_event, replay  # noqa: E402
from sf_core.lint import META_PHRASES  # noqa: E402
from sf_core.pack import pack_scene, segment_bounds  # noqa: E402
from sf_core.parse import assign_ids, classify, load_project  # noqa: E402
from sf_core.plan import plan_project, write_episode  # noqa: E402

SAMPLE = ROOT / 'skill' / 'shortdrama-director' / 'examples' / 'sample'
CAP = {'unit_seconds': [4, 15], 'handle_seconds': 0.5, 'max_shots_per_unit': 4, 'images_reliable': 6}


def write(root: Path, files: dict[str, str]):
    for name, text in files.items():
        path = root / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding='utf-8')


SERIES = '- 片名：测试\n- 格式：横屏剧集\n- 模型：seedance-2.0\n- 画风：写实电影质感\n'
BIBLE = '''# 人物
## 李树
- 别名：树哥
- 身份：成年男子，短黑发
- 造型（便服）：灰色T恤，深色长裤
- 造型（制服）：白衬衫，黑马甲，黑裤
## 刘军
- 身份：四十岁，短发，深色衬衫
# 群演
## 打手
- 人数：4
- 造型：黑夹克，平头
# 场景
## 办公室
- 布局：办公桌在北侧，门在南侧
## 巷口
- 布局：窄巷，西侧路灯
# 道具
## 铁棍
- 外观：一米长的锈铁棍
## 纱布
- 外观：白色方形纱布
- 参考图：否
'''


class ParseTests(unittest.TestCase):
    def test_line_kinds(self):
        self.assertEqual(classify('【画面】他推门进来。')[0], 'action')
        self.assertEqual(classify('李树：军哥，你腿怎么了？')[:2], ('speech', '李树'))
        kind, speaker, paren, offscreen, body = classify('刘军：（冷笑）你也配？')
        self.assertEqual((kind, paren, body), ('speech', '冷笑', '你也配？'))
        self.assertEqual(classify('李树（心声）：不对劲。')[0], 'inner')
        self.assertEqual(classify('李树：（心声）不对劲。')[0], 'inner')
        self.assertTrue(classify('刘军（画外）：开门！')[3])
        self.assertEqual(classify('旁白：那天下着雨。')[0], 'narration')
        self.assertEqual(classify('【状态】李树 拿起 铁棍')[0], 'state')
        self.assertEqual(classify('【时间跳转】三天后')[0], 'jump')

    def test_assign_ids_keeps_existing_and_skips_state_lines(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / 'script.md'
            path.write_text('## 场1 办公室 · 日\n【画面】甲。 ^L007\n李树：乙。\n【状态】李树 拿起 铁棍\n【音效】雷声\n', encoding='utf-8')
            self.assertEqual(assign_ids(path), 1)
            text = path.read_text(encoding='utf-8')
            self.assertIn('^L007', text)
            self.assertIn('李树：乙。 ^L008', text)
            self.assertNotIn('铁棍 ^L', text)
            self.assertEqual(assign_ids(path), 0)

    def test_shot_options_keep_commas_inside_values(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            write(root, {'series.md': SERIES, 'bible.md': BIBLE,
                         'episodes/EP01/script.md': '## 场1 办公室 · 日\n【画面】甲。 ^L001\n李树：乙。 ^L002\n刘军：丙。 ^L003\n',
                         'episodes/EP01/shots.md': '## 场1\n默认：光线=顶灯；声音=空调声\n'
                                                   '- S01 | 中景 | 李树、刘军 | L001-L003 | 动作 | 钩子 | 舞台=李树画左，刘军画右 | 时长=3\n'})
            project = load_project(root)
            shot = project.episodes[0].shot_scenes[0].shots[0]
            self.assertEqual(shot.lines, ['L001', 'L002', 'L003'])
            self.assertEqual(shot.stage, '李树画左，刘军画右')
            self.assertEqual(shot.duration, 3.0)
            self.assertEqual(shot.tags, ['钩子'])
            self.assertEqual(project.episodes[0].shot_scenes[0].defaults['声音'], '空调声')
            self.assertEqual(project.lookup('树哥').name, '李树')
            self.assertEqual(list(project.entities['李树'].looks), ['便服', '制服'])


class LedgerTests(unittest.TestCase):
    def project(self, script: str, script2: str = ''):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        root = Path(tmp.name)
        files = {'series.md': SERIES, 'bible.md': BIBLE, 'episodes/EP01/script.md': script}
        if script2:
            files['episodes/EP02/script.md'] = script2
        write(root, files)
        return load_project(root)

    def test_event_grammar(self):
        project = self.project('## 场1 办公室 · 日\n')
        cases = {
            '李树 拿起 铁棍：右手': ('hold', '李树', '铁棍'),
            '李树把铁棍交给刘军': ('give', '李树', '铁棍'),
            '铁棍 放在：门后': ('place', '', '铁棍'),
            '李树 换上 制服': ('dress', '李树', '制服'),
            '刘军 受伤：右腿，跛行（昨夜，画外）': ('hurt', '刘军', ''),
        }
        for text, (kind, subject, obj) in cases.items():
            event, warning = parse_event(text, project)
            self.assertEqual((event.kind, event.subject, event.obj), (kind, subject, obj), text)
            self.assertEqual(warning, '', text)
        event, _ = parse_event('李树 把 铁棍 交给 刘军', project)
        self.assertEqual(event.target, '刘军')
        self.assertTrue(parse_event('刘军 受伤：右腿（昨夜，画外）', project)[0].offscreen)
        self.assertIsNone(parse_event('天气很好', project)[0])

    def test_replay_carries_state_across_episodes(self):
        project = self.project(
            '## 场1 办公室 · 日\n【画面】甲。 ^L001\n【状态】李树 拿起 铁棍：右手\n【状态】李树 换上 制服\n'
            '【状态】刘军 受伤：右腿，跛行\n李树：走。 ^L002\n',
            '## 场1 巷口 · 夜\n【画面】乙。 ^L001\n【状态】李树 把 铁棍 交给 刘军\n刘军：拿着。 ^L002\n【状态】刘军 痊愈：右腿\n')
        rp = replay(project)
        start2 = rp.episode_start['EP02']
        self.assertEqual(start2['chars']['李树']['look'], '制服')
        self.assertEqual(start2['props']['铁棍']['holder'], '李树')
        self.assertEqual(start2['chars']['刘军']['conditions'], {'右腿': '跛行'})
        before = rp.before[('EP02', 'L002')]
        self.assertEqual(before['props']['铁棍']['holder'], '刘军')
        self.assertEqual(rp.episode_end['EP02']['chars']['刘军']['conditions'], {})


class PackTests(unittest.TestCase):
    def test_units_fit_whole_second_window_and_cut_limit(self):
        durations = [2.0] * 9
        spans = pack_scene(durations, CAP, lambda a, b: 2, lambda a, b: True)
        self.assertEqual(sum(b - a for a, b in spans), 9)
        for a, b in spans:
            self.assertLessEqual(b - a, 4)
            self.assertLessEqual(sum(durations[a:b]) + 0.5, 15)

    def test_invalid_spans_are_split(self):
        spans = pack_scene([2, 2, 2, 2], CAP, lambda a, b: 1, lambda a, b: not (a < 2 < b))
        self.assertTrue(all(not (a < 2 < b) for a, b in spans))

    def test_reference_budget_splits_units(self):
        spans = pack_scene([2, 2], CAP, lambda a, b: 4 * (b - a), lambda a, b: True)
        self.assertEqual(spans, [(0, 1), (1, 2)])

    def test_segment_bounds(self):
        for durations, total in (([2.7, 3.9, 2.4, 2.2], 12), ([1.0, 1.0, 1.0], 4), ([9.0], 10)):
            bounds = segment_bounds(durations, total)
            self.assertEqual(bounds[0][0], 0)
            self.assertEqual(bounds[-1][1], total)
            self.assertTrue(all(b - a >= 1 for a, b in bounds))
            self.assertTrue(all(bounds[i][1] == bounds[i + 1][0] for i in range(len(bounds) - 1)))


class PlanTests(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.root = Path(tmp.name)
        write(self.root, {
            'series.md': SERIES, 'bible.md': BIBLE,
            'episodes/EP01/script.md': (
                '## 场1 办公室 · 日 · 第1天\n'
                '【状态】李树 受伤：左额角（贴着纱布）（画外）\n'
                '【画面】刘军撑着桌沿起身。 ^L001\n李树：军哥，你腿怎么了？ ^L002\n'
                '刘军：昨晚去动李老三的场子，一组伤了不少人。 ^L003\n'
                '李树（心声）：他在瞒我。 ^L004\n'
                '## 场2 巷口 · 夜 · 第1天\n'
                '【画面】四个打手堵住巷口。 ^L005\n'
                '【状态】李树 拿起 铁棍：右手\n'
                '李树：让开。 ^L006\n打手（画外）：上！ ^L007\n'
                '【时间跳转】片刻之后\n【画面】打手们倒在地上。 ^L008\n'),
            'episodes/EP01/shots.md': (
                '## 场1\n默认：光线=暖白顶灯；声音=空调声；轴线=李树画左，刘军画右\n'
                '- S01 | 中景 | 李树, 刘军 | L001,L002 | 刘军撑着桌沿起身，右腿不敢吃力 | 钩子\n'
                '- S02 | 近景 | 刘军 | L003 | 刘军坐回椅子，揉着右膝 | 冲突\n'
                '- S03 | 近景 | 李树 | L004 | 李树盯着刘军的腿\n'
                '## 场2\n默认：光线=路灯\n'
                '- S04 | 全景 | 打手 | L005 | 四个打手堵住巷口 | 反转\n'
                '- S05 | 近景 | 李树, 铁棍 | L006,L007 | 李树握紧铁棍 | 爽点\n'
                '- S06 | 全景 | 打手, 李树 | L008 | 打手们倒在地上，李树站着喘气 | 卡点\n'),
        })

    def plan(self):
        project = load_project(self.root)
        return project, plan_project(project)[0]

    def test_prompts_are_clean_and_complete(self):
        project, plan = self.plan()
        allowed = {'KTV'}
        for unit in plan.units:
            self.assertLessEqual(unit.gen_seconds, 15)
            self.assertGreaterEqual(unit.gen_seconds, 4)
            self.assertFalse(set(re.findall(r'[A-Za-z][A-Za-z0-9_]+', unit.prompt)) - allowed, unit.prompt)
            self.assertFalse([p for p in META_PHRASES if p in unit.prompt], unit.prompt)
            self.assertTrue(unit.prompt.startswith('16:9'))
        text = '\n'.join(u.prompt for u in plan.units)
        for line in ('军哥，你腿怎么了？', '让开。'):
            self.assertIn(line, text)
        self.assertIn('李树的内心独白（画外音，李树不开口）', text)
        self.assertIn('画外传来打手的声音', text)
        self.assertIn('@图片1', text)
        self.assertIn('左额角贴着纱布', text)
        first = plan.units[0].prompt
        self.assertIn('李树画左，刘军画右', first)

    def test_axis_mentions_only_people_in_frame(self):
        project, plan = self.plan()
        unit = next(u for u in plan.units if u.shots[0].shot.id == 'S02') if any(u.shots[0].shot.id == 'S02' for u in plan.units) else None
        if unit:
            self.assertNotIn('李树画左', unit.prompt)

    def test_time_skip_and_text_only_props(self):
        project, plan = self.plan()
        units = [u for u in plan.units if u.scene.id == '场2']
        self.assertTrue(any(u.shots[0].shot.id == 'S06' for u in units), [[p.shot.id for p in u.shots] for u in units])
        refs = {r.entity for u in plan.units for r in u.references}
        self.assertNotIn('纱布', refs)
        self.assertIn('铁棍', refs)
        self.assertIn('打手', refs)

    def test_checks_flag_missing_and_duplicate_lines(self):
        shots = self.root / 'episodes/EP01/shots.md'
        shots.write_text(shots.read_text(encoding='utf-8').replace('L003', 'L002'), encoding='utf-8')
        _, plan = self.plan()
        codes = {i.code for i in plan.issues}
        self.assertIn('LINE_UNCOVERED', codes)
        self.assertIn('LINE_DUPLICATE', codes)

    def test_editing_one_scene_leaves_other_prompts_unchanged(self):
        project, plan = self.plan()
        write_episode(project, plan)
        prompts = self.root / 'derived/EP01/prompts'
        before = {p.name: p.read_text(encoding='utf-8') for p in prompts.glob('*.txt')}
        shots = self.root / 'episodes/EP01/shots.md'
        shots.write_text(shots.read_text(encoding='utf-8').replace('李树握紧铁棍', '李树握紧铁棍，往前一步'), encoding='utf-8')
        project, plan = self.plan()
        write_episode(project, plan)
        after = {p.name: p.read_text(encoding='utf-8') for p in prompts.glob('*.txt')}
        changed = {name for name in after if before.get(name) != after[name]}
        self.assertTrue(changed and all(name.startswith('U02-') for name in changed), changed)
        requests = json.loads((self.root / 'derived/EP01/requests.json').read_text(encoding='utf-8'))
        self.assertEqual(requests[0]['command'][:2], ['dreamina', 'multimodal2video'])
        self.assertIn('--duration', requests[0]['command'])

    def test_format_checks(self):
        _, plan = self.plan()
        codes = {i.code for i in plan.issues}
        self.assertIn('EP_LENGTH', codes)          # a few seconds, far below 180
        self.assertNotIn('HOOK_MISSING', codes)
        self.assertNotIn('CLIFF_MISSING', codes)


class LegacyTests(unittest.TestCase):
    def board(self):
        state = {'C1.wardrobe': '服务生制服', 'C1.injury': '左额角敷料，伤未宣称痊愈', 'P1.holder': 'none', 'P1.place': 'table'}
        end = dict(state, **{'P1.holder': 'C1', 'P1.place': 'right_hand'})
        return {
            'project': {'title': '测试剧 EP02｜夜路', 'aspect_ratio': '16:9', 'style': '写实质感，16:9横屏，暴力非血腥',
                        'zh_chars_per_second': 5, 'directing_intent': '只在控制权变化时切镜'},
            'entities': [{'id': 'C1', 'kind': 'character', 'name': '李树', 'visual_anchor': '成年男子，独立道具'},
                         {'id': 'P1', 'kind': 'prop', 'name': '铁棍', 'visual_anchor': '锈铁棍'},
                         {'id': 'L1', 'kind': 'location', 'name': '巷口', 'visual_anchor': '窄巷'}],
            'beats': [{'id': 'B1', 'summary': '李树拿到铁棍', 'drama': {'events': [{'kind': 'immediate_payoff', 'shot_id': 'SH02'}]}}],
            'cuts': [{'source_id': 'L0001'}] * 5,
            'scenes': [{'id': 'SC01', 'location_id': 'L1', 'time_domain': '当晚', 'initial_state': state, 'shots': [
                {'id': 'SH01', 'visual': '李树走进巷口。', 'camera': {'size': '全景'}, 'dialogue': [],
                 'start_state': state, 'end_state': state, 'visible_entities': ['C1', 'L1']},
                {'id': 'SH02', 'visual': '李树抄起铁棍。', 'camera': {'size': '近景', 'composition': '李树画左'},
                 'dialogue': [{'speaker_id': 'C1', 'text': '来啊。'}], 'start_state': state, 'end_state': end,
                 'visible_entities': ['C1', 'P1']}], 'units': []}],
        }

    def test_import_and_plan(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            board = root / 'board.json'
            board.write_text(json.dumps(self.board(), ensure_ascii=False), encoding='utf-8')
            from sf_core.legacy import import_board
            report = import_board(board, root / 'proj')
            self.assertIn('逐行删改记录 5 条', report)
            proj = root / 'proj'
            self.assertTrue((proj / 'episodes/EP02/script.md').is_file())
            series = (proj / 'series.md').read_text(encoding='utf-8')
            self.assertIn('- 片名：测试剧', series)
            self.assertNotIn('16:9横屏', series)
            script = (proj / 'episodes/EP02/script.md').read_text(encoding='utf-8')
            self.assertIn('【状态】李树 拿起 铁棍：右手', script)
            self.assertNotIn('宣称', script)
            shots = (proj / 'episodes/EP02/shots.md').read_text(encoding='utf-8')
            self.assertIn('爽点', shots)
            self.assertIn('舞台=李树画左', shots)
            project = load_project(proj)
            plan = plan_project(project)[0]
            self.assertEqual(plan.metrics['errors'], 0)
            self.assertNotIn('独立道具', (proj / 'bible.md').read_text(encoding='utf-8'))
            # a second episode appends only new entities to the bible
            second = self.board()
            second['project']['title'] = '测试剧 EP03｜回家'
            second['entities'].append({'id': 'C2', 'kind': 'character', 'name': '刘军', 'visual_anchor': '四十岁'})
            board.write_text(json.dumps(second, ensure_ascii=False), encoding='utf-8')
            import_board(board, proj)
            bible = load_project(proj).entities
            self.assertIn('刘军', bible)
            self.assertEqual(sum(1 for name in bible if name == '李树'), 1)

    @unittest.skipUnless(os.environ.get('SF_LEGACY_BOARD'), 'set SF_LEGACY_BOARD to a real 1.2.x board.json')
    def test_real_board(self):
        with tempfile.TemporaryDirectory() as tmp:
            from sf_core.legacy import import_board
            import_board(Path(os.environ['SF_LEGACY_BOARD']), Path(tmp))
            project = load_project(Path(tmp))
            plan = plan_project(project)[0]
            self.assertEqual(plan.metrics['errors'], 0)
            self.assertFalse([i for i in plan.issues if i.code in ('PROMPT_ASCII', 'PROMPT_META')])


class CliTests(unittest.TestCase):
    def run_sf(self, *args, cwd=ROOT):
        env = dict(os.environ, PYTHONIOENCODING='utf-8')
        return subprocess.run([sys.executable, str(ROOT / 'skill/shortdrama-director/scripts/sf.py'), *args],
                              cwd=cwd, capture_output=True, text=True, encoding='utf-8', env=env)

    def test_init_and_plan_sample(self):
        with tempfile.TemporaryDirectory() as tmp:
            project = Path(tmp) / 'sample'
            shutil.copytree(SAMPLE, project, ignore=shutil.ignore_patterns('derived'))
            result = self.run_sf('plan', str(project))
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            self.assertIn('EP01', result.stdout)
            self.assertTrue((project / 'derived/EP01/storyboard.md').is_file())
            result = self.run_sf('assets', str(project))
            self.assertEqual(result.returncode, 0, result.stderr)
            assets = json.loads((project / 'derived/assets.json').read_text(encoding='utf-8'))
            self.assertTrue(any(row['parent'] for row in assets))
            fresh = Path(tmp) / 'new'
            result = self.run_sf('init', str(fresh), '--title', '新剧')
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertIn('- 片名：新剧', (fresh / 'series.md').read_text(encoding='utf-8'))
            result = self.run_sf('check', str(fresh))
            self.assertIn(result.returncode, (0, 1))


if __name__ == '__main__':
    unittest.main()
