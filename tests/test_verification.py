"""Delivery gates reject incomplete success claims across every publishing path."""
import json
from pathlib import Path
import pytest
from studio.db import now,uid
from studio.files import copy_source,source_files,TEMPLATE
from studio.runner import RunnerError
from studio.verification import checked,evidence_errors
from studio.workflow import Workflow
from studio.models import Parameters
from studio.parameters import read_config
from studio.routing import save
from scripts.evaluate import CASES
from test_game_modes import ModeGateway
from test_team import setup,approve
from test_workbench import ParameterRunner
from test_studio import FakeGateway,PLAN

class IncompleteRunner(ParameterRunner):
    def __init__(self,fault):super().__init__();self.fault=fault
    async def run(self,path,rid):
        evidence=await super().run(path,rid)
        if self.fault=='missing':evidence['checks']=evidence['checks'][:1]
        if self.fault=='contradictory':evidence['checks'].append({'name':'交互故障','passed':False})
        if self.fault=='build':evidence['build']=False
        if self.fault=='exit':evidence['exit_code']=2
        if self.fault=='no_exit':evidence.pop('exit_code')
        if self.fault=='malformed':return None
        if self.fault=='exception':raise RunnerError('验证进程中断')
        return evidence

@pytest.mark.asyncio
@pytest.mark.parametrize('case',CASES[:4],ids=lambda c:c['mode'])
@pytest.mark.parametrize('fault',['missing','contradictory','build','exit','no_exit','malformed','exception'])
async def test_eight_role_generation_requires_complete_actual_checks(tmp_path,case,fault):
    s,w,pid,rid=setup(tmp_path,ModeGateway(case),IncompleteRunner(fault))
    await approve(w,rid)
    run=s.run(rid)
    assert run['status']=='failed' and run['repairs']==2
    assert w.runner.calls==3 and not s.query('SELECT * FROM versions')
    events=s.query("SELECT payload FROM events WHERE run_id=? AND kind='test_result'",(rid,))
    assert len(events)==3
    assert all(not json.loads(e['payload'])['passed'] and json.loads(e['payload'])['gate_errors'] for e in events)
    assert len(s.query("SELECT id FROM agent_steps WHERE run_id=? AND task_key='qa_report'",(rid,)))==3
    assert not s.query("SELECT id FROM agent_steps WHERE run_id=? AND task_key='delivery'",(rid,))
    s.con.close()

@pytest.mark.asyncio
async def test_final_publish_gate_cannot_be_bypassed(tmp_path):
    s,w,pid,rid=setup(tmp_path)
    s.execute("UPDATE runs SET plan=?,status='testing' WHERE id=?",(PLAN.model_dump_json(),rid))
    workspace=tmp_path/'candidate';copy_source(TEMPLATE,workspace)
    fake={'passed':True,'build':True,'config':{'mode':'collector'},'checks':[],'exit_code':0}
    with pytest.raises(ValueError,match='发布门禁'):w.publish(s.run(rid),workspace,source_files(workspace),fake)
    assert s.one("SELECT id FROM events WHERE kind='publish_rejected'")
    assert not s.query('SELECT * FROM versions') and s.one('SELECT active_version FROM projects')['active_version'] is None
    s.con.close()

@pytest.mark.asyncio
async def test_parameter_editor_preserves_version_when_checks_are_missing(tmp_path):
    s,w,pid,rid=setup(tmp_path,ModeGateway(CASES[1]),ParameterRunner());await approve(w,rid)
    base=s.one('SELECT * FROM versions');before=source_files(Path(base['path']))
    values=read_config(before['src/config.ts']);params={k:values[k] for k in Parameters.model_fields};params['lives']=5
    new=uid();s.execute('INSERT INTO runs(id,project_id,status,requirement,base_version,plan,created_at) VALUES(?,?,?,?,?,?,?)',(new,pid,'queued','生命增加至五条',base['id'],s.run(rid)['plan'],now()))
    s.execute('INSERT INTO run_options VALUES(?,?,?)',(new,'parameters',json.dumps(params)))
    w.runner=IncompleteRunner('missing');await w.work(new,'parameters')
    assert s.run(new)['status']=='failed' and w.runner.calls==1
    assert s.one('SELECT active_version FROM projects')['active_version']==base['id']
    assert source_files(Path(base['path']))==before
    s.con.close()

@pytest.mark.asyncio
async def test_config_route_preserves_version_when_checks_are_missing(tmp_path):
    from test_config_flow import existing
    from config_fixture import ConfigGateway
    from test_routing import modification
    s,w,pid,base=await existing(tmp_path,ConfigGateway())
    rid=modification(s,pid,base['id'],'config');w.runner=IncompleteRunner('missing');await approve(w,rid)
    assert s.run(rid)['status']=='failed' and w.runner.calls==3
    assert s.one('SELECT active_version FROM projects')['active_version']==base['id']
    assert not s.one('SELECT * FROM versions WHERE run_id=?',(rid,))
    s.con.close()

@pytest.mark.asyncio
async def test_legacy_generation_uses_the_same_gate(tmp_path):
    s,w,pid,rid=setup(tmp_path,FakeGateway(),IncompleteRunner('missing'))
    s.execute('DELETE FROM run_options WHERE run_id=?',(rid,));await approve(w,rid)
    assert s.run(rid)['status']=='failed' and w.runner.calls==3
    assert not s.query('SELECT * FROM versions')
    s.con.close()

@pytest.mark.parametrize('evidence',[None,[],{'passed':True,'build':True,'checks':[{'name':[],'passed':True}],'config':[]}, {'exit_code':False}])
def test_malformed_evidence_fails_closed(evidence):
    assert not checked(evidence,'match3')['passed']
    assert evidence_errors(evidence,'match3')

@pytest.mark.parametrize('mode,runtime,extra',[
    ('collector','canvas-input-v2',['移动端布局','触屏拖动与停止','倒计时与重开']),
    ('clicker','canvas-input-v2',['移动端布局','触屏点击得分','倒计时与重开']),
    ('match3','match3-v1',['移动端布局','触屏交换消除']),
])
def test_mobile_runtime_requires_mobile_evidence(mode,runtime,extra):
    from studio.verification import required_checks
    evidence={'passed':True,'build':True,'config':{'mode':mode},'exit_code':0,'runtime':runtime,
        'checks':[{'name':n,'passed':True} for n in required_checks(mode)]}
    assert not checked(evidence,mode)['passed']
    evidence['checks'] += [{'name':n,'passed':True} for n in extra]
    assert checked(evidence,mode)['passed']
