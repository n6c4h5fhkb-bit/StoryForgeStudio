"""Assemble the installable shortdrama-director Skill from this repository.

The Skill is a build artifact, so it can never drift from the platform's kernel:

    skill/shortdrama-director/   SKILL.md, agent card, entry script, sample sources
    methods/*.md              -> references/
    sf_core/                  -> scripts/sf_core/ (without tests)

    python tools/build_skill.py                 # build into dist/shortdrama-director
    python tools/build_skill.py --zip           # also write dist/shortdrama-director.zip
    python tools/build_skill.py --verify <dir>  # check an installed Skill against this repository
"""
from __future__ import annotations

import argparse
import hashlib
import json
import shutil
import subprocess
import sys
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SHELL = ROOT / 'skill' / 'shortdrama-director'
IGNORE = shutil.ignore_patterns('__pycache__', '*.pyc', 'tests', 'derived')


def core_hash(directory: Path) -> str:
    digest = hashlib.sha256()
    for path in sorted(p for p in directory.rglob('*') if p.is_file() and '__pycache__' not in p.parts and 'tests' not in p.parts):
        digest.update(path.relative_to(directory).as_posix().encode())
        digest.update(path.read_bytes())
    return digest.hexdigest()


def git_commit() -> str:
    try:
        return subprocess.run(['git', 'rev-parse', '--short', 'HEAD'], cwd=ROOT, capture_output=True, text=True, check=True).stdout.strip()
    except (OSError, subprocess.CalledProcessError):
        return 'unknown'


def build(out: Path) -> dict:
    if out.exists():
        shutil.rmtree(out)
    shutil.copytree(SHELL, out, ignore=IGNORE)
    references = out / 'references'
    references.mkdir(exist_ok=True)
    for method in sorted((ROOT / 'methods').glob('*.md')):
        shutil.copyfile(method, references / method.name)
    shutil.copytree(ROOT / 'sf_core', out / 'scripts' / 'sf_core', ignore=IGNORE)
    sys.dont_write_bytecode = True
    sys.path.insert(0, str(out / 'scripts'))
    from sf_core import VERSION
    from sf_core.assets import write_assets
    from sf_core.parse import load_project
    from sf_core.plan import plan_project, write_episode
    sample = out / 'examples' / 'sample'
    if sample.is_dir():
        project = load_project(sample)
        plans = plan_project(project)
        for plan in plans:
            write_episode(project, plan)
        write_assets(project, plans)
    for cache in list(out.rglob('__pycache__')):
        shutil.rmtree(cache)
    info = {'name': 'shortdrama-director', 'version': VERSION, 'commit': git_commit(),
            'sf_core_sha256': core_hash(out / 'scripts' / 'sf_core'),
            'methods': sorted(p.name for p in references.glob('*.md'))}
    (out / 'VERSION.json').write_text(json.dumps(info, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    return info


def verify(installed: Path) -> int:
    info_path = installed / 'VERSION.json'
    if not info_path.is_file():
        print(f'{installed}: no VERSION.json — not built from this repository (an old 1.2.x Skill?)')
        return 1
    info = json.loads(info_path.read_text(encoding='utf-8'))
    expected = core_hash(ROOT / 'sf_core')
    actual = core_hash(installed / 'scripts' / 'sf_core')
    problems = []
    if actual != expected:
        problems.append('scripts/sf_core differs from the repository sf_core (rebuild and reinstall)')
    for method in (ROOT / 'methods').glob('*.md'):
        copy = installed / 'references' / method.name
        if not copy.is_file() or copy.read_bytes() != method.read_bytes():
            problems.append(f'references/{method.name} differs from methods/{method.name}')
    print(f'{installed}: version {info.get("version")} from commit {info.get("commit")}')
    for problem in problems:
        print('  - ' + problem)
    print('  in sync with this repository' if not problems else f'  {len(problems)} difference(s)')
    return 1 if problems else 0


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument('--out', default=str(ROOT / 'dist' / 'shortdrama-director'))
    parser.add_argument('--zip', action='store_true')
    parser.add_argument('--verify', metavar='INSTALLED_SKILL_DIR')
    args = parser.parse_args(argv)
    if args.verify:
        return verify(Path(args.verify))
    out = Path(args.out)
    info = build(out)
    print(f'built {out} (sf_core {info["version"]}, commit {info["commit"]})')
    if args.zip:
        archive = out.with_suffix('.zip')
        with zipfile.ZipFile(archive, 'w', zipfile.ZIP_DEFLATED) as bundle:
            for path in sorted(out.rglob('*')):
                if path.is_file():
                    bundle.write(path, Path(out.name) / path.relative_to(out))
        print(f'wrote {archive}')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
