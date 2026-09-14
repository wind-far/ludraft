import asyncio
import json
import os
import stat
import httpx
import pytest
from fastapi.testclient import TestClient
from studio.app import create_app
from studio.connections import RoleConnection,ConnectionProbe
from studio.llm import Gateway,ModelError
from studio.models import ModelSettings
from studio.team_models import TeamModels,Review
from test_studio import FakeRunner


def mock_http(monkeypatch,respond):
    real=httpx.AsyncClient
    monkeypatch.setattr(httpx,'AsyncClient',lambda **kw:real(transport=httpx.MockTransport(respond),**kw))


@pytest.mark.asyncio
async def test_independent_provider_credentials_and_shared_override(tmp_path,monkeypatch):
    g=Gateway(tmp_path);g.save(ModelSettings(model='default-model',api_key='DEFAULT-PRIVATE'))
    g.save_connection('程序',RoleConnection(mode='independent',provider='deepseek',model='code-model',api_key='CODE-PRIVATE',max_tokens=8000))
    g.save_connection('QA',RoleConnection(mode='shared',model='review-model'))
    sent=[]
    def respond(r):
        sent.append(r);return httpx.Response(200,json={'choices':[{'message':{'content':Review(summary='协议响应',issues=[]).model_dump_json()}}]})
    mock_http(monkeypatch,respond)
    for role in ('程序','QA','策划'):await g.call(role,'测试',Review)
    assert [r.url.host for r in sent]==['api.deepseek.com','api.openai.com','api.openai.com']
    assert [r.headers['authorization'] for r in sent]==['Bearer CODE-PRIVATE','Bearer DEFAULT-PRIVATE','Bearer DEFAULT-PRIVATE']
    assert [json.loads(r.content)['model'] for r in sent]==['code-model','review-model','default-model']
    assert json.loads(sent[0].content)['max_tokens']==8000
    with TestClient(create_app(tmp_path,g,FakeRunner())) as c:
        for path in ('/api/settings/connections','/api/settings/team','/api/settings/model','/api/health'):
            response=c.get(path);assert response.status_code==200
            assert 'DEFAULT-PRIVATE' not in response.text and 'CODE-PRIVATE' not in response.text


@pytest.mark.asyncio
async def test_anthropic_protocol_and_cache_usage(tmp_path,monkeypatch):
    g=Gateway(tmp_path);g.save_connection('主程',RoleConnection(mode='independent',provider='anthropic',model='claude-example',api_key='ANTHROPIC-PRIVATE'))
    def respond(r):
        body=json.loads(r.content)
        assert str(r.url)=='https://api.anthropic.com/v1/messages'
        assert r.headers['x-api-key']=='ANTHROPIC-PRIVATE' and 'authorization' not in r.headers
        assert r.headers['anthropic-version']=='2023-06-01'
        assert body['system'] and body['messages']==[{'role':'user','content':'测试'}]
        return httpx.Response(200,json={'content':[{'type':'text','text':'{"summary":"角色连接正常"}'}],
            'usage':{'input_tokens':10,'output_tokens':4,'cache_creation_input_tokens':2,'cache_read_input_tokens':3}})
    mock_http(monkeypatch,respond)
    result,meta=await g.call('主程','测试',ConnectionProbe)
    assert result.summary=='角色连接正常' and meta['usage']=={'prompt_tokens':15,'completion_tokens':4,'total_tokens':19}
    assert meta['provider']=='anthropic' and 'ANTHROPIC-PRIVATE' not in json.dumps(meta)


