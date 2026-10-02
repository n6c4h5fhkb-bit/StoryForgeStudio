"""Build or verify deterministic SHA-256 release manifests for System A and B."""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
EXCLUDED_DIRS = {'.git', '.venv', 'data', '.tmp', 'v', '__pycache__', '.pytest_cache', '.mypy_cache', '.ruff_cache'}
TEST_COUNTS = {'system-a': 164, 'system-b': 218}


def included_files(root: Path):
    for path in root.rglob('*'):
        if not path.is_file() or path.name == 'MANIFEST.json':
            continue
        relative = path.relative_to(root)
        if any(part in EXCLUDED_DIRS or part.startswith(('.test-tmp', '.tmp-')) for part in relative.parts) or path.suffix in {'.pyc', '.pyo'}:
            continue
        yield relative.as_posix(), path


def build(system: str):
    root = ROOT / system
    files = {
        relative: hashlib.sha256(path.read_bytes()).hexdigest()
        for relative, path in sorted(included_files(root))
    }
    return {
        'release': '2.0.0',
        'system': 'SYSTEM A' if system == 'system-a' else 'SYSTEM B',
        'edition': 'independent-local-source',
        'pythonMinimum': '3.11',
        'testCount': TEST_COUNTS[system],
        'paidProvidersLiveVerified': False,
        'nativeWindowsVerified': True,
        'browserVerified': 'Windows Edge 1440px / 390px',
        'handoffChecks': 31,
        'files': files,
    }


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--check', action='store_true')
    args = parser.parse_args()
    failed = False
    for system in ('system-a', 'system-b'):
        target = ROOT / system / 'MANIFEST.json'
        expected = build(system)
        if args.check:
            current = json.loads(target.read_text(encoding='utf-8')) if target.is_file() else None
            ok = current == expected
            print(f'{system}: {"ok" if ok else "outdated"} ({len(expected["files"])} files)')
            failed = failed or not ok
        else:
            target.write_text(json.dumps(expected, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
            print(f'{system}: wrote {len(expected["files"])} files')
    raise SystemExit(1 if failed else 0)


if __name__ == '__main__':
    main()
