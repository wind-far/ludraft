import asyncio
import io
import json
import re
import zipfile
from pathlib import Path
import pytest
from fastapi.testclient import TestClient
from studio.app import create_app, create_preview_app
from studio.db import Store, now, uid
from studio.files import TEMPLATE, apply_changes, source_files
from studio.llm import Gateway, ModelError
from studio.models import Plan, Changes, ModelSettings
from studio.workflow import Workflow

PLAN = Plan(title='测试星光', summary='接金币躲炸弹，三条生命，持续一分钟。', mode='collector', controls='左右方向键移动', acceptance=['开始后可移动', '金币增加得分', '炸弹扣减生命'])

class FakeGateway:
    """Protocol fixture only. Does not represent a real model call or generation quality."""
    def __init__(self, fail=False): self.calls = 0; self.fail = fail
    def public(self): return {'model':'test-fixture','has_key':False,'base_url':'http://localhost'}
    async def call(self, role, prompt, schema):
        self.calls += 1
        if self.fail: raise ModelError('测试用模型失败')
        if schema is Plan: return PLAN, {'model':'test-fixture','usage':{}}
        return Changes(summary='测试文件变更', files=[{'path':'src/config.ts','content':(TEMPLATE/'src/config.ts').read_text().replace('星光收集站','测试星光')}]), {'model':'test-fixture','usage':{}}

class FakeRunner:
    """Workflow test double; the Docker integration suite validates real execution."""
    def __init__(self, passed=True, available=True): self.passed=passed; self.ready=available; self.calls=0
    async def available(self): return self.ready
    async def run(self, path, run_id):
        self.calls += 1
        (path/'dist').mkdir(exist_ok=True)
        (path/'dist/main.js').write_text('// fixture, not playable')
        from studio.verification import required_checks
        match=re.search(r'''["']?mode["']?\s*:\s*["'](collector|dodger|clicker|match3)["']''',(path/'src/config.ts').read_text())
        mode=match[1] if match else 'collector'
        return {'passed':self.passed,'build':self.passed,'config':{'mode':mode},
            'checks':[{'name':name,'passed':self.passed} for name in required_checks(mode)],
            'exit_code':0 if self.passed else 1,'source':'unit-test-double'}

def create_run(store, base=None):
    pid, rid = uid(), uid()
    store.execute('INSERT INTO projects VALUES(?,?,?,?)', (pid,'测试',base,now()))
    store.execute('INSERT INTO runs(id,project_id,status,requirement,base_version,created_at) VALUES(?,?,?,?,?,?)', (rid,pid,'queued','接金币躲炸弹',base,now()))
    return pid,rid

@pytest.mark.asyncio
async def test_plan_waits_without_coding(tmp_path):
    store=Store(tmp_path); _,rid=create_run(store);g=FakeGateway();r=FakeRunner();w=Workflow(store,g,r)
    await w.work(rid,'plan')
    assert store.run(rid)['status']=='waiting_confirmation'
    assert g.calls==1 and r.calls==0
    assert store.query('SELECT * FROM versions')==[]
    store.con.close()

@pytest.mark.asyncio
async def test_real_error_is_failure_not_success(tmp_path):
    store=Store(tmp_path);_,rid=create_run(store);w=Workflow(store,FakeGateway(True),FakeRunner())
    await w.work(rid,'plan')
    assert store.run(rid)['status']=='failed'
    assert store.query('SELECT * FROM versions')==[]
    store.con.close()

@pytest.mark.asyncio
async def test_repair_cap_and_previous_version_unchanged(tmp_path):
    store=Store(tmp_path);pid,rid=create_run(store,'previous-version');r=FakeRunner(False);w=Workflow(store,FakeGateway(),r)
    store.execute('UPDATE runs SET plan=? WHERE id=?',(PLAN.model_dump_json(),rid))
    # Missing version record means a fresh template, but active pointer must still stay untouched.
    await w.work(rid,'implement')
    assert r.calls==3
    assert store.run(rid)['status']=='failed' and store.run(rid)['repairs']==2
    assert store.one('SELECT * FROM projects WHERE id=?',(pid,))['active_version']=='previous-version'
    assert not store.query('SELECT * FROM versions')
    store.con.close()

@pytest.mark.asyncio
async def test_published_version_is_snapshot(tmp_path):
    store=Store(tmp_path);pid,rid=create_run(store);w=Workflow(store,FakeGateway(),FakeRunner())
    store.execute('UPDATE runs SET plan=? WHERE id=?',(PLAN.model_dump_json(),rid))
    await w.work(rid,'implement')
    assert store.run(rid)['status']=='succeeded'
    v=store.one('SELECT * FROM versions')
    assert v['id']==store.one('SELECT * FROM projects')['active_version']
    assert '测试星光' in v['diff']
    assert (Path(v['path'])/'src/config.ts').stat().st_mode & 0o222 == 0
    store.con.close()

