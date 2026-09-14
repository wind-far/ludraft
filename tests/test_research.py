import asyncio
import io
import json
import zipfile
import pytest
from fastapi.testclient import TestClient
from studio.app import create_app
from studio.team_models import ResearchResult,ResearchReview
from studio.routing import options,save
from studio.research import previous_research
from studio.llm import ModelError
from test_team import setup,approve
from test_routing import modification
from test_messages import wait_run
from research_fixture import ResearchGateway,FixturePages
from testing_fixture import EvidenceRunner

def start(root,g=None):
    s,w,pid,rid=setup(root,g or ResearchGateway(),EvidenceRunner());w.pages=FixturePages()
    save(s,rid,{'requested_type':'research','research_urls':['https://example.org/match3']})
    s.execute('UPDATE runs SET requirement=? WHERE id=?',('比较三消的经典和连锁方向',rid))
    return s,w,pid,rid

@pytest.mark.asyncio
async def test_research_approval_precedes_web_read_and_no_game_publication(tmp_path):
    s,w,pid,rid=start(tmp_path);await w.work(rid,'plan')
    assert s.run(rid)['status']=='waiting_confirmation' and not w.pages.calls and w.runner.calls==0
    s.execute("UPDATE runs SET status='queued' WHERE id=?",(rid,));await w.work(rid,'implement')
    assert s.run(rid)['status']=='succeeded',s.run(rid)
    report=json.loads(s.one('SELECT payload FROM run_reports')['payload'])
    assert report['passed'] and len(report['steps'])==4 and set(s['role'] for s in report['steps'])=={'制作人','策划'}
    assert 'web:0' in report['sources'] and report['result']['recommendation']=='classic'
    assert not s.query('SELECT * FROM versions') and w.runner.calls==0
    assert not s.one("SELECT * FROM events WHERE kind IN ('published','test_result')")
    s.con.close()
    with TestClient(create_app(tmp_path,ResearchGateway(),EvidenceRunner(),FixturePages())) as c:
        with zipfile.ZipFile(io.BytesIO(c.get('/api/runs/'+rid+'/report/export').content)) as z:
            assert {'report.json','research.md','sources.json','rules.json','licenses/upstream-MIT.txt'}<=set(z.namelist())
            assert json.loads(z.read('report.json'))==report
            assert '待验证问题' in z.read('research.md').decode()

@pytest.mark.asyncio
@pytest.mark.parametrize('failure',['web','quote','missing','question','direction','criterion','recommendation','review','model'])
async def test_research_failures_remain_visible_and_never_become_prior_evidence(tmp_path,failure):
    class G(ResearchGateway):
        async def call(self,role,prompt,schema):
            if failure=='model' and schema is ResearchReview:raise ModelError('fixture failure')
            result,meta=await super().call(role,prompt,schema)
            if schema is ResearchResult:
                if failure=='quote':result.answers[0].statement.citations[0].quote='不存在的来源内容'
                if failure=='missing':result.answers[0].statement.citations=[]
                if failure=='question':result.answers[0].question_id='missing'
                if failure=='direction':result.directions[0].id='missing'
                if failure=='criterion':result.directions[0].assessments[0].criterion='新维度'
                if failure=='recommendation':result.recommendation='unknown'
            if schema is ResearchReview and failure=='review':result.accepted=False;result.issues=['来源不足以支持结论']
            return result,meta
    s,w,pid,rid=start(tmp_path,G());w.pages.fail=failure=='web';await approve(w,rid)
    assert s.run(rid)['status']=='failed',s.run(rid)
    report=json.loads(s.one('SELECT payload FROM run_reports')['payload']);assert not report['passed']
    if failure=='web':assert report['result'] is None and report['source_fetches'][0]['status']=='failed' and not any(schema is ResearchResult for _,schema,_ in w.gateway.trace)
    assert s.run(rid)['repairs']==(0 if failure in ('web','model') else 2)
    later=modification(s,pid,None,'feature');assert previous_research(s,s.run(later)) is None
    assert not s.query('SELECT * FROM versions') and w.runner.calls==0
    s.con.close()

def test_user_adopts_exact_direction_after_report_and_export_records_choice(tmp_path):
    with TestClient(create_app(tmp_path,ResearchGateway(),EvidenceRunner(),FixturePages())) as c:
        made=c.post('/api/projects',json={'text':'调研三消方向','task_type':'research'}).json();pid,rid=made['project_id'],made['run_id']
        wait_run(c,pid,lambda r:r['status']=='waiting_confirmation');revision=options(c.app.state.store,rid)['scope_revision']
        assert c.post('/api/runs/'+rid+'/decision',json={'approve':True,'expected_scope_revision':revision}).status_code==200
        r=wait_run(c,pid,lambda r:r['status'] in ('failed','succeeded'));assert r['status']=='succeeded',r
        report=c.get('/api/runs/'+rid+'/report').json();assert not report['source_fetches'] and '没有读取外部网页' in report['evidence_scope']
        choice={'run_id':rid,'direction_id':'chain'}
        assert c.post('/api/projects/'+pid+'/runs',json={'text':'选择未知方向','task_type':'feature','research_choice':{**choice,'direction_id':'missing'}}).status_code==409
        game=c.post('/api/projects/'+pid+'/runs',json={'text':'采用连锁挑战制作三消','task_type':'feature','research_choice':choice}).json()['run_id']
        r=wait_run(c,pid,lambda r:r['status']=='waiting_confirmation')
        assert previous_research(c.app.state.store,c.app.state.store.run(game))['selected_direction']=='chain'
        assert c.post('/api/runs/'+game+'/decision',json={'approve':True,'expected_plan':r['plan']}).status_code==200
        r=wait_run(c,pid,lambda r:r['status'] in ('failed','succeeded'));assert r['status']=='succeeded',r
        p=c.get('/api/projects/'+pid).json();assert len(p['versions'])==1
        with zipfile.ZipFile(io.BytesIO(c.get('/api/versions/'+p['active_version']+'/export').content)) as z:
            assert json.loads(z.read('research-history.json'))[rid]==report
            assert json.loads(z.read('research-selections.json'))[game]==choice
        assert c.post('/api/projects/'+pid+'/runs',json={'text':'旧基准选择','task_type':'feature','research_choice':choice}).status_code==409
        assert c.get('/api/runs/'+rid+'/report').json()==report

