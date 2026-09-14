import asyncio
import hashlib
import io
import json
import zipfile
from pathlib import Path
import pytest
from fastapi.testclient import TestClient
from studio.app import create_app
from studio.team_models import ReviewScope,CodeAudit,AuditResponse,AuditVerdict,Brief
from studio.code_review import previous_review
from studio.routing import options
from studio.reports import encoded
from studio.llm import ModelError
from studio.test_flow import manifest
from test_reports import existing
from test_team import approve
from test_routing import modification
from test_messages import wait_run
from testing_fixture import EvidenceRunner
from review_fixture import ReviewGateway


@pytest.mark.asyncio
@pytest.mark.parametrize('outcome',['finding','clean','dismissed','unresolved'])
async def test_review_only_reports_coverage_response_decision_and_export(tmp_path,outcome):
    g=ReviewGateway();g.include_finding=outcome!='clean';g.decision=outcome if outcome in ('dismissed','unresolved') else 'confirmed'
    s,w,pid,base=await existing(tmp_path,g);before=manifest(Path(base['path']))
    async def forbidden(*args):raise AssertionError('Review cannot run games')
    w.runner.available=w.runner.run=forbidden
    rid=modification(s,pid,base['id'],'review');await approve(w,rid)
    assert s.run(rid)['status']=='succeeded',s.run(rid)
    result=json.loads(s.one('SELECT payload FROM run_reports')['payload']);sha=result.pop('sha256')
    assert hashlib.sha256(encoded(result).encode()).hexdigest()==sha
    assert result['passed'] and result['input_unchanged']
    assert len(result['open_findings'])==(1 if outcome in ('finding','unresolved') else 0)
    assert [x['task_key'] for x in result['steps']]==['brief','review_scope','code_audit','audit_response','audit_verdict']
    assert len(s.query('SELECT * FROM versions'))==1 and s.one('SELECT active_version FROM projects')['active_version']==base['id']
    assert manifest(Path(base['path']))==before
    assert not s.one("SELECT * FROM events WHERE run_id=? AND kind IN ('testing','test_result','published','files_changed')",(rid,))
    s.con.close()
    with TestClient(create_app(tmp_path,ReviewGateway(),EvidenceRunner())) as c:
        first=c.get('/api/runs/'+rid+'/report').json()
        with zipfile.ZipFile(io.BytesIO(c.get('/api/runs/'+rid+'/report/export').content)) as z:
            assert {'code-review.md','report.json','sources.json','rules.json','licenses/upstream-MIT.txt'}<=set(z.namelist())
            assert json.loads(z.read('report.json'))==first
            assert base['id'] in z.read('code-review.md').decode()
        assert c.post('/api/runs/'+rid+'/messages',json={'content':'修改历史审查'}).status_code==409
        assert c.get('/api/runs/'+rid+'/report').json()==first


@pytest.mark.asyncio
@pytest.mark.parametrize('failure',['quote','line','source','coverage','duplicate','response','response_quote','decision','verdict','model'])
async def test_invalid_audit_cannot_complete_or_feed_fixes(tmp_path,failure):
    class G(ReviewGateway):
        async def call(self,role,prompt,schema):
            if schema is AuditVerdict and failure=='model':raise ModelError('fixture model failure')
            result,meta=await super().call(role,prompt,schema)
            if schema is CodeAudit:
                c=result.findings[0].citations[0]
                if failure=='quote':c.quote='不存在的代码片段'
                if failure=='line':c.start=19999;c.end=20000
                if failure=='source':c.source_id='file:../../config.json'
                if failure=='coverage':result.coverage[0].path='src/main.ts'
                if failure=='duplicate':result.findings.append(result.findings[0].model_copy(deep=True))
            if schema is AuditResponse:
                if failure=='response':result.responses=[]
                if failure=='response_quote':result.responses[0].citations[0].quote='假代码'
            if schema is AuditVerdict:
                if failure=='decision':result.decisions[0].finding_id='unknown'
                if failure=='verdict':result.accepted=False
            return result,meta
    s,w,pid,base=await existing(tmp_path,G());rid=modification(s,pid,base['id'],'review');await approve(w,rid)
    assert s.run(rid)['status']=='failed',s.run(rid)
    assert s.run(rid)['repairs']==(0 if failure=='model' else 2)
    report=json.loads(s.one('SELECT payload FROM run_reports')['payload']);assert not report['passed'] and report['open_findings']
    later=modification(s,pid,base['id'],'bugfix');assert previous_review(s,s.run(later)) is None
    assert w.runner.calls==1 and len(s.query('SELECT * FROM versions'))==1
    s.con.close()


