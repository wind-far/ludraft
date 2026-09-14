import asyncio
import json
import time

import httpx
import pytest

from studio.files import copy_source
from studio.opengame_tools import CandidateTools, MAX_BODY, PROTOCOL, create_tool_app
from studio.project_files import source_digest
from studio.template_registry import TEMPLATES


def payload(result):
    return json.loads(result['content'][0]['text'])


class FakeRunner:
    def __init__(self):
        self.calls = 0

    async def run(self, root, run_id):
        self.calls += 1
        return {'passed': False, 'scope': 'phaser-integration-smoke',
                'log': 'src/config.ts(1,1): error TS1005: expected token', 'checks': []}


@pytest.fixture
def session(tmp_path):
    root = tmp_path.resolve() / 'candidate'
    copy_source(TEMPLATES['phaser-tower_defense'].source, root)
    return CandidateTools(root, writable_paths={'src/config.ts', 'src/entities/IceTower.ts'}, runner=FakeRunner())


def change(session, content='export const damage = 2;'):
    return {'summary': 'adjust damage', 'base_digest': source_digest(session.root),
            'files': [{'operation': 'update', 'path': 'src/config.ts', 'content': content}]}


@pytest.mark.asyncio
async def test_inventory_read_edit_and_idempotent_retransmission(session):
    listed = payload(await session.call(1, 'project_inventory', {'limit': 1}))
    assert len(listed['files']) == 1 and listed['next_offset'] == 1
    assert listed['source_digest'] == source_digest(session.root)
    assert listed['writable_paths'] == ['src/config.ts', 'src/entities/IceTower.ts']
    original = (session.root / 'src/config.ts').read_text()
    read = payload(await session.call(2, 'project_read', {'path': 'src/config.ts', 'limit': 10}))
    assert read['content'] == original[:10] and read['next_offset'] == 10
    args = change(session)
    first, duplicate = await asyncio.gather(session.call(3, 'project_apply', args), session.call(3, 'project_apply', args))
    assert first == duplicate and not first['isError']
    assert session.calls == 3
    assert (session.root / 'src/config.ts').read_text() == args['files'][0]['content']
    conflict = await session.call(3, 'project_apply', change(session, 'different'))
    assert conflict['isError'] and '请求标识' in payload(conflict)['error']
    stale = await session.call(4, 'project_apply', args)
    assert stale['isError'] and '项目已变化' in payload(stale)['error']


@pytest.mark.asyncio
@pytest.mark.parametrize('path', ['../outside.txt', '/etc/passwd', '.env', 'dist/index.html', 'public/assets/tower.png'])
async def test_reads_cannot_escape_source_inventory(session, path):
    result = await session.call(1, 'project_read', {'path': path})
    assert result['isError']


@pytest.mark.asyncio
async def test_task_scope_and_invalid_batch_never_partially_commit(session):
    before = source_digest(session.root)
    args = change(session)
    args['files'].append({'operation': 'create', 'path': 'src/entities/Other.ts', 'content': 'outside task'})
    result = await session.call(1, 'project_apply', args)
    assert result['isError'] and source_digest(session.root) == before
    args['files'][1]['path'] = 'src/entities/IceTower.ts'
    result = await session.call(2, 'project_apply', args)
    assert not result['isError']
    delete = {'summary': 'remove', 'base_digest': source_digest(session.root),
              'files': [{'operation': 'delete', 'path': 'src/entities/IceTower.ts'}]}
    assert not (await session.call(3, 'project_apply', delete))['isError']
    assert not (session.root / 'src/entities/IceTower.ts').exists()


@pytest.mark.asyncio
async def test_error_can_be_read_then_repaired_and_reverified(session):
    assert not (await session.call(1, 'project_apply', change(session, 'invalid TS')))['isError']
    first = payload(await session.call(2, 'project_verify', {'base_digest': source_digest(session.root)}))
    assert not first['passed'] and 'TS1005' in first['log']
    assert not first['publication_approved']
    assert not (await session.call(3, 'project_apply', change(session)))['isError']
    second = payload(await session.call(4, 'project_verify', {'base_digest': source_digest(session.root)}))
    assert second['diagnostic_attempt'] == 2


