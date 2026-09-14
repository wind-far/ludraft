import asyncio
import io
import json
import zipfile
from pathlib import Path
import pytest
from fastapi.testclient import TestClient
from studio.app import create_app
from studio.files import source_files
from studio.models import Plan
from studio.team_models import Brief,ConfigProposal,QAReport,Delivery,Issue
from studio.routing import options
from studio.lineage import resolve
from test_team import setup,approve
from test_routing import modification
from test_workbench import ParameterRunner
from test_messages import wait_run
from config_fixture import ConfigGateway

async def existing(tmp_path,g=None):
    s,w,pid,first=setup(tmp_path,g or ConfigGateway(),ParameterRunner())
    await approve(w,first)
    assert s.run(first)['status']=='succeeded'
    return s,w,pid,s.one('SELECT * FROM versions')


@pytest.mark.asyncio
async def test_config_proposal_approval_scoped_code_evidence_lineage_and_export(tmp_path):
    s,w,pid,base=await existing(tmp_path)
    before=source_files(Path(base['path']));rid=modification(s,pid,base['id'],'config')
    await w.work(rid,'plan')
    assert s.run(rid)['status']=='waiting_confirmation'
    assert [x['task_key'] for x in s.query('SELECT task_key FROM agent_steps WHERE run_id=?',(rid,))]==['brief','config_plan']
    assert w.runner.calls==1 and s.one('SELECT active_version FROM projects')['active_version']==base['id']
    proposal=options(s,rid);assert proposal['config_proposal']['parameters']['moves']==30
    s.execute("UPDATE runs SET status='queued' WHERE id=?",(rid,));await w.work(rid,'implement')
    assert s.run(rid)['status']=='succeeded',s.run(rid)
    version=s.one('SELECT * FROM versions WHERE run_id=?',(rid,));e=json.loads(version['evidence'])
    assert e['parameter_match'] and e['unchanged_sources'] and e['config']['moves']==30 and e['config']['targetScore']==1500
    after=source_files(Path(version['path']));assert [k for k,v in before.items() if after[k]!=v]==['src/config.ts']
    assert source_files(Path(base['path']))==before
    steps=s.query('SELECT * FROM agent_steps WHERE run_id=?',(rid,));assert len(steps)==6
    assert {x['role'] for x in steps}=={'制作人','PM','程序','QA'}
    lineage=resolve(s,version['id']);assert len(lineage['designs'])==3
    assert all(x['source_run']!=rid for x in lineage['designs'])
    ids={x['id'] for x in lineage['steps']};assert all(set(x['inputs'])<=ids for x in lineage['steps'])
    s.con.close()
    with TestClient(create_app(tmp_path,ConfigGateway(),ParameterRunner())) as c:
        with zipfile.ZipFile(io.BytesIO(c.get('/api/versions/'+version['id']+'/export').content)) as z:
            assert json.loads(z.read('verification.json'))['parameter_match']
            assert {x['task_key'] for x in json.loads(z.read('collaboration.json'))}>={'config_plan','tech','art','ux'}
            assert 'config_plan' in z.read('rules.json').decode()


@pytest.mark.asyncio
@pytest.mark.parametrize('fault',['wrong_file','wrong_value','wrong_title','dynamic'])
async def test_program_cannot_change_unapproved_files_or_values(tmp_path,fault):
    g=ConfigGateway();s,w,pid,base=await existing(tmp_path,g)
    before=source_files(Path(base['path']));g.fault=fault
    rid=modification(s,pid,base['id'],'config');await approve(w,rid)
    assert s.run(rid)['status']=='failed'
    assert w.runner.calls==1
    assert s.one('SELECT active_version FROM projects')['active_version']==base['id']
    assert source_files(s.root/'candidates'/rid)==before
    assert not s.one('SELECT id FROM versions WHERE run_id=?',(rid,))
    s.con.close()


@pytest.mark.asyncio
@pytest.mark.parametrize('failure',['tools','qa','delivery','edited'])
async def test_config_gates_preserve_previous_version(tmp_path,failure):
    class G(ConfigGateway):
        enabled=False
        async def call(self,role,prompt,schema):
            result,meta=await super().call(role,prompt,schema)
            if self.enabled and failure=='qa' and schema is QAReport:
                result.issues=[Issue(owner='程序',severity='blocking',description='参数反馈有问题',evidence='固定测试阻断')]
            if self.enabled and failure=='delivery' and schema is Delivery:result.ready=False
            return result,meta
    g=G();s,w,pid,base=await existing(tmp_path,g);g.enabled=True
    rid=modification(s,pid,base['id'],'config')
    await w.work(rid,'plan')
    if failure=='tools':w.runner.passed=False
    if failure=='edited':
        p=json.loads(s.run(rid)['plan']);p['summary']='已被篡改的确认方案';s.execute('UPDATE runs SET plan=? WHERE id=?',(json.dumps(p),rid))
    s.execute("UPDATE runs SET status='queued' WHERE id=?",(rid,));await w.work(rid,'implement')
    assert s.run(rid)['status']=='failed'
    assert s.one('SELECT active_version FROM projects')['active_version']==base['id']
    assert w.runner.calls==({'tools':4,'qa':4,'delivery':2,'edited':1}[failure])
    if failure in ('tools','qa'):assert s.run(rid)['repairs']==2
    s.con.close()


