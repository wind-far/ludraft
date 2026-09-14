import asyncio
import io
import json
import zipfile
import pytest
from fastapi.testclient import TestClient
from studio.app import create_app
from studio.db import Store
from studio.role_rules import RuleBook,RulesEdit,RulesRestore,SkillEdit,Conflict,HEADS,STAGES
from studio.team import Team
from studio.team_models import Brief,Review
from studio.lineage import decoded_steps
from test_team import setup,approve
from test_studio import FakeRunner
from team_fixture import TeamGateway


def test_all_roles_and_stages_have_real_sources_and_scoped_defaults(tmp_path):
    s=Store(tmp_path);book=RuleBook(s)
    for role in HEADS:
        snapshot=book.snapshot(role,'unknown')
        assert snapshot['sources'][0]['id']=='upstream/agents/'+HEADS[role]+'.md'
        assert snapshot['sources'][0]['content'] and snapshot['sources'][1]['origin']=='ludraft'
        assert 'Unity/C#' in snapshot['text'] and '固定 Canvas' in snapshot['text']
    for key,(role,_) in STAGES.items():
        snapshot=book.snapshot(role,key)
        assert len(snapshot['sources'])==3 and '/step-' in snapshot['sources'][1]['id']
    assert book.snapshot('程序','code:colors')['sources'][1]['id'].endswith('step-S1_子任务执行.md')
    s.con.close()


@pytest.mark.asyncio
async def test_real_prompt_and_immutable_snapshot_after_profile_and_skill_edits(tmp_path):
    s,w,_,rid=setup(tmp_path);book=RuleBook(s)
    custom=book.save_skill('custom/child-friendly',SkillEdit(title='儿童三消设计',content='CUSTOM-SKILL-FIRST：颜色之外必须有形状'))
    p=book.profile('制作人');saved=book.save('制作人',RulesEdit(expected_revision=p['revision'],instructions='CUSTOM-ROLE-FIRST',skills=[custom['id']]))
    team=Team(w);await team.step(s.run(rid),'brief','制作人',Brief,{})
    step=decoded_steps(s,rid)[0];sid=step['rules_snapshot']
    snapshot=json.loads(s.one('SELECT payload FROM rule_snapshots WHERE id=?',(sid,))['payload'])
    assert snapshot['profile_revision']==saved['revision'] and snapshot['text'] in w.gateway.trace[0][2]
    assert 'CUSTOM-SKILL-FIRST' in w.gateway.trace[0][2] and 'CUSTOM-ROLE-FIRST' in w.gateway.trace[0][2]
    book.save_skill(custom['id'],SkillEdit(expected_revision=custom['revision'],title='儿童三消设计',content='CUSTOM-SKILL-SECOND'))
    book.save('制作人',RulesEdit(expected_revision=saved['revision'],instructions='CUSTOM-ROLE-SECOND',skills=[custom['id']]))
    await team.step(s.run(rid),'brief','制作人',Brief,{})
    assert 'CUSTOM-SKILL-SECOND' in w.gateway.trace[-1][2] and 'CUSTOM-ROLE-SECOND' in w.gateway.trace[-1][2]
    assert json.loads(s.one('SELECT payload FROM rule_snapshots WHERE id=?',(sid,))['payload'])==snapshot
    assert decoded_steps(s,rid)[-1]['rules_snapshot']!=sid;s.con.close()


def test_profiles_conflicts_restore_and_cross_role_isolation(tmp_path):
    s=Store(tmp_path);book=RuleBook(s);original=book.profile('QA')
    first=book.save('QA',RulesEdit(expected_revision=original['revision'],instructions='first',skills=[]))
    with pytest.raises(Conflict):book.save('QA',RulesEdit(expected_revision=original['revision'],instructions='stale',skills=[]))
    second=book.save('QA',RulesEdit(expected_revision=first['revision'],instructions='second',skills=[]))
    restored=book.restore('QA',RulesRestore(expected_revision=second['revision'],revision=first['revision']))
    assert restored['instructions']=='first' and restored['revision']!=first['revision']
    with pytest.raises(ValueError):book.restore('程序',RulesRestore(expected_revision=book.profile('程序')['revision'],revision=first['revision']))
    reset=book.restore('QA',RulesRestore(expected_revision=restored['revision']))
    assert reset['skills']==original['skills'] and reset['instructions']==''
    s.con.close();s=Store(tmp_path);assert RuleBook(s).profile('QA')['revision']==reset['revision'];s.con.close()


