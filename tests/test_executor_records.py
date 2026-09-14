import asyncio
import json

from fastapi.testclient import TestClient
import pytest

from studio.db import Store
from studio.executor_records import ExecutorRecords
from studio.opengame_executor import ExecutorError, OpenGameExecutor

IMAGE = 'sha256:' + 'a' * 64
CID = 'b' * 64


class DockerFixture:
    def __init__(self, records, row):
        self.calls = []
        self.present = True
        self.info = {'Id': CID, 'Name': '/' + row['container_name'], 'Image': IMAGE,
                     'Config': {'Labels': {**records.labels(row), 'com.ludraft.role': 'opengame-executor'}}}

    async def __call__(self, *args, **kwargs):
        self.calls.append(args)
        if args[0] == 'ps':
            return CID.encode() if self.present else b''
        if args[:2] == ('container', 'inspect'):
            return json.dumps([self.info]).encode()
        if args[:2] == ('rm', '-f'):
            assert args[2] == CID
            self.present = False
            return CID.encode()
        raise AssertionError(args)


@pytest.fixture
def record(tmp_path):
    store = Store(tmp_path)
    records = ExecutorRecords(store)
    row = records.begin(IMAGE, 'd' * 32)
    yield records, row
    store.con.close()


@pytest.mark.asyncio
async def test_restart_removes_only_verified_owned_id_and_retains_interruption(record):
    records, row = record
    records.state(row['id'], 'created')
    fixture = DockerFixture(records, row)
    reopened = Store(records.store.root)
    try:
        restored = ExecutorRecords(reopened)
        with restored.lease():
            result = await restored.recover(fixture)
        assert result['can_start'] and not fixture.present
        assert restored.get(row['id'])['state'] == 'interrupted'
        assert restored.get(row['id'])['cleanup'] == 'removed'
        assert fixture.calls[-1] == ('rm', '-f', CID)
        assert await restored.recover(fixture) == result  # Idempotent, no extra Docker calls.
        assert len(fixture.calls) == 3
    finally:
        reopened.con.close()


@pytest.mark.asyncio
@pytest.mark.parametrize('field', ['owner', 'attempt', 'role', 'image', 'name', 'id'])
async def test_mismatch_never_removes_foreign_container(record, field):
    records, row = record
    records.state(row['id'], 'creating')
    fixture = DockerFixture(records, row)
    if field in ('owner', 'attempt', 'role'):
        fixture.info['Config']['Labels']['com.ludraft.' + field] = 'foreign'
    else:
        fixture.info[{'image':'Image', 'name':'Name', 'id':'Id'}[field]] = 'foreign'
    result = await records.recover(fixture)
    assert not result['can_start'] and result['pending_cleanup'] == 1
    assert not any(call[0] == 'rm' for call in fixture.calls)


@pytest.mark.asyncio
async def test_daemon_failure_survives_reopen_and_blocks_new_execution(record):
    records, row = record
    records.state(row['id'], 'created')
    async def unavailable(*args, **kwargs):
        raise ExecutorError('DO-NOT-LOG-SECRET')
    assert not (await records.recover(unavailable))['can_start']
    reopened = Store(records.store.root)
    try:
        restored = ExecutorRecords(reopened)
        with pytest.raises(RuntimeError, match='待确认清理'):
            restored.begin(IMAGE)
        assert 'DO-NOT-LOG' not in json.dumps(restored.summary())
        fixture = DockerFixture(restored, row)
        fixture.present = False
        assert (await restored.recover(fixture))['can_start']
    finally:
        reopened.con.close()


@pytest.mark.asyncio
async def test_unacknowledged_create_absence_remains_unknown_until_owned_container_appears(record):
    records, row = record
    records.state(row['id'], 'creating')
    fixture = DockerFixture(records, row)
    fixture.present = False
    for _ in range(2):
        assert not (await records.recover(fixture))['can_start']
    fixture.present = True
    assert (await records.recover(fixture))['can_start']
    assert not fixture.present


@pytest.mark.asyncio
async def test_prepared_intent_is_safe_even_after_failed_recovery(record):
    records, row = record
    async def unavailable(*args, **kwargs):
        raise ExecutorError('offline')
    await records.recover(unavailable)
    fixture = DockerFixture(records, row)
    fixture.present = False
    assert (await records.recover(fixture))['can_start']


@pytest.mark.asyncio
async def test_busy_owner_prevents_recovery_from_other_instance(record, monkeypatch):
    records, row = record
    engine = OpenGameExecutor(records.store)
    async def forbidden(*args, **kwargs):
        raise AssertionError('must not inspect active container')
    monkeypatch.setattr('studio.opengame_executor.docker', forbidden)
    with records.lease():
        result = await engine.recover()
    assert result['busy'] and not result['can_start']


def test_startup_recovery_and_readonly_execution_status(tmp_path, monkeypatch):
    from studio.app import create_app
    app = create_app(tmp_path)
    records = app.state.workflow.opengame.records
    row = records.begin(IMAGE)
    records.state(row['id'], 'created')
    fixture = DockerFixture(records, row)
    monkeypatch.setattr('studio.opengame_executor.docker', fixture)
    with TestClient(app) as client:
        result = client.get('/api/settings/opengame/executions').json()
        assert result['can_start'] and result['attempts'][0]['state'] == 'interrupted'
        assert not fixture.present
        assert client.post('/api/settings/opengame/recover').status_code == 200
        assert client.post('/api/settings/opengame/recover', headers={'Origin':'null'}).status_code == 403


def test_second_app_startup_does_not_interrupt_live_owner(tmp_path):
    from studio.app import create_app
    app = create_app(tmp_path)
    store = Store(tmp_path)
    records = app.state.workflow.opengame.records
    store.execute("INSERT INTO runs(id,project_id,status) VALUES(?,?,'running')", ('d' * 32, 'p'))
    try:
        with records.lease(), pytest.raises(RuntimeError, match='重复启动'):
            with TestClient(app):
                pass
        assert store.run('d' * 32)['status'] == 'running'
    finally:
        store.con.close()
