import asyncio
import json
import time

import httpx
import pytest
from starlette.requests import Request

from studio.budget import BudgetLedger, connection_key
from studio.files import copy_source
from studio.opengame_proxy import MAX_REQUEST, ModelProxy, SSEDecoder
from studio.opengame_tools import CandidateTools, TOOL_MODELS, create_tool_app
from studio.template_registry import TEMPLATES

CONFIG = {'provider': 'openai', 'base_url': 'https://provider.example/v1', 'model': 'coding-test',
          'api_key': 'SUPPLIER-SECRET', 'max_tokens': 512}
USAGE = {'prompt_tokens': 100, 'completion_tokens': 20, 'total_tokens': 120}


def request(data, *, query=b''):
    body = json.dumps(data).encode()
    async def receive():
        return {'type': 'http.request', 'body': body, 'more_body': False}
    return Request({'type': 'http', 'method': 'POST', 'path': '/v1/chat/completions',
                    'query_string': query, 'headers': [(b'content-type', b'application/json')]}, receive)


def prompt(**extra):
    return {'model': 'coding-test', 'messages': [{'role': 'user', 'content': 'test request'}], **extra}


def completion(usage=USAGE):
    return {'id': 'fixture', 'object': 'chat.completion', 'model': 'coding-test',
            'choices': [{'index': 0, 'message': {'role': 'assistant', 'content': 'OK'}, 'finish_reason': 'stop'}],
            'usage': usage}


def event(value):
    return ('data: ' + (value if isinstance(value, str) else json.dumps(value, ensure_ascii=False)) + '\n\n').encode()


def frames(*, usage=USAGE, done=True):
    values = [event({'id': 'fixture', 'choices': [{'index': 0, 'delta': {'content': '塔'}, 'finish_reason': None}]}),
              event({'id': 'fixture', 'choices': [{'index': 0, 'delta': {}, 'finish_reason': 'stop'}]})]
    if usage is not None:
        values.append(event({'choices': [], 'usage': usage}))
    if done:
        values.append(event('[DONE]'))
    return values


class BytesStream(httpx.AsyncByteStream):
    def __init__(self, chunks):
        self.chunks = chunks
        self.closed = False

    async def __aiter__(self):
        for chunk in self.chunks:
            yield chunk

    async def aclose(self):
        self.closed = True


@pytest.fixture
def setup(tmp_path):
    ledger = BudgetLedger(tmp_path / 'budget')
    ledger.configure('1')
    ledger.set_price(connection_key(CONFIG), '1', '2', 'offline fixture pricing')
    root = tmp_path.resolve() / 'candidate'
    copy_source(TEMPLATES['phaser-tower_defense'].source, root)
    session = CandidateTools(root, writable_paths={'src/config.ts'})
    return ledger, session


def proxy_for(setup, handler):
    ledger, session = setup
    return ModelProxy(CONFIG, ledger, allowed_tools=TOOL_MODELS, deadline=session.deadline,
                      active=session.active, transport=httpx.MockTransport(handler))


@pytest.mark.asyncio
async def test_reserve_before_http_and_snapshot_route_credentials_limits(setup):
    ledger, session = setup
    async def upstream(req):
        assert ledger.history()[0]['state'] == 'reserved'
        assert str(req.url) == CONFIG['base_url'] + '/chat/completions'
        assert req.headers['authorization'] == 'Bearer SUPPLIER-SECRET'
        body = json.loads(req.content)
        assert body['model'] == 'coding-test' and body['max_tokens'] == 512
        assert 'x-forwarded-host' not in req.headers
        return httpx.Response(200, json={**completion(), 'provider_metadata': 'SUPPLIER-SECRET'})
    proxy = proxy_for(setup, upstream)
    response = await proxy.handle(request(prompt()))
    assert response.status_code == 200
    assert 'SUPPLIER-SECRET' not in response.body.decode()
    assert ledger.summary()['settled_cny'] == 0.00014
    assert ledger.summary()['calls'] == 1
    assert 'SUPPLIER-SECRET' not in str(ledger.history())
    assert ledger.history()[0]['output_limit'] == 512
    await proxy.close()