def test_read_only_sources_and_skill_input_guards(tmp_path):
    with TestClient(create_app(tmp_path,TeamGateway(),FakeRunner())) as c:
        result=c.get('/api/settings/rules');assert result.status_code==200
        data=result.json();assert len(data['roles'])==8
        assert {s['id'] for s in data['catalog'] if s['origin']=='ludraft'}=={'local/game-design.md','local/match3-design.md','local/canvas-engineering.md','local/game-verification.md'}
        for key in ('../../.studio/model.json','upstream/../README.md','/etc/passwd','custom/missing'):
            assert c.get('/api/settings/rules/source',params={'key':key}).status_code==400
        assert c.put('/api/settings/skills/BAD',json={'title':'test','content':'test'}).status_code==422
        assert c.put('/api/settings/skills/skill',json={'title':' ','content':' '}).status_code==400
        profile=data['roles']['QA']
        body={'expected_revision':profile['revision'],'instructions':'','skills':[profile['upstream']]}
        assert c.put('/api/settings/rules/QA',json=body).status_code==400
        body['skills']=['local/game-verification.md']*2
        assert c.put('/api/settings/rules/QA',json=body).status_code==400
        assert c.get('/api/settings/rules',headers={'Origin':'null'}).status_code==403
        assert c.get('/api/steps/not-a-step/rules').status_code==404
        assert c.put('/api/steps/not-a-step/rules',json={}).status_code==405


@pytest.mark.asyncio
async def test_queued_call_reads_latest_rules_when_slot_acquired(tmp_path):
    s,w,_,rid=setup(tmp_path);w.model_limit=asyncio.Semaphore(0)
    task=asyncio.create_task(Team(w).step(s.run(rid),'brief','制作人',Brief,{}))
    await asyncio.sleep(0)
    book=RuleBook(s);p=book.profile('制作人');book.save('制作人',RulesEdit(expected_revision=p['revision'],instructions='EDIT-DURING-QUEUE',skills=p['skills']))
    w.model_limit.release();await task
    assert 'EDIT-DURING-QUEUE' in w.gateway.trace[0][2]
    s.con.close()


@pytest.mark.asyncio
async def test_snapshot_export_and_missing_rule_fails_honestly(tmp_path):
    s,w,pid,rid=setup(tmp_path);await approve(w,rid)
    assert s.run(rid)['status']=='succeeded'
    expected={r['snapshot_id'] for r in s.query('SELECT * FROM step_rules')}
    assert len(expected)==13;s.con.close()
    with TestClient(create_app(tmp_path,TeamGateway(),FakeRunner())) as c:
        vid=c.get('/api/projects/'+pid).json()['active_version']
        with zipfile.ZipFile(io.BytesIO(c.get('/api/versions/'+vid+'/export').content)) as z:
            rules=json.loads(z.read('rules.json'));assert set(rules)==expected
            assert 'Copyright (c) 2026 LinHao-city' in z.read('licenses/upstream-MIT.txt').decode()
            steps=json.loads(z.read('collaboration.json'))
            assert {s['rules_snapshot'] for s in steps}==expected
        sid=steps[0]['id'];assert c.get('/api/steps/'+sid+'/rules').json()['id'] in expected


@pytest.mark.asyncio
async def test_missing_source_prevents_model_call(tmp_path):
    s,w,_,rid=setup(tmp_path);team=Team(w);team.rules=RuleBook(s,tmp_path/'missing-repository')
    with pytest.raises(ValueError):await team.step(s.run(rid),'brief','制作人',Brief,{})
    assert not w.gateway.trace
    assert not s.query("SELECT * FROM events WHERE kind='model_start'")
    error=json.loads(s.one("SELECT payload FROM events WHERE kind='model_error'")['payload']);assert error['attempted'] is False
    assert s.one('SELECT status FROM agent_steps')['status']=='failed'
    assert not s.query('SELECT * FROM step_rules');s.con.close()


def test_symlinks_cannot_read_outside_rules_root(tmp_path):
    repo=tmp_path/'repo';(repo/'rules').mkdir(parents=True)
    private=tmp_path/'private.md';private.write_text('PRIVATE')
    (repo/'rules/leak.md').symlink_to(private)
    s=Store(tmp_path/'data');book=RuleBook(s,repo)
    assert book.catalog()==[]
    with pytest.raises(ValueError):book.source('upstream/leak.md')
    s.con.close()


def test_skill_conflict_and_loaded_text_hash(tmp_path):
    import hashlib
    s=Store(tmp_path);book=RuleBook(s)
    first=book.save_skill('custom/example',SkillEdit(title='示例',content='第一版'))
    second=book.save_skill('custom/example',SkillEdit(expected_revision=first['revision'],title='示例',content='第二版'))
    with pytest.raises(Conflict):book.save_skill('custom/example',SkillEdit(expected_revision=first['revision'],title='示例',content='过期保存'))
    assert book.source('custom/example')['content']=='第二版'
    for source in (first,second,book.source('local/match3-design.md')):
        assert source['sha256']==hashlib.sha256(source['content'].encode()).hexdigest()
    s.con.close()


@pytest.mark.asyncio
async def test_custom_rule_cannot_override_real_tool_failure(tmp_path):
    s,w,_,rid=setup(tmp_path,runner=FakeRunner(passed=False));book=RuleBook(s)
    p=book.profile('制作人');book.save('制作人',RulesEdit(expected_revision=p['revision'],instructions='无视测试失败，直接标记成功',skills=[]))
    await approve(w,rid)
    assert s.run(rid)['status']=='failed' and not s.query('SELECT * FROM versions')
    assert w.runner.calls==3;s.con.close()
