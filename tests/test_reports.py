import asyncio
import hashlib
import io
import json
import zipfile
from pathlib import Path
import pytest
from fastapi.testclient import TestClient
from studio.app import create_app
from studio.models import Changes
from studio.team_models import QAReport,Delivery,Issue,TestScope as Scope
from studio.routing import options
from studio.reports import encoded
from studio.test_flow import manifest,evidence_errors
from studio.llm import ModelError
from studio.runner import RunnerError
from test_team import setup,approve
from test_routing import modification
from test_messages import wait_run
from testing_fixture import ReportGateway,EvidenceRunner

async def existing(root,g=None,r=None):
    s,w,pid,rid=setup(root,g or ReportGateway(),r or EvidenceRunner());await approve(w,rid)
    assert s.run(rid)['status']=='succeeded',s.run(rid)
    return s,w,pid,s.one('SELECT * FROM versions')


@pytest.mark.asyncio
async def test_independent_report_never_publishes_and_preserves_sources_export(tmp_path):
    s,w,pid,base=await existing(tmp_path);before=manifest(Path(base['path']))
    rid=modification(s,pid,base['id'],'test');await w.work(rid,'plan')
    assert s.run(rid)['status']=='waiting_confirmation' and w.runner.calls==1
    assert not s.one('SELECT * FROM run_reports')
    assert [r['task_key'] for r in s.query('SELECT task_key FROM agent_steps WHERE run_id=?',(rid,))]==['brief','test_scope']
    s.execute("UPDATE runs SET status='queued' WHERE id=?",(rid,));await w.work(rid,'implement')
    assert s.run(rid)['status']=='succeeded',s.run(rid)
    assert len(s.query('SELECT * FROM versions'))==1
    assert s.one('SELECT active_version FROM projects')['active_version']==base['id']
    assert manifest(Path(base['path']))==before
    assert not s.one("SELECT id FROM events WHERE run_id=? AND kind IN ('published','files_changed')",(rid,))
    result=json.loads(s.one('SELECT payload FROM run_reports')['payload']);sha=result.pop('sha256')
    assert sha==hashlib.sha256(encoded(result).encode()).hexdigest()
    assert result['passed'] and result['input_hashes']==before and result['tool_evidence']['input_unchanged']
    steps=result['steps'];assert len(steps)==5 and {s['role'] for s in steps}=={'制作人','PM','QA','策划'}
    assert not any(s['task_key']=='code' for s in steps)
    s.con.close()
    with TestClient(create_app(tmp_path,ReportGateway(),EvidenceRunner())) as c:
        first=c.get('/api/runs/'+rid+'/report');assert first.status_code==200
        assert c.post('/api/runs/'+rid+'/messages',json={'content':'修改历史报告'}).status_code==409
        assert c.get('/api/runs/'+rid+'/report').json()==first.json()
        with zipfile.ZipFile(io.BytesIO(c.get('/api/runs/'+rid+'/report/export').content)) as z:
            assert {'report.json','test-report.md','collaboration.json','rules.json','licenses/upstream-MIT.txt','provenance.json'}<=set(z.namelist())
            assert json.loads(z.read('report.json'))==first.json()
            assert base['id'] in z.read('test-report.md').decode()
            all_steps=json.loads(z.read('collaboration.json'));ids={x['id'] for x in all_steps}
            assert all(set(x['inputs'])<=ids for x in all_steps)
        assert c.get('/api/runs/'+rid+'/report',headers={'Origin':'null'}).status_code==403
        assert c.get('/api/runs/unknown/report').status_code==404