@pytest.mark.asyncio
@pytest.mark.parametrize('streaming', [False, True])
async def test_unlimited_proxy_dispatches_unpriced_and_records_usage(setup, tmp_path, streaming):
    _, session = setup
    ledger = BudgetLedger(tmp_path / 'unlimited')
    ledger.unlimited()
    async def upstream(req):
        assert ledger.history()[0]['state'] == 'unpriced'
        if streaming:
            return httpx.Response(200, headers={'content-type':'text/event-stream'}, stream=BytesStream(frames()))
        return httpx.Response(200, json=completion())
    proxy = proxy_for((ledger, session), upstream)
    try:
        response = await proxy.handle(request(prompt(stream=streaming)))
        assert response.status_code == 200
        if streaming:
            async for _ in response.body_iterator:
                pass
    finally:
        await proxy.close()
    row = ledger.history()[0]
    assert row['state'] == 'unpriced' and row['actual'] is None
    assert row['prompt_tokens'] == USAGE['prompt_tokens']
    assert row['completion_tokens'] == USAGE['completion_tokens']
    assert ledger.summary()['unpriced_calls'] == 1


@pytest.mark.asyncio
@pytest.mark.parametrize('extra', [
    {'model': 'different'}, {'base_url': 'https://attacker.example'}, {'max_tokens': 513}, {'max_tokens': True},
    {'n': 2}, {'stream': 'true'}, {'temperature': {'bad': 1}}, {'temperature': float('nan')},
    {'tools': [{'type': 'function', 'function': {'name': 'shell'}}]},
    {'messages': [{'role': 'user', 'content': [{'type': 'image_url', 'image_url': {'url': 'https://image.example'}}]}]},
    {'tool_choice': {'type': 'function', 'function': {'name': 'shell'}}},
])
async def test_invalid_requests_never_reserve_or_contact_provider(setup, extra):
    def forbidden(req):
        raise AssertionError('must not call upstream')
    proxy = proxy_for(setup, forbidden)
    assert (await proxy.handle(request(prompt(**extra)))).status_code == 400
    assert setup[0].summary()['calls'] == 0


@pytest.mark.asyncio
async def test_missing_budget_or_price_blocks_dispatch(setup, tmp_path):
    def forbidden(req):
        raise AssertionError('must not call upstream')
    proxy = proxy_for(setup, forbidden)
    proxy.ledger = BudgetLedger(tmp_path / 'unconfigured')
    assert (await proxy.handle(request(prompt()))).status_code == 402
    assert proxy.ledger.summary() == {'enabled': False}
    proxy.ledger.configure('1')
    assert (await proxy.handle(request(prompt()))).status_code == 402
    assert proxy.ledger.summary()['calls'] == 0


@pytest.mark.asyncio
async def test_streaming_byte_boundaries_and_usage_request(setup):
    encoded = b''.join(frames()).replace(b'\n', b'\r\n')
    source = BytesStream([encoded[i:i+1] for i in range(len(encoded))])
    def upstream(req):
        assert json.loads(req.content)['stream_options'] == {'include_usage': True}
        return httpx.Response(200, headers={'content-type': 'text/event-stream'}, stream=source)
    proxy = proxy_for(setup, upstream)
    response = await proxy.handle(request(prompt(stream=True, stream_options={'include_usage': False})))
    body = b''.join([chunk async for chunk in response.body_iterator])
    assert '塔' in body.decode() and body.endswith(b'data: [DONE]\n\n')
    assert source.closed and setup[0].summary()['settled_cny'] == 0.00014


