"""Routing saves only unaffected design calls; all delivery gates stay mandatory."""
import asyncio
import io
import json
import zipfile
import pytest
from fastapi.testclient import TestClient
from studio.app import create_app
from studio.db import uid,now
from studio.lineage import resolve
from studio.team import Team
from studio.team_models import Brief,Design,TaskBoard,Review,Issue
from studio.routing import options
from test_team import setup,approve
from team_fixture import TeamGateway
from test_workbench import ParameterRunner


def modification(store,pid,base,kind='auto'):
    rid=uid()
    store.execute('INSERT INTO runs(id,project_id,status,requirement,base_version,created_at) VALUES(?,?,?,?,?,?)',
        (rid,pid,'queued','保留玩法并修改指定问题',base,now()))
    store.execute('INSERT INTO run_options VALUES(?,?,?)',(rid,'team8',json.dumps({'requested_type':kind})))
    return rid


@pytest.mark.asyncio
@pytest.mark.parametrize('kind,updated,count',[('feature',{'tech','art','ux'},13),('bugfix',{'tech'},11),('visual',{'art','ux'},12),('optimize',{'tech'},11)])
async def test_profiles_reuse_designs_keep_gates_and_account_only_new_calls(tmp_path,kind,updated,count):
    s,w,pid,first=setup(tmp_path,runner=ParameterRunner());await approve(w,first)
    base=s.one('SELECT * FROM versions');rid=modification(s,pid,base['id'],kind)
    await approve(w,rid)
    assert s.run(rid)['status']=='succeeded',s.run(rid)
    route=options(s,rid)['route'];assert route['task_type']==kind and set(route['update'])==updated
    steps=s.query('SELECT * FROM agent_steps WHERE run_id=?',(rid,));assert len(steps)==count
    assert {x['task_key'] for x in steps if x['task_key'] in ('tech','art','ux')}==updated
    assert {'review','test_strategy','qa_report','delivery'}<={x['task_key'] for x in steps}
    events=s.query("SELECT payload FROM events WHERE run_id=? AND kind='model_result'",(rid,))
    assert sum(json.loads(e['payload'])['usage']['total_tokens'] for e in events)==count*12
    old={x['task_key']:x['id'] for x in s.query('SELECT * FROM agent_steps WHERE run_id=?',(first,))}
    code=next(x for x in steps if x['task_key']=='code')
    assert {old[k] for k in route['reuse']}<=set(json.loads(code['inputs']))
    version=s.one('SELECT id FROM versions WHERE run_id=?',(rid,));lineage=resolve(s,version['id'])
    assert len(lineage['designs'])==3 and lineage['plan']==json.loads(s.run(rid)['plan'])
    byid={x['id']:x for x in lineage['steps']}
    assert all(set(x['inputs'] or [])<=byid.keys() for x in lineage['steps'])
    assert w.runner.calls==2
    s.con.close()


@pytest.mark.asyncio
async def test_auto_routing_uses_producer_and_reject_stops_downstream(tmp_path):
    class G(TeamGateway):
        async def call(self,role,prompt,schema):
            result,meta=await super().call(role,prompt,schema)
            if schema is Brief:result.task_type='visual';result.routing_reason='仅调整配色与反馈'
            return result,meta
    s,w,pid,first=setup(tmp_path,G());await approve(w,first)
    rid=modification(s,pid,s.one('SELECT id FROM versions')['id'])
    await w.work(rid,'plan');assert options(s,rid)['route']['task_type']=='visual'
    await w.cancel(rid)
    assert len(s.query('SELECT * FROM agent_steps WHERE run_id=?',(rid,)))==3
    assert s.run(rid)['status']=='cancelled' and w.runner.calls==1
    s.con.close()


