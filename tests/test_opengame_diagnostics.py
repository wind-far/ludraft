import json

from fastapi.testclient import TestClient
import pytest

from studio.app import create_app
from studio.budget import connection_key
from studio.connections import RoleConnection
from studio.models import ModelSettings
import studio.opengame_diagnostics as module


@pytest.fixture
def app(tmp_path, monkeypatch):
    app = create_app(tmp_path)
    gateway = app.state.workflow.gateway
    async def forbidden(*args, **kwargs):
        raise AssertionError('Diagnostics must not contact a model or remove resources')
    async def image():
        return 'sha256:' + 'a' * 64
    async def inspect(*args, **kwargs):
        assert args[:2] == ('image', 'inspect')
        return json.dumps([{'Id': 'sha256:' + 'b'*64}]).encode()
    monkeypatch.setattr(gateway, 'call', forbidden)
    monkeypatch.setattr(module, 'verified_image', image)
    monkeypatch.setattr(module, 'docker', inspect)
    monkeypatch.setattr('studio.opengame_executor.docker', forbidden)
    return app


def configured(app, *, local=False):
    gateway = app.state.workflow.gateway
    gateway.save(ModelSettings(base_url='http://localhost:1234/v1' if local else 'https://fixture.invalid/v1',
                               model='fixture', api_key='' if local else 'DO-NOT-EXPOSE-KEY'))
    cfg = gateway.effective('程序')
    gateway.budget.configure('1')
    gateway.budget.set_price(connection_key(cfg), '1', '2', 'test rates')
    return gateway, cfg


def checks(value):
    return {check['id']: check['status'] for check in value['checks']}


def test_missing_model_budget_and_price_are_reported_without_calls(app):
    with TestClient(app) as client:
        value = client.get('/api/settings/opengame/diagnostics').json()
        assert checks(value)['cli_image'] == 'passed'
        assert checks(value)['model_config'] == checks(value)['price'] == checks(value)['budget'] == 'failed'
        assert not value['model_called'] and not value['preflight_passed']
        assert value['executions']['attempts'] == []
        assert not app.state.workflow.gateway.budget.path.exists()


@pytest.mark.parametrize('local', [False, True])
def test_preflight_is_not_live_model_or_tower_acceptance(app, local):
    gateway, cfg = configured(app, local=local)
    with TestClient(app) as client:
        before = gateway.budget.summary()
        value = client.get('/api/settings/opengame/diagnostics').json()
        assert value['preflight_passed'] and not value['live_tool_call_verified']
        assert not value['tower_creation_available'] and not value['model_called']
        assert value['price']['output_cny_per_million'] == 2
        assert gateway.budget.summary() == before
        assert 'DO-NOT-EXPOSE' not in json.dumps(value)
        assert 'api_key' not in json.dumps(value)


def test_model_change_invalidates_price_and_wrong_protocol_is_rejected(app):
    gateway, _ = configured(app)
    gateway.save(ModelSettings(base_url='https://fixture.invalid/v1', model='other'))
    with TestClient(app) as client:
        assert checks(client.get('/api/settings/opengame/diagnostics').json())['price'] == 'failed'
        gateway.save_connection('程序', RoleConnection(mode='independent',provider='anthropic',
            base_url='https://fixture.invalid/v1',model='fixture',api_key='DO-NOT-EXPOSE-KEY'))
        value = client.get('/api/settings/opengame/diagnostics').json()
        assert checks(value)['model_config'] == 'failed' and value['price'] is None


def test_image_failure_and_unknown_cost_hold_are_not_ready(app, monkeypatch):
    gateway, cfg = configured(app)
    gateway.budget.reserve_model(cfg, 1_000_000, 0, 'fixture')
    async def unavailable(*args, **kwargs):
        raise RuntimeError('DO-NOT-EXPOSE-INTERNAL-ERROR')
    monkeypatch.setattr(module, 'verified_image', unavailable)
    with TestClient(app) as client:
        value = client.get('/api/settings/opengame/diagnostics').json()
        assert checks(value)['cli_image'] == checks(value)['budget'] == 'failed'
        assert value['budget']['held_cny'] == 1 and value['budget']['unsettled_calls'] == 1
        assert not value['preflight_passed']
        assert 'DO-NOT-EXPOSE' not in json.dumps(value)


def test_active_execution_is_not_offered_as_orphan(app):
    with TestClient(app) as client:
        records = app.state.workflow.opengame.records
        row = records.begin('sha256:' + 'a'*64)
        records.state(row['id'], 'running')
        with records.lease():
            value = client.get('/api/settings/opengame/diagnostics').json()
            assert value['executions']['busy'] and checks(value)['resources'] == 'unverified'
            assert client.get('/api/settings/opengame/executions').json()['busy']
        value = client.get('/api/settings/opengame/diagnostics').json()
        assert checks(value)['resources'] == 'failed' and not value['executions']['busy']
        assert records.get(row['id'])['state'] == 'running'  # Read did not clean or interrupt it.
        assert client.get('/api/settings/opengame/diagnostics', headers={'Origin':'null'}).status_code == 403


def test_unlimited_preflight_allows_missing_price_and_old_holds(app):
    gateway, cfg = configured(app)
    gateway.budget.reserve_model(cfg, 1_000_000, 0, 'old hold')
    gateway.save(ModelSettings(base_url=cfg['base_url'], model='unpriced-model'))
    gateway.budget.unlimited()
    with TestClient(app) as client:
        before = gateway.budget.history()
        value = client.get('/api/settings/opengame/diagnostics').json()
        assert checks(value)['price'] == checks(value)['budget'] == 'passed'
        assert value['price'] is None and value['budget']['cap_cny'] is None
        assert value['budget']['held_cny'] == 1
        assert value['preflight_passed'] and not value['model_called']
        assert gateway.budget.history() == before
