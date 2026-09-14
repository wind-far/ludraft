import asyncio
import hashlib
import io
import json
import zipfile
import pytest
from fastapi.testclient import TestClient
from studio.app import create_app
from studio.documents import validate_bundle,previous_documents
from studio.team_models import DocumentScope,DocumentBundle,DocumentReview
from studio.routing import options,save
from studio.llm import ModelError
from studio.reports import encoded
from test_team import setup,approve
from test_routing import modification
from test_messages import wait_run
from document_fixture import DocumentGateway
from testing_fixture import EvidenceRunner


def start(root,g=None):
    s,w,pid,rid=setup(root,g or DocumentGateway(),EvidenceRunner())
    save(s,rid,{'requested_type':'doc'})
    s.execute('UPDATE runs SET requirement=? WHERE id=?',('编写三消玩法说明',rid))
    return s,w,pid,rid


@pytest.mark.asyncio
async def test_new_project_document_no_runner_no_versions_and_cited_export(tmp_path):
    s,w,pid,rid=start(tmp_path)
    async def forbidden(*args):raise AssertionError('Document flow must not invoke Docker')
    w.runner.available=w.runner.run=forbidden
    await approve(w,rid)
    assert s.run(rid)['status']=='succeeded',s.run(rid)
    assert not s.query('SELECT * FROM versions')
    result=json.loads(s.one('SELECT payload FROM run_reports')['payload']);digest=result.pop('sha256')
    assert digest==hashlib.sha256(encoded(result).encode()).hexdigest()
    assert list(result['sources'])==['messages','requirement']
    assert [x['task_key'] for x in result['steps']]==['brief','document_scope','documents','document_review']
    assert not s.one("SELECT * FROM events WHERE kind IN ('testing','published','test_result')")
    s.con.close()
    with TestClient(create_app(tmp_path,DocumentGateway(),EvidenceRunner())) as c:
        first=c.get('/api/runs/'+rid+'/report').json()
        with zipfile.ZipFile(io.BytesIO(c.get('/api/runs/'+rid+'/report/export').content)) as z:
            assert {'documents/match3-design.md','sources.json','report.json','README.md','rules.json','licenses/upstream-MIT.txt'}<=set(z.namelist())
            assert json.loads(z.read('report.json'))==first
            assert '规则建议' in z.read('documents/match3-design.md').decode()
            assert all('..' not in p and not p.startswith('/') for p in z.namelist())
        assert c.post('/api/runs/'+rid+'/messages',json={'content':'重写历史文档'}).status_code==409
        assert c.get('/api/runs/'+rid+'/report').json()==first


@pytest.mark.asyncio
@pytest.mark.parametrize('failure',['quote','source','lines','empty','missing','sections','id','review','model'])
async def test_invalid_documents_fail_after_bounded_repairs_and_preserve_previous(tmp_path,failure):
    class G(DocumentGateway):
        enabled=False
        async def call(self,role,prompt,schema):
            if self.enabled and failure=='model' and schema is DocumentReview:raise ModelError('fixture failed')
            result,meta=await super().call(role,prompt,schema)
            if self.enabled and schema is DocumentBundle:
                d=result.documents[0];section=d.sections[0];citation=section.citations[0]
                if failure=='quote':citation.quote='这段引文不存在'
                if failure=='source':citation.source_id='file:../../secret'
                if failure=='lines':citation.end=2
                if failure=='empty':section.body=' '
                if failure=='missing':section.citations=[]
                if failure=='sections':d.sections.reverse()
                if failure=='id':d.id='unknown'
            if self.enabled and failure=='review':
                if schema is DocumentReview:result.accepted=False;result.issues=['引用存在但不支持结论']
            return result,meta
    g=G();s,w,pid,first=start(tmp_path,g);await approve(w,first)
    original=s.one('SELECT payload FROM run_reports')['payload'];g.enabled=True
    rid=modification(s,pid,None,'doc');await approve(w,rid)
    assert s.run(rid)['status']=='failed',s.run(rid)
    assert s.run(rid)['repairs']==(0 if failure=='model' else 2)
    report=json.loads(s.one('SELECT payload FROM run_reports WHERE run_id=?',(rid,))['payload'])
    assert not report['passed'] and report['documents'] and (report['validation']['errors'] or report['analysis_error'])
    assert s.one('SELECT payload FROM run_reports WHERE run_id=?',(first,))['payload']==original
    next_id=modification(s,pid,None,'doc')
    assert previous_documents(s,s.run(next_id))['run_id']==first
    assert w.runner.calls==0 and not s.query('SELECT * FROM versions')
    s.con.close()


