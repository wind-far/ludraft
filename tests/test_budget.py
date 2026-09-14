import asyncio
from concurrent.futures import ThreadPoolExecutor

import httpx
import pytest
from fastapi.testclient import TestClient

from studio.app import create_app
from studio.budget import BudgetError, BudgetLedger, connection_key, money
from studio.connections import ConnectionProbe
from studio.llm import Gateway, ModelError
from studio.models import ModelSettings


CONFIG = {'provider':'openai', 'base_url':'https://example.com/v1', 'model':'sample', 'api_key':'SECRET'}


def ledger(root, cap='1', images=2):
    result = BudgetLedger(root)
    result.configure(cap, images)
    result.set_price(connection_key(CONFIG), '1', '2', 'test-only price')
    return result


def test_reservations_persist_unknown_outcomes_and_actual_overruns(tmp_path):
    b = ledger(tmp_path)
    call = b.reserve_model(CONFIG, 100_000, 100_000, '程序')
    b.finish_model(call, {})
    restored = BudgetLedger(tmp_path)
    assert restored.summary()['held_cny'] == 0.3
    assert restored.summary()['unsettled_calls'] == 1
    # Provider-reported usage may exceed estimates. Record it, then stop new work.
    restored.finish_model(call, {'prompt_tokens':2_000_000, 'completion_tokens':0})
    assert restored.summary()['over_budget'] is True
    with pytest.raises(BudgetError, match='达到实验预算'):
        restored.reserve_model(CONFIG, 1, 1, 'QA')
    assert restored.summary()['settled_cny'] == 2


def test_reservations_are_atomic_across_workers(tmp_path):
    ledger(tmp_path)
    def reserve(_):
        try:
            return BudgetLedger(tmp_path).reserve_image('provider', '0.7', 'test')
        except BudgetError:
            return None
    with ThreadPoolExecutor(max_workers=6) as pool:
        results = list(pool.map(reserve, range(6)))
    assert sum(item is not None for item in results) == 1
    assert BudgetLedger(tmp_path).summary()['held_cny'] == 0.7


def test_image_limit_counts_failed_attempts_and_idempotency(tmp_path):
    b = ledger(tmp_path)
    call = b.reserve_image('image', '0.1', 'image', 'same-id')
    assert b.reserve_image('image', '0.1', 'image', 'same-id') == call
    with pytest.raises(BudgetError, match='同一请求'):
        b.reserve_image('image', '0.2', 'image', 'same-id')
    b.reconcile(call, '0')  # A refunded failure still consumed an attempt.
    b.reserve_image('image', '0.1', 'image')
    with pytest.raises(BudgetError, match='图片生成尝试'):
        b.reserve_image('image', '0.1', 'image')
    b.configure('2', 2)
    assert b.summary()['image_attempts'] == 2
    with pytest.raises(BudgetError, match='已经核账'):
        b.reconcile(call, '1')


@pytest.mark.parametrize('value', ['NaN', 'Infinity', '-1', True, None])
def test_invalid_prices_rejected(value):
    with pytest.raises(BudgetError):
        money(value)


def test_rates_bound_to_connection_and_snapshot(tmp_path):
    b = ledger(tmp_path)
    changed = {**CONFIG, 'model':'new-model'}
    with pytest.raises(BudgetError, match='实际价格'):
        b.reserve_model(changed, 1, 1, '程序')
    call = b.reserve_model(CONFIG, 100, 100, '程序')
    b.set_price(connection_key(CONFIG), '10', '20', 'updated test price')
    b.finish_model(call, {'prompt_tokens':100, 'completion_tokens':100})
    assert b.summary()['settled_cny'] == 0.0003
    assert 'SECRET' not in str(b.history())


def gateway(root):
    g = Gateway(root)
    g.save(ModelSettings(base_url=CONFIG['base_url'], model=CONFIG['model'], api_key='SECRET'))
    ledger(root)
    return g


