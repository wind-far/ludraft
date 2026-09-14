"""Four creation paths using fixed protocol responses, not model-quality claims."""
import json
import pytest
from studio.models import Plan, Changes
from studio.team import Team
from studio.files import source_files
from studio.parameters import read_config
from studio.workflow import PLANNING_CONTRACT, MATCH3_CONTRACT, CONTRACT
from studio.role_rules import RuleBook
from scripts.evaluate import CASES, configure, template_for
from team_fixture import TeamGateway
from test_team import setup, approve
from test_workbench import ParameterRunner

class ModeGateway(TeamGateway):
    def __init__(self,case):super().__init__();self.case=case
    def effective(self,role):return {'model':'protocol-fixture'}
    async def call(self,role,prompt,schema):
        result,meta=await super().call(role,prompt,schema)
        if schema is Plan:
            result=result.model_copy(update={'mode':self.case['mode'],'summary':self.case['text']})
        if schema is Changes:
            context=json.loads(prompt.split('本步骤上下文：',1)[1].split('\n依赖交付物：',1)[0])
            config=read_config(context['files']['src/config.ts'])
            assert (config['mode']=='match3')==(self.case['mode']=='match3')
            content=context['files']['src/config.ts']
            # Use the same literal update as the authored benchmark cases.
            from studio.models import Parameters, Match3Parameters
            from studio.parameters import update_config
            cls=Match3Parameters if self.case['mode']=='match3' else Parameters
            params=cls(**{k:self.case.get(k,config[k]) for k in cls.model_fields})
            content,_=update_config(content,params)
            content=content.replace('"mode": '+json.dumps(config['mode']),'"mode": '+json.dumps(self.case['mode']))
            result=Changes(summary='固定协议响应，非模型生成',files=[{'path':'src/config.ts','content':content}])
        return result,meta

@pytest.mark.asyncio
@pytest.mark.parametrize('case',CASES[:4],ids=lambda c:c['mode'])
async def test_new_game_selects_template_after_plan(tmp_path,case):
    s,w,pid,rid=setup(tmp_path,ModeGateway(case),ParameterRunner())
    s.execute('UPDATE runs SET requirement=? WHERE id=?',(case['text'],rid))
    context=Team(w).context(s.run(rid))
    assert context['files']=={} and context['files_source']=='not_selected'
    assert w.contract_for(s.run(rid))==PLANNING_CONTRACT
    await approve(w,rid)
    assert s.run(rid)['status']=='succeeded',s.run(rid)
    version=s.one('SELECT * FROM versions')
    assert json.loads(version['evidence'])['config']['mode']==case['mode']
    assert w.contract_for(s.run(rid))==(MATCH3_CONTRACT if case['mode']=='match3' else CONTRACT)
    assert len({r['role'] for r in s.query("SELECT role FROM agent_steps WHERE status='succeeded'")})==8
    s.con.close()

def test_default_rules_support_all_modes_and_keep_match3_skill(tmp_path):
    s,w,_,_=setup(tmp_path);book=RuleBook(s)
    content=book.snapshot('策划','plan')['text']
    assert all(mode in content for mode in ('collector','dodger','clicker','match3'))
    assert book.profile('策划')['skills']==['local/game-design.md']
    assert book.source('local/match3-design.md')['content']
    s.con.close()

def test_new_research_scope_does_not_select_a_game_contract(tmp_path):
    from studio.routing import save
    s,w,_,rid=setup(tmp_path)
    # A report's approval shell is not an approved game design.
    s.execute('UPDATE runs SET plan=? WHERE id=?',(json.dumps({'mode':'match3'}),rid))
    save(s,rid,{'route':{'task_type':'research'}})
    assert w.contract_for(s.run(rid))==PLANNING_CONTRACT
    assert Team(w).context(s.run(rid))['files']=={}
    s.con.close()
