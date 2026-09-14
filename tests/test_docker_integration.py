"""Opt-in integration: fixed model-protocol responses, REAL Docker builds/browser tests.
Does not measure LLM quality. Run STUDIO_DOCKER_TESTS=1 python -m pytest tests/test_docker_integration.py.
"""
import io
import json
import os
import zipfile
from pathlib import Path
import pytest
from fastapi.testclient import TestClient
from studio.app import create_app
from studio.db import Store, uid, now
from studio.files import TEMPLATE
from studio.models import Plan, Changes
from studio.runner import Runner
from studio.workflow import Workflow

pytestmark = pytest.mark.skipif(os.getenv('STUDIO_DOCKER_TESTS')!='1',reason='opt-in real Docker integration')

class ScriptedGateway:
    def __init__(self):self.phase=0
    def public(self):return {'model':'protocol-fixture','has_key':False,'base_url':'http://localhost'}
    async def call(self,role,prompt,schema):
        if schema is Plan:
            result=Plan(title='协议集成测试',summary='接金币躲炸弹，并验证版本连续迭代。',mode='collector',controls='左右键移动',acceptance=['开始与移动','金币得分','炸弹扣命'])
        else:
            content=(TEMPLATE/'src/config.ts').read_text()
            if self.phase==1:content=content.replace('speed: 320','speed: 180').replace('lives: 3','lives: 5').replace('#10192b','#231a32')
            if self.phase==2:content='export const config = ; // intentionally invalid TypeScript'
            result=Changes(summary='固定响应协议测试，不是模型生成',files=[{'path':'src/config.ts','content':content}])
        return result,{'model':'protocol-fixture','usage':{}}

@pytest.mark.asyncio
async def test_real_build_modify_failure_rollback_export(tmp_path):
    store=Store(tmp_path);gateway=ScriptedGateway();runner=Runner();w=Workflow(store,gateway,runner)
    assert await runner.available(), 'Build gamedev-runner:1 first'
    pid=uid();store.execute('INSERT INTO projects VALUES(?,?,?,?)',(pid,'集成测试',None,now()))
    async def run(text):
        rid=uid();base=store.one('SELECT * FROM projects WHERE id=?',(pid,))['active_version']
        store.execute('INSERT INTO runs(id,project_id,status,requirement,base_version,created_at) VALUES(?,?,?,?,?,?)',(rid,pid,'queued',text,base,now()))
        await w.work(rid,'plan')
        assert store.run(rid)['status']=='waiting_confirmation'
        store.execute("UPDATE runs SET status='queued' WHERE id=?",(rid,))
        await w.work(rid,'implement')
        return store.run(rid)
    first=await run('创建基础游戏')
    assert first['status']=='succeeded'
    v1=store.one('SELECT * FROM versions WHERE run_id=?',(first['id'],))
    before=(Path(v1['path'])/'src/config.ts').read_text()
    gateway.phase=1
    second=await run('移动慢一点，五条生命，紫色背景')
    assert second['status']=='succeeded'
    v2=store.one('SELECT * FROM versions WHERE run_id=?',(second['id'],))
    evidence=json.loads(v2['evidence'])
    assert evidence['config']['speed']==180 and evidence['config']['lives']==5 and evidence['config']['background']=='#231a32'
    assert (Path(v1['path'])/'src/config.ts').read_text()==before
    gateway.phase=2
    failure=await run('固定错误响应，验证失败保护')
    assert failure['status']=='failed' and failure['repairs']==2
    assert store.one('SELECT * FROM projects WHERE id=?',(pid,))['active_version']==v2['id']
    assert len(store.query('SELECT * FROM versions'))==2
    failed_evidence=store.query("SELECT payload FROM events WHERE run_id=? AND kind='test_result'",(failure['id'],))
    assert len(failed_evidence)==3 and all(not json.loads(e['payload'])['build'] for e in failed_evidence)
    app=create_app(tmp_path,gateway,runner)
    with TestClient(app) as client:
        r=client.post(f'/api/projects/{pid}/rollback',json={'version_id':v1['id']})
        assert r.status_code==200
        assert client.get(f'/api/projects/{pid}').json()['active_version']==v1['id']
        exported=client.get(f"/api/versions/{v1['id']}/export")
        with zipfile.ZipFile(io.BytesIO(exported.content)) as archive:
            assert 'dist/main.js' in archive.namelist()
            assert archive.read('src/config.ts').decode()==before
            assert json.loads(archive.read('verification.json'))['passed'] is True
    store.con.close()