@pytest.mark.asyncio
async def test_cancel_prevents_work(tmp_path):
    store=Store(tmp_path);_,rid=create_run(store);g=FakeGateway();w=Workflow(store,g,FakeRunner())
    await w.cancel(rid);await w.work(rid,'plan')
    assert store.run(rid)['status']=='cancelled' and g.calls==0
    store.con.close()

@pytest.mark.asyncio
async def test_missing_runner_stops_before_model(tmp_path):
    store=Store(tmp_path);_,rid=create_run(store);g=FakeGateway();w=Workflow(store,g,FakeRunner(available=False))
    await w.work(rid,'implement')
    assert store.run(rid)['status']=='failed' and g.calls==0
    store.con.close()

def test_recovery_preserves_approval_wait(tmp_path):
    store=Store(tmp_path);_,rid=create_run(store)
    _,waiting=create_run(store);store.execute("UPDATE runs SET status='waiting_confirmation' WHERE id=?",(waiting,))
    store.recover()
    assert store.run(rid)['status']=='failed'
    assert store.run(waiting)['status']=='waiting_confirmation'
    store.con.close()

@pytest.mark.parametrize('path',['../secret','/etc/passwd','src/../../x','package.json','src/main.ts'])
def test_model_cannot_edit_tools_or_escape(path):
    with pytest.raises(ValueError): Changes.model_validate({'summary':'x','files':[{'path':path,'content':'abc'}]})

def test_duplicate_file_rejected(tmp_path):
    with pytest.raises(ValueError):
        apply_changes(tmp_path,Changes(summary='重复',files=[{'path':'style.css','content':'a'},{'path':'style.css','content':'b'}]))

def test_symlink_rejected(tmp_path):
    (tmp_path/'style.css').symlink_to('/etc/hosts')
    with pytest.raises(ValueError): apply_changes(tmp_path,Changes(summary='越界',files=[{'path':'style.css','content':'bad'}]))

def test_key_never_returned_and_file_private(tmp_path):
    gateway=Gateway(tmp_path)
    result=gateway.save(ModelSettings(model='example',api_key='secret-test-value'))
    assert 'secret-test-value' not in json.dumps(result) and 'api_key' not in result
    assert gateway.path.stat().st_mode & 0o077==0
    gateway.save(ModelSettings(model='example'))
    assert gateway.config()['api_key']=='secret-test-value'
    gateway.save(ModelSettings(clear_key=True))
    assert not gateway.public()['has_key']

def test_model_url_no_credentials(tmp_path):
    with pytest.raises(ValueError): Gateway(tmp_path).save(ModelSettings(base_url='https://secret@example.com/v1'))

@pytest.mark.asyncio
async def test_missing_model_fails_explicitly(tmp_path,monkeypatch):
    monkeypatch.delenv('STUDIO_MODEL',raising=False)
    with pytest.raises(ModelError): await Gateway(tmp_path).call('策划','hello',Plan)

def test_api_decision_rejection_export_and_origin(tmp_path):
    app=create_app(tmp_path,FakeGateway(),FakeRunner())
    with TestClient(app) as client:
        store=app.state.store
        pid,rid=create_run(store)
        store.execute("UPDATE runs SET status='waiting_confirmation',plan=? WHERE id=?",(PLAN.model_dump_json(),rid))
        assert client.post(f'/api/runs/{rid}/decision',json={'approve':False}).json()['status']=='cancelled'
        assert client.post(f'/api/runs/{rid}/decision',json={'approve':True}).status_code==409
        assert client.post('/api/projects',json={'text':'abc'},headers={'Origin':'http://evil.example'}).status_code==403
        assert client.get('/api/settings/model',headers={'Origin':'null'}).status_code==403
        assert client.get('/api/health',headers={'Host':'evil.example'}).status_code==403
        vid=uid();base=tmp_path/'versions'/vid;base.mkdir(parents=True);(base/'index.html').write_text('test')
        store.execute('INSERT INTO versions VALUES(?,?,?,?,?,?,?,?)',(vid,pid,rid,'test',str(base),'{}','',now()))
        archive=client.get('/api/versions/'+vid+'/export')
        assert archive.status_code==200
        with zipfile.ZipFile(io.BytesIO(archive.content)) as z:
            assert set(z.namelist())=={'index.html','verification.json','provenance.json','RUN_GAME.md','licenses/upstream-MIT.txt'}
        assert client.post('/api/projects/'+pid+'/rollback',json={'version_id':vid}).status_code==200
        assert store.one('SELECT * FROM projects WHERE id=?',(pid,))['active_version']==vid

