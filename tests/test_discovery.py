import asyncio
import json
from pathlib import Path
import pytest
from fastapi.testclient import TestClient
from studio.app import create_app, create_preview_app
from studio.db import uid, now
from studio.files import copy_source, TEMPLATE
from studio.llm import Gateway, ModelError
from studio.models import ModelSettings, Parameters
from studio.parameters import update_config, read_config
from studio.runner import Runner
from test_studio import FakeGateway, PLAN
from test_workbench import seed, ParameterRunner


class DiagnosticRunner(ParameterRunner):
    async def diagnostics(self):return {'cli':True,'daemon':True,'image':True}


@pytest.fixture
def preview_ok(monkeypatch):
    async def ready(origin):return 'passed'
    monkeypatch.setattr('studio.discovery.preview_status',ready)


def test_diagnostics_never_calls_model_or_returns_secrets(tmp_path,preview_ok):
    gateway=Gateway(tmp_path);gateway.save(ModelSettings(model='model-id',api_key='test-secret',base_url='https://example.com/v1'))
    app=create_app(tmp_path,gateway,DiagnosticRunner())
    with TestClient(app) as c:
        result=c.get('/api/diagnostics')
        data=result.json()
        assert result.status_code==200 and data['model_called'] is False
        assert data['checks'][-1]['status']=='unverified' and not data['ready']
        assert 'test-secret' not in result.text and gateway.configuration_id() not in result.text
        assert c.get('/api/diagnostics',headers={'Origin':'https://bad.example'}).status_code==403
        assert c.get('/api/diagnostics',headers={'Host':'bad.example'}).status_code==403


def test_model_test_is_bound_to_configuration(tmp_path,preview_ok):
    class GatewayFixture(Gateway):
        fails=False
        async def call(self,*args):
            if self.fails:raise ModelError('测试连接失败')
            return PLAN,{'model':self.config()['model'],'usage':{}}
    gateway=GatewayFixture(tmp_path);gateway.save(ModelSettings(model='model-id',api_key='first-secret'))
    app=create_app(tmp_path,gateway,DiagnosticRunner())
    with TestClient(app) as c:
        assert c.post('/api/settings/model/test').status_code==200
        checked=c.get('/api/diagnostics').json()
        assert checked['ready'] and checked['checks'][-1]['checked_at']
        # A key-only change invalidates the result even though public model fields match.
        gateway.save(ModelSettings(model='model-id',api_key='second-secret'))
        assert c.get('/api/diagnostics').json()['checks'][-1]['status']=='unverified'
        gateway.fails=True
        assert c.post('/api/settings/model/test').status_code==400
        assert c.get('/api/diagnostics').json()['checks'][-1]['status']=='failed'
        assert c.put('/api/settings/model',json={'model':'model-id','api_key':'third-secret'}).status_code==200
        assert c.get('/api/diagnostics').json()['checks'][-1]['status']=='unverified'


def test_inflight_model_test_cannot_validate_new_settings(tmp_path,preview_ok):
    class ChangingGateway(Gateway):
        async def call(self,*args):
            self.save(ModelSettings(model='new-model',api_key='changed-key'))
            return PLAN,{'model':'old-model'}
    gateway=ChangingGateway(tmp_path);gateway.save(ModelSettings(model='old-model',api_key='old-key'))
    app=create_app(tmp_path,gateway,DiagnosticRunner())
    with TestClient(app) as c:
        assert c.post('/api/settings/model/test').status_code==409
        assert c.get('/api/diagnostics').json()['checks'][-1]['status']=='unverified'


def test_preview_identity():
    with TestClient(create_preview_app()) as c:
        assert c.get('/health').json()=={'service':'ludraft-preview'}


@pytest.mark.asyncio
@pytest.mark.parametrize('origin',['https://example.com','http://user:secret@localhost:8081','http://localhost:8081/path','http://localhost:8081?key=secret','http://[invalid'])
async def test_diagnostics_does_not_probe_arbitrary_urls(origin):
    from studio.discovery import preview_status
    assert await preview_status(origin)=='unverified'


@pytest.mark.asyncio
async def test_preview_identity_failure(monkeypatch):
    import httpx
    from studio.discovery import preview_status
    real=httpx.AsyncClient
    monkeypatch.setattr(httpx,'AsyncClient',lambda **kw:real(transport=httpx.MockTransport(lambda req:httpx.Response(200,json={'service':'other'})),**kw))
    assert await preview_status('http://127.0.0.1:8081')=='failed'