def test_research_replanning_restart_rejects_old_approval_and_bad_web_inputs(tmp_path):
    pages=FixturePages()
    with TestClient(create_app(tmp_path,ResearchGateway(),EvidenceRunner(),pages)) as c:
        assert c.post('/api/projects',json={'text':'研究内部接口','task_type':'research','research_urls':['http://127.0.0.1/secret']}).status_code==400
        assert c.get('/api/projects').json()==[]
        made=c.post('/api/projects',json={'text':'调研三消方向','task_type':'research','research_urls':['https://example.org/design']}).json();pid,rid=made['project_id'],made['run_id']
        r=wait_run(c,pid,lambda r:r['status']=='waiting_confirmation');old=options(c.app.state.store,rid)['scope_revision']
        assert not pages.calls
        assert c.post('/api/runs/'+rid+'/decision',json={'approve':True}).status_code==409
        assert c.put('/api/runs/'+rid+'/plan',json={'plan':json.loads(r['plan']),'expected_plan':r['plan']}).status_code==409
        assert c.post('/api/runs/'+rid+'/messages',json={'content':'优先比较新手友好性'}).status_code==201
        r=wait_run(c,pid,lambda r:r['status']=='waiting_confirmation' and r['plan']);new=options(c.app.state.store,rid)['scope_revision'];assert old!=new
        assert c.post('/api/runs/'+rid+'/decision',json={'approve':True,'expected_scope_revision':old,'expected_revision':r['approval_revision']}).status_code==409
    with TestClient(create_app(tmp_path,ResearchGateway(),EvidenceRunner(),pages)) as c:
        r=c.get('/api/projects/'+pid).json()['runs'][0]
        assert c.post('/api/runs/'+rid+'/decision',json={'approve':True,'expected_scope_revision':new,'expected_revision':r['approval_revision']}).status_code==200
        r=wait_run(c,pid,lambda r:r['status'] in ('failed','succeeded'));assert r['status']=='succeeded',r

@pytest.mark.asyncio
async def test_cancel_joins_web_read_without_final_report(tmp_path):
    entered=asyncio.Event();joined=asyncio.Event()
    class Pages:
        async def fetch(self,url):
            entered.set()
            try:await asyncio.Event().wait()
            finally:joined.set()
    s,w,pid,rid=start(tmp_path);w.pages=Pages();await w.work(rid,'plan');s.execute("UPDATE runs SET status='queued' WHERE id=?",(rid,));w.launch(rid,'implement')
    await asyncio.wait_for(entered.wait(),3);await w.cancel(rid)
    assert joined.is_set() and not s.query('SELECT * FROM run_reports') and s.run(rid)['status']=='cancelled'
    s.con.close()


def test_research_clarification_discards_draft_and_refreshes_sources_after_reapproval(tmp_path):
    class G(ResearchGateway):
        asked=False
        async def call(self,role,prompt,schema):
            result,meta=await super().call(role,prompt,schema)
            if schema is ResearchReview and not self.asked:self.asked=True;result.clarification='是否将入门难度作为优先目标？'
            return result,meta
    pages=FixturePages()
    with TestClient(create_app(tmp_path,G(),EvidenceRunner(),pages)) as c:
        made=c.post('/api/projects',json={'text':'调研三消方向','task_type':'research','research_urls':['https://example.org/']}).json();pid,rid=made['project_id'],made['run_id']
        wait_run(c,pid,lambda r:r['status']=='waiting_confirmation');old=options(c.app.state.store,rid)['scope_revision']
        assert c.post('/api/runs/'+rid+'/decision',json={'approve':True,'expected_scope_revision':old}).status_code==200
        wait_run(c,pid,lambda r:r['status']=='waiting_confirmation' and not r['plan'])
        assert c.get('/api/runs/'+rid+'/report').status_code==404 and len(pages.calls)==1
        question=c.get('/api/runs/'+rid+'/messages').json()['pending_questions'][0]
        assert c.post('/api/runs/'+rid+'/messages',json={'content':'优先新手入门','reply_to':question}).status_code==201
        r=wait_run(c,pid,lambda r:r['status']=='waiting_confirmation' and r['plan']);new=options(c.app.state.store,rid)['scope_revision'];assert old!=new
        assert len(pages.calls)==1
        assert c.post('/api/runs/'+rid+'/decision',json={'approve':True,'expected_scope_revision':new,'expected_revision':r['approval_revision']}).status_code==200
        r=wait_run(c,pid,lambda r:r['status'] in ('failed','succeeded'));assert r['status']=='succeeded',r
        assert len(pages.calls)==2 and not c.get('/api/projects/'+pid).json()['versions']