@pytest.mark.asyncio
async def test_diagnostic_limit_and_dedup_prevent_extra_builds(session):
    args = {'base_digest': source_digest(session.root)}
    first = await session.call(1, 'project_verify', args)
    assert await session.call(1, 'project_verify', args) == first
    for request_id in range(2, 7):
        assert not (await session.call(request_id, 'project_verify', args))['isError']
    assert (await session.call(7, 'project_verify', args))['isError']
    assert session.runner.calls == 6


class WaitingRunner:
    def __init__(self):
        self.started = asyncio.Event()
        self.cleaned = asyncio.Event()

    async def run(self, root, run_id):
        self.started.set()
        try:
            await asyncio.Event().wait()
        finally:
            await asyncio.sleep(0)
            self.cleaned.set()


@pytest.mark.asyncio
async def test_close_waits_for_runner_cleanup_and_denies_queued_writes(session):
    session.runner = WaitingRunner()
    before = source_digest(session.root)
    running = asyncio.create_task(session.call(1, 'project_verify', {'base_digest': before}))
    await session.runner.started.wait()
    queued = asyncio.create_task(session.call(2, 'project_apply', change(session)))
    await asyncio.sleep(0)
    await session.close()
    assert session.runner.cleaned.is_set()
    assert (await running)['isError'] and (await queued)['isError']
    assert source_digest(session.root) == before
    assert (await session.call(3, 'project_inventory', {}))['isError']


@pytest.mark.asyncio
async def test_lost_http_waiter_does_not_cancel_runner(session):
    session.runner = WaitingRunner()
    args = {'base_digest': source_digest(session.root)}
    waiter = asyncio.create_task(session.call(1, 'project_verify', args))
    await session.runner.started.wait()
    waiter.cancel()
    with pytest.raises(asyncio.CancelledError):
        await waiter
    assert not session.runner.cleaned.is_set()
    session.cancel_request(1)
    result = await session.call(1, 'project_verify', args)
    assert result['isError'] and session.runner.cleaned.is_set()


@pytest.mark.asyncio
async def test_repeated_cancel_and_close_do_not_interrupt_cleanup(session):
    entered_cleanup, release_cleanup = asyncio.Event(), asyncio.Event()

    class CleanupRunner(WaitingRunner):
        async def run(self, root, run_id):
            self.started.set()
            try:
                await asyncio.Event().wait()
            finally:
                entered_cleanup.set()
                await release_cleanup.wait()
                self.cleaned.set()

    session.runner = CleanupRunner()
    running = asyncio.create_task(session.call(1, 'project_verify', {'base_digest': source_digest(session.root)}))
    await session.runner.started.wait()
    session.cancel_request(1)
    await entered_cleanup.wait()
    session.cancel_request(1)
    closing = asyncio.create_task(session.close())
    await asyncio.sleep(0)
    assert not closing.done()
    release_cleanup.set()
    await closing
    assert session.runner.cleaned.is_set() and (await running)['isError']


@pytest.mark.asyncio
async def test_call_limit_counts_invalid_calls_without_running_more(session):
    for i in range(200):
        assert (await session.call(i, 'shell', {}))['isError']
    assert '上限' in payload(await session.call(200, 'project_inventory', {}))['error']
    assert session.calls == 200


@pytest.mark.asyncio
async def test_expiry_stops_active_runner_and_future_calls(session):
    session.deadline = time.monotonic() + 0.05
    session.runner = WaitingRunner()
    result = await session.call(1, 'project_verify', {'base_digest': source_digest(session.root)})
    assert result['isError'] and session.runner.cleaned.is_set()
    assert (await session.call(2, 'project_inventory', {}))['isError']


