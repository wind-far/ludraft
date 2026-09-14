import asyncio
import io
import json
import zipfile
import pytest
from fastapi.testclient import TestClient
from studio.app import create_app
from studio.db import Store
from studio.models import Plan, ModelSettings
from studio.team_models import TaskBoard, Design, Review, QAReport, Delivery, Issue, TeamModels
from studio.workflow import Workflow
from studio.llm import Gateway, ModelError
from test_studio import create_run, FakeRunner
from team_fixture import TeamGateway, BOARD


def setup(tmp_path,gateway=None,runner=None):
    store=Store(tmp_path);pid,rid=create_run(store)
    store.execute('INSERT INTO run_options VALUES(?,?,?)',(rid,'team8','{}'))
    return store,Workflow(store,gateway or TeamGateway(),runner or FakeRunner()),pid,rid

async def approve(w,rid):
    await w.work(rid,'plan')
    assert w.store.run(rid)['status']=='waiting_confirmation',w.store.run(rid)
    w.store.execute("UPDATE runs SET status='queued' WHERE id=?",(rid,))
    await w.work(rid,'implement')

@pytest.mark.asyncio
async def test_eight_roles_artifacts_references_and_actual_gate(tmp_path):
    s,w,pid,rid=setup(tmp_path)
    await approve(w,rid)
    assert s.run(rid)['status']=='succeeded',s.run(rid)
    steps=s.query('SELECT * FROM agent_steps ORDER BY rowid')
    assert {step['role'] for step in steps}=={'制作人','PM','策划','主程','美术','UX','程序','QA'}
    completed=set()
    for step in steps:
        assert step['status']=='succeeded' and json.loads(step['usage'])['total_tokens']==12
        assert set(json.loads(step['inputs']))<=completed
        completed.add(step['id'])
    assert w.runner.calls==1
    version=s.one('SELECT * FROM versions');evidence=json.loads(version['evidence'])
    assert evidence['passed'] and evidence['team']['qa_step'] in completed
    assert '趣味性' in evidence['team']['manual_checks'][0]
    s.con.close()

@pytest.mark.asyncio
async def test_edited_approved_plan_reaches_pm_and_designers(tmp_path):
    s,w,_,rid=setup(tmp_path)
    await w.work(rid,'plan')
    plan=json.loads(s.run(rid)['plan']);plan['controls']='用户编辑后的 A D 操作'
    s.execute("UPDATE runs SET status='queued',plan=? WHERE id=?",(json.dumps(plan),rid))
    await w.work(rid,'implement')
    assert s.run(rid)['status']=='succeeded'
    for role,schema,prompt in w.gateway.trace[3:]:
        assert '用户编辑后的 A D 操作' in prompt
    s.con.close()

@pytest.mark.asyncio
async def test_design_parallel_and_failure_cancels_siblings(tmp_path):
    reached=set();gate=asyncio.Event();cancelled=[]
    class G(TeamGateway):
        async def call(self,role,prompt,schema):
            if schema is Design:
                reached.add(role)
                if len(reached)==3:gate.set()
                await gate.wait()
                if role=='美术':raise ModelError('视觉协议失败')
                try:await asyncio.Event().wait()
                finally:cancelled.append(role)
            return await super().call(role,prompt,schema)
    s,w,_,rid=setup(tmp_path,G())
    await asyncio.wait_for(approve(w,rid),2)
    assert reached=={'主程','美术','UX'} and set(cancelled)=={'主程','UX'}
    assert s.run(rid)['status']=='failed' and w.runner.calls==0
    assert not s.query("SELECT * FROM agent_steps WHERE status='running'")
    assert not s.query("SELECT * FROM agent_steps WHERE role='程序'")
    s.con.close()