@pytest.mark.asyncio
async def test_one_bad_quote_revised_and_selected_review_used_by_fix_and_export(tmp_path):
    class G(ReviewGateway):
        once=True
        async def call(self,role,prompt,schema):
            result,meta=await super().call(role,prompt,schema)
            if schema is CodeAudit and self.once:self.once=False;result.findings[0].citations[0].quote='先返回无效引用'
            return result,meta
    s,w,pid,base=await existing(tmp_path,G());rid=modification(s,pid,base['id'],'review');await approve(w,rid)
    assert s.run(rid)['status']=='succeeded' and s.run(rid)['repairs']==1
    second=modification(s,pid,base['id'],'review');await approve(w,second)
    assert options(s,second)['code_review_source']==rid
    s.con.close()
    g=ReviewGateway()
    with TestClient(create_app(tmp_path,g,EvidenceRunner())) as c:
        # Explicitly select the older successful review; do not silently substitute latest.
        made=c.post('/api/projects/'+pid+'/runs',json={'text':'复核所选审查并修复','task_type':'bugfix','code_review_id':rid});assert made.status_code==201,made.text
        fixed=made.json()['run_id'];r=wait_run(c,pid,lambda r:r['status']=='waiting_confirmation')
        assert options(c.app.state.store,fixed)['code_review_source']==rid
        assert c.post('/api/runs/'+fixed+'/decision',json={'approve':True,'expected_plan':r['plan']}).status_code==200
        r=wait_run(c,pid,lambda r:r['status'] in ('failed','succeeded'));assert r['status']=='succeeded',r
        assert any(rid in prompt and 'previous_code_review' in prompt for _,_,prompt in g.trace)
        p=c.get('/api/projects/'+pid).json();assert len(p['versions'])==2
        with zipfile.ZipFile(io.BytesIO(c.get('/api/versions/'+p['active_version']+'/export').content)) as z:
            refs=json.loads(z.read('code-reviews.json'));assert rid in refs and second not in refs
        before=len(p['runs'])
        assert c.post('/api/projects/'+pid+'/runs',json={'text':'旧审查用于新版本','task_type':'bugfix','code_review_id':rid}).status_code==409
        assert len(c.get('/api/projects/'+pid).json()['runs'])==before


@pytest.mark.asyncio
@pytest.mark.parametrize('when',['before','during'])
async def test_source_changes_block_current_review(tmp_path,when):
    class G(ReviewGateway):
        path=None
        async def call(self,role,prompt,schema):
            if schema is AuditResponse and when=='during':self.path.write_text(self.path.read_text()+'\n// changed\n')
            return await super().call(role,prompt,schema)
    g=G();s,w,pid,base=await existing(tmp_path,g);g.path=Path(base['path'])/'src/game.ts';g.path.chmod(0o644)
    rid=modification(s,pid,base['id'],'review');await w.work(rid,'plan')
    if when=='before':g.path.write_text(g.path.read_text()+'\n// changed\n')
    s.execute("UPDATE runs SET status='queued' WHERE id=?",(rid,));await w.work(rid,'implement')
    assert s.run(rid)['status']=='failed'
    report=s.one('SELECT payload FROM run_reports')
    if when=='before':assert not report
    else:assert not json.loads(report['payload'])['input_unchanged']
    s.con.close()


def test_review_api_replanning_restart_and_source_selection_boundaries(tmp_path):
    s,w,pid,base=asyncio.run(existing(tmp_path,ReviewGateway()));s.con.close()
    with TestClient(create_app(tmp_path,ReviewGateway(),EvidenceRunner())) as c:
        count=len(c.get('/api/projects').json())
        assert c.post('/api/projects',json={'text':'直接审查','task_type':'review'}).status_code==400
        assert len(c.get('/api/projects').json())==count
        assert c.post('/api/projects/'+pid+'/runs',json={'text':'未知审查','task_type':'bugfix','code_review_id':'0'*32}).status_code==409
        rid=c.post('/api/projects/'+pid+'/runs',json={'text':'审查三消边界','task_type':'review'}).json()['run_id']
        r=wait_run(c,pid,lambda r:r['status']=='waiting_confirmation');old=options(c.app.state.store,rid)['scope_revision']
        assert c.post('/api/runs/'+rid+'/decision',json={'approve':True}).status_code==409
        assert c.put('/api/runs/'+rid+'/plan',json={'plan':json.loads(r['plan']),'expected_plan':r['plan']}).status_code==409
        assert c.post('/api/runs/'+rid+'/messages',json={'content':'增加连锁状态关注点'}).status_code==201
        r=wait_run(c,pid,lambda r:r['status']=='waiting_confirmation' and r['plan']);new=options(c.app.state.store,rid)['scope_revision'];assert new!=old
        assert c.post('/api/runs/'+rid+'/decision',json={'approve':True,'expected_scope_revision':old,'expected_revision':r['approval_revision']}).status_code==409
    with TestClient(create_app(tmp_path,ReviewGateway(),EvidenceRunner())) as c:
        r=c.get('/api/projects/'+pid).json()['runs'][0]
        assert c.post('/api/runs/'+rid+'/decision',json={'approve':True,'expected_scope_revision':new,'expected_revision':r['approval_revision']}).status_code==200
        r=wait_run(c,pid,lambda r:r['status'] in ('failed','succeeded'));assert r['status']=='succeeded',r
        assert c.post('/api/projects',json={'text':'跨项目引用','code_review_id':rid}).status_code==400
        assert c.post('/api/projects/'+pid+'/runs',json={'text':'错误任务类型','task_type':'doc','code_review_id':rid}).status_code==400