@pytest.mark.asyncio
@pytest.mark.parametrize('bad',['http','shape','text','usage'])
async def test_anthropic_failures_visible_no_secret_leak(tmp_path,monkeypatch,bad):
    g=Gateway(tmp_path);g.save_connection('QA',RoleConnection(mode='independent',provider='anthropic',model='test',api_key='SECRET'))
    def respond(r):
        if bad=='http':return httpx.Response(401,json={'error':{'message':'SECRET'},'usage':{'input_tokens':3,'output_tokens':2}})
        if bad=='shape':return httpx.Response(200,json={'content':'SECRET'})
        if bad=='text':return httpx.Response(200,json={'content':[{'type':'text','text':'SECRET'}]})
        return httpx.Response(200,json={'content':[{'type':'text','text':'{"summary":"正常连接"}'}],'usage':{'input_tokens':True,'output_tokens':-2}})
    mock_http(monkeypatch,respond)
    if bad=='usage':
        _,meta=await g.call('QA','test',ConnectionProbe);assert meta['usage']=={}
    else:
        with pytest.raises(ModelError) as exc:await g.call('QA','test',ConnectionProbe)
        assert 'SECRET' not in str(exc.value) and 'SECRET' not in json.dumps(exc.value.metadata)
        if bad=='http':assert exc.value.metadata['usage']['total_tokens']==5


def test_migration_atomic_permissions_and_legacy_edit_preserves_connections(tmp_path):
    g=Gateway(tmp_path);g.team_path.write_text('{"models":{"策划":"old-model"}}')
    assert g.effective('策划')['model']=='old-model'
    g.save_connection('QA',RoleConnection(mode='independent',model='independent',api_key='PRIVATE'))
    assert g.effective('策划')['model']=='old-model'
    g.save_team_models(TeamModels(models={'主程':'other-model'}))
    assert g.effective('QA')['api_key']=='PRIVATE' and g.effective('QA')['model']=='independent'
    assert stat.S_IMODE(g.connections_path.stat().st_mode)==0o600
    g.path.write_text('{}');os.chmod(g.path,0o644)
    g.save(ModelSettings(model='default',api_key='DEFAULT'))
    assert stat.S_IMODE(g.path.stat().st_mode)==0o600
    assert not list(tmp_path.glob('*.tmp'))
    assert Gateway(tmp_path).effective('QA')['api_key']=='PRIVATE'


def test_key_retention_change_address_clear_and_shared_mode(tmp_path):
    g=Gateway(tmp_path);g.save(ModelSettings(model='default',api_key='DEFAULT'))
    base={'mode':'independent','model':'qa','base_url':'https://one.example/v1'}
    g.save_connection('QA',RoleConnection(**base,api_key='QA-KEY'))
    g.save_connection('QA',RoleConnection(**base));assert g.effective('QA')['api_key']=='QA-KEY'
    changed={**base,'base_url':'https://two.example/v1'}
    with pytest.raises(ValueError,match='地址已改变'):g.save_connection('QA',RoleConnection(**changed))
    assert g.effective('QA')['base_url']=='https://one.example/v1'
    g.save_connection('QA',RoleConnection(**changed,clear_key=True));assert g.effective('QA')['api_key']==''
    g.save_connection('QA',RoleConnection(mode='shared',model='qa-shared'))
    assert g.effective('QA')['api_key']=='DEFAULT' and g.connections()['QA']['api_key']==''
    with pytest.raises(ValueError):g.save(ModelSettings(model='default',base_url='https://new.example'))


@pytest.mark.asyncio
async def test_independent_remote_never_borrows_default_key_and_local_needs_none(tmp_path,monkeypatch):
    g=Gateway(tmp_path);g.save(ModelSettings(model='default',api_key='DEFAULT'))
    g.save_connection('QA',RoleConnection(mode='independent',model='remote'))
    with pytest.raises(ModelError) as exc:await g.call('QA','test',ConnectionProbe)
    assert exc.value.metadata['attempted'] is False
    g.save_connection('QA',RoleConnection(mode='independent',provider='custom',base_url='http://127.0.0.1:1234/v1',model='local'))
    def respond(r):
        assert 'authorization' not in r.headers
        return httpx.Response(200,json={'choices':[{'message':{'content':'{"summary":"本地连接正常"}'}}]})
    mock_http(monkeypatch,respond);await g.call('QA','test',ConnectionProbe)


