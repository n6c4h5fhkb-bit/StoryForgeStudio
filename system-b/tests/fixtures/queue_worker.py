"""Independent process used to verify shared-account admission and crash cleanup."""
import json
import os
from pathlib import Path
import sys
import time

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from app.call_queue import AccountQueue
from app.core import DomainError

home, result, mode = Path(sys.argv[1]), Path(sys.argv[2]), sys.argv[3]
def check():
    if result.with_suffix('.cancel').exists():raise DomainError('cancelled', 'cancelled', 409)
try:
    with AccountQueue(home).acquire(check=check) as meta:
        start=time.time()
        result.with_suffix('.entered').write_text('entered')
        if mode=='crash':os._exit(23)
        time.sleep(float(sys.argv[4]))
        result.write_text(json.dumps({'start':start,'end':time.time(),**meta}))
except DomainError as error:
    result.write_text(json.dumps({'error':error.code}))