@pytest.mark.asyncio
async def test_cancel_joins_audit_model_and_no_final_report(tmp_path):
    reached=asyncio.Event();joined=asyncio.Event()
    class G(ReviewGateway):
        async def call(self,role,prompt,schema):
            if schema is AuditResponse:
                reached.set()
                try:await asyncio.Event().wait()
                finally:joined.set()
            return await super().call(role,prompt,schema)
    s,w,pid,base=await existing(tmp_path,G());rid=modification(s,pid,base['id'],'review');await w.work(rid,'plan')
    s.execute("UPDATE runs SET status='queued' WHERE id=?",(rid,));w.launch(rid,'implement');await asyncio.wait_for(reached.wait(),3);await w.cancel(rid)
    assert joined.is_set() and s.run(rid)['status']=='cancelled' and not s.query('SELECT * FROM run_reports')
    s.con.close()


@pytest.mark.asyncio
async def test_scope_rejects_unknown_files_before_confirmation(tmp_path):
    class G(ReviewGateway):
        async def call(self,role,prompt,schema):
            result,meta=await super().call(role,prompt,schema)
            if schema is ReviewScope:result.files=['../../outside.ts']
            return result,meta
    s,w,pid,base=await existing(tmp_path,G());rid=modification(s,pid,base['id'],'review');await w.work(rid,'plan')
    assert s.run(rid)['status']=='failed' and s.run(rid)['plan'] is None
    assert not s.query('SELECT * FROM run_reports')
    s.con.close()


def test_programmer_clarification_requires_new_review_scope(tmp_path):
    class G(ReviewGateway):
        asked=False
        async def call(self,role,prompt,schema):
            result,meta=await super().call(role,prompt,schema)
            if schema is AuditResponse and not self.asked:self.asked=True;result.clarification='该边界行为是否属于预期规则？'
            return result,meta
    g=G();s,w,pid,base=asyncio.run(existing(tmp_path,g));s.con.close()
    with TestClient(create_app(tmp_path,g,EvidenceRunner())) as c:
        rid=c.post('/api/projects/'+pid+'/runs',json={'text':'审查三消边界','task_type':'review'}).json()['run_id']
        wait_run(c,pid,lambda r:r['status']=='waiting_confirmation');old=options(c.app.state.store,rid)['scope_revision']
        assert c.post('/api/runs/'+rid+'/decision',json={'approve':True,'expected_scope_revision':old}).status_code==200
        wait_run(c,pid,lambda r:r['status']=='waiting_confirmation' and not r['plan'])
        assert c.get('/api/runs/'+rid+'/report').status_code==404
        q=c.get('/api/runs/'+rid+'/messages').json()['pending_questions'][0]
        assert c.post('/api/runs/'+rid+'/messages',json={'content':'按现有三消规则判断','reply_to':q}).status_code==201
        r=wait_run(c,pid,lambda r:r['status']=='waiting_confirmation' and r['plan']);new=options(c.app.state.store,rid)['scope_revision'];assert new!=old
        assert c.post('/api/runs/'+rid+'/decision',json={'approve':True,'expected_scope_revision':new,'expected_revision':r['approval_revision']}).status_code==200
        r=wait_run(c,pid,lambda r:r['status'] in ('failed','succeeded'));assert r['status']=='succeeded',r
        assert len(c.get('/api/projects/'+pid).json()['versions'])==1


@pytest.mark.asyncio
async def test_cross_kind_export_keeps_review_referenced_only_by_document(tmp_path):
    from studio.routing import save
    s,w,pid,base=await existing(tmp_path,ReviewGateway())
    review=modification(s,pid,base['id'],'review');await approve(w,review)
    doc=modification(s,pid,base['id'],'doc');await approve(w,doc)
    # A later run references only the document; its audit source must still be exported.
    later=modification(s,pid,base['id'],'doc')
    save(s,later,{'requested_type':'doc','document_source':doc,'code_review_source':None,'test_report_source':None})
    await approve(w,later);assert s.run(later)['status']=='succeeded'
    s.con.close()
    with TestClient(create_app(tmp_path,ReviewGateway(),EvidenceRunner())) as c:
        with zipfile.ZipFile(io.BytesIO(c.get('/api/runs/'+later+'/report/export').content)) as z:
            docs=json.loads(z.read('document-history.json'));reviews=json.loads(z.read('code-reviews.json'))
            assert docs[doc]['previous_code_review']==review
            assert reviews[review]['kind']=='review' and reviews[review]['sources']
