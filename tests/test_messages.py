"""Protocol fixtures test communication mechanics, never real model quality."""
import asyncio
import io
import json
import time
import zipfile
import pytest
from fastapi.testclient import TestClient
from studio.app import create_app
from studio.db import Store
from studio.messages import add, inbox, pending, history, revision
from studio.models import AgentMessage, Plan, Changes
from studio.team_models import Brief, Design, Delivery
from test_team import setup, approve
from test_studio import FakeRunner, create_run
from team_fixture import TeamGateway


def wait_run(client,pid,predicate):
    for _ in range(200):
        run=client.get('/api/projects/'+pid).json()['runs'][0]
        if predicate(run):return run
        time.sleep(.01)
    raise AssertionError(run)


@pytest.mark.asyncio
async def test_direct_broadcast_receipts_and_export(tmp_path):
    class G(TeamGateway):
        async def call(self,role,prompt,schema):
            result,meta=await super().call(role,prompt,schema)
            if schema is Brief:result.messages=[AgentMessage(recipient='QA',content='仅 QA 检查无效交换'),AgentMessage(recipient='all',content='所有角色关注儿童操作')]
            return result,meta
    s,w,pid,rid=setup(tmp_path,G());await approve(w,rid)
    assert s.run(rid)['status']=='succeeded'
    for role,schema,prompt in w.gateway.trace[1:]:
        # Dependency outputs intentionally omit messages, so recipients stay scoped.
        assert ('仅 QA 检查无效交换' in prompt)==(role=='QA')
        assert '所有角色关注儿童操作' in prompt
    rows=history(s,rid)
    assert {r['role'] for r in rows[0]['receipts']}=={'QA'}
    assert len(rows[1]['receipts'])==12
    first=rows[1]['receipts'][0]['step_id'];inbox(s,rid,'PM',first)
    assert len(history(s,rid)[1]['receipts'])==12
    s.con.close()
    app=create_app(tmp_path,TeamGateway(),FakeRunner())
    with TestClient(app) as c:
        vid=c.get('/api/projects/'+pid).json()['active_version']
        with zipfile.ZipFile(io.BytesIO(c.get('/api/versions/'+vid+'/export').content)) as archive:
            exported=json.loads(archive.read('messages.json'))
            assert len(exported[rid])==2 and exported[rid][0]['receipts']


@pytest.mark.asyncio
@pytest.mark.parametrize('phase',['plan','design','code','delivery'])
async def test_question_pauses_without_publishing_and_preserves_usage(tmp_path,phase):
    class G(TeamGateway):
        async def call(self,role,prompt,schema):
            result,meta=await super().call(role,prompt,schema)
            if (phase=='plan' and schema is Plan) or (phase=='design' and schema is Design and role=='UX') or (phase=='code' and schema is Changes) or (phase=='delivery' and schema is Delivery):
                result.clarification='步数设为 20 还是 30？'
            return result,meta
    s,w,_,rid=setup(tmp_path,G())
    await w.work(rid,'plan')
    if phase!='plan':
        s.execute("UPDATE runs SET status='queued' WHERE id=?",(rid,));await w.work(rid,'implement')
    assert s.run(rid)['status']=='waiting_confirmation' and s.run(rid)['plan'] is None
    assert not s.query('SELECT * FROM versions') and len(pending(s,rid))==1
    step=s.one("SELECT * FROM agent_steps WHERE status='waiting_input'")
    assert step['output'] is None and json.loads(step['usage'])['total_tokens']==12
    assert not s.query("SELECT * FROM agent_steps WHERE status='running'")
    assert not s.query("SELECT * FROM events WHERE kind='model_error'")
    s.recover();assert pending(s,rid) and s.run(rid)['status']=='waiting_confirmation'
    await w.cancel(rid);assert s.run(rid)['status']=='cancelled';s.con.close()