@pytest.mark.asyncio
@pytest.mark.parametrize('kind', ['missing_usage', 'missing_done', 'bad_usage', 'conflicting_usage', 'provider_error', 'no_finish', 'truncated_json'])
async def test_unknown_or_broken_stream_never_releases_reservation(setup, kind):
    chunks = frames()
    if kind == 'missing_usage':
        chunks = frames(usage=None)
    elif kind == 'missing_done':
        chunks = frames(done=False)
    elif kind == 'bad_usage':
        chunks = frames(usage={'prompt_tokens': True, 'completion_tokens': 0})
    elif kind == 'conflicting_usage':
        chunks.insert(-1, event({'choices': [], 'usage': {'prompt_tokens': 100, 'completion_tokens': 21}}))
    elif kind == 'provider_error':
        chunks = [event({'error': {'message': 'SUPPLIER-SECRET'}})]
    elif kind == 'no_finish':
        chunks = [event({'choices': [], 'usage': USAGE}), event('[DONE]')]
    else:
        chunks = [b'data: {"unfinished":']
    proxy = proxy_for(setup, lambda req: httpx.Response(200, headers={'content-type': 'text/event-stream'}, stream=BytesStream(chunks)))
    response = await proxy.handle(request(prompt(stream=True)))
    output = b''.join([chunk async for chunk in response.body_iterator]).decode()
    assert setup[0].summary()['unsettled_calls'] == 1 and setup[0].summary()['held_cny'] > 0
    assert ('[DONE]' in output) is (kind == 'missing_usage')
    assert 'SUPPLIER-SECRET' not in output


@pytest.mark.asyncio
@pytest.mark.parametrize('kind', ['http_error', 'redirect', 'timeout', 'malformed', 'missing_usage'])
async def test_nonstream_failures_record_unknown_without_exposing_provider_body(setup, kind):
    attempts = []
    def upstream(req):
        attempts.append(req)
        if kind == 'timeout':
            raise httpx.ReadTimeout('SUPPLIER-SECRET')
        if kind == 'redirect':
            return httpx.Response(307, headers={'location': 'https://attacker.example'}, json={'error': 'SUPPLIER-SECRET'})
        if kind == 'http_error':
            return httpx.Response(429, json={'error': 'SUPPLIER-SECRET'})
        if kind == 'malformed':
            return httpx.Response(200, json={'unexpected': 'SUPPLIER-SECRET'})
        return httpx.Response(200, json=completion(usage=None))
    proxy = proxy_for(setup, upstream)
    response = await proxy.handle(request(prompt()))
    assert response.status_code == (200 if kind == 'missing_usage' else 502)
    assert len(attempts) == 1
    assert setup[0].summary()['unsettled_calls'] == 1
    assert 'SUPPLIER-SECRET' not in response.body.decode()


class HeldStream(httpx.AsyncByteStream):
    def __init__(self):
        self.started = asyncio.Event()
        self.release = asyncio.Event()
        self.closed = False

    async def __aiter__(self):
        yield frames()[0]
        self.started.set()
        await self.release.wait()
        for chunk in frames()[1:]:
            yield chunk

    async def aclose(self):
        self.closed = True


@pytest.mark.asyncio
async def test_first_small_chunk_is_live_and_disconnect_closes_upstream(setup):
    source = HeldStream()
    proxy = proxy_for(setup, lambda req: httpx.Response(200, headers={'content-type': 'text/event-stream'}, stream=source))
    response = await proxy.handle(request(prompt(stream=True)))
    chunk = await asyncio.wait_for(anext(response.body_iterator), 1)
    assert '塔' in chunk.decode() and not source.release.is_set()
    await response.body_iterator.aclose()
    assert source.closed and setup[0].summary()['unsettled_calls'] == 1
    assert proxy.jobs[0].task.done()


@pytest.mark.asyncio
async def test_session_close_stops_model_and_parallel_request_is_rejected(setup):
    source = HeldStream()
    proxy = proxy_for(setup, lambda req: httpx.Response(200, headers={'content-type': 'text/event-stream'}, stream=source))
    create_tool_app(setup[1], model_proxy=proxy)
    await proxy.handle(request(prompt(stream=True)))
    await source.started.wait()
    assert (await proxy.handle(request(prompt()))).status_code == 409
    assert setup[0].summary()['calls'] == 1
    await setup[1].close()
    assert source.closed and setup[0].summary()['unsettled_calls'] == 1
    assert (await proxy.handle(request(prompt()))).status_code == 410


@pytest.mark.asyncio
async def test_request_retry_always_reserves_again_and_twentieth_is_last(setup):
    proxy = proxy_for(setup, lambda req: httpx.Response(500, json={'error': 'failure'}))
    for i in range(20):
        assert (await proxy.handle(request(prompt()))).status_code == 502
        assert setup[0].summary()['calls'] == i + 1
    assert (await proxy.handle(request(prompt()))).status_code == 429
    assert setup[0].summary()['calls'] == 20