@pytest.mark.asyncio
@pytest.mark.parametrize('reason',['new','missing','edited','pm','dependency'])
async def test_conservative_expansion(tmp_path,reason):
    class G(TeamGateway):
        expand=False
        async def call(self,role,prompt,schema):
            result,meta=await super().call(role,prompt,schema)
            if self.expand and schema is TaskBoard:
                if reason=='pm':result.design_updates=['art','ux']
                if reason=='dependency':
                    next(t for t in result.tasks if t.key=='art').depends_on=['tech']
                    next(t for t in result.tasks if t.key=='ux').depends_on=['art']
            return result,meta
    g=G();s,w,pid,first=setup(tmp_path,g)
    if reason=='new':
        s.execute('UPDATE run_options SET payload=? WHERE run_id=?',(json.dumps({'requested_type':'bugfix'}),first));rid=first
    else:
        await approve(w,first);base=s.one('SELECT id FROM versions')['id']
        if reason=='missing':s.execute("DELETE FROM agent_steps WHERE task_key IN ('art','ux')")
        rid=modification(s,pid,base,'bugfix')
    g.expand=True
    await w.work(rid,'plan')
    if reason=='edited':
        plan=json.loads(s.run(rid)['plan']);plan['controls']='改为键盘 A D 移动'
        s.execute('UPDATE runs SET plan=? WHERE id=?',(json.dumps(plan),rid))
    s.execute("UPDATE runs SET status='queued' WHERE id=?",(rid,));await w.work(rid,'implement')
    assert s.run(rid)['status']=='succeeded',s.run(rid)
    assert options(s,rid)['route']['reuse']==[]
    assert len(s.query('SELECT * FROM agent_steps WHERE run_id=?',(rid,)))==13
    s.con.close()


@pytest.mark.asyncio
async def test_reused_design_can_be_revised_and_export_keeps_old_input_closure(tmp_path):
    class G(TeamGateway):
        fix=False
        reviews=0
        async def call(self,role,prompt,schema):
            result,meta=await super().call(role,prompt,schema)
            if self.fix and schema is Review:
                self.reviews+=1
                if self.reviews==1:result.issues=[Issue(owner='主程',severity='blocking',description='需更新沿用技术方案',evidence='新实现影响渲染路径')]
            return result,meta
    g=G();s,w,pid,first=setup(tmp_path,g);await approve(w,first)
    base=s.one('SELECT id FROM versions')['id'];rid=modification(s,pid,base,'visual');g.fix=True
    await approve(w,rid);assert s.run(rid)['status']=='succeeded' and s.run(rid)['repairs']==1
    v=s.one('SELECT id FROM versions WHERE run_id=?',(rid,))['id']
    lineage=resolve(s,v);ids={x['id'] for x in lineage['steps']}
    assert all(set(x['inputs'] or [])<=ids for x in lineage['steps'])
    assert {x['source_run'] for x in lineage['designs']}=={rid}
    assert options(s,rid)['route']['reuse']==[]
    s.con.close()
    with TestClient(create_app(tmp_path,TeamGateway(),ParameterRunner())) as c:
        with zipfile.ZipFile(io.BytesIO(c.get('/api/versions/'+v+'/export').content)) as z:
            steps=json.loads(z.read('collaboration.json'));ids={x['id'] for x in steps}
            assert all(set(x['inputs'] or [])<=ids for x in steps)
            assert base in {x['version_id'] for x in json.loads(z.read('provenance.json'))['chain']}


@pytest.mark.asyncio
async def test_profile_tool_failure_preserves_previous_version(tmp_path):
    s,w,pid,first=setup(tmp_path);await approve(w,first);base=s.one('SELECT id FROM versions')['id']
    rid=modification(s,pid,base,'bugfix');w.runner.passed=False
    await approve(w,rid)
    assert s.run(rid)['status']=='failed'
    assert s.one('SELECT active_version FROM projects')['active_version']==base
    assert s.run(rid)['repairs']==2
    s.con.close()


def test_api_explicit_type_validation_and_route_visibility(tmp_path):
    import time
    app=create_app(tmp_path,TeamGateway(),ParameterRunner())
    with TestClient(app) as c:
        assert c.post('/api/projects',json={'text':'测试需求','task_type':'arbitrary'}).status_code==422
        response=c.post('/api/projects',json={'text':'制作新的游戏','task_type':'visual'})
        assert response.status_code==201
        rid=response.json()['run_id']
        for _ in range(200):
            if app.state.store.run(rid)['status']=='waiting_confirmation':break
            time.sleep(.01)
        team=c.get('/api/runs/'+rid+'/team').json()
        assert team['route']['task_type']=='visual' and team['route']['reuse']==[]
        assert c.post('/api/runs/'+rid+'/decision',json={'approve':False}).status_code==200
