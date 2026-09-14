"""Regressions for current design handoffs, lineage and failed-call accounting."""
import asyncio
import io
import json
import zipfile
import httpx
import pytest
from fastapi.testclient import TestClient
from studio.app import create_app
from studio.models import ModelSettings, Parameters
from studio.team import Team
from studio.team_models import Design, Review, TestStrategy as QAStrategy, QAReport, Issue
from studio.llm import Gateway, ModelError
from studio.lineage import resolve
from test_team import setup, approve
from team_fixture import TeamGateway
from test_workbench import ParameterRunner, wait


@pytest.mark.asyncio
async def test_review_and_qa_consume_latest_complete_designs(tmp_path):
    class G(TeamGateway):
        revisions=0
        async def call(self,role,prompt,schema):
            result,meta=await super().call(role,prompt,schema)
            if schema is Design and role in ('美术','UX'):
                result.decisions=[f'{role}-unique-design-{self.revisions}']
            if schema in (Review,QAStrategy,QAReport):
                assert '美术-unique-design-' in prompt and 'UX-unique-design-0' in prompt
            if schema is Review:
                if self.revisions==0:
                    result.issues=[Issue(owner='美术',severity='blocking',description='修订配色',evidence='颜色对比不足')]
                self.revisions+=1
            return result,meta
    s,w,_,rid=setup(tmp_path,G());await approve(w,rid)
    assert s.run(rid)['status']=='succeeded'
    arts=s.query("SELECT id FROM agent_steps WHERE task_key='art' ORDER BY rowid")
    ux=s.one("SELECT id FROM agent_steps WHERE task_key='ux'")
    for key in ('review','test_strategy','qa_report'):
        steps=s.query('SELECT inputs FROM agent_steps WHERE task_key=? ORDER BY rowid',(key,))
        assert len(steps)==2
        for index,step in enumerate(steps):
            inputs=json.loads(step['inputs'])
            assert arts[index]['id'] in inputs and ux['id'] in inputs
            assert arts[1-index]['id'] not in inputs
    s.con.close()


def test_copy_parameters_legacy_lineage_and_export(tmp_path):
    s,w,pid,rid=setup(tmp_path,runner=ParameterRunner());asyncio.run(approve(w,rid))
    original=s.one('SELECT * FROM versions');plan=json.loads(s.run(rid)['plan']);s.con.close()
    app=create_app(tmp_path,TeamGateway(),ParameterRunner())
    with TestClient(app) as c:
        store=app.state.store
        copy=c.post(f'/api/projects/{pid}/duplicate').json()
        copy_version=store.one('SELECT * FROM versions WHERE run_id=?',(copy['run_id'],))
        # Existing copies had only an event source pointer.
        store.execute('UPDATE runs SET base_version=NULL WHERE id=?',(copy['run_id'],))
        inherited=c.get('/api/runs/'+copy['run_id']+'/team').json()
        assert inherited['steps']==[] and len(inherited['inherited_steps'])==13
        assert all(x['inherited'] and x['source_version']==original['id'] for x in inherited['inherited_steps'])
        with zipfile.ZipFile(io.BytesIO(c.get('/api/versions/'+copy_version['id']+'/export').content)) as z:
            steps=json.loads(z.read('collaboration.json'))
            evidence=json.loads(z.read('verification.json'))
            assert evidence['team']['review_step'] in {x['id'] for x in steps}
            assert len(json.loads(z.read('provenance.json'))['chain'])==2
        params=c.get('/api/versions/'+copy_version['id']).json()['parameters']
        params={k:params[k] for k in Parameters.model_fields};params['lives']=5
        result=c.post('/api/projects/'+copy['project_id']+'/parameters',json={'base_version':copy_version['id'],'parameters':params})
        assert result.status_code==201,result.text
        parameter_run=wait(c,result.json()['run_id']);assert parameter_run['status']=='succeeded'
        assert json.loads(parameter_run['plan'])==plan
        version=store.one('SELECT * FROM versions WHERE run_id=?',(parameter_run['id'],))
        # Old parameter runs replaced the gameplay summary; ancestry repairs their read path too.
        store.execute('UPDATE runs SET plan=? WHERE id=?',(json.dumps({**plan,'summary':'参数调整：旧版内容'}),parameter_run['id']))
        context=Team(app.state.workflow).context({'base_version':version['id'],'plan':None})
        assert context['previous_plan']==plan and len(context['previous_designs'])==3
        assert context['previous_evidence']['config']['lives']==5
        assert '"lives": 5' in context['files']['src/config.ts']
        assert len(context['design_lineage'])==3
        assert not store.query('SELECT * FROM agent_steps WHERE run_id=?',(parameter_run['id'],))
        with zipfile.ZipFile(io.BytesIO(c.get('/api/versions/'+version['id']+'/export').content)) as z:
            assert len(json.loads(z.read('collaboration.json')))==13
            assert json.loads(z.read('verification.json'))['parameter_match']
        # Missing source and corrupt cycles terminate without inventing artifacts.
        store.execute('UPDATE runs SET base_version=? WHERE id=?',(version['id'],copy['run_id']))
        assert len(resolve(store,version['id'])['chain'])==2
        assert resolve(store,'missing')['steps']==[]