@pytest.mark.asyncio
@pytest.mark.parametrize('cli,daemon,image,expected',[(False,False,False,{'cli':False,'daemon':None,'image':None}),(True,False,False,{'cli':True,'daemon':False,'image':None}),(True,True,False,{'cli':True,'daemon':True,'image':False}),(True,True,True,{'cli':True,'daemon':True,'image':True})])
async def test_docker_diagnostic_stages(monkeypatch,cli,daemon,image,expected):
    monkeypatch.setattr('studio.runner.shutil.which',lambda command:'/bin/docker' if cli else None)
    async def probe(*args):return daemon if args==('info',) else image
    runner=Runner();monkeypatch.setattr(runner,'_probe',probe)
    assert await runner.diagnostics()==expected


@pytest.mark.asyncio
async def test_probe_timeout_kills_child(monkeypatch):
    class Process:
        returncode=None
        killed=False
        async def wait(self):return self.returncode
        def kill(self):self.killed=True;self.returncode=-9
    process=Process()
    async def spawn(*args,**kwargs):return process
    async def timeout(coro,*args):coro.close();raise asyncio.TimeoutError
    monkeypatch.setattr('studio.runner.asyncio.create_subprocess_exec',spawn)
    monkeypatch.setattr('studio.runner.asyncio.wait_for',timeout)
    assert not await Runner()._probe('info')
    assert process.killed


def test_comparison_correct_direction_and_project_boundary(tmp_path):
    app=create_app(tmp_path,FakeGateway(),ParameterRunner())
    with TestClient(app) as c:
        pid,rid,vid,params=seed(app.state.store)
        v2=uid();source=tmp_path/'versions'/vid;dest=tmp_path/'versions'/v2;copy_source(source,dest)
        params.update(lives=5,speed=180,background='#123456')
        content,_=update_config((dest/'src/config.ts').read_text(),Parameters(**params));(dest/'src/config.ts').write_text(content)
        app.state.store.execute('INSERT INTO versions VALUES(?,?,?,?,?,?,?,?)',(v2,pid,rid,'修改版',str(dest),'{}','',now()))
        result=c.get(f'/api/projects/{pid}/compare',params={'before':vid,'after':v2})
        assert result.status_code==200
        data=result.json();values={x['key']:x for x in data['parameters']}
        assert values['lives']=={'key':'lives','before':3,'after':5}
        assert len(data['files'])==1 and data['files'][0]['path']=='src/config.ts'
        assert str(tmp_path) not in result.text and data['added']>0 and data['removed']>0
        reverse=c.get(f'/api/projects/{pid}/compare',params={'before':v2,'after':vid}).json()
        assert next(x for x in reverse['parameters'] if x['key']=='speed')['before']==180
        assert reverse['added']==data['removed'] and reverse['removed']==data['added']
        same=c.get(f'/api/projects/{pid}/compare',params={'before':vid,'after':vid}).json()
        assert same['identical'] and same['files']==[] and same['parameters']==[]
        other,_,foreign,_=seed(app.state.store)
        assert c.get(f'/api/projects/{pid}/compare',params={'before':vid,'after':foreign}).status_code==400
        assert c.get(f'/api/projects/{pid}/compare',params={'before':vid,'after':'missing'}).status_code==404
        assert c.get(f'/api/projects/{pid}').json()['active_version']==vid
        (dest/'src/config.ts').write_text('export const config = dynamicConfig();')
        dynamic=c.get(f'/api/projects/{pid}/compare',params={'before':vid,'after':v2}).json()
        assert dynamic['parameters'] is None and dynamic['parameter_note'] and dynamic['files']

