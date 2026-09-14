"""Behavior regressions; fixture tests do not claim model or gameplay quality."""
import asyncio
import json
import time
from pathlib import Path
import pytest
from fastapi.testclient import TestClient
from studio.app import create_app
from studio.db import uid, now
from studio.files import TEMPLATE, copy_source
from studio.models import Parameters, Plan
from studio.parameters import read_config, update_config
from test_studio import FakeGateway, FakeRunner, PLAN, create_run


def seed(store):
    pid,rid=create_run(store)
    vid=uid();dest=store.root/'versions'/vid;copy_source(TEMPLATE,dest)
    (dest/'dist').mkdir();(dest/'dist/main.js').write_text('// test double')
    config=read_config((dest/'src/config.ts').read_text())
    evidence={'passed':True,'build':True,'checks':[{'name':'TypeScript 构建','passed':True}],'config':config,'source':'test-double'}
    store.execute("UPDATE runs SET status='succeeded',plan=? WHERE id=?",(PLAN.model_dump_json(),rid))
    store.execute('INSERT INTO versions VALUES(?,?,?,?,?,?,?,?)',(vid,pid,rid,PLAN.title,str(dest),json.dumps(evidence),'',now()))
    store.execute('UPDATE projects SET active_version=? WHERE id=?',(vid,pid))
    for f in dest.rglob('*'):
        if f.is_file():f.chmod(0o444)
    params={k:config[k] for k in Parameters.model_fields}
    return pid,rid,vid,params


class ParameterRunner(FakeRunner):
    async def run(self,path,rid):
        result=await super().run(path,rid)
        result['config']=read_config((path/'src/config.ts').read_text())
        return result


def wait(client,rid):
    for _ in range(200):
        r=client.app.state.store.run(rid)
        if r['status'] in ('succeeded','failed','cancelled'):return r
        time.sleep(.01)
    raise AssertionError('Task did not finish')


def test_project_organization_copy_and_restore(tmp_path):
    app=create_app(tmp_path,FakeGateway(),ParameterRunner())
    with TestClient(app) as c:
        pid,rid,vid,_=seed(app.state.store)
        assert c.put(f'/api/projects/{pid}',json={'title':'新名称'}).status_code==200
        assert c.post(f'/api/projects/{pid}/open').status_code==200
        row=c.get('/api/projects').json()[0]
        assert row['title']=='新名称' and row['last_opened']
        result=c.post(f'/api/projects/{pid}/duplicate').json()
        copied=c.get('/api/projects/'+result['project_id']).json()
        assert copied['title']=='新名称 · 副本' and copied['active_version']!=vid
        assert c.get('/api/versions/'+copied['active_version']).json()['files']==c.get('/api/versions/'+vid).json()['files']
        for state in ('archived','trash'):
            assert c.put(f'/api/projects/{pid}',json={'state':state}).json()['state']==state
            assert c.post(f'/api/projects/{pid}/runs',json={'text':'修改配色'}).status_code==409
            assert c.post(f'/api/projects/{pid}/rollback',json={'version_id':vid}).status_code==409
        assert c.post(f'/api/projects/{pid}/duplicate').status_code==409
        assert c.put(f'/api/projects/{pid}',json={'state':'active'}).json()['active_version']==vid
        assert c.put(f'/api/projects/{pid}',json={'title':'   '}).status_code==422


def test_edit_plan_still_needs_confirmation_and_stale_edit_rejected(tmp_path):
    g=FakeGateway();app=create_app(tmp_path,g,ParameterRunner())
    with TestClient(app) as c:
        pid,rid=create_run(app.state.store)
        app.state.store.execute("UPDATE runs SET status='waiting_confirmation',plan=? WHERE id=?",(PLAN.model_dump_json(),rid))
        changed=PLAN.model_copy(update={'title':'编辑过的玩法','controls':'使用 A D 移动'})
        result=c.put(f'/api/runs/{rid}/plan',json={'plan':changed.model_dump(),'expected_plan':PLAN.model_dump_json()})
        assert result.status_code==200 and result.json()['status']=='waiting_confirmation' and g.calls==0
        assert c.put(f'/api/runs/{rid}/plan',json={'plan':PLAN.model_dump(),'expected_plan':PLAN.model_dump_json()}).status_code==409
        assert c.post(f'/api/runs/{rid}/decision',json={'approve':True,'expected_plan':PLAN.model_dump_json()}).status_code==409
        assert c.put(f'/api/projects/{pid}',json={'state':'archived'}).status_code==409
        assert c.post(f'/api/runs/{rid}/decision',json={'approve':False}).status_code==200
        assert c.put(f'/api/runs/{rid}/plan',json={'plan':changed.model_dump(),'expected_plan':changed.model_dump_json()}).status_code==409


