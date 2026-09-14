"""Publish four genre examples ONLY after real container verification, explicitly labeled."""
import asyncio
import json
import sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from scripts.evaluate import CASES, configure, template_for
from studio.app import DATA
from studio.db import Store, uid, now
from studio.files import TEMPLATE, MATCH3, copy_source, source_files
from studio.llm import Gateway
from studio.runner import Runner
from studio.workflow import Workflow

async def main():
    store=Store(DATA);runner=Runner();workflow=Workflow(store,Gateway(DATA),runner)
    if not await runner.available():raise SystemExit('Runner unavailable; no unverified examples published')
    for case in CASES[:4]:
        title='示例 · '+case['title']
        if store.one('SELECT id FROM projects WHERE title=? AND active_version IS NOT NULL',(title,)):continue
        pid,rid=uid(),uid();workspace=DATA/'candidates'/rid
        source=template_for(case)
        copy_source(source,workspace);configure(workspace,case)
        controls={'match3':'点击或滑动交换相邻宝石；方向键与空格也可操作','collector':'左右方向键或 A/D 移动接物','dodger':'左右方向键或 A/D 移动躲避','clicker':'点击星星得分，避开危险物'}
        acceptance=['有效交换消除，无效交换回退','连锁加分且每次有效交换只扣一步','目标达成或步数耗尽后结束，可重新开始'] if case['mode']=='match3' else ['开始后可按对应操作交互','得分与扣命反馈正确','生命耗尽或时间结束后停止，可重新开始']
        plan={'title':title,'summary':case['text'],'mode':case['mode'],'controls':controls[case['mode']],'acceptance':acceptance}
        store.execute('INSERT INTO projects VALUES(?,?,?,?)',(pid,title,None,now()))
        store.execute('INSERT INTO runs(id,project_id,status,requirement,plan,created_at) VALUES(?,?,?,?,?,?)',(rid,pid,'testing','人工编写的模板示例；未调用 LLM。'+case['text'],json.dumps(plan,ensure_ascii=False),now()))
        store.event(rid,'system','example',message='此案例为人工编写模板，经真实容器测试；不代表模型生成结果。')
        try:
            evidence=await runner.run(workspace,rid)
            store.event(rid,'QA','test_result',**evidence)
            from studio.evaluation import automatic_checks
            checks=automatic_checks(case,evidence)
            if not checks['passed']:
                evidence['passed']=False; evidence['error']='；'.join(checks['errors'])
            if not evidence['passed']:raise RuntimeError(evidence.get('error','容器验证失败'))
            workflow.publish(store.run(rid),workspace,source_files(source),evidence)
            print(title+' verified',flush=True)
        except Exception as exc:
            store.execute("UPDATE runs SET status='failed',error=?,finished_at=? WHERE id=?",(str(exc),now(),rid));raise
    store.con.close()

if __name__=='__main__':asyncio.run(main())