@pytest.mark.asyncio
async def test_validation_no_input_echo_and_symlink_denied(session, tmp_path):
    secret = 'private-input-that-must-not-be-echoed'
    result = await session.call(1, 'project_read', {'path': 'src/config.ts', 'extra': secret})
    assert result['isError'] and secret not in json.dumps(result)
    (tmp_path / 'outside.ts').write_text(secret)
    (session.root / 'src/entities/link.ts').symlink_to(tmp_path / 'outside.ts')
    result = await session.call(2, 'project_read', {'path': 'src/entities/link.ts'})
    assert result['isError'] and secret not in json.dumps(result)


@pytest.mark.asyncio
async def test_mcp_transport_auth_protocol_and_four_tools(session):
    app = create_tool_app(session)
    headers = {'Authorization': 'Bearer ' + session.token,
               'Accept': 'application/json, text/event-stream'}
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url='http://localhost', headers=headers) as client:
        init = {'jsonrpc': '2.0', 'id': 1, 'method': 'initialize',
                'params': {'protocolVersion': '2025-11-25', 'capabilities': {}, 'clientInfo': {'name': 'test', 'version': '1'}}}
        response = await client.post('/mcp', json=init)
        assert response.json()['result']['protocolVersion'] == PROTOCOL
        client.headers['MCP-Protocol-Version'] = PROTOCOL
        initialized = await client.post('/mcp', json={'jsonrpc': '2.0', 'method': 'notifications/initialized'})
        assert initialized.status_code == 202 and not initialized.content
        listing = await client.post('/mcp', json={'jsonrpc': '2.0', 'id': 2, 'method': 'tools/list'})
        assert {t['name'] for t in listing.json()['result']['tools']} == {'project_inventory', 'project_read', 'project_apply', 'project_verify'}
        assert (await client.get('/mcp')).status_code == 405
        call = {'jsonrpc': '2.0', 'id': 3, 'method': 'tools/call', 'params': {'name': 'project_inventory'}}
        assert not (await client.post('/mcp', json=call)).json()['result']['isError']
        for override, status in [({'Origin': 'null'}, 403), ({'Origin': 'http://localhost'}, 403),
                                 ({'Authorization': 'Bearer wrong'}, 401), ({'Host': 'evil.test'}, 400),
                                 ({'MCP-Protocol-Version': 'bad'}, 400), ({'Accept': 'text/html'}, 406)]:
            assert (await client.post('/mcp', json=call, headers=override)).status_code == status
        assert (await client.post('/mcp', content=b'x' * (MAX_BODY + 1), headers={'Content-Type': 'application/json'})).status_code == 413
        assert (await client.post('/mcp', json=[call])).status_code == 400
        assert (await client.post('/mcp', json={**call, 'id': None})).status_code == 400
        for invalid in (b'{"jsonrpc":"2.0","params":{"offset":NaN}}', b'[' * 2000 + b']' * 2000):
            assert (await client.post('/mcp', content=invalid, headers={'Content-Type': 'application/json'})).status_code == 400
        await session.close()
        assert (await client.post('/mcp', json=call)).status_code == 410


@pytest.mark.asyncio
async def test_mcp_cancel_notification_stops_matching_diagnostic(session):
    session.runner = WaitingRunner()
    headers = {'Authorization': 'Bearer ' + session.token, 'Accept': 'application/json, text/event-stream',
               'MCP-Protocol-Version': PROTOCOL}
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=create_tool_app(session)), base_url='http://localhost', headers=headers) as client:
        request = asyncio.create_task(client.post('/mcp', json={'jsonrpc': '2.0', 'id': 'build', 'method': 'tools/call',
            'params': {'name': 'project_verify', 'arguments': {'base_digest': source_digest(session.root)}}}))
        await session.runner.started.wait()
        cancel = await client.post('/mcp', json={'jsonrpc': '2.0', 'method': 'notifications/cancelled', 'params': {'requestId': 'build'}})
        assert cancel.status_code == 202
        assert (await request).json()['result']['isError']
        assert session.runner.cleaned.is_set()
