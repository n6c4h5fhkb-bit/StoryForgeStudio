#!/usr/bin/env python3
"""Entry point for the Skill: python scripts/sf.py <command> ...

Finds the bundled sf_core next to this file (installed Skill) or at the
repository root (development checkout), then runs its command line.
"""
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
for candidate in (HERE, *HERE.parents):
    if (candidate / 'sf_core' / '__init__.py').is_file():
        sys.path.insert(0, str(candidate))
        break

from sf_core.cli import main  # noqa: E402

raise SystemExit(main())
