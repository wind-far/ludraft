import asyncio
import json
import pytest
from studio.team_models import CodingPlan
from studio.models import Changes
from studio.files import TEMPLATE
from studio.lineage import resolve
from test_team import setup,approve
from team_fixture import TeamGateway


def task(id,files,deps=()):
    return {'id':id,'goal':'实现 '+id,'files':files,'depends_on':list(deps),'acceptance':['结果符合确认需求']}

TASKS=[task('configuration',['src/config.ts']),task('appearance',['style.css']),task('logic',['src/game.ts'],['configuration']),task('tuning',['src/config.ts'],['logic'])]

class SplitGateway(TeamGateway):
    def __init__(self):super().__init__();self.started=set();self.parallel=asyncio.Event()
    async def call(self,role,prompt,schema):
        if schema is CodingPlan:
            return CodingPlan(summary='主程动态分工',tasks=TASKS),{'model':'split-fixture','usage':{'total_tokens':3}}
        if schema is Changes:
            context=json.loads(prompt.split('本步骤上下文：',1)[1].split('\n依赖交付物：',1)[0])
            assignment=context['coding_task'];key=assignment['id'];self.started.add(key)
            if key in ('configuration','appearance'):
                if {'configuration','appearance'}<=self.started:self.parallel.set()
                await asyncio.wait_for(self.parallel.wait(),2)
            if key=='logic':
                assert 'subtask-config' in context['files']['src/config.ts']
                assert set(context['completed_dependencies'])=={'configuration'}
            if key=='tuning':assert 'subtask-logic' in context['files']['src/game.ts']
            files=[{'path':path,'content':context['files'][path]+'\n// subtask-'+('config' if key=='configuration' else key)+'\n'} for path in assignment['files']]
            return Changes(summary='完成 '+key,files=files),{'model':'split-fixture','usage':{'total_tokens':5}}
        return await super().call(role,prompt,schema)


@pytest.mark.asyncio
async def test_dynamic_parallel_dependency_merge_and_provenance(tmp_path):
    s,w,_,rid=setup(tmp_path,SplitGateway());await approve(w,rid)
    assert s.run(rid)['status']=='succeeded',s.run(rid)
    v=s.one('SELECT * FROM versions');steps=s.query('SELECT * FROM agent_steps WHERE run_id=?',(rid,))
    subtasks=[x for x in steps if x['task_key'].startswith('code:')]
    assert len(subtasks)==4 and all(x['status']=='succeeded' for x in subtasks)
    aggregate=next(x for x in steps if x['task_key']=='code')
    assert aggregate['status']=='assembled' and aggregate['model'] is None and aggregate['usage'] is None
    assert {x['id'] for x in subtasks}<=set(json.loads(aggregate['inputs']))
    assert len(json.loads(aggregate['output'])['files'])==3
    lineage=resolve(s,v['id']);ids={x['id'] for x in lineage['steps']}
    assert all(set(x['inputs'] or [])<=ids for x in lineage['steps'])
    from pathlib import Path
    config=(Path(v['path'])/'src/config.ts').read_text()
    assert 'subtask-config' in config and 'subtask-tuning' in config
    assert not s.query("SELECT * FROM events WHERE kind='model_result' AND json_extract(payload,'$.step_id')=?",(aggregate['id'],))
    s.con.close()


@pytest.mark.parametrize('tasks',[
    [task('a',['src/config.ts']),task('a',['style.css'])],
    [task('a',['src/config.ts'],['missing'])],
    [task('a',['src/config.ts'],['b']),task('b',['style.css'],['a'])],
    [task('a',['src/config.ts']),task('b',['src/config.ts'])],
    [task('a',['src/config.ts','src/config.ts'])],
    [task('a',['../outside'])],
])
def test_invalid_graph_or_ownership_is_rejected(tasks):
    with pytest.raises(ValueError):CodingPlan(summary='无效任务图',tasks=tasks)


@pytest.mark.asyncio
async def test_unassigned_write_cancels_batch_without_applying_any_files(tmp_path):
    class G(SplitGateway):
        async def call(self,role,prompt,schema):
            if schema is Changes and '"id": "appearance"' in prompt:
                return Changes(summary='越界子任务',files=[{'path':'src/config.ts','content':'bad'}]),{'model':'fixture','usage':{}}
            return await super().call(role,prompt,schema)
    s,w,_,rid=setup(tmp_path,G());await approve(w,rid)
    assert s.run(rid)['status']=='failed' and w.runner.calls==0
    assert not s.query('SELECT * FROM versions')
    assert (tmp_path/'candidates'/rid/'src/config.ts').read_text()==(TEMPLATE/'src/config.ts').read_text()
    assert not s.query("SELECT * FROM agent_steps WHERE status='running'")
    failed=s.one("SELECT * FROM agent_steps WHERE task_key='code:appearance'")
    assert failed['status']=='failed' and failed['output'] is None
    s.con.close()


@pytest.mark.asyncio
async def test_cancel_stops_all_parallel_coding_children(tmp_path):
    entered=asyncio.Event()
    class G(SplitGateway):
        async def call(self,role,prompt,schema):
            if schema is Changes:entered.set();await asyncio.Event().wait()
            return await super().call(role,prompt,schema)
    s,w,_,rid=setup(tmp_path,G());await w.work(rid,'plan')
    s.execute("UPDATE runs SET status='queued' WHERE id=?",(rid,));w.launch(rid,'implement')
    await asyncio.wait_for(entered.wait(),3);await w.cancel(rid)
    assert s.run(rid)['status']=='cancelled' and not s.query("SELECT * FROM agent_steps WHERE status='running'")
    assert not s.query('SELECT * FROM versions') and w.runner.calls==0
    s.con.close()
