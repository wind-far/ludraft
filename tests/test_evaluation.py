import copy
import json
import pytest
from scripts.evaluate import CASES, evaluate
from studio.evaluation import automatic_checks, usage_summary, apply_human_reviews, human_template
from studio.test_flow import required_checks
from studio.parameters import read_config
from test_game_modes import ModeGateway
from test_workbench import ParameterRunner

class EvidenceRunner(ParameterRunner):
    async def run(self,path,rid):
        result=await super().run(path,rid)
        result['checks']=[{'name':n,'passed':True} for n in required_checks(result['config']['mode'])]
        return result

@pytest.mark.asyncio
async def test_mixed_template_evidence_and_no_overwrite(tmp_path):
    report=await evaluate(tmp_path/'evaluation',CASES,1,EvidenceRunner())
    assert report['summary']['delivery_passed']==5
    assert {r['game_mode'] for r in report['records']}=={'collector','dodger','clicker','match3'}
    assert all(r['artifact'] and r['tokens']['total_tokens']==0 and r['human_playability'] is None for r in report['records'])
    with pytest.raises(ValueError,match='非空'):await evaluate(tmp_path/'evaluation',CASES,1,EvidenceRunner())
    reviews=human_template(report);review=reviews['reviews'][0]
    review.update(reviewer='测试评分协议',reviewed_at='2026-09-13',playability=3,rule_clarity=4,feedback=3,difficulty=4,notes='仅测试评分导入协议')
    apply_human_reviews(report,reviews)
    assert report['records'][0]['human_playability']['playability']==3
    reviews['reviews'][1]['artifact_sha256']='wrong'
    original=copy.deepcopy(report)
    with pytest.raises(ValueError,match='摘要'):apply_human_reviews(report,reviews)
    assert report==original

@pytest.mark.asyncio
@pytest.mark.parametrize('case',CASES[:4],ids=lambda c:c['mode'])
async def test_eight_roles_are_required_in_model_evaluation_protocol(tmp_path,case):
    report=await evaluate(tmp_path/'eval',[case],1,EvidenceRunner(),ModeGateway(case),source_root=tmp_path/'config')
    record=report['records'][0]
    assert record['status']=='succeeded',record
    assert record['checks']['missing_roles']==[] and record['version_id']
    assert record['rule_snapshots'] and record['attempts']
    assert record['tokens']['total_tokens']>0

@pytest.mark.asyncio
async def test_clarification_never_auto_approved(tmp_path):
    from studio.models import Plan
    class Questions(ModeGateway):
        async def call(self,role,prompt,schema):
            result,meta=await super().call(role,prompt,schema)
            if schema is Plan:result.clarification='需要补充目标用户'
            return result,meta
    report=await evaluate(tmp_path/'eval',[CASES[0]],1,EvidenceRunner(),Questions(CASES[0]),source_root=tmp_path/'config')
    record=report['records'][0]
    assert record['status']=='needs_input' and record['version_id'] is None
    assert not any(s['role']=='程序' for s in record['agent_steps'])

@pytest.mark.asyncio
async def test_wrong_mode_never_auto_approved(tmp_path):
    report=await evaluate(tmp_path/'eval',[CASES[0]],1,EvidenceRunner(),ModeGateway(CASES[1]),source_root=tmp_path/'config')
    assert report['records'][0]['status']=='needs_input'
    assert report['records'][0]['version_id'] is None

@pytest.mark.asyncio
async def test_missing_model_fails_before_creating_results(tmp_path):
    class Missing(ModeGateway):
        def effective(self,role):return {'model':'' if role=='QA' else 'fixture'}
    with pytest.raises(ValueError,match='QA'):await evaluate(tmp_path/'eval',[CASES[0]],1,EvidenceRunner(),Missing(CASES[0]))
    assert not (tmp_path/'eval').exists()

def test_boolean_success_does_not_replace_interaction_and_parameter_evidence():
    case=CASES[1]
    evidence={'build':True,'passed':True,'config':{**case,'lives':5},'checks':[],'exit_code':0}
    checks=automatic_checks(case,evidence)
    assert not checks['passed'] and not checks['interaction_passed'] and not checks['requirement_passed']
    evidence['checks']=[{'name':n,'passed':True} for n in required_checks(case['mode'])]
    evidence['config']['lives']=3
    assert automatic_checks(case,evidence)['passed']
    assert not automatic_checks(case,evidence,live=True)['passed']

def test_unknown_usage_is_not_zero():
    assert usage_summary([{'outcome':'model_result','usage':{}},{'outcome':'model_error','attempted':True}])['total_tokens'] is None
    assert usage_summary([{'outcome':'model_result','usage':{'prompt_tokens':2,'completion_tokens':3}}])['total_tokens']==5