def test_answer_requires_replanning_and_new_approval_even_identical_plan(tmp_path):
    class G(TeamGateway):
        asked=False
        async def call(self,role,prompt,schema):
            result,meta=await super().call(role,prompt,schema)
            if schema is Changes and not self.asked:
                self.asked=True;result.clarification='用户希望多少步？'
            return result,meta
    gateway=G();app=create_app(tmp_path,gateway,FakeRunner())
    with TestClient(app) as c:
        ids=c.post('/api/projects',json={'text':'接金币测试消息机制'}).json();pid,rid=ids['project_id'],ids['run_id']
        old=wait_run(c,pid,lambda r:r['status']=='waiting_confirmation')
        assert c.post('/api/runs/'+rid+'/decision',json={'approve':True,'expected_plan':old['plan']}).status_code==200
        wait_run(c,pid,lambda r:r['status']=='waiting_confirmation' and not r['plan'])
        q=c.get('/api/runs/'+rid+'/messages').json()['pending_questions'][0]
        assert c.post('/api/runs/'+rid+'/decision',json={'approve':True}).status_code==409
        assert c.post('/api/runs/'+rid+'/messages',json={'content':'补充需求'}).status_code==409
        assert c.post('/api/runs/'+rid+'/messages',json={'content':'30 步即可','reply_to':'foreign'}).status_code==409
        assert c.post('/api/runs/'+rid+'/messages',json={'content':'30 步即可','reply_to':q}).status_code==201
        new=wait_run(c,pid,lambda r:r['status']=='waiting_confirmation' and r['plan'])
        assert new['plan']==old['plan'] and new['approval_revision']>old['approval_revision']
        assert c.post('/api/runs/'+rid+'/messages',json={'content':'重复答复','reply_to':q}).status_code==409
        assert c.post('/api/runs/'+rid+'/decision',json={'approve':True,'expected_plan':old['plan'],'expected_revision':old['approval_revision']}).status_code==409
        assert c.post('/api/runs/'+rid+'/decision',json={'approve':True,'expected_plan':new['plan'],'expected_revision':new['approval_revision']}).status_code==200
        done=wait_run(c,pid,lambda r:r['status'] in ('succeeded','failed'))
        assert done['status']=='succeeded',done
        assert any('30 步即可' in prompt for role,schema,prompt in gateway.trace if schema is Brief)
        assert c.post('/api/runs/'+rid+'/messages',json={'content':'已结束不允许再发送'}).status_code==409


@pytest.mark.asyncio
async def test_parallel_question_cancels_and_joins_siblings(tmp_path):
    barrier=asyncio.Event();entered=set();cancelled=set()
    class G(TeamGateway):
        async def call(self,role,prompt,schema):
            if schema is Design:
                entered.add(role)
                if len(entered)==3:barrier.set()
                await barrier.wait()
                if role!='UX':
                    try:await asyncio.Event().wait()
                    finally:cancelled.add(role)
            result,meta=await super().call(role,prompt,schema)
            if schema is Design:result.clarification='面向儿童还是成人？'
            return result,meta
    s,w,_,rid=setup(tmp_path,G());await asyncio.wait_for(approve(w,rid),2)
    assert s.run(rid)['status']=='waiting_confirmation' and cancelled=={'主程','美术'}
    assert not s.query("SELECT * FROM agent_steps WHERE role='程序'")
    s.con.close()


def test_mid_run_feedback_stops_model_and_invalidate_stale_plan_edit(tmp_path):
    class G(TeamGateway):
        async def call(self,role,prompt,schema):
            if schema is Changes:await asyncio.Event().wait()
            return await super().call(role,prompt,schema)
    app=create_app(tmp_path,G(),FakeRunner())
    with TestClient(app) as c:
        ids=c.post('/api/projects',json={'text':'消息中途修改需求'}).json();rid,pid=ids['run_id'],ids['project_id']
        old=wait_run(c,pid,lambda r:bool(r['plan']))
        c.post('/api/runs/'+rid+'/decision',json={'approve':True})
        for _ in range(200):
            steps=c.get('/api/runs/'+rid+'/team').json()['steps']
            if any(s['task_key']=='code' and s['status']=='running' for s in steps):break
            time.sleep(.01)
        else:raise AssertionError('programmer did not start')
        assert c.post('/api/runs/'+rid+'/messages',json={'content':'三消主题改为海洋风格'}).status_code==201
        new=wait_run(c,pid,lambda r:r['status']=='waiting_confirmation' and bool(r['plan']))
        assert c.put('/api/runs/'+rid+'/plan',json={'plan':json.loads(old['plan']),'expected_plan':old['plan'],'expected_revision':0}).status_code==409
        assert c.put('/api/runs/'+rid+'/plan',json={'plan':json.loads(new['plan']),'expected_plan':new['plan'],'expected_revision':new['approval_revision']}).status_code==200
        assert not app.state.store.query('SELECT * FROM versions')
        assert app.state.store.one("SELECT status FROM agent_steps WHERE task_key='code'")['status']=='cancelled'
        assert c.post('/api/runs/'+rid+'/cancel').json()['status']=='cancelled'