def test_preview_only_allowlisted_immutable_files(tmp_path):
    vid=uid();base=tmp_path/'versions'/vid;base.mkdir(parents=True);(base/'index.html').write_text('<h1>game</h1>')
    with TestClient(create_preview_app(tmp_path)) as client:
        response=client.get('/v/'+vid+'/index.html')
        assert response.status_code==200
        assert "connect-src 'none'" in response.headers['content-security-policy']
        assert 'sandbox allow-scripts' in response.headers['content-security-policy']
        assert client.get('/v/'+vid+'/evidence.json').status_code==404
        assert client.get('/api/settings/model').status_code==404

def test_only_one_active_run_per_project(tmp_path):
    import sqlite3
    store=Store(tmp_path);pid,rid=create_run(store)
    with pytest.raises(sqlite3.IntegrityError):
        store.execute('INSERT INTO runs(id,project_id,status) VALUES(?,?,?)',(uid(),pid,'queued'))
    store.con.close()

def test_upstream_key_serialization():
    from src.core.llm_adapter import AgentModelConfig
    cfg=AgentModelConfig(agent_id='test',api_key='secret-upstream-key')
    assert 'api_key' not in cfg.to_dict()
    assert cfg.to_dict_full()['api_key']=='secret-upstream-key'

def test_upstream_gate_failure_not_completed():
    from types import SimpleNamespace
    from src.core.orchestrator import Orchestrator
    orchestrator=object.__new__(Orchestrator)
    step=SimpleNamespace(parallel_with=[],status='pending',stage='test',agent_id='test',quality_gate='gate_3')
    pipeline=SimpleNamespace(current_step=step,pipeline_id='p',status='running')
    orchestrator._record_log=lambda *args,**kwargs: None
    orchestrator._execute_agent_step=lambda *args: {'status':'completed'}
    orchestrator._check_quality_gate=lambda *args: False
    result=orchestrator._execute_pipeline(pipeline)
    assert result['status']=='failed' and pipeline.status=='failed'

@pytest.mark.asyncio
async def test_model_http_protocol_and_invalid_json(tmp_path,monkeypatch):
    import httpx
    real_client=httpx.AsyncClient
    seen=[]
    def respond(request):
        seen.append(json.loads(request.content))
        return httpx.Response(200,json={'choices':[{'message':{'content':PLAN.model_dump_json()}}],'usage':{'total_tokens':42}})
    monkeypatch.setattr(httpx,'AsyncClient',lambda **kwargs:real_client(transport=httpx.MockTransport(respond),**kwargs))
    g=Gateway(tmp_path);g.save(ModelSettings(model='fixture-model',base_url='http://localhost:9999/v1'))
    plan,metadata=await g.call('策划','需求',Plan)
    assert plan.title==PLAN.title and metadata['usage']['total_tokens']==42
    assert seen[0]['model']=='fixture-model'
    monkeypatch.setattr(httpx,'AsyncClient',lambda **kwargs:real_client(transport=httpx.MockTransport(lambda r:httpx.Response(200,json={'choices':[{'message':{'content':'not json'}}]})),**kwargs))
    with pytest.raises(ModelError):await g.call('策划','需求',Plan)

@pytest.mark.asyncio
async def test_cancel_during_tool_preserves_previous(tmp_path):
    started=asyncio.Event();cancelled=asyncio.Event()
    class SlowRunner(FakeRunner):
        async def run(self,path,rid):
            started.set()
            try:await asyncio.Event().wait()
            finally:cancelled.set()
    store=Store(tmp_path);pid,rid=create_run(store,'old');w=Workflow(store,FakeGateway(),SlowRunner())
    store.execute('UPDATE runs SET plan=? WHERE id=?',(PLAN.model_dump_json(),rid))
    w.launch(rid,'implement');await asyncio.wait_for(started.wait(),2)
    await w.cancel(rid)
    assert cancelled.is_set() and store.run(rid)['status']=='cancelled'
    assert store.one('SELECT * FROM projects')['active_version']=='old'
    store.con.close()

@pytest.mark.asyncio
async def test_modify_readonly_snapshot_and_preserve_original(tmp_path):
    store=Store(tmp_path);pid,rid=create_run(store);w=Workflow(store,FakeGateway(),FakeRunner())
    store.execute('UPDATE runs SET plan=? WHERE id=?',(PLAN.model_dump_json(),rid))
    await w.work(rid,'implement')
    base=store.one('SELECT * FROM versions');before=source_files(Path(base['path']))
    second=uid()
    store.execute('INSERT INTO runs(id,project_id,status,requirement,base_version,plan,created_at) VALUES(?,?,?,?,?,?,?)',
                  (second,pid,'queued','修改配色',base['id'],PLAN.model_dump_json(),now()))
    await w.work(second,'implement')
    assert store.run(second)['status']=='succeeded'
    assert store.one('SELECT * FROM projects')['active_version']!=base['id']
    assert source_files(Path(base['path']))==before
    store.con.close()