@pytest.mark.parametrize('passed',[True,False])
def test_parameters_version_gate_and_no_model(tmp_path,passed):
    g=FakeGateway();app=create_app(tmp_path,g,ParameterRunner(passed))
    with TestClient(app) as c:
        pid,_,vid,params=seed(app.state.store)
        before=c.get('/api/versions/'+vid).json()['files']
        params.update(speed=180,lives=5,background='#123456')
        response=c.post(f'/api/projects/{pid}/parameters',json={'base_version':vid,'parameters':params})
        assert response.status_code==201,response.text
        result=wait(c,response.json()['run_id'])
        assert result['status']==('succeeded' if passed else 'failed') and g.calls==0
        p=c.get(f'/api/projects/{pid}').json()
        assert (p['active_version']!=vid)==passed
        assert c.get('/api/versions/'+vid).json()['files']==before
        if passed:
            version=c.get('/api/versions/'+p['active_version']).json()
            assert version['parameters']['lives']==5 and version['evidence']['parameter_match']
            assert c.post(f'/api/projects/{pid}/parameters',json={'base_version':vid,'parameters':params}).status_code==409


def test_parameters_invalid_unchanged_archived(tmp_path):
    app=create_app(tmp_path,FakeGateway(),ParameterRunner())
    with TestClient(app) as c:
        pid,_,vid,params=seed(app.state.store)
        body={'base_version':vid,'parameters':params}
        assert c.post(f'/api/projects/{pid}/parameters',json=body).status_code==422
        for key,value in [('lives',1.5),('speed',2000),('background','url(secret)'),('duration',0)]:
            assert c.post(f'/api/projects/{pid}/parameters',json={**body,'parameters':{**params,key:value}}).status_code==422
        assert len(app.state.store.query('SELECT * FROM runs'))==1
        c.put(f'/api/projects/{pid}',json={'state':'archived'})
        assert c.post(f'/api/projects/{pid}/parameters',json={**body,'parameters':{**params,'lives':5}}).status_code==409


@pytest.mark.parametrize('source',[
    'export const config = getConfig();',
    'export const config = { ...defaults, lives: 5 };',
    (TEMPLATE/'src/config.ts').read_text().replace('speed: 320','speed: 160*2'),
    (TEMPLATE/'src/config.ts').read_text()+'export const secret = 1;',
    (TEMPLATE/'src/config.ts').read_text().replace('speed: 320','speed: 320, speed: 250'),
])
def test_dynamic_config_is_never_executed_or_rewritten(source):
    with pytest.raises(ValueError): read_config(source)


@pytest.mark.asyncio
async def test_cancel_parameter_validation_keeps_previous(tmp_path):
    from studio.db import Store
    from studio.workflow import Workflow
    started=asyncio.Event()
    class Slow(ParameterRunner):
        async def run(self,path,rid):
            started.set();await asyncio.Event().wait()
    store=Store(tmp_path);pid,_,vid,params=seed(store);rid=uid();params['lives']=5
    store.execute('INSERT INTO runs(id,project_id,status,base_version,plan,requirement,created_at) VALUES(?,?,?,?,?,?,?)',(rid,pid,'queued',vid,PLAN.model_dump_json(),'参数调整',now()))
    store.execute('INSERT INTO run_options VALUES(?,?,?)',(rid,'parameters',json.dumps(params)))
    w=Workflow(store,FakeGateway(),Slow());w.launch(rid,'parameters');await asyncio.wait_for(started.wait(),2);await w.cancel(rid)
    assert store.run(rid)['status']=='cancelled'
    assert store.one('SELECT * FROM projects WHERE id=?',(pid,))['active_version']==vid
    store.con.close()