@pytest.mark.asyncio
async def test_auto_config_no_base_expands_to_creation_and_noop_fails(tmp_path):
    class G(ConfigGateway):
        async def call(self,role,prompt,schema):
            result,meta=await super().call(role,prompt,schema)
            if schema is Brief:result.task_type='config'
            return result,meta
    g=G();s,w,pid,base=await existing(tmp_path,g)
    assert options(s,base['run_id'])['route']['task_type']=='feature'
    g.moves=20;g.target=1200
    rid=modification(s,pid,base['id'],'config');await w.work(rid,'plan')
    assert s.run(rid)['status']=='failed' and '没有参数变化' in s.run(rid)['error']
    s.con.close()


def test_config_api_stale_approval_replan_cancel_restart_and_plan_edit(tmp_path):
    g=ConfigGateway();s,w,pid,base=asyncio.run(existing(tmp_path,g));s.con.close()
    with TestClient(create_app(tmp_path,g,ParameterRunner())) as c:
        count=len(c.get('/api/projects').json())
        assert c.post('/api/projects',json={'text':'新项目配置','task_type':'config'}).status_code==400
        assert len(c.get('/api/projects').json())==count
        rid=c.post('/api/projects/'+pid+'/runs',json={'text':'把步数调整为30','task_type':'config'}).json()['run_id']
        run=wait_run(c,pid,lambda r:r['status']=='waiting_confirmation');assert run['id']==rid
        config=options(c.app.state.store,rid);old_revision=config['config_revision']
        assert c.post('/api/runs/'+rid+'/decision',json={'approve':True}).status_code==409
        assert c.put('/api/runs/'+rid+'/plan',json={'plan':json.loads(run['plan']),'expected_plan':run['plan']}).status_code==409
        # Same summary/plan but a new parameter proposal still invalidates the old approval.
        g.moves=35
        assert c.post('/api/runs/'+rid+'/messages',json={'content':'改为35步'}).status_code==201
        run=wait_run(c,pid,lambda r:r['status']=='waiting_confirmation' and bool(r['plan']))
        new_revision=options(c.app.state.store,rid)['config_revision'];assert new_revision!=old_revision
        assert c.post('/api/runs/'+rid+'/decision',json={'approve':True,'expected_revision':run['approval_revision'],'expected_config_revision':old_revision}).status_code==409
    with TestClient(create_app(tmp_path,g,ParameterRunner())) as c:
        run=c.get('/api/projects/'+pid).json()['runs'][0]
        assert run['status']=='waiting_confirmation'
        assert c.post('/api/runs/'+rid+'/decision',json={'approve':True,'expected_revision':run['approval_revision'],'expected_config_revision':new_revision,'expected_plan':run['plan']}).status_code==200
        done=wait_run(c,pid,lambda r:r['status'] in ('succeeded','failed'));assert done['status']=='succeeded',done
        p=c.get('/api/projects/'+pid).json()
        assert c.get('/api/versions/'+p['active_version']).json()['parameters']['moves']==35
        g.moves=40
        next_id=c.post('/api/projects/'+pid+'/runs',json={'text':'再改40步','task_type':'config'}).json()['run_id']
        wait_run(c,pid,lambda r:r['status']=='waiting_confirmation')
        assert c.post('/api/runs/'+next_id+'/decision',json={'approve':False}).status_code==200
        assert c.get('/api/projects/'+pid).json()['active_version']==p['active_version']

@pytest.mark.asyncio
async def test_configuration_cancel_during_program_never_publishes(tmp_path):
    from studio.models import Changes
    reached=asyncio.Event();joined=asyncio.Event()
    class G(ConfigGateway):
        hold=False
        async def call(self,role,prompt,schema):
            if self.hold and schema is Changes:
                reached.set()
                try:await asyncio.Event().wait()
                finally:joined.set()
            return await super().call(role,prompt,schema)
    g=G();s,w,pid,base=await existing(tmp_path,g);g.hold=True
    rid=modification(s,pid,base['id'],'config');await w.work(rid,'plan')
    s.execute("UPDATE runs SET status='queued' WHERE id=?",(rid,));w.launch(rid,'implement')
    await asyncio.wait_for(reached.wait(),3);await w.cancel(rid)
    assert joined.is_set() and s.run(rid)['status']=='cancelled'
    assert s.one('SELECT active_version FROM projects')['active_version']==base['id']
    assert not s.one("SELECT id FROM agent_steps WHERE status='running'")
    assert w.runner.calls==1
    s.con.close()


@pytest.mark.asyncio
async def test_configuration_legacy_game_keeps_mode_and_updates_speed(tmp_path):
    from studio.db import Store
    from studio.workflow import Workflow
    from test_workbench import seed
    s=Store(tmp_path);pid,_,vid,_=seed(s)
    w=Workflow(s,ConfigGateway(),ParameterRunner());rid=modification(s,pid,vid,'config')
    await approve(w,rid);assert s.run(rid)['status']=='succeeded',s.run(rid)
    v=s.one('SELECT * FROM versions WHERE run_id=?',(rid,));e=json.loads(v['evidence'])
    assert e['config']['mode']=='collector' and e['config']['speed']==180 and e['parameter_match']
    s.con.close()