@pytest.mark.asyncio
async def test_pm_dependencies_restrict_actual_dispatch(tmp_path):
    ready=False
    class G(TeamGateway):
        async def call(self,role,prompt,schema):
            nonlocal ready
            result,meta=await super().call(role,prompt,schema)
            if schema is TaskBoard:
                for t in result.tasks:
                    if t.key=='art':t.depends_on=['tech']
            if schema is Design and role=='主程':
                await asyncio.sleep(.01);ready=True
            if schema is Design and role=='美术':assert ready
            return result,meta
    s,w,_,rid=setup(tmp_path,G());await approve(w,rid)
    assert s.run(rid)['status']=='succeeded'
    art=s.one("SELECT inputs FROM agent_steps WHERE task_key='art'")
    tech=s.one("SELECT id FROM agent_steps WHERE task_key='tech'")
    assert tech['id'] in json.loads(art['inputs'])
    s.con.close()

@pytest.mark.asyncio
@pytest.mark.parametrize('dependent',[False,True])
async def test_review_routes_visual_issue_and_programmer_consumes_revision(tmp_path,dependent):
    class G(TeamGateway):
        reviews=0
        async def call(self,role,prompt,schema):
            result,meta=await super().call(role,prompt,schema)
            if schema is TaskBoard and dependent:
                next(t for t in result.tasks if t.key=='ux').depends_on=['art']
            if schema is Review:
                self.reviews+=1
                if self.reviews==1:result.issues=[Issue(owner='美术',severity='blocking',description='颜色反馈需要修订',evidence='config.ts 背景对比要求未满足')]
            return result,meta
    s,w,_,rid=setup(tmp_path,G());await approve(w,rid)
    assert s.run(rid)['status']=='succeeded' and s.run(rid)['repairs']==1
    assert len(s.query("SELECT * FROM agent_steps WHERE task_key='art'"))==2
    assert len(s.query("SELECT * FROM agent_steps WHERE task_key='ux'"))==(2 if dependent else 1)
    codes=s.query("SELECT * FROM agent_steps WHERE task_key='code' ORDER BY rowid")
    art=s.query("SELECT id FROM agent_steps WHERE task_key='art' ORDER BY rowid")[-1]
    assert art['id'] in json.loads(codes[-1]['inputs'])
    assert any('颜色反馈需要修订' in prompt for role,_,prompt in w.gateway.trace if role=='程序')
    s.con.close()

@pytest.mark.asyncio
@pytest.mark.parametrize('failure',['tool','review','qa','delivery','format'])
async def test_no_model_judgment_bypasses_gates(tmp_path,failure):
    class G(TeamGateway):
        async def call(self,role,prompt,schema):
            result,meta=await super().call(role,prompt,schema)
            if (schema is Review and failure=='review') or (schema is QAReport and failure=='qa'):
                result.issues=[Issue(owner='程序',severity='blocking',description='必须处理',evidence='测试依据')]
            if schema is Delivery and failure=='delivery':result.ready=False
            if schema is QAReport and failure=='format':result=Design(summary='错误协议',decisions=['不应发布'],acceptance=['失败'])
            return result,meta
    s,w,_,rid=setup(tmp_path,G(),FakeRunner(passed=failure!='tool'));await approve(w,rid)
    assert s.run(rid)['status']=='failed' and not s.query('SELECT * FROM versions')
    assert w.runner.calls==(1 if failure in ('delivery','format') else 3)
    assert s.one('SELECT active_version FROM projects')['active_version'] is None
    s.con.close()

@pytest.mark.asyncio
async def test_cancel_parallel_steps_and_recover_approval(tmp_path):
    started=asyncio.Event()
    class G(TeamGateway):
        async def call(self,role,prompt,schema):
            if schema is Design:started.set();await asyncio.Event().wait()
            return await super().call(role,prompt,schema)
    s,w,_,rid=setup(tmp_path,G());await w.work(rid,'plan');s.recover()
    assert s.run(rid)['status']=='waiting_confirmation'
    s.execute("UPDATE runs SET status='queued' WHERE id=?",(rid,));w.launch(rid,'implement')
    await asyncio.wait_for(started.wait(),2);await w.cancel(rid)
    assert s.run(rid)['status']=='cancelled' and not s.query("SELECT * FROM agent_steps WHERE status='running'")
    assert not s.query('SELECT * FROM versions');s.con.close()