@pytest.mark.asyncio
async def test_gateway_blocks_unpriced_models_before_http(tmp_path, monkeypatch):
    g = gateway(tmp_path)
    g.budget.configure('0.000001')
    def forbidden(**kwargs):
        raise AssertionError('HTTP must not start')
    monkeypatch.setattr(httpx, 'AsyncClient', forbidden)
    with pytest.raises(ModelError) as exc:
        await g.call('程序', 'test', ConnectionProbe)
    assert exc.value.metadata == {'attempted':False, 'failure_type':'budget'}
    assert g.budget.summary()['calls'] == 0


@pytest.mark.asyncio
@pytest.mark.parametrize('outcome', ['success', 'http_error', 'invalid_json', 'cancel', 'no_usage'])
async def test_gateway_records_every_dispatched_outcome(tmp_path, monkeypatch, outcome):
    g = gateway(tmp_path)
    async def respond(request):
        if outcome == 'cancel':
            raise asyncio.CancelledError()
        return httpx.Response(500 if outcome == 'http_error' else 200, json={
            'choices':[{'message':{'content':'bad' if outcome == 'invalid_json' else '{"summary":"连接正常"}'}}],
            'usage':{} if outcome == 'no_usage' else {'prompt_tokens':100, 'completion_tokens':20}})
    real = httpx.AsyncClient
    monkeypatch.setattr(httpx, 'AsyncClient', lambda **kw: real(transport=httpx.MockTransport(respond), **kw))
    if outcome == 'cancel':
        with pytest.raises(asyncio.CancelledError):
            await g.call('程序', 'test', ConnectionProbe)
    elif outcome in ('http_error', 'invalid_json'):
        with pytest.raises(ModelError):
            await g.call('程序', 'test', ConnectionProbe)
    else:
        _, meta = await g.call('程序', 'test', ConnectionProbe)
        assert meta['budget_call_id']
    status = g.budget.summary()
    assert status['calls'] == 1
    assert status['unsettled_calls'] == (1 if outcome in ('cancel', 'no_usage') else 0)
    if outcome not in ('cancel', 'no_usage'):
        assert status['settled_cny'] == 0.00014
    assert 'SECRET' not in str(g.budget.history())


def test_readonly_status_and_legacy_opt_in(tmp_path):
    assert Gateway(tmp_path).budget.enabled is False
    with TestClient(create_app(tmp_path)) as client:
        assert client.get('/api/settings/budget').json() == {'enabled':False}
        ledger(tmp_path)
        status = client.get('/api/settings/budget')
        assert status.json()['cap_cny'] == 1
        assert 'SECRET' not in status.text


def test_unlimited_preserves_history_and_survives_restart(tmp_path):
    b = ledger(tmp_path, cap='0.1', images=0)
    call = b.reserve_model(CONFIG, 100_000, 0, 'old request')
    b.finish_model(call, {})
    before = b.history()
    b.unlimited()
    restored = BudgetLedger(tmp_path)
    assert restored.history() == before
    assert restored.summary()['enforce_limits'] is False
    assert restored.summary()['cap_cny'] is None
    assert restored.summary()['remaining_cny'] is None
    assert restored.summary()['held_cny'] == 0.1
    restored.reserve_model(CONFIG, 100_000_000, 0, 'over old cap')
    restored.reserve_image('image', '500', 'over old image limit')
    assert restored.summary()['calls'] == 3
    assert restored.summary()['over_budget'] is False
    # Restoring limits is explicit and does not reset history or old holds.
    restored.configure('1', 1)
    assert restored.summary()['calls'] == 3 and restored.summary()['over_budget']
    with pytest.raises(BudgetError):
        restored.reserve_model(CONFIG, 1, 1, 'limited again')


