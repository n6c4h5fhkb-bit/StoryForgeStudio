"""Keep test module imports away from the user's live System B database."""
from __future__ import annotations

import os
import shutil
import tempfile
from pathlib import Path


_BOOT_DATA = Path(tempfile.mkdtemp(prefix='storysystems-b-tests-')).resolve()
os.environ['STUDIO_DATA'] = str(_BOOT_DATA)


def pytest_sessionfinish(session, exitstatus):
    # app.main exposes a production ASGI instance at import time.  During tests
    # it is deliberately backed by this disposable directory.
    try:
        from app.main import app
        app.state.jobs.pool.shutdown(wait=True, cancel_futures=True)
    finally:
        shutil.rmtree(_BOOT_DATA, ignore_errors=True)