@pytest.mark.asyncio
async def test_real_parameter_editor_without_model_call(tmp_path):
    import asyncio
    from studio.models import Parameters
    from studio.parameters import read_config
    gateway=ScriptedGateway();runner=Runner();store=Store(tmp_path);w=Workflow(store,gateway,runner)
    pid,rid=uid(),uid()
    store.execute('INSERT INTO projects VALUES(?,?,?,?)',(pid,'参数集成测试',None,now()))
    store.execute('INSERT INTO runs(id,project_id,status,requirement,created_at) VALUES(?,?,?,?,?)',(rid,pid,'queued','创建基础模板',now()))
    await w.work(rid,'plan');store.execute("UPDATE runs SET status='queued' WHERE id=?",(rid,));await w.work(rid,'implement')
    assert store.run(rid)['status']=='succeeded'
    base=store.one('SELECT * FROM versions');original=(Path(base['path'])/'src/config.ts').read_text()
    values=read_config(original)
    params={k:values[k] for k in Parameters.model_fields};params.update(lives=5,speed=180,background='#19213b')
    class NoModel:
        def public(self):return {'model':'','has_key':False,'base_url':'http://localhost'}
        async def call(self,*args):raise AssertionError('Parameter edits must not call the model')
    app=create_app(tmp_path,NoModel(),runner)
    with TestClient(app) as c:
        result=c.post(f'/api/projects/{pid}/parameters',json={'base_version':base['id'],'parameters':params})
        assert result.status_code==201,result.text
        new_run=result.json()['run_id']
        for _ in range(400):
            state=app.state.store.run(new_run)
            if state['status'] in ('succeeded','failed'):break
            await asyncio.sleep(.1)
        assert state['status']=='succeeded',state
        project=c.get(f'/api/projects/{pid}').json();v=c.get('/api/versions/'+project['active_version']).json()
        assert v['evidence']['passed'] and v['evidence']['parameter_match']
        assert v['parameters']['lives']==5 and v['parameters']['speed']==180
        assert (Path(base['path'])/'src/config.ts').read_text()==original
        assert c.post(f'/api/projects/{pid}/rollback',json={'version_id':base['id']}).status_code==200
    store.con.close()

@pytest.mark.asyncio
async def test_eight_role_build_modify_failure_and_export(tmp_path):
    from team_fixture import TeamGateway
    gateway=TeamGateway();runner=Runner();store=Store(tmp_path);w=Workflow(store,gateway,runner)
    assert await runner.available(), 'Build gamedev-runner:1 first'
    pid=uid();store.execute('INSERT INTO projects VALUES(?,?,?,?)',(pid,'八角色集成测试',None,now()))
    async def execute(text):
        rid=uid();base=store.one('SELECT active_version FROM projects WHERE id=?',(pid,))['active_version']
        store.execute('INSERT INTO runs(id,project_id,status,requirement,base_version,created_at) VALUES(?,?,?,?,?,?)',(rid,pid,'queued',text,base,now()))
        store.execute('INSERT INTO run_options VALUES(?,?,?)',(rid,'team8','{}'))
        await w.work(rid,'plan');assert store.run(rid)['status']=='waiting_confirmation'
        store.execute("UPDATE runs SET status='queued' WHERE id=?",(rid,));await w.work(rid,'implement')
        return store.run(rid)
    first=await execute('接金币躲炸弹');assert first['status']=='succeeded',first
    v1=store.one('SELECT * FROM versions WHERE run_id=?',(first['id'],))
    gateway.phase=1;second=await execute('移动慢一点，增加生命');assert second['status']=='succeeded',second
    v2=store.one('SELECT * FROM versions WHERE run_id=?',(second['id'],));evidence=json.loads(v2['evidence'])
    assert evidence['config']['speed']==180 and evidence['config']['lives']==5 and evidence['team']['mode']=='team8'
    gateway.phase=2;failed=await execute('验证错误 TypeScript 的旧版保护');assert failed['status']=='failed' and failed['repairs']==2
    assert store.one('SELECT active_version FROM projects')['active_version']==v2['id']
    assert len(store.query('SELECT * FROM versions'))==2
    assert len(store.query("SELECT * FROM events WHERE run_id=? AND kind='test_result'",(failed['id'],)))==3
    with TestClient(create_app(tmp_path,gateway,runner)) as c:
        assert c.post('/api/projects/'+pid+'/rollback',json={'version_id':v1['id']}).status_code==200
        result=c.get('/api/versions/'+v2['id']+'/export')
        with zipfile.ZipFile(io.BytesIO(result.content)) as z:
            assert len(json.loads(z.read('collaboration.json')))==13
            assert json.loads(z.read('verification.json'))['team']['mode']=='team8'
    store.con.close()

@pytest.mark.asyncio
async def test_routed_visual_build_and_inherited_design_export(tmp_path):
    from test_team import setup,approve
    from test_routing import modification
    from studio.routing import options
    from team_fixture import TeamGateway
    gateway=TeamGateway();s,w,pid,rid=setup(tmp_path,gateway,Runner())
    await approve(w,rid);assert s.run(rid)['status']=='succeeded'
    base=s.one('SELECT id FROM versions')['id']
    second=modification(s,pid,base,'visual')
    gateway.phase=1
    await approve(w,second);assert s.run(second)['status']=='succeeded',s.run(second)
    assert options(s,second)['route']['reuse']==['tech']
    assert len(s.query('SELECT * FROM agent_steps WHERE run_id=?',(second,)))==12
    version=s.one('SELECT * FROM versions WHERE run_id=?',(second,))
    assert json.loads(version['evidence'])['passed']
    with TestClient(create_app(tmp_path,gateway,Runner())) as c:
        with zipfile.ZipFile(io.BytesIO(c.get('/api/versions/'+version['id']+'/export').content)) as z:
            steps=json.loads(z.read('collaboration.json'));ids={x['id'] for x in steps}
            assert all(set(x['inputs'] or [])<=ids for x in steps)
            assert json.loads(z.read('verification.json'))['passed']
    s.con.close()

