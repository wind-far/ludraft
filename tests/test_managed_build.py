import asyncio
import json
import os
from pathlib import Path
import tempfile

import pytest

from studio.db import Store
from studio.executor_records import ACTIVE_EXECUTION, ExecutorRecords
from studio.managed_build import run_build
from studio.opengame_executor import ExecutorError
from studio.runner import Runner, RunnerError

IMAGE = 'sha256:' + 'a' * 64
CID = 'b' * 64


class BuildFixture:
    def __init__(self, records, *, hold=False):
        self.records = records
        self.calls = []
        self.row = None
        self.present = False
        self.created = asyncio.Event()
        self.release = asyncio.Event()
        self.hold_create = False
        self.unknown_create = False
        self.fail_cleanup = False
        self.stdout = asyncio.StreamReader()
        self.done = asyncio.Event()
        self.returncode = None
        if not hold:
            self.kill(0)

    def kill(self, code=-9):
        self.returncode = code
        self.stdout.feed_eof()
        self.done.set()

    async def wait(self):
        await self.done.wait()
        return self.returncode

    async def spawn(self, *args, **kwargs):
        self.calls.append(args)
        assert args[:3] == ('docker', 'start', '-a')
        assert self.records.get(self.row['id'])['create_ack'] == 1
        return self

    async def docker(self, *args, **kwargs):
        self.calls.append(args)
        if args[:2] == ('image', 'inspect'):
            return json.dumps([{'Id': IMAGE}]).encode()
        if args[0] == 'create':
            self.row = self.records.store.one("SELECT * FROM executor_attempts WHERE kind='build'")
            assert self.row['state'] == 'creating' and self.row['create_sent'] == 1
            assert 'com.ludraft.parent=' + self.row['parent_id'] in args
            assert args[-1] == IMAGE and '--rm' not in args
            assert args[args.index('--network')+1] == 'none' and '--read-only' in args
            self.present = True
            self.created.set()
            if self.hold_create:
                await self.release.wait()
            if self.unknown_create:
                self.present = False
                raise ExecutorError('timed out; daemon result unknown', uncertain=True)
            return CID.encode()
        if self.fail_cleanup:
            raise ExecutorError('daemon unavailable')
        if args[0] == 'ps':
            return CID.encode() if self.present and self.row['container_name'] in args[-1] else b''
        if args[:2] == ('container', 'inspect'):
            return json.dumps([{'Id': CID, 'Name': '/' + self.row['container_name'], 'Image': IMAGE,
                'Config': {'Labels': {**self.records.labels(self.row), 'com.ludraft.role': 'opengame-build'}}}]).encode()
        if args[:2] == ('rm', '-f'):
            assert args[2] == CID
            self.present = False
            return CID.encode()
        raise AssertionError(args)


@pytest.fixture
def setup_build(tmp_path, monkeypatch):
    store = Store(tmp_path)
    records = ExecutorRecords(store)
    parent = records.begin(IMAGE, 'd' * 32)
    records.state(parent['id'], 'running')
    with tempfile.TemporaryDirectory(prefix='gamedev-runner-', dir='/private/tmp' if os.uname().sysname == 'Darwin' else None) as directory:
        staged = Path(directory).resolve()
        (staged / 'evidence.json').write_text('{"passed":true,"build":true}')
        yield records, parent, staged, monkeypatch
    store.con.close()


def install(setup, **kwargs):
    records, parent, staged, monkeypatch = setup
    fixture = BuildFixture(records, **kwargs)
    monkeypatch.setattr('studio.opengame_executor.docker', fixture.docker)
    monkeypatch.setattr(asyncio, 'create_subprocess_exec', fixture.spawn)
    return fixture


@pytest.mark.asyncio
async def test_child_build_keeps_parent_alive_and_collectable_evidence(setup_build):
    records, parent, staged, _ = setup_build
    fixture = install(setup_build)
    evidence = await run_build(staged, 'fixed-runner:1', (records, parent['id']))
    row = records.get(evidence['build_execution_id'])
    assert row['kind'] == 'build' and row['parent_id'] == parent['id'] and row['run_id'] == 'd' * 32
    assert row['state'] == 'succeeded' and row['cleanup'] == 'removed'
    assert records.get(parent['id'])['state'] == 'running'
    assert staged.exists() and (staged / 'evidence.json').exists()
    await records.recover(fixture.docker)
    assert not staged.exists() and records.get(row['id'])['stage_path'] is None