@pytest.mark.asyncio
async def test_provider_usage_overestimate_stops_next_request(setup):
    proxy = proxy_for(setup, lambda req: httpx.Response(200, json=completion({'prompt_tokens': 2_000_000, 'completion_tokens': 0})))
    assert (await proxy.handle(request(prompt()))).status_code == 200
    assert setup[0].summary()['over_budget']
    assert (await proxy.handle(request(prompt()))).status_code == 402
    assert setup[0].summary()['calls'] == 1


@pytest.mark.asyncio
async def test_http_proxy_uses_internal_auth_and_rejects_query_or_oversize(setup):
    proxy = proxy_for(setup, lambda req: httpx.Response(200, json=completion()))
    app = create_tool_app(setup[1], model_proxy=proxy)
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app), base_url='http://localhost') as client:
        assert (await client.post('/v1/chat/completions', json=prompt())).status_code == 401
        client.headers['Authorization'] = 'Bearer ' + setup[1].token
        assert (await client.post('/v1/chat/completions', headers={'Origin': 'null'}, json=prompt())).status_code == 403
        assert (await client.post('/v1/chat/completions?url=bad', json=prompt())).status_code == 400
        assert (await client.post('/v1/chat/completions', content=b'x' * (MAX_REQUEST + 1), headers={'Content-Type': 'application/json'})).status_code == 413
        assert (await client.post('/v1/chat/completions', json=prompt())).status_code == 200
    assert setup[0].summary()['calls'] == 1


def test_decoder_cr_and_multiline_data():
    decoder = SSEDecoder()
    assert decoder.feed(b'\xef\xbb\xbfdata: {\rdata: "x":1}\r\r') == ['{\n"x":1}']
    assert decoder.feed(b'\n') == []
    assert decoder.feed(b'data: [DONE]\r\r') == ['[DONE]']


@pytest.mark.asyncio
async def test_deadline_cancels_live_response_and_keeps_unknown_charge(setup):
    source = HeldStream()
    proxy = proxy_for(setup, lambda req: httpx.Response(200, headers={'content-type': 'text/event-stream'}, stream=source))
    proxy.deadline = time.monotonic() + 0.05
    response = await proxy.handle(request(prompt(stream=True)))
    output = b''.join([chunk async for chunk in response.body_iterator])
    assert b'[DONE]' not in output and source.closed
    assert setup[0].summary()['unsettled_calls'] == 1


@pytest.mark.asyncio
async def test_close_does_not_deadlock_when_consumer_stops_draining(setup):
    source = BytesStream([frames()[0]] * 100)
    proxy = proxy_for(setup, lambda req: httpx.Response(200, headers={'content-type': 'text/event-stream'}, stream=source))
    await proxy.handle(request(prompt(stream=True)))
    assert proxy.jobs[0].queue.full()
    await asyncio.wait_for(proxy.close(), 1)
    assert source.closed and setup[0].summary()['unsettled_calls'] == 1


@pytest.mark.asyncio
async def test_cancel_before_producer_starts_unblocks_request_and_retains_charge(setup):
    def forbidden(req):
        raise AssertionError('cancelled before network dispatch')
    proxy = proxy_for(setup, forbidden)
    waiting = asyncio.create_task(proxy.handle(request(prompt())))
    await asyncio.sleep(0)
    assert len(proxy.jobs) == 1 and not proxy.jobs[0].started
    await proxy.close()
    response = await asyncio.wait_for(waiting, 1)
    assert response.status_code == 502
    assert setup[0].summary()['unsettled_calls'] == 1
    assert setup[0].history()[0]['state'] == 'unknown'


@pytest.mark.asyncio
async def test_failed_ledger_settlement_returns_error_and_keeps_reservation(setup, monkeypatch):
    proxy = proxy_for(setup, lambda req: httpx.Response(200, json=completion()))
    def fail(*args):
        raise OSError('SUPPLIER-SECRET')
    monkeypatch.setattr(setup[0], 'finish_model', fail)
    response = await asyncio.wait_for(proxy.handle(request(prompt())), 1)
    assert response.status_code == 502 and 'SUPPLIER-SECRET' not in response.body.decode()
    assert setup[0].summary()['unsettled_calls'] == 1