@pytest.mark.asyncio
async def test_match3_real_game_and_parallel_role_generation(tmp_path):
    from match3_fixture import Match3Gateway
    from test_team import setup,approve
    s,w,pid,rid=setup(tmp_path,Match3Gateway(),Runner());await approve(w,rid)
    assert s.run(rid)['status']=='succeeded',s.run(rid)
    v=s.one('SELECT * FROM versions');evidence=json.loads(v['evidence'])
    assert evidence['passed'] and evidence['config']['mode']=='match3'
    names={c['name'] for c in evidence['checks'] if c['passed']}
    assert {'下落补位与连锁','无解棋盘重排','目标达成与失败','真实交换消除与步数'}<=names
    assert s.one("SELECT status FROM agent_steps WHERE run_id=? AND task_key='code'",(rid,))['status']=='assembled'
    s.con.close()

@pytest.mark.asyncio
async def test_config_route_real_match3_parameters_and_export(tmp_path):
    from test_team import setup,approve
    from test_routing import modification
    from config_fixture import ConfigGateway
    from studio.files import source_files
    s,w,pid,rid=setup(tmp_path,ConfigGateway(),Runner());await approve(w,rid)
    assert s.run(rid)['status']=='succeeded'
    base=s.one('SELECT * FROM versions');before=source_files(Path(base['path']))
    second=modification(s,pid,base['id'],'config');await approve(w,second)
    assert s.run(second)['status']=='succeeded',s.run(second)
    v=s.one('SELECT * FROM versions WHERE run_id=?',(second,));e=json.loads(v['evidence'])
    assert e['passed'] and e['parameter_match'] and e['unchanged_sources']
    assert e['config']['moves']==30 and e['config']['targetScore']==1500
    assert {'真实交换消除与步数','下落补位与连锁','目标达成与失败'}<={c['name'] for c in e['checks'] if c['passed']}
    assert source_files(Path(v['path']))['src/game.ts']==before['src/game.ts']
    assert len(s.query('SELECT id FROM agent_steps WHERE run_id=?',(second,)))==6
    s.con.close()
    with TestClient(create_app(tmp_path,ConfigGateway(),Runner())) as c:
        with zipfile.ZipFile(io.BytesIO(c.get('/api/versions/'+v['id']+'/export').content)) as z:
            assert json.loads(z.read('verification.json'))['parameter_match']
            steps=json.loads(z.read('collaboration.json'));ids={x['id'] for x in steps}
            assert all(set(x['inputs'] or [])<=ids for x in steps)
        assert c.post('/api/projects/'+pid+'/rollback',json={'version_id':base['id']}).status_code==200

@pytest.mark.asyncio
async def test_standalone_test_reports_real_pass_and_compile_failure_without_publication(tmp_path):
    from test_team import setup,approve
    from test_routing import modification
    from testing_fixture import ReportGateway
    from studio.test_flow import manifest
    class CorruptCandidate(Runner):
        async def run(self,path,rid):
            (path/'src/game.ts').write_text('export class Game { broken TypeScript = ; }')
            return await super().run(path,rid)
    s,w,pid,rid=setup(tmp_path,ReportGateway(),Runner());await approve(w,rid)
    assert s.run(rid)['status']=='succeeded'
    base=s.one('SELECT * FROM versions');before=manifest(Path(base['path']))
    second=modification(s,pid,base['id'],'test');await approve(w,second)
    assert s.run(second)['status']=='succeeded',s.run(second)
    report=json.loads(s.one('SELECT payload FROM run_reports WHERE run_id=?',(second,))['payload'])
    assert report['passed'] and report['tool_evidence']['input_unchanged']
    assert len(s.query('SELECT * FROM versions'))==1
    w.runner=CorruptCandidate();third=modification(s,pid,base['id'],'test');await approve(w,third)
    assert s.run(third)['status']=='failed' and s.run(third)['repairs']==0
    failed=json.loads(s.one('SELECT payload FROM run_reports WHERE run_id=?',(third,))['payload'])
    assert not failed['passed'] and not failed['tool_evidence']['build'] and not failed['tool_evidence']['input_unchanged']
    assert manifest(Path(base['path']))==before
    assert s.one('SELECT active_version FROM projects')['active_version']==base['id']
    s.con.close()
    with TestClient(create_app(tmp_path,ReportGateway(),Runner())) as c:
        for report_id in (second,third):
            with zipfile.ZipFile(io.BytesIO(c.get('/api/runs/'+report_id+'/report/export').content)) as z:
                assert json.loads(z.read('report.json'))['run_id']==report_id