def test_message_scope_dedup_and_pending_survive_reopen(tmp_path):
    s=Store(tmp_path);_,rid=create_run(s);_,other=create_run(s)
    mid=add(s,rid,'QA','all','note','广播消息',source_step='one',slot=0)
    assert mid==add(s,rid,'QA','all','note','广播消息',source_step='one',slot=0)
    assert inbox(s,other,'程序','other')==[]
    q=add(s,rid,'主程','user','question','确认目标')
    s.execute("UPDATE runs SET status='waiting_confirmation' WHERE id=?",(rid,));s.con.close()
    s=Store(tmp_path);s.recover();assert pending(s,rid)[0]['id']==q
    assert len(s.query('SELECT * FROM messages'))==2;s.con.close()

@pytest.mark.asyncio
async def test_inbox_is_read_after_model_semaphore_wait(tmp_path):
    from studio.team import Team
    s,w,_,rid=setup(tmp_path);w.model_limit=asyncio.Semaphore(0)
    task=asyncio.create_task(Team(w).step(s.run(rid),'brief','制作人',Brief,{}))
    await asyncio.sleep(0)
    mid=add(s,rid,'QA','制作人','note','排队期间新消息')
    w.model_limit.release();await task
    assert '排队期间新消息' in w.gateway.trace[0][2]
    assert len(history(s,rid)[0]['receipts'])==1
    s.con.close()


def test_all_questions_answered_before_resume_and_replies_include_original(tmp_path):
    class G(TeamGateway):
        async def call(self,role,prompt,schema):
            result,meta=await super().call(role,prompt,schema)
            if schema is Brief:
                assert '题目甲的条件' in prompt and '题目乙的条件' in prompt
            return result,meta
    app=create_app(tmp_path,G(),FakeRunner())
    with TestClient(app) as c:
        s=app.state.store;pid,rid=create_run(s)
        s.execute('INSERT INTO run_options VALUES(?,?,?)',(rid,'team8','{}'))
        s.execute("UPDATE runs SET status='waiting_confirmation' WHERE id=?",(rid,))
        a=add(s,rid,'策划','user','question','题目甲的条件');b=add(s,rid,'UX','user','question','题目乙的条件')
        assert c.post('/api/runs/'+rid+'/messages',json={'content':'确认甲','reply_to':a}).json()['status']=='waiting_confirmation'
        assert not s.query('SELECT * FROM agent_steps')
        assert c.post('/api/runs/'+rid+'/messages',json={'content':'确认乙','reply_to':b}).status_code==201
        r=wait_run(c,pid,lambda r:r['status']!='queued' and r['status']!='running')
        assert r['status']=='waiting_confirmation' and r['plan'],r


def test_answer_remains_possible_at_message_limit(tmp_path):
    s=Store(tmp_path);_,rid=create_run(s)
    for i in range(99):add(s,rid,'QA','all','note',str(i))
    q=add(s,rid,'策划','user','question','最后一个问题')
    with pytest.raises(ValueError):add(s,rid,'QA','all','note','超额')
    add(s,rid,'user','all','answer','仍可答复',reply_to=q)
    assert not pending(s,rid);s.con.close()


def test_feedback_during_testing_cancels_runner_before_replanning(tmp_path):
    class R(FakeRunner):
        cancelled=False
        async def run(self,workspace,rid):
            try:await asyncio.Event().wait()
            finally:self.cancelled=True
    runner=R();app=create_app(tmp_path,TeamGateway(),runner)
    with TestClient(app) as c:
        ids=c.post('/api/projects',json={'text':'验证工具中途补充消息'}).json();pid,rid=ids['project_id'],ids['run_id']
        wait_run(c,pid,lambda r:r['status']=='waiting_confirmation')
        c.post('/api/runs/'+rid+'/decision',json={'approve':True})
        wait_run(c,pid,lambda r:r['status']=='testing')
        assert c.post('/api/runs/'+rid+'/messages',json={'content':'目标改为轻松三消'}).status_code==201
        r=wait_run(c,pid,lambda r:r['status']=='waiting_confirmation')
        assert r['plan'] and runner.cancelled
        assert not app.state.store.query('SELECT * FROM versions')