@pytest.mark.asyncio
async def test_document_repair_then_iteration_downstream_generation_history(tmp_path):
    class G(DocumentGateway):
        once=True
        async def call(self,role,prompt,schema):
            result,meta=await super().call(role,prompt,schema)
            if schema is DocumentBundle and self.once:
                self.once=False;result.documents[0].sections[0].citations[0].quote='错误引用'
            return result,meta
    s,w,pid,first=start(tmp_path,G());await approve(w,first)
    assert s.run(first)['status']=='succeeded' and s.run(first)['repairs']==1
    second=modification(s,pid,None,'doc');await approve(w,second)
    assert s.run(second)['status']=='succeeded' and options(s,second)['document_source']==first
    assert 'document:match3-design' in options(s,second)['document_sources']
    game=modification(s,pid,None,'feature');await approve(w,game)
    assert s.run(game)['status']=='succeeded',s.run(game)
    assert options(s,game)['document_source']==second
    assert any(second in p and 'previous_documents' in p for _,_,p in w.gateway.trace)
    vid=s.one('SELECT id FROM versions')['id']
    current=modification(s,pid,vid,'doc');await approve(w,current)
    assert s.run(current)['status']=='succeeded' and len(s.query('SELECT * FROM versions'))==1
    assert {'file:src/game.ts','file:src/config.ts','plan','tests'}<=options(s,current)['document_sources'].keys()
    assert s.one('SELECT active_version FROM projects')['active_version']==vid
    s.con.close()
    with TestClient(create_app(tmp_path,DocumentGateway(),EvidenceRunner())) as c:
        for url in ('/api/versions/'+vid+'/export','/api/runs/'+current+'/report/export'):
            with zipfile.ZipFile(io.BytesIO(c.get(url).content)) as z:
                refs=json.loads(z.read('document-history.json'));assert {first,second}<=refs.keys()
                for report in refs.values():
                    for source in report['sources'].values():assert hashlib.sha256(source['text'].encode()).hexdigest()==source['sha256']


def test_doc_scope_reject_revise_restart_stale_approval(tmp_path):
    with TestClient(create_app(tmp_path,DocumentGateway(),EvidenceRunner())) as c:
        result=c.post('/api/projects',json={'text':'编写三消设计文档','task_type':'doc'});assert result.status_code==201,result.text
        pid=result.json()['project_id'];rid=result.json()['run_id']
        r=wait_run(c,pid,lambda r:r['status']=='waiting_confirmation');old=options(c.app.state.store,rid)['scope_revision']
        assert c.post('/api/runs/'+rid+'/decision',json={'approve':True}).status_code==409
        assert c.put('/api/runs/'+rid+'/plan',json={'plan':json.loads(r['plan']),'expected_plan':r['plan']}).status_code==409
        assert c.post('/api/runs/'+rid+'/decision',json={'approve':False}).status_code==200
        assert c.get('/api/runs/'+rid+'/report').status_code==404
        assert c.get('/api/projects/'+pid).json()['runs'][0]['status']=='cancelled'
        assert c.post('/api/runs/'+rid+'/messages',json={'content':'补充连锁规则的建议'}).status_code==409
        rid=c.post('/api/projects/'+pid+'/runs',json={'text':'重新编写三消规则文档','task_type':'doc'}).json()['run_id']
        wait_run(c,pid,lambda r:r['status']=='waiting_confirmation')
        old=options(c.app.state.store,rid)['scope_revision']
        assert c.post('/api/runs/'+rid+'/messages',json={'content':'补充连锁规则的建议'}).status_code==201
        r=wait_run(c,pid,lambda r:r['status']=='waiting_confirmation' and r['plan'])
        new=options(c.app.state.store,rid)['scope_revision'];assert new!=old
        assert c.post('/api/runs/'+rid+'/decision',json={'approve':True,'expected_scope_revision':old,'expected_revision':r['approval_revision']}).status_code==409
    with TestClient(create_app(tmp_path,DocumentGateway(),EvidenceRunner())) as c:
        r=c.get('/api/projects/'+pid).json()['runs'][0]
        assert c.post('/api/runs/'+rid+'/decision',json={'approve':True,'expected_scope_revision':new,'expected_revision':r['approval_revision'],'expected_plan':r['plan']}).status_code==200
        r=wait_run(c,pid,lambda r:r['status'] in ('failed','succeeded'));assert r['status']=='succeeded',r


