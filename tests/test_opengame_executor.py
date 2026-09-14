import asyncio
import base64
import hashlib
import json

import httpx
import pytest

import studio.opengame_executor as executor_module
from studio.budget import BudgetLedger, connection_key
from studio.files import copy_source
from studio.opengame import CLI_SHA256, UPSTREAM_COMMIT
from studio.opengame_executor import BRIDGE, ExecutorError, OpenGameExecutor, create_args, decode64, relay_request, verified_image
from studio.opengame_proxy import ModelProxy
from studio.opengame_tools import CandidateTools, TOOL_MODELS, create_tool_app
from studio.template_registry import TEMPLATES


@pytest.fixture
def context(tmp_path):
    root = tmp_path.resolve() / 'candidate'
    copy_source(TEMPLATES['phaser-tower_defense'].source, root)
    session = CandidateTools(root, writable_paths={'src/config.ts'})
    cfg = {'provider': 'openai', 'base_url': 'https://fixture.invalid/v1', 'model': 'fixture',
           'api_key': 'PROVIDER-KEY-NOT-FOR-CONTAINER', 'max_tokens': 512}
    ledger = BudgetLedger(tmp_path / 'ledger'); ledger.configure('1')
    ledger.set_price(connection_key(cfg), '1', '2', 'test only')
    proxy = ModelProxy(cfg, ledger, allowed_tools=TOOL_MODELS, deadline=session.deadline, active=session.active,
                       transport=httpx.MockTransport(lambda request: httpx.Response(500)))
    return session, proxy


def test_container_arguments_do_not_grant_host_or_network_access():
    args = create_args('sha256:' + 'a' * 64, 'gamedev-opengame-example')
    assert args[args.index('--network') + 1] == 'none'
    assert '--read-only' in args and args[args.index('--user')+1] == '1000:1000'
    assert args[args.index('--cap-drop')+1] == 'ALL'
    assert args[args.index('--security-opt')+1] == 'no-new-privileges'
    assert args[args.index('--log-driver')+1] == 'none'
    assert not {'--mount', '--volume', '-v', '--publish', '-p', '--privileged', '--env', '-e'} & set(args)
    assert 'noexec' in args[args.index('--tmpfs')+1]


@pytest.mark.asyncio
async def test_image_must_match_commit_bundle_and_bridge(monkeypatch):
    labels = {'com.ludraft.opengame.commit': UPSTREAM_COMMIT,
              'com.ludraft.opengame.cli-sha256': CLI_SHA256,
              'com.ludraft.opengame.bridge-sha256': hashlib.sha256(BRIDGE.read_bytes()).hexdigest()}
    async def inspect(*args, **kwargs):
        return json.dumps([{'Id': 'sha256:' + 'a'*64, 'Config': {'Labels': labels}}]).encode()
    monkeypatch.setattr(executor_module, 'docker', inspect)
    assert await verified_image() == 'sha256:' + 'a'*64
    labels['com.ludraft.opengame.bridge-sha256'] = 'old bridge'
    with pytest.raises(ExecutorError, match='不匹配'):
        await verified_image()


def frame(session, data=None, **changes):
    value = {'kind': 'http', 'id': 1, 'method': 'POST', 'path': '/mcp',
             'headers': {'authorization': 'Bearer ' + session.token, 'accept': 'application/json, text/event-stream',
                         'content-type': 'application/json', 'mcp-protocol-version': '2025-06-18'},
             'body': base64.b64encode(json.dumps(data or {'jsonrpc': '2.0', 'id': 1, 'method': 'tools/list'}).encode()).decode()}
    return {**value, **changes}


@pytest.mark.asyncio
async def test_stdio_relay_reaches_only_candidate_mcp_and_preserves_auth(context):
    session, proxy = context
    app = create_tool_app(session, model_proxy=proxy)
    emitted = []
    async def emit(value):
        emitted.append(value)
    await relay_request(app, frame(session), emit)
    assert emitted[0]['status'] == 200 and emitted[-1]['kind'] == 'http_end'
    body = b''.join(base64.b64decode(f['data']) for f in emitted if f['kind'] == 'http_body')
    assert len(json.loads(body)['result']['tools']) == 4
    emitted.clear()
    invalid = frame(session); invalid['headers']['authorization'] = 'Bearer wrong'
    await relay_request(app, invalid, emit)
    assert emitted[0]['status'] == 401