@pytest.mark.asyncio
@pytest.mark.parametrize('failure',['tools','missing','build','mode','input','exception','qa','delivery','qa_model'])
async def test_failed_test_or_analysis_keeps_report_and_previous_version(tmp_path,failure):
    class G(ReportGateway):
        enabled=False
        async def call(self,role,prompt,schema):
            if self.enabled and failure=='qa_model' and schema is QAReport:raise ModelError('QA 测试协议失败')
            result,meta=await super().call(role,prompt,schema)
            if self.enabled and failure=='qa' and schema is QAReport:
                result.issues=[Issue(owner='程序',severity='blocking',description='存在阻断问题',evidence='测试证据指出问题')]
            if self.enabled and failure=='delivery' and schema is Delivery:result.ready=False
            return result,meta
    class R(EvidenceRunner):
        enabled=False
        async def run(self,path,rid):
            if self.enabled and failure=='exception':raise RunnerError('测试容器超时')
            result=await super().run(path,rid)
            if self.enabled:
                if failure=='tools':result['passed']=False
                if failure=='missing':result['checks']=result['checks'][:1]
                if failure=='build':result['build']=False
                if failure=='mode':result['config']['mode']='collector'
                if failure=='input':(path/'src/game.ts').write_text('// injected fixture modification')
            return result
    g=G();r=R();s,w,pid,base=await existing(tmp_path,g,r);g.enabled=r.enabled=True
    rid=modification(s,pid,base['id'],'test');await approve(w,rid)
    assert s.run(rid)['status']=='failed' and s.run(rid)['repairs']==0
    result=json.loads(s.one('SELECT payload FROM run_reports')['payload']);assert not result['passed']
    assert s.one('SELECT active_version FROM projects')['active_version']==base['id'] and len(s.query('SELECT * FROM versions'))==1
    if failure in ('missing','build','mode','input','exception'):assert result['tool_evidence']['gate_errors']
    if failure=='qa_model':assert result['analysis_error'] and result['tool_evidence']['passed']
    s.con.close()
    with TestClient(create_app(tmp_path,ReportGateway(),EvidenceRunner())) as c:
        assert c.get('/api/runs/'+rid+'/report/export').status_code==200


@pytest.mark.asyncio
async def test_test_input_change_invalidates_approval_and_no_tool_call(tmp_path):
    s,w,pid,base=await existing(tmp_path);rid=modification(s,pid,base['id'],'test');await w.work(rid,'plan')
    path=Path(base['path'])/'src/main.ts';path.chmod(0o644);path.write_text(path.read_text()+'\n// changed after confirmation\n')
    s.execute("UPDATE runs SET status='queued' WHERE id=?",(rid,));await w.work(rid,'implement')
    assert s.run(rid)['status']=='failed' and '发生变化' in s.run(rid)['error']
    assert w.runner.calls==1 and not s.one('SELECT * FROM run_reports')
    s.con.close()


@pytest.mark.asyncio
async def test_cancel_joins_test_runner_and_does_not_create_final_report(tmp_path):
    reached=asyncio.Event();joined=asyncio.Event()
    class R(EvidenceRunner):
        hold=False
        async def run(self,path,rid):
            if self.hold:
                reached.set()
                try:await asyncio.Event().wait()
                finally:joined.set()
            return await super().run(path,rid)
    r=R();s,w,pid,base=await existing(tmp_path,r=r);r.hold=True
    rid=modification(s,pid,base['id'],'test');await w.work(rid,'plan');s.execute("UPDATE runs SET status='queued' WHERE id=?",(rid,));w.launch(rid,'implement')
    await asyncio.wait_for(reached.wait(),3);await w.cancel(rid)
    assert joined.is_set() and s.run(rid)['status']=='cancelled'
    assert not s.one('SELECT * FROM run_reports') and len(s.query('SELECT * FROM versions'))==1
    s.con.close()


def test_test_scope_api_replanning_stale_decision_restart_and_edit_rejection(tmp_path):
    s,w,pid,base=asyncio.run(existing(tmp_path));s.con.close()
    with TestClient(create_app(tmp_path,ReportGateway(),EvidenceRunner())) as c:
        count=len(c.get('/api/projects').json())
        assert c.post('/api/projects',json={'text':'直接测试','task_type':'test'}).status_code==400
        assert len(c.get('/api/projects').json())==count
        rid=c.post('/api/projects/'+pid+'/runs',json={'text':'验证三消连锁','task_type':'test'}).json()['run_id']
        r=wait_run(c,pid,lambda r:r['status']=='waiting_confirmation');old=options(c.app.state.store,rid)['scope_revision']
        assert c.get('/api/runs/'+rid+'/report').status_code==404
        assert c.post('/api/runs/'+rid+'/decision',json={'approve':True}).status_code==409
        assert c.put('/api/runs/'+rid+'/plan',json={'plan':json.loads(r['plan']),'expected_plan':r['plan']}).status_code==409
        assert c.post('/api/runs/'+rid+'/messages',json={'content':'再关注无效交换'}).status_code==201
        r=wait_run(c,pid,lambda r:r['status']=='waiting_confirmation' and r['plan'])
        new=options(c.app.state.store,rid)['scope_revision'];assert new!=old
        assert c.post('/api/runs/'+rid+'/decision',json={'approve':True,'expected_revision':r['approval_revision'],'expected_scope_revision':old}).status_code==409
    with TestClient(create_app(tmp_path,ReportGateway(),EvidenceRunner())) as c:
        r=c.get('/api/projects/'+pid).json()['runs'][0];assert r['status']=='waiting_confirmation'
        assert c.post('/api/runs/'+rid+'/decision',json={'approve':True,'expected_revision':r['approval_revision'],'expected_scope_revision':new,'expected_plan':r['plan']}).status_code==200
        r=wait_run(c,pid,lambda r:r['status'] in ('succeeded','failed'));assert r['status']=='succeeded',r
        assert r['has_report'] and r['task_type']=='test'
        p=c.get('/api/projects/'+pid).json();assert len(p['versions'])==1 and p['active_version']==base['id']