@pytest.mark.asyncio
@pytest.mark.parametrize('body,status',[
    ({'choices':[{'message':{'content':'invalid PRIVATE'}}]},200),
    ({'choices':[{'message':{'content':'{"bad":"PRIVATE"}'}}]},200),
    ({'choices':[]},200),
    ({'error':'PRIVATE'},429),
])
async def test_failed_calls_keep_safe_usage_model_and_single_error_event(tmp_path,monkeypatch,body,status):
    g=Gateway(tmp_path);g.save(ModelSettings(model='real-model-id',api_key='PRIVATE'))
    body={**body,'usage':{'total_tokens':123,'prompt_tokens':100,'completion_tokens':23,'secret':'PRIVATE'}}
    real=httpx.AsyncClient
    monkeypatch.setattr(httpx,'AsyncClient',lambda **kw:real(transport=httpx.MockTransport(lambda r:httpx.Response(status,json=body)),**kw))
    s,w,_,rid=setup(tmp_path,g);await w.work(rid,'plan')
    assert s.run(rid)['status']=='failed'
    step=s.one('SELECT * FROM agent_steps');assert step['model']=='real-model-id'
    assert json.loads(step['usage'])=={'total_tokens':123,'prompt_tokens':100,'completion_tokens':23}
    events=s.query("SELECT kind,payload FROM events WHERE kind IN ('model_result','model_error')")
    assert len(events)==1 and events[0]['kind']=='model_error'
    assert json.loads(events[0]['payload'])['attempted'] is True
    assert 'PRIVATE' not in json.dumps([step,events,s.run(rid)])
    s.con.close()


@pytest.mark.asyncio
async def test_timeout_unknown_usage_and_preflight_no_call(tmp_path,monkeypatch):
    g=Gateway(tmp_path);g.save(ModelSettings(model='test-model',base_url='http://localhost:9999'))
    real=httpx.AsyncClient
    def fail(r):raise httpx.ReadTimeout('PRIVATE',request=r)
    monkeypatch.setattr(httpx,'AsyncClient',lambda **kw:real(transport=httpx.MockTransport(fail),**kw))
    with pytest.raises(ModelError) as caught:await g.call('QA','test',Review)
    assert caught.value.metadata=={'model':'test-model','provider':'openai','base_url':'http://localhost:9999','usage':{},'attempted':True}
    g.save(ModelSettings(model='',base_url='http://localhost:9999'))
    monkeypatch.delenv('STUDIO_MODEL',raising=False)
    with pytest.raises(ModelError) as caught:await g.call('QA','test',Review)
    assert caught.value.metadata=={'attempted':False}


@pytest.mark.asyncio
async def test_custom_gateway_schema_failure_keeps_returned_usage(tmp_path):
    class G(TeamGateway):
        async def call(self,role,prompt,schema):
            return Review(summary='wrong schema',issues=[]),{'model':'custom','usage':{'total_tokens':9}}
    s,w,_,rid=setup(tmp_path,G());await w.work(rid,'plan')
    step=s.one('SELECT * FROM agent_steps')
    assert step['status']=='failed' and step['model']=='custom' and json.loads(step['usage'])['total_tokens']==9
    assert not s.query("SELECT * FROM events WHERE kind='model_result'")
    s.con.close()