@pytest.mark.asyncio
async def test_repeated_cancel_waits_for_create_ack_before_cleanup(setup_build):
    records, parent, staged, _ = setup_build
    fixture = install(setup_build, hold=True)
    fixture.hold_create = True
    task = asyncio.create_task(run_build(staged, 'fixed-runner:1', (records, parent['id'])))
    await fixture.created.wait()
    task.cancel()
    await asyncio.sleep(0)
    task.cancel()
    await asyncio.sleep(0)
    assert not task.done() and fixture.present
    fixture.release.set()
    with pytest.raises(asyncio.CancelledError):
        await asyncio.wait_for(task, 2)
    row = records.get(fixture.row['id'])
    assert row['state'] == 'cancelled' and row['create_ack'] == 1 and row['cleanup'] == 'removed'
    assert not fixture.present
    assert not any(call[:2] == ('docker', 'start') for call in fixture.calls)


@pytest.mark.asyncio
async def test_unknown_creation_blocks_next_build_until_restart_cleanup(setup_build):
    records, parent, staged, _ = setup_build
    fixture = install(setup_build)
    fixture.unknown_create = True
    with pytest.raises(RunnerError):
        await run_build(staged, 'fixed-runner:1', (records, parent['id']))
    assert records.get(fixture.row['id'])['cleanup'] == 'unknown'
    with pytest.raises(RuntimeError, match='待确认清理'):
        records.begin(IMAGE, parent_id=parent['id'])
    fixture.present = True
    assert (await records.recover(fixture.docker))['can_start']


@pytest.mark.asyncio
async def test_successful_build_with_failed_cleanup_cannot_be_delivered(setup_build):
    records, parent, staged, _ = setup_build
    fixture = install(setup_build)
    fixture.fail_cleanup = True
    with pytest.raises(RunnerError, match='不能交付'):
        await run_build(staged, 'fixed-runner:1', (records, parent['id']))
    row = records.get(fixture.row['id'])
    assert row['state'] == 'succeeded' and row['cleanup'] == 'unknown'


@pytest.mark.asyncio
async def test_foreign_stage_marker_is_preserved_and_blocks_recovery(setup_build):
    records, parent, staged, _ = setup_build
    fixture = install(setup_build)
    result = await run_build(staged, 'fixed-runner:1', (records, parent['id']))
    (staged / '.ludraft-stage.json').write_text('{"owner":"someone else"}')
    assert not (await records.recover(fixture.docker))['can_start']
    assert staged.exists() and records.get(result['build_execution_id'])['cleanup'] == 'unknown'


@pytest.mark.asyncio
async def test_runner_retains_stage_until_uncertain_container_is_removed(setup_build):
    records, parent, workspace, _ = setup_build
    fixture = install(setup_build)
    fixture.fail_cleanup = True
    token = ACTIVE_EXECUTION.set((records, parent['id']))
    try:
        with pytest.raises(RunnerError, match='不能交付'):
            await Runner().run(workspace, 'fixture')
        staged = Path(fixture.row['stage_path'])
        assert staged != workspace and staged.is_dir()
        assert fixture.present
        fixture.fail_cleanup = False
        assert (await records.recover(fixture.docker))['can_start']
        assert not staged.exists() and workspace.is_dir()
    finally:
        ACTIVE_EXECUTION.reset(token)


def test_previous_cli_schema_migrates_without_changing_records(tmp_path):
    store = Store(tmp_path)
    store.execute('''CREATE TABLE executor_attempts(id TEXT PRIMARY KEY,run_id TEXT,
        container_name TEXT UNIQUE NOT NULL,image_id TEXT NOT NULL,owner TEXT NOT NULL,state TEXT NOT NULL,
        cleanup TEXT NOT NULL,create_ack INTEGER NOT NULL DEFAULT 0,create_sent INTEGER NOT NULL DEFAULT 0,
        reason TEXT,created_at TEXT NOT NULL,updated_at TEXT NOT NULL)''')
    store.execute("INSERT INTO executor_attempts(id,container_name,image_id,owner,state,cleanup,created_at,updated_at) VALUES('old','old',?,'owner','cancelled','removed','then','then')", (IMAGE,))
    try:
        records = ExecutorRecords(store)
        assert records.get('old')['kind'] == 'cli' and records.get('old')['state'] == 'cancelled'
        assert ExecutorRecords(store).get('old') == records.get('old')
    finally:
        store.con.close()
