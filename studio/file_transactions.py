"""Synchronous directory transactions with recovery after interrupted renames.

Candidates are private to a run. Readers using the file helpers share the same
lock. A crash between directory renames is recovered before the next read/edit;
published versions never use this mutation path.
"""
import fcntl
import json
import os
import re
import shutil
import stat
import tempfile
from contextlib import contextmanager
from pathlib import Path


def sync_dir(path):
    fd = os.open(path, os.O_RDONLY)
    try:
        os.fsync(fd)
    finally:
        os.close(fd)


def journal_path(root):
    return root.parent / f'.{root.name}.transaction.json'


def _recover(root):
    journal = journal_path(root)
    if not journal.exists():
        return
    if journal.is_symlink() or journal.stat().st_size > 2000:
        raise ValueError('变更恢复记录无效')
    data = json.loads(journal.read_text())
    if not isinstance(data, dict):
        raise ValueError('变更恢复记录无效')
    stage_name = data.get('stage', '')
    if not isinstance(stage_name, str) or not re.fullmatch(re.escape(f'.{root.name}.stage-') + r'[a-zA-Z0-9_-]+', stage_name):
        raise ValueError('变更恢复路径无效')
    stage = root.parent / stage_name
    backup = root.parent / f'.{root.name}.previous'
    if any(p.is_symlink() for p in (root, stage, backup)):
        raise ValueError('变更恢复目录不能是符号链接')
    if not root.exists():
        if not backup.is_dir():
            raise ValueError('变更恢复缺少原始工程')
        os.replace(backup, root)
    elif backup.exists() and stage.exists():
        raise ValueError('变更恢复状态不一致')
    if stage.exists():
        shutil.rmtree(stage)
    if backup.exists():
        shutil.rmtree(backup)
    journal.unlink()
    sync_dir(root.parent)


@contextmanager
def workspace_lock(root):
    root = Path(root)
    lock = root.parent / f'.{root.name}.edit.lock'
    fd = os.open(lock, os.O_CREAT | os.O_RDWR | os.O_NOFOLLOW, 0o600)
    try:
        fcntl.flock(fd, fcntl.LOCK_EX)
        _recover(root)
        yield
    finally:
        fcntl.flock(fd, fcntl.LOCK_UN)
        os.close(fd)


def recover_edits(root):
    with workspace_lock(root):
        pass


def atomic_edit(root, edit):
    root = Path(root)
    with workspace_lock(root):
        if root.is_symlink() or not root.is_dir():
            raise ValueError('工程目录无效')
        for path in root.rglob('*'):
            if path.is_symlink() or not (path.is_dir() or path.is_file()):
                raise ValueError('工程不能包含符号链接或特殊文件')
        stage = Path(tempfile.mkdtemp(prefix=f'.{root.name}.stage-', dir=root.parent))
        backup = root.parent / f'.{root.name}.previous'
        journal = journal_path(root)
        if backup.exists():
            shutil.rmtree(stage)
            raise ValueError('工程有未识别的恢复副本，请先核对')
        try:
            shutil.copytree(root, stage, dirs_exist_ok=True)
            for path in stage.rglob('*'):
                path.chmod(0o755 if path.is_dir() else 0o644)
            edit(stage)
            for path in stage.rglob('*'):
                if path.is_file():
                    with path.open('rb') as file:
                        os.fsync(file.fileno())
            for path in sorted((p for p in stage.rglob('*') if p.is_dir()), reverse=True):
                sync_dir(path)
            sync_dir(stage)
            # The exclusive create prevents clobbering any unexpected journal.
            with journal.open('x') as file:
                os.chmod(journal, stat.S_IRUSR | stat.S_IWUSR)
                json.dump({'stage': stage.name}, file)
                file.flush(); os.fsync(file.fileno())
            sync_dir(root.parent)
            os.replace(root, backup)
            os.replace(stage, root)
            sync_dir(root.parent)
        except BaseException:
            if journal.exists():
                _recover(root)
            elif stage.exists():
                shutil.rmtree(stage)
            raise
        _recover(root)