def test_role_tests_bound_to_effective_connection_not_default(tmp_path,monkeypatch):
    g=Gateway(tmp_path);g.save(ModelSettings(model='default',api_key='DEFAULT'))
    g.save_connection('QA',RoleConnection(mode='independent',model='qa',api_key='QA'))
    mock_http(monkeypatch,lambda r:httpx.Response(200,json={'choices':[{'message':{'content':'{"summary":"正常连接"}'}}]}))
    with TestClient(create_app(tmp_path,g,FakeRunner())) as c:
        assert c.post('/api/settings/connections/QA/test').status_code==200
        assert c.post('/api/settings/connections/策划/test').status_code==200
        g.save(ModelSettings(model='changed-default',api_key='DEFAULT-2'))
        profiles=c.get('/api/settings/connections').json()['roles']
        assert profiles['QA']['check']['status']=='passed' and profiles['策划']['check']['status']=='unverified'
        assert c.put('/api/settings/connections/QA',json={'mode':'independent','model':'qa','api_key':'QA-2'}).status_code==200
        assert c.get('/api/settings/connections').json()['roles']['QA']['check']['status']=='unverified'
        assert c.put('/api/settings/connections/unknown',json={}).status_code==422
        assert c.put('/api/settings/connections/QA',json={'mode':'independent','provider':'custom','base_url':'https://user:PRIVATE@host','model':'m'}).status_code==400
        assert c.get('/api/settings/connections',headers={'Origin':'null'}).status_code==403


def test_inflight_role_test_cannot_certify_changed_key(tmp_path):
    class G(Gateway):
        async def call(self,*args):
            self.save_connection('QA',RoleConnection(mode='independent',model='qa',api_key='CHANGED'))
            return ConnectionProbe(summary='正常连接'),{'model':'qa'}
    g=G(tmp_path);g.save_connection('QA',RoleConnection(mode='independent',model='qa',api_key='ORIGINAL'))
    with TestClient(create_app(tmp_path,g,FakeRunner())) as c:
        assert c.post('/api/settings/connections/QA/test').status_code==409
        assert c.get('/api/settings/connections').json()['roles']['QA']['check']['status']=='unverified'


def test_invalid_credentials_never_echo_in_validation_response(tmp_path):
    with TestClient(create_app(tmp_path,Gateway(tmp_path),FakeRunner())) as c:
        secret='PRIVATE-CREDENTIAL-'*90
        for path in ('/api/settings/model','/api/settings/connections/QA'):
            r=c.put(path,json={'model':'test','api_key':secret})
            assert r.status_code==422 and 'PRIVATE-CREDENTIAL' not in r.text


@pytest.mark.asyncio
async def test_call_source_persists_through_artifact_and_export(tmp_path,monkeypatch):
    from studio.team import Team
    from studio.lineage import decoded_steps
    from test_team import setup
    g=Gateway(tmp_path);g.save_connection('主程',RoleConnection(mode='independent',model='review-id',api_key='PRIVATE'))
    mock_http(monkeypatch,lambda r:httpx.Response(200,json={'choices':[{'message':{'content':Review(summary='审查完成',issues=[]).model_dump_json()}}]}))
    s,w,_,rid=setup(tmp_path,g)
    await Team(w).step(s.run(rid),'review','主程',Review,{})
    step=decoded_steps(s,rid)[0]
    assert step['connection']=={'provider':'openai','base_url':'https://api.openai.com/v1'}
    assert 'PRIVATE' not in json.dumps(step)
    s.con.close()


@pytest.mark.asyncio
async def test_cancelled_call_keeps_requested_model_and_connection(tmp_path,monkeypatch):
    from studio.team import Team
    from studio.lineage import decoded_steps
    from test_team import setup
    entered=asyncio.Event()
    async def respond(request):
        entered.set();await asyncio.Event().wait()
    mock_http(monkeypatch,respond)
    g=Gateway(tmp_path);g.save_connection('QA',RoleConnection(mode='independent',model='qa-model',api_key='PRIVATE'))
    s,w,_,rid=setup(tmp_path,g)
    task=asyncio.create_task(Team(w).step(s.run(rid),'review','QA',Review,{}))
    await entered.wait();task.cancel()
    with pytest.raises(asyncio.CancelledError):await task
    step=decoded_steps(s,rid)[0]
    assert step['status']=='cancelled' and step['model']=='qa-model'
    assert step['connection']=={'provider':'openai','base_url':'https://api.openai.com/v1'} and step['usage']=={}
    s.con.close()
