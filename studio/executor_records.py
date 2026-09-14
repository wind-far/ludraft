"""Durable CLI/build ownership and restart cleanup. No prompts or tokens."""
import asyncio
from contextlib import contextmanager
from contextvars import ContextVar
import fcntl
import hashlib
import json
import re
import os
from pathlib import Path
import shutil
import tempfile

from .db import now, uid

ACTIVE_EXECUTION = ContextVar('opengame_execution_resources', default=None)


class ExecutorRecords:
    def __init__(self, store):
        self.store = store
        self.owner = hashlib.sha256(str(store.root.resolve()).encode()).hexdigest()
        store.execute('''CREATE TABLE IF NOT EXISTS executor_attempts(
            id TEXT PRIMARY KEY, run_id TEXT, container_name TEXT UNIQUE NOT NULL,
            image_id TEXT NOT NULL, owner TEXT NOT NULL, state TEXT NOT NULL,
            cleanup TEXT NOT NULL, create_ack INTEGER NOT NULL DEFAULT 0,
            create_sent INTEGER NOT NULL DEFAULT 0,
            reason TEXT, created_at TEXT NOT NULL, updated_at TEXT NOT NULL)''')
        # Additive migration keeps previous CLI attempts recoverable.
        with store.lock, store.con:
            columns = {row['name'] for row in store.query('PRAGMA table_info(executor_attempts)')}
            for name, definition in [('kind', "TEXT NOT NULL DEFAULT 'cli'"), ('parent_id', 'TEXT'),
                                     ('stage_path', 'TEXT')]:
                if name not in columns:
                    store.con.execute(f'ALTER TABLE executor_attempts ADD COLUMN {name} {definition}')

    @contextmanager
    def lease(self):
        # A second backend/recovery pass must not kill an actively owned CLI.
        with (self.store.root / '.opengame-executor.lock').open('a') as handle:
            try:
                fcntl.flock(handle, fcntl.LOCK_EX | fcntl.LOCK_NB)
            except BlockingIOError:
                raise RuntimeError('此数据目录已有 OpenGame 执行或恢复正在进行') from None
            try:
                yield
            finally:
                fcntl.flock(handle, fcntl.LOCK_UN)

    def pending(self):
        return self.store.query("SELECT * FROM executor_attempts WHERE cleanup!='removed' ORDER BY created_at,id")

    def begin(self, image_id, run_id=None, *, parent_id=None, stage_path=None):
        parent = self.get(parent_id) if parent_id else None
        if parent_id and (not parent or parent['owner'] != self.owner or parent['kind'] != 'cli'
                          or parent['state'] != 'running' or parent['cleanup'] != 'pending'):
            raise ValueError('构建必须属于正在执行的 OpenGame 任务')
        if any(row['id'] != parent_id for row in self.pending()):
            raise RuntimeError('仍有 OpenGame 资源待确认清理，请先恢复执行环境')
        if not re.fullmatch(r'sha256:[a-f0-9]{64}', image_id):
            raise ValueError('执行镜像标识无效')
        if run_id is not None and (not isinstance(run_id, str) or not re.fullmatch(r'[a-f0-9]{32}', run_id)):
            raise ValueError('执行任务标识无效')
        attempt = uid()
        kind = 'build' if parent else 'cli'
        name = ('gamedev-build-' if parent else 'gamedev-opengame-') + attempt
        self.store.execute('''INSERT INTO executor_attempts
            (id,run_id,container_name,image_id,owner,state,cleanup,created_at,updated_at,kind,parent_id,stage_path)
            VALUES(?,?,?,?,?,'prepared','pending',?,?,?,?,?)''',
            (attempt, parent['run_id'] if parent else run_id, name, image_id, self.owner,
             now(), now(), kind, parent_id, str(stage_path) if stage_path else None))
        return self.get(attempt)

    def get(self, attempt):
        return self.store.one('SELECT * FROM executor_attempts WHERE id=?', (attempt,))

    def state(self, attempt, state):
        if state not in ('creating', 'created', 'running', 'succeeded', 'failed', 'cancelled', 'interrupted'):
            raise ValueError('执行状态无效')
        self.store.execute('''UPDATE executor_attempts SET state=?,updated_at=?,
            create_ack=CASE WHEN ?='created' THEN 1 ELSE create_ack END,
            create_sent=CASE WHEN ?='creating' THEN 1 ELSE create_sent END WHERE id=?''',
            (state, now(), state, state, attempt))

    def cleanup(self, attempt, status, reason=None):
        if status not in ('pending', 'unknown', 'removed'):
            raise ValueError('清理状态无效')
        self.store.execute('UPDATE executor_attempts SET cleanup=?,reason=?,updated_at=? WHERE id=?',
                           (status, reason, now(), attempt))

    def labels(self, row):
        labels = {'com.ludraft.owner': self.owner, 'com.ludraft.attempt': row['id']}
        if row.get('parent_id'):
            labels['com.ludraft.parent'] = row['parent_id']
        return labels

    async def recover(self, docker, *, only=None):
        """Caller holds lease. Docker errors are never treated as absence."""
        # Child cleanup can run during normal execution without touching its parent.
        rows = sorted(self.pending(), key=lambda row: row['kind'] != 'build')
        for row in rows:
            if only is not None and row['id'] not in only:
                continue
            if row['state'] in ('prepared', 'creating', 'created', 'running'):
                self.state(row['id'], 'interrupted')
            try:
                prefix = {'cli': 'gamedev-opengame-', 'build': 'gamedev-build-'}.get(row['kind'])
                if not prefix or row['owner'] != self.owner or row['container_name'] != prefix + row['id']:
                    raise ValueError('执行记录与当前数据目录不匹配')
                found = (await docker('ps', '-aq', '--no-trunc', '--filter',
                                      'name=^/' + row['container_name'] + '$', timeout=4)).decode().split()
                if not found:
                    # A create client may have died before the daemon acknowledged.
                    if not row['create_ack'] and row['create_sent']:
                        raise ValueError('创建结果未确认；未找到容器仍不能证明清理完成')
                    self.cleanup(row['id'], 'removed')
                    continue
                if len(found) != 1 or not re.fullmatch(r'[a-f0-9]{64}', found[0]):
                    raise ValueError('容器身份无法确认')
                info = json.loads(await docker('container', 'inspect', found[0], timeout=4))[0]
                expected = {**self.labels(row), 'com.ludraft.role':
                            'opengame-build' if row['kind'] == 'build' else 'opengame-executor'}
                labels = info.get('Config', {}).get('Labels') or {}
                if (info.get('Id') != found[0] or info.get('Name') != '/' + row['container_name']
                        or info.get('Image') != row['image_id']
                        or any(labels.get(k) != v for k, v in expected.items())):
                    raise ValueError('容器归属不匹配，未执行清理')
                # Remove the inspected ID, never an unchecked name or a global prefix.
                await docker('rm', '-f', found[0], timeout=4)
                self.cleanup(row['id'], 'removed')
            except asyncio.CancelledError:
                raise
            except Exception:
                # Do not persist raw Docker/provider error content.
                self.cleanup(row['id'], 'unknown', '无法确认资源已清理，请检查 Docker 与容器归属')
        if only is None:
            self.release_stages()
        return self.summary()

    def release_stages(self):
        # Normal child cleanup leaves its files in place for Runner.run to collect
        # evidence. Full session/startup cleanup can remove interrupted staging.
        base = Path('/private/tmp' if os.uname().sysname == 'Darwin' else tempfile.gettempdir()).resolve()
        rows = self.store.query("SELECT * FROM executor_attempts WHERE stage_path IS NOT NULL AND cleanup='removed'")
        for row in rows:
            try:
                path = Path(row['stage_path'])
                if (row['owner'] != self.owner or row['kind'] != 'build' or path.parent != base
                        or not path.name.startswith('gamedev-runner-') or path.is_symlink()
                        or path.resolve() != path):
                    raise ValueError('构建临时目录身份不匹配')
                if path.exists():
                    marker = path / '.ludraft-stage.json'
                    if marker.is_symlink() or marker.stat().st_size > 1024:
                        raise ValueError('构建临时目录标记无效')
                    if json.loads(marker.read_text()) != {'owner': self.owner, 'id': row['id']}:
                        raise ValueError('构建临时目录标记不匹配')
                    shutil.rmtree(path)
                self.store.execute('UPDATE executor_attempts SET stage_path=NULL WHERE id=?', (row['id'],))
            except Exception:
                self.cleanup(row['id'], 'unknown', '构建临时目录清理未确认，保留目录待检查')

    def summary(self):
        pending = self.pending()
        return {'pending_cleanup': len(pending), 'can_start': not pending,
                'attempts': self.store.query('''SELECT id,run_id,kind,parent_id,state,cleanup,reason,created_at,updated_at
                    FROM executor_attempts ORDER BY created_at DESC,id DESC LIMIT 30''')}
