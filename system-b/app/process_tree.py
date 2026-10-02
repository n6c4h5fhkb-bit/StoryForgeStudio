"""Compatibility import for the shared studio runtime."""
from pathlib import Path
import sys
_studio_root = str(Path(__file__).resolve().parents[2])
if _studio_root not in sys.path: sys.path.insert(0, _studio_root)
from studio.process_tree import *
