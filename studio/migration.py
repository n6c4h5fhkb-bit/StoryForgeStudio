"""Copy legacy records into one database without moving original media or sessions."""
from __future__ import annotations

import copy
import json
import sqlite3
from pathlib import Path

from .core import canonical, digest, now, ensure


MIGRATION = 'unified-workspaces-v1'


def merge_settings(root, legacy_roots):
    destination = root / 'settings.json'
    if destination.exists():
        return
    configs = []
    for path in legacy_roots:
        source = path / 'settings.json'
        configs.append(json.loads(source.read_text(encoding='utf-8-sig')) if source.is_file() else {})
    a, b = configs
    merged = copy.deepcopy(b)
    for key, value in a.items():
        if key not in ('models', 'media', 'mediaImages', 'mediaVideos', 'runners', 'routing', 'gatePlugins', 'ffmpeg', 'ffprobe'):
            merged[key] = copy.deepcopy(value)
    merged['models'] = {**copy.deepcopy(b.get('models', {})), **copy.deepcopy(a.get('models', {}))}
    # Preserve effective connections when legacy workspaces used different defaults.
    for config, roles in ((a, ('ideation', 'structure', 'story', 'script', 'validator', 'reviewer', 'intent')),
                          (b, ('normalizer', 'assets', 'direction', 'shots', 'vision', 'treatment'))):
        for role in roles:
            if config.get('llm'):
                fallback = {'ideation': 'structure', 'reviewer': 'validator', 'shots': 'direction', 'treatment': 'direction'}.get(role)
                merged['models'][role] = {**copy.deepcopy(config['llm']), **copy.deepcopy(config.get('models', {}).get(role, config.get('models', {}).get(fallback, {})))}
    if 'presentation' not in merged['models'] and merged['models'].get('treatment'):
        merged['models']['presentation'] = copy.deepcopy(merged['models']['treatment'])
    merged['workspaces'] = {'A': {'name': '剧本创作'}, 'B': {'name': '导演与制作'}}
    destination.write_text(json.dumps(merged, ensure_ascii=False, indent=2), encoding='utf-8')


def import_legacy(store, legacy_roots):
    """One transaction, durable marker, original paths and exact Codex IDs retained."""
    marker = 'migration_' + MIGRATION
    if store.get(marker, required=False):
        merge_settings(store.root, legacy_roots)
        return
    snapshots = []
    for workspace, root in zip(('A', 'B'), legacy_roots):
        path = root / 'studio.sqlite3'
        if not path.is_file() or path.resolve() == store.path.resolve():
            continue
        with sqlite3.connect(path.as_uri() + '?mode=ro', uri=True) as source:
            source.row_factory = sqlite3.Row
            tables = {row[0] for row in source.execute("SELECT name FROM sqlite_master WHERE type='table'")}
            records = {table: [dict(row) for row in source.execute('SELECT * FROM ' + table)]
                       for table in ('documents', 'operations', 'events', 'cache', 'redirects', 'jobs', 'job_idempotency') if table in tables}
        running = [row['id'] for row in records.get('jobs', []) if row['state'] in ('queued', 'running')]
        ensure(not running, '旧工作区仍有任务运行；请结束或取消后再启动统一工作室。原数据未改变。', 'legacy_jobs_running', 409,
               {'workspace': workspace, 'jobIds': running})
        snapshots.append((workspace, root, records))
    counts = {}
    with store.transaction() as target:
        for workspace, root, records in snapshots:
            counts[workspace] = {}
            for row in records.get('documents', []):
                value = json.loads(row['data'])
                if row['kind'] == 'project':
                    value['workspace'] = workspace
                existing = target.execute('SELECT kind,data FROM documents WHERE id=?', (row['id'],)).fetchone()
                ensure(not existing or (existing['kind'] == row['kind'] and digest(json.loads(existing['data'])) == digest(value)),
                       '旧记录 ID 冲突，迁移已停止，两个原数据库保留。', 'migration_conflict', 409, {'id': row['id'], 'workspace': workspace})
                target.execute('INSERT OR IGNORE INTO documents(id,project,kind,data,version,updated) VALUES(?,?,?,?,?,?)',
                               (row['id'], row['project'], row['kind'], canonical(value), row['version'], row['updated']))
            for table in ('operations', 'events'):
                for row in records.get(table, []):
                    fields = [key for key in row if key != 'seq']
                    target.execute('INSERT OR IGNORE INTO ' + table + '(' + ','.join(fields) + ') VALUES(' + ','.join('?' for _ in fields) + ')', tuple(row[key] for key in fields))
            for table in ('cache', 'redirects', 'jobs', 'job_idempotency'):
                for row in records.get(table, []):
                    fields = list(row)
                    target.execute('INSERT OR IGNORE INTO ' + table + '(' + ','.join(fields) + ') VALUES(' + ','.join('?' for _ in fields) + ')', tuple(row[key] for key in fields))
            counts[workspace] = {table: len(rows) for table, rows in records.items()}
        store.put('migration', {'id': marker, 'createdAt': now(), 'counts': counts,
                               'legacyRoots': [str(path) for path in legacy_roots], 'originalMediaRetained': True}, 'studio', conn=target)
    merge_settings(store.root, legacy_roots)