def test_unpriced_usage_is_unknown_cost_until_reconciled(tmp_path):
    b = BudgetLedger(tmp_path)
    b.unlimited()
    rid = b.reserve_model(CONFIG, 1000, 500, 'unpriced', 'same-id')
    assert b.reserve_model(CONFIG, 1000, 500, 'unpriced', 'same-id') == rid
    with pytest.raises(BudgetError, match='同一请求'):
        b.reserve_model(CONFIG, 2000, 500, 'unpriced', 'same-id')
    b.finish_model(rid, {'prompt_tokens':100, 'completion_tokens':20})
    row = b.history()[0]
    assert row['state'] == 'unpriced' and row['actual'] is None and row['priced'] == 0
    assert row['prompt_tokens'] == 100 and row['completion_tokens'] == 20
    assert b.summary()['unpriced_calls'] == b.summary()['unsettled_calls'] == 1
    # Later price changes must not silently reprice an earlier request.
    b.set_price(connection_key(CONFIG), '1', '2', 'new rates')
    b.finish_model(rid, {'prompt_tokens':100, 'completion_tokens':20})
    assert b.history()[0]['actual'] is None
    b.reconcile(rid, '0.25')
    assert b.summary()['settled_cny'] == 0.25
    assert b.summary()['unpriced_calls'] == b.summary()['unsettled_calls'] == 0


def test_unlimited_migrates_legacy_ledger_without_losing_records(tmp_path):
    import sqlite3
    b = BudgetLedger(tmp_path)
    con = sqlite3.connect(b.path)
    con.executescript('''
        CREATE TABLE policy(id INTEGER PRIMARY KEY, cap INTEGER NOT NULL, image_limit INTEGER NOT NULL);
        INSERT INTO policy VALUES(1,100000000,10);
        CREATE TABLE calls(id TEXT PRIMARY KEY,identity TEXT NOT NULL,kind TEXT NOT NULL,
            label TEXT NOT NULL,reserved INTEGER NOT NULL,actual INTEGER,input_rate INTEGER NOT NULL,
            output_rate INTEGER NOT NULL,input_limit INTEGER NOT NULL,output_limit INTEGER NOT NULL,
            state TEXT NOT NULL,created TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP);
        INSERT INTO calls(id,identity,kind,label,reserved,actual,input_rate,output_rate,input_limit,output_limit,state)
            VALUES('old','provider','model','previous',1000000,NULL,1000000,2000000,1000000,0,'unknown');
    ''')
    con.close()
    b.unlimited()
    assert b.summary()['held_cny'] == 1 and b.summary()['calls'] == 1
    row = b.history()[0]
    assert row['id'] == 'old' and row['state'] == 'unknown' and row['priced'] == 1
    b.finish_model('old', {'prompt_tokens':500000, 'completion_tokens':0})
    assert b.summary()['settled_cny'] == 0.5


@pytest.mark.asyncio
@pytest.mark.parametrize('priced', [False, True])
async def test_unlimited_gateway_dispatches_without_price_or_available_budget(tmp_path, monkeypatch, priced):
    g = gateway(tmp_path)
    g.budget.configure('0.000001')
    if not priced:
        g.save(ModelSettings(base_url=CONFIG['base_url'], model='unpriced-model'))
    g.budget.unlimited()
    called = []
    async def respond(request):
        called.append(request)
        return httpx.Response(200, json={'choices':[{'message':{'content':'{"summary":"ok"}'}}],
                                        'usage':{'prompt_tokens':100,'completion_tokens':20}})
    real = httpx.AsyncClient
    monkeypatch.setattr(httpx, 'AsyncClient', lambda **kw: real(transport=httpx.MockTransport(respond), **kw))
    result, meta = await g.call('程序', 'test', ConnectionProbe)
    assert result.summary == 'ok' and len(called) == 1 and meta['budget_call_id']
    row = g.budget.history()[0]
    assert row['prompt_tokens'] == 100 and row['completion_tokens'] == 20
    assert (row['actual'] is not None) == priced
    assert row['state'] == ('settled' if priced else 'unpriced')