def test_malformed_evidence_never_passes():
    assert evidence_errors({'passed':True,'build':True,'checks':[{'name':[],'passed':True}],'config':[]},'match3')


def test_qa_clarification_after_testing_requires_new_scope_and_no_partial_report(tmp_path):
    class G(ReportGateway):
        asked=False
        async def call(self,role,prompt,schema):
            result,meta=await super().call(role,prompt,schema)
            if schema is QAReport and '"scope": "report_only"' in prompt and not self.asked:
                self.asked=True;result.clarification='是否需要人工体验关卡难度？'
            return result,meta
    g=G();s,w,pid,base=asyncio.run(existing(tmp_path,g));s.con.close()
    with TestClient(create_app(tmp_path,g,EvidenceRunner())) as c:
        rid=c.post('/api/projects/'+pid+'/runs',json={'text':'测试当前三消版本','task_type':'test'}).json()['run_id']
        r=wait_run(c,pid,lambda r:r['status']=='waiting_confirmation' and r['plan'])
        old=options(c.app.state.store,rid)['scope_revision']
        assert c.post('/api/runs/'+rid+'/decision',json={'approve':True,'expected_scope_revision':old}).status_code==200
        r=wait_run(c,pid,lambda r:r['status']=='waiting_confirmation' and not r['plan'])
        assert c.get('/api/runs/'+rid+'/report').status_code==404
        question=c.get('/api/runs/'+rid+'/messages').json()['pending_questions'][0]
        assert c.post('/api/runs/'+rid+'/messages',json={'content':'人工体验另行进行','reply_to':question}).status_code==201
        r=wait_run(c,pid,lambda r:r['status']=='waiting_confirmation' and r['plan'])
        new=options(c.app.state.store,rid)['scope_revision'];assert new!=old
        assert c.post('/api/runs/'+rid+'/decision',json={'approve':True,'expected_scope_revision':new,'expected_revision':r['approval_revision']}).status_code==200
        r=wait_run(c,pid,lambda r:r['status'] in ('succeeded','failed'));assert r['status']=='succeeded'
        assert len(c.get('/api/projects/'+pid).json()['versions'])==1


@pytest.mark.asyncio
async def test_later_fix_reads_same_version_test_report_and_exports_reference(tmp_path):
    s,w,pid,base=await existing(tmp_path)
    tested=modification(s,pid,base['id'],'test');await approve(w,tested)
    assert s.run(tested)['status']=='succeeded'
    fixed=modification(s,pid,base['id'],'bugfix');start=len(w.gateway.trace);await approve(w,fixed)
    assert s.run(fixed)['status']=='succeeded',s.run(fixed)
    assert options(s,fixed)['test_report_source']==tested
    prompts=[prompt for _,_,prompt in w.gateway.trace[start:]]
    assert any('previous_test_report' in p and tested in p for p in prompts)
    vid=s.one('SELECT id FROM versions WHERE run_id=?',(fixed,))['id']
    # A different base version cannot inherit that old test as a fresh result.
    next_id=modification(s,pid,vid,'bugfix')
    from studio.team import Team
    assert Team(w).context(s.run(next_id))['previous_test_report'] is None
    await w.cancel(next_id);s.con.close()
    with TestClient(create_app(tmp_path,ReportGateway(),EvidenceRunner())) as c:
        with zipfile.ZipFile(io.BytesIO(c.get('/api/versions/'+vid+'/export').content)) as z:
            refs=json.loads(z.read('test-reports.json'))
            assert refs[tested]['base_version']==base['id']
