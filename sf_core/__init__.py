"""StoryForge shared production kernel.

Pure, stdlib-only Python used by the shortdrama-director Skill and, later, by the
platform. Authors write small readable Markdown files (series, bible, outline,
script, shots); this package derives everything else: the continuity ledger,
timing, generation units, reference bindings, Seedance prompts and reports.
"""
from __future__ import annotations

VERSION = '2.0.0'