@pytest.mark.asyncio
async def test_document_cancel_waiting_writer_no_report(tmp_path):
    reached=asyncio.Event();joined=asyncio.Event()
    class G(DocumentGateway):
        async def call(self,role,prompt,schema):
            if schema is DocumentBundle:
                reached.set()
                try:await asyncio.Event().wait()
                finally:joined.set()
            return await super().call(role,prompt,schema)
    s,w,pid,rid=start(tmp_path,G());await w.work(rid,'plan')
    s.execute("UPDATE runs SET status='queued' WHERE id=?",(rid,));w.launch(rid,'implement')
    await asyncio.wait_for(reached.wait(),3);await w.cancel(rid)
    assert joined.is_set() and s.run(rid)['status']=='cancelled' and not s.query('SELECT * FROM run_reports')
    s.con.close()


def test_document_clarification_requires_reapproval(tmp_path):
    class G(DocumentGateway):
        asked=False
        async def call(self,role,prompt,schema):
            result,meta=await super().call(role,prompt,schema)
            if schema is DocumentReview and not self.asked:self.asked=True;result.clarification='目标分数是建议还是已确定的要求？'
            return result,meta
    with TestClient(create_app(tmp_path,G(),EvidenceRunner())) as c:
        x=c.post('/api/projects',json={'text':'编写三消设计文档','task_type':'doc'}).json();pid=x['project_id'];rid=x['run_id']
        wait_run(c,pid,lambda r:r['status']=='waiting_confirmation');old=options(c.app.state.store,rid)['scope_revision']
        assert c.post('/api/runs/'+rid+'/decision',json={'approve':True,'expected_scope_revision':old}).status_code==200
        wait_run(c,pid,lambda r:r['status']=='waiting_confirmation' and not r['plan'])
        assert c.get('/api/runs/'+rid+'/report').status_code==404
        q=c.get('/api/runs/'+rid+'/messages').json()['pending_questions'][0]
        assert c.post('/api/runs/'+rid+'/messages',json={'content':'分数只是建议','reply_to':q}).status_code==201
        r=wait_run(c,pid,lambda r:r['status']=='waiting_confirmation' and r['plan'])
        new=options(c.app.state.store,rid)['scope_revision'];assert new!=old
        assert c.post('/api/runs/'+rid+'/decision',json={'approve':True,'expected_scope_revision':new,'expected_revision':r['approval_revision']}).status_code==200
        r=wait_run(c,pid,lambda r:r['status'] in ('failed','succeeded'));assert r['status']=='succeeded',r


def test_document_schema_rejects_unsafe_paths_duplicate_files_and_blank_headings():
    from pydantic import ValidationError
    from studio.team_models import DocumentTarget
    for target in ({'id':'../escape','title':'规则','sections':['规则']},{'id':'safe','title':'规则','sections':[' ']},{'id':'safe','title':'规则\n伪造标题','sections':['规则']}):
        with pytest.raises(ValidationError):DocumentTarget.model_validate(target)
    doc={'id':'same','title':'规则','sections':[{'heading':'规则','body':'建议','kind':'proposal','citations':[]}]}
    with pytest.raises(ValidationError):DocumentBundle(summary='禁止同名覆盖',documents=[doc,doc])


def test_document_uses_reviewed_upload_not_raw_extract(tmp_path):
    with TestClient(create_app(tmp_path,DocumentGateway(),EvidenceRunner())) as c:
        upload=c.post('/api/uploads?name=research.md',content='原始参考：三消 20 步'.encode(),headers={'Content-Type':'application/octet-stream'})
        assert upload.status_code==201,upload.text
        material={'upload_id':upload.json()['id'],'text':'人工核对后的参考：三消 30 步'}
        made=c.post('/api/projects',json={'text':'编写三消规则文档','task_type':'doc','materials':[material]}).json()
        pid,rid=made['project_id'],made['run_id'];wait_run(c,pid,lambda r:r['status']=='waiting_confirmation')
        scope=options(c.app.state.store,rid)['scope_revision']
        assert c.post('/api/runs/'+rid+'/decision',json={'approve':True,'expected_scope_revision':scope}).status_code==200
        r=wait_run(c,pid,lambda r:r['status'] in ('failed','succeeded'));assert r['status']=='succeeded',r
        result=c.get('/api/runs/'+rid+'/report').json()
        assert result['sources']['material:0']['text']==material['text']