@pytest.mark.asyncio
@pytest.mark.parametrize('changes', [
    {'path': '/api/settings'}, {'path': 'http://example.com/mcp'}, {'path': '/mcp?url=elsewhere'},
    {'method': 'DELETE'}, {'headers': {'host': 'attacker'}}, {'headers': {'authorization': 'bad\nheader'}},
    {'body': 'invalid base64!'},
])
async def test_stdio_relay_rejects_untrusted_routes_and_frames(context, changes):
    async def forbidden(*args):
        raise AssertionError('must not reach application')
    with pytest.raises(ExecutorError):
        await relay_request(forbidden, frame(context[0], **changes), forbidden)


class HeldStream(httpx.AsyncByteStream):
    def __init__(self):
        self.release = asyncio.Event()
        self.closed = False

    async def __aiter__(self):
        yield b'data: {"choices":[{"index":0,"delta":{"content":"first"}}]}\n\n'
        await self.release.wait()
        yield b'data: {"choices":[{"index":0,"delta":{},"finish_reason":"stop"}]}\n\ndata: [DONE]\n\n'

    async def aclose(self):
        self.closed = True


@pytest.mark.asyncio
async def test_stdio_relay_forwards_first_stream_chunk_before_upstream_finishes(context):
    session, proxy = context
    source = HeldStream()
    proxy.transport = httpx.MockTransport(lambda req: httpx.Response(200, headers={'content-type':'text/event-stream'}, stream=source))
    app = create_tool_app(session, model_proxy=proxy)
    first, emitted = asyncio.Event(), []
    async def emit(value):
        emitted.append(value)
        if value['kind'] == 'http_body': first.set()
    req = frame(session, {'model': 'fixture', 'stream': True, 'messages':[{'role':'user','content':'test'}]}, path='/v1/chat/completions')
    running = asyncio.create_task(relay_request(app, req, emit))
    await asyncio.wait_for(first.wait(), 1)
    assert not running.done() and not source.release.is_set()
    source.release.set()
    await running
    assert emitted[-1]['kind'] == 'http_end' and source.closed
    assert proxy.ledger.summary()['unsettled_calls'] == 1  # No usage was supplied.


class FakeInput:
    def __init__(self):
        self.values = []
        self.sent = asyncio.Event()

    def write(self, data):
        self.values.append(json.loads(data))

    async def drain(self):
        self.sent.set()


class FakeProcess:
    def __init__(self, frames, hold=False):
        self.stdin = FakeInput()
        self.stdout, self.stderr = asyncio.StreamReader(), asyncio.StreamReader()
        for f in frames:
            self.stdout.feed_data((json.dumps(f)+'\n').encode())
        self.done = asyncio.Event()
        self.returncode = None
        if not hold:
            self.kill(code=0)

    def kill(self, code=-9):
        self.returncode = code
        self.stdout.feed_eof(); self.stderr.feed_eof(); self.done.set()

    async def wait(self):
        await self.done.wait()
        return self.returncode


def successful_frames():
    result = {'type':'result', 'session_id':'fixture', 'subtype':'success', 'is_error':False,
              'num_turns':0, 'permission_denials':[], 'usage':{}}
    return [{'kind':'ready','protocol':1}, {'kind':'started'},
            {'kind':'event','data':base64.b64encode((json.dumps(result)+'\n').encode()).decode()}, {'kind':'exit','code':0}]


def mock_docker(monkeypatch, process, *, cleanup_fails=False):
    calls = []
    async def operation(*args, **kwargs):
        calls.append(args)
        if cleanup_fails and args[0] in ('rm','ps'):
            raise ExecutorError('daemon unavailable')
        return b''
    async def image():
        return 'sha256:'+'a'*64
    async def spawn(*args, **kwargs):
        calls.append(args)
        return process
    monkeypatch.setattr(executor_module, 'docker', operation)
    monkeypatch.setattr(executor_module, 'verified_image', image)
    monkeypatch.setattr(executor_module.asyncio, 'create_subprocess_exec', spawn)
    return calls


@pytest.mark.asyncio
async def test_executor_passes_only_task_token_and_removes_container(context, monkeypatch):
    process = FakeProcess(successful_frames())
    calls = mock_docker(monkeypatch, process)
    engine = OpenGameExecutor()
    report = await engine.run(*context, 'controlled request')
    assert report['execution_completed'] and not report['gameplay_verified']
    launch = process.stdin.values[0]
    assert launch['token'] == context[0].token and launch['model'] == 'fixture'
    assert 'PROVIDER-KEY' not in json.dumps(launch)
    assert any(c[0] == 'rm' and c[1] == '-f' for c in calls)
    assert engine.container_name is None and context[0].closed and context[1].closed


