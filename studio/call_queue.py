"""Cross-process FIFO admission for studios using one Codex home.

The queue contains only process/lease metadata, never story text or credentials.
Each studio still owns its own projects, sessions, and caches.
"""
from __future__ import annotations
from contextlib import contextmanager
from pathlib import Path
import os
import sqlite3
import time
import uuid

from .core import DomainError
from .process_tree import process_alive


class AccountQueue:
    def __init__(self, home):
        self.path = Path(home) / 'story-studio' / 'call-queue.sqlite3'

    @contextmanager
    def connect(self):
        self.path.parent.mkdir(parents=True, exist_ok=True)
        conn = sqlite3.connect(self.path, timeout=2)
        conn.row_factory = sqlite3.Row
        try:
            conn.execute('PRAGMA busy_timeout=2000')
            conn.execute('''CREATE TABLE IF NOT EXISTS tickets(
                seq INTEGER PRIMARY KEY AUTOINCREMENT, id TEXT UNIQUE NOT NULL,
                pid INTEGER NOT NULL, capacity INTEGER NOT NULL, state TEXT NOT NULL,
                created REAL NOT NULL, heartbeat REAL NOT NULL)''')
            conn.commit()
            conn.execute('BEGIN IMMEDIATE')
            yield conn
            conn.commit()
        except BaseException:
            conn.rollback()
            raise
        finally:
            conn.close()

    def _reap(self, conn):
        # A live owner is never displaced just because inference takes longer.
        # Its process-tree job object kills the CLI if the owner crashes.
        for row in conn.execute('SELECT id,pid FROM tickets').fetchall():
            if not process_alive(row['pid']):
                conn.execute('DELETE FROM tickets WHERE id=?', (row['id'],))

    @contextmanager
    def acquire(self, capacity=1, check=lambda: None):
        identifier = uuid.uuid4().hex
        start = time.monotonic()
        registered = False
        try:
            check()
            with self.connect() as conn:
                self._reap(conn)
                conn.execute('INSERT INTO tickets(id,pid,capacity,state,created,heartbeat) VALUES(?,?,?,?,?,?)',
                             (identifier, os.getpid(), max(1, int(capacity)), 'waiting', time.time(), time.time()))
                registered = True
            while True:
                check()
                with self.connect() as conn:
                    self._reap(conn)
                    rows = conn.execute('SELECT * FROM tickets ORDER BY seq').fetchall()
                    running = [r for r in rows if r['state'] == 'running']
                    waiting = [r for r in rows if r['state'] == 'waiting']
                    # Different clients' limits combine conservatively. FIFO
                    # prevents a stream of retries from overtaking another app.
                    limit = min(r['capacity'] for r in rows)
                    ready = waiting and waiting[0]['id'] == identifier and len(running) < limit
                    conn.execute('UPDATE tickets SET state=?,heartbeat=? WHERE id=?',
                                 ('running' if ready else 'waiting', time.time(), identifier))
                if ready:
                    yield {'queueWaitSeconds': round(time.monotonic() - start, 3), 'accountConcurrency': limit}
                    break
                time.sleep(.1)
        except (OSError, sqlite3.Error) as exc:
            raise DomainError('无法访问本机调用队列，未提交模型请求；请检查 Codex 登录目录的访问权限', 'codex_queue', 503) from exc
        finally:
            if registered:
                with self.connect() as conn:
                    conn.execute('DELETE FROM tickets WHERE id=?', (identifier,))