@pytest.mark.parametrize('kind',['cycle','missing','duplicate'])
def test_invalid_task_dependency_rejected(kind):
    data=json.loads(json.dumps(BOARD))
    if kind=='cycle':data['tasks'][0]['depends_on']=['code']
    if kind=='missing':data['tasks'][3]['depends_on']=[]
    if kind=='duplicate':data['tasks'][0]['key']='art'
    with pytest.raises(ValueError):TaskBoard.model_validate(data)


def test_api_default_team_rejection_and_export(tmp_path):
    import time
    g=TeamGateway();app=create_app(tmp_path,g,FakeRunner())
    with TestClient(app) as c:
        result=c.post('/api/projects',json={'text':'接金币躲炸弹'}).json();rid=result['run_id'];pid=result['project_id']
        for _ in range(200):
            if app.state.store.run(rid)['status']=='waiting_confirmation':break
            time.sleep(.01)
        p=c.get('/api/projects/'+pid).json();assert p['runs'][0]['engine']=='team8'
        assert len(c.get('/api/runs/'+rid+'/team').json()['steps'])==3
        assert c.post('/api/runs/'+rid+'/decision',json={'approve':False}).status_code==200
        assert len(c.get('/api/runs/'+rid+'/team').json()['steps'])==3
        assert c.get('/api/runs/missing/team').status_code==404
        assert c.get('/api/runs/'+rid+'/team',headers={'Origin':'https://bad.example'}).status_code==403
    # A fully published run exports role artifacts alongside tool evidence.
    s,w,_,rid=setup(tmp_path/'export');asyncio.run(approve(w,rid));v=s.one('SELECT * FROM versions');s.con.close()
    with TestClient(create_app(tmp_path/'export',TeamGateway(),FakeRunner())) as c:
        with zipfile.ZipFile(io.BytesIO(c.get('/api/versions/'+v['id']+'/export').content)) as z:
            assert len(json.loads(z.read('collaboration.json')))==13
            assert json.loads(z.read('verification.json'))['passed']

@pytest.mark.asyncio
async def test_role_models_override_without_exposing_credentials(tmp_path,monkeypatch):
    import httpx
    g=Gateway(tmp_path);g.save(ModelSettings(model='default',api_key='private-test-secret'))
    identity=g.configuration_id();g.save_team_models(TeamModels(models={'主程':'review-model'}))
    assert g.configuration_id()!=identity
    sent=[];real=httpx.AsyncClient
    def respond(r):
        sent.append(json.loads(r.content))
        return httpx.Response(200,json={'choices':[{'message':{'content':Review(summary='测试响应',issues=[]).model_dump_json()}}]})
    monkeypatch.setattr(httpx,'AsyncClient',lambda **kw:real(transport=httpx.MockTransport(respond),**kw))
    await g.call('主程','测试',Review);await g.call('QA','测试',Review)
    assert [r['model'] for r in sent]==['review-model','default']
    with TestClient(create_app(tmp_path,g,FakeRunner())) as c:
        result=c.get('/api/settings/team');assert 'private-test-secret' not in result.text
        assert c.put('/api/settings/team',json={'models':{'unknown':'model'}}).status_code==422
        assert c.put('/api/settings/team',json={'models':{'主程':''}}).status_code==200

@pytest.mark.asyncio
async def test_iteration_carries_previous_plan_and_role_designs(tmp_path):
    from studio.db import uid,now
    from studio.team import Team
    s,w,pid,rid=setup(tmp_path);await approve(w,rid)
    v=s.one('SELECT * FROM versions');second=uid()
    s.execute('INSERT INTO runs(id,project_id,status,requirement,base_version,created_at) VALUES(?,?,?,?,?,?)',
        (second,pid,'queued','调整速度，保留原设计',v['id'],now()))
    s.execute('INSERT INTO run_options VALUES(?,?,?)',(second,'team8','{}'))
    context=Team(w).context(s.run(second))
    assert context['previous_plan']==json.loads(s.run(rid)['plan'])
    assert {x['role'] for x in context['previous_designs']}=={'主程','美术','UX'}
    await w.work(second,'plan')
    assert s.run(second)['status']=='waiting_confirmation'
    assert all('previous_designs' in prompt and '主程设计交付' in prompt for _,_,prompt in w.gateway.trace[-3:])
    s.con.close()