@pytest.mark.parametrize('before_mode',['collector','dodger','clicker','match3'])
@pytest.mark.parametrize('after_mode',['collector','dodger','clicker','match3'])
def test_comparison_all_modes_and_cross_mode_parameters(tmp_path,before_mode,after_mode):
    from scripts.evaluate import CASES,configure,template_for
    cases={case['mode']:case for case in CASES[:4]}
    with TestClient(create_app(tmp_path,FakeGateway(),ParameterRunner())) as c:
        store=c.app.state.store;pid,rid,active,_=seed(store)
        versions=[];configs=[]
        for index,mode in enumerate([before_mode,after_mode]):
            case={**cases[mode]};case['title']='对比 '+str(index)
            if index:case['moves' if mode=='match3' else 'lives']=30 if mode=='match3' else 5
            vid=uid();dest=tmp_path/'versions'/vid;copy_source(template_for(case),dest);configure(dest,case)
            configs.append(read_config((dest/'src/config.ts').read_text()))
            store.execute('INSERT INTO versions VALUES(?,?,?,?,?,?,?,?)',(vid,pid,rid,case['title'],str(dest),'{}','',now()));versions.append(vid)
        result=c.get(f'/api/projects/{pid}/compare',params={'before':versions[0],'after':versions[1]})
        assert result.status_code==200,result.text
        changes={p['key']:p for p in result.json()['parameters']}
        expected={k for k in configs[0].keys()|configs[1].keys() if configs[0].get(k)!=configs[1].get(k)}
        assert set(changes)==expected
        for k in changes:assert changes[k]=={'key':k,'before':configs[0].get(k),'after':configs[1].get(k)}
        if (before_mode=='match3')!=(after_mode=='match3'):
            assert changes['moves']['before'] is None or changes['moves']['after'] is None
            assert changes['lives']['before'] is None or changes['lives']['after'] is None
        reverse=c.get(f'/api/projects/{pid}/compare',params={'before':versions[1],'after':versions[0]}).json()
        assert {r['key']:r['before'] for r in reverse['parameters']}=={k:v['after'] for k,v in changes.items()}
        same=c.get(f'/api/projects/{pid}/compare',params={'before':versions[0],'after':versions[0]}).json()
        assert same['identical'] and same['parameters']==[]
        assert c.get(f'/api/projects/{pid}').json()['active_version']==active


def test_diagnostics_includes_every_effective_role_and_invalidates_stale_proof(tmp_path,preview_ok):
    from studio.connections import RoleConnection,ConnectionProbe
    from studio.team import ROLES
    class G(Gateway):
        failing=None
        calls=0
        async def call(self,role,prompt,schema):
            self.calls+=1
            if role==self.failing:raise ModelError('固定连接失败')
            return (PLAN if schema is type(PLAN) else ConnectionProbe(summary='协议连接测试')),{'model':self.effective(role)['model'],'usage':{}}
    g=G(tmp_path);g.save(ModelSettings(model='shared',api_key='SHARED-SECRET'))
    g.save_connection('QA',RoleConnection(mode='independent',model='qa-model',api_key='QA-SECRET'))
    with TestClient(create_app(tmp_path,g,DiagnosticRunner())) as c:
        assert c.post('/api/settings/model/test').status_code==200
        before=g.calls;data=c.get('/api/diagnostics').json()
        assert g.calls==before and not data['ready']
        assert sum(r['status']=='passed' for r in data['model_roles'])==7
        assert next(r for r in data['model_roles'] if r['role']=='QA')['status']=='unverified'
        assert next(r for r in data['model_roles'] if r['role']=='程序')['verification_source']=='策划'
        assert c.post('/api/settings/connections/QA/test').status_code==200
        assert c.get('/api/diagnostics').json()['ready']
        g.failing='QA';assert c.post('/api/settings/connections/QA/test').status_code==400
        assert not c.get('/api/diagnostics').json()['ready']
        g.failing=None
        # A changed independent key invalidates that role's proof.
        g.save_connection('QA',RoleConnection(mode='independent',model='qa-model',api_key='NEW-QA-SECRET'))
        data=c.get('/api/diagnostics').json()
        assert not data['ready'] and next(r for r in data['model_roles'] if r['role']=='QA')['status']=='unverified'
        raw=json.dumps(data)
        assert all(secret not in raw for secret in ('SHARED-SECRET','QA-SECRET','NEW-QA-SECRET',g.role_identity('QA')))


def test_planner_only_configuration_is_not_eight_role_ready(tmp_path,preview_ok):
    from studio.connections import RoleConnection,ConnectionProbe
    class G(Gateway):
        async def call(self,role,prompt,schema):return ConnectionProbe(summary='固定测试连接正常'),{'model':'planner','usage':{}}
    g=G(tmp_path)
    g.save_connection('策划',RoleConnection(mode='independent',model='planner',api_key='PLANNER-SECRET'))
    with TestClient(create_app(tmp_path,g,DiagnosticRunner())) as c:
        assert c.post('/api/settings/connections/策划/test').status_code==200
        data=c.get('/api/diagnostics').json()
        assert not data['ready']
        assert sum(r['status']=='passed' for r in data['model_roles'])==1
        assert sum(r['status']=='failed' for r in data['model_roles'])==7