@pytest.mark.asyncio
async def test_durable_execution_persists_intent_before_dispatch_and_safe_result(context, monkeypatch, tmp_path):
    from studio.db import Store
    process = FakeProcess(successful_frames())
    calls = mock_docker(monkeypatch, process)
    store = Store(tmp_path / 'persistent-executor')
    engine = OpenGameExecutor(store)
    original = executor_module.docker
    async def checked(*args, **kwargs):
        if args[0] == 'create':
            rows = engine.records.pending()
            assert len(rows) == 1 and rows[0]['state'] == 'creating'
            assert 'com.ludraft.owner=' + engine.records.owner in args
            assert 'com.ludraft.attempt=' + rows[0]['id'] in args
        return await original(*args, **kwargs)
    monkeypatch.setattr(executor_module, 'docker', checked)
    try:
        report = await engine.run(*context, 'PRIVATE PROMPT', run_id='d' * 32)
        row = engine.records.get(report['execution_id'])
        assert row['run_id'] == 'd' * 32 and row['state'] == 'succeeded'
        assert row['cleanup'] == 'removed' and row['create_ack'] == 1
        assert 'PRIVATE PROMPT' not in json.dumps(row) and context[0].token not in json.dumps(row)
        assert 'PROVIDER-KEY' not in json.dumps(row)
    finally:
        store.con.close()


@pytest.mark.asyncio
async def test_cancel_waits_for_task_revocation_and_container_removal(context, monkeypatch):
    process = FakeProcess(successful_frames()[:2], hold=True)
    calls = mock_docker(monkeypatch, process)
    engine = OpenGameExecutor()
    running = asyncio.create_task(engine.run(*context, 'controlled request'))
    await process.stdin.sent.wait()
    running.cancel()
    with pytest.raises(asyncio.CancelledError):
        await running
    assert context[0].closed and context[1].closed and process.returncode is not None
    assert any(c[0] == 'rm' for c in calls) and engine.container_name is None


@pytest.mark.asyncio
async def test_daemon_error_does_not_masquerade_as_cleanup_success(context, monkeypatch):
    process = FakeProcess(successful_frames())
    mock_docker(monkeypatch, process, cleanup_fails=True)
    engine = OpenGameExecutor()
    with pytest.raises(ExecutorError, match='清理'):
        await engine.run(*context, 'controlled request')
    assert engine.container_name == engine.last_container_name
    assert engine.cleanup_errors


@pytest.mark.asyncio
async def test_malformed_control_stream_still_cleans_container(context, monkeypatch):
    process = FakeProcess([{'kind':'http','id':1}])
    calls = mock_docker(monkeypatch, process)
    with pytest.raises(ExecutorError):
        await OpenGameExecutor().run(*context, 'controlled request')
    assert any(c[0] == 'rm' for c in calls) and context[0].closed


@pytest.mark.asyncio
async def test_cancel_during_create_waits_for_daemon_result_before_removal(context, monkeypatch):
    started, release = asyncio.Event(), asyncio.Event()
    actions = []
    async def operation(*args, **kwargs):
        if args[0] == 'create':
            started.set()
            await release.wait()
            actions.append('created')
        else:
            actions.append(args[0])
        return b''
    async def image(): return 'sha256:'+'a'*64
    monkeypatch.setattr(executor_module,'docker',operation)
    monkeypatch.setattr(executor_module,'verified_image',image)
    running=asyncio.create_task(OpenGameExecutor().run(*context,'controlled request'))
    await started.wait();running.cancel();await asyncio.sleep(0)
    assert not running.done() and not actions
    release.set()
    with pytest.raises(asyncio.CancelledError):await running
    assert actions == ['created','rm']
    assert context[0].closed and context[1].closed


@pytest.mark.asyncio
async def test_unknown_create_outcome_is_not_cleared_by_one_empty_listing(context, monkeypatch):
    async def operation(*args, **kwargs):
        if args[0]=='create':raise ExecutorError('create timed out',uncertain=True)
        if args[0]=='rm':raise ExecutorError('not found yet')
        return b''
    async def image():return 'sha256:'+'a'*64
    monkeypatch.setattr(executor_module,'docker',operation)
    monkeypatch.setattr(executor_module,'verified_image',image)
    engine=OpenGameExecutor()
    with pytest.raises(ExecutorError):await engine.run(*context,'controlled request')
    assert engine.cleanup_errors and engine.container_name is not None


def test_base64_bounds():
    assert decode64('YWJj',3) == b'abc'
    with pytest.raises(ExecutorError): decode64('YWJj',2)
