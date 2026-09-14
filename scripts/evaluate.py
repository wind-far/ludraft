"""Five fixed requirements x three runs; never substitutes fixtures for LLM evaluation.
Use --live only with a configured model. Default runs real Docker tests on authored templates.
"""
import argparse
import asyncio
import json
import sys
import time
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from studio.app import DATA
from studio.db import Store, uid, now
from studio.files import TEMPLATE, MATCH3, copy_source, source_files
from studio.llm import Gateway
from studio.models import Plan
from studio.runner import Runner, RunnerError
from studio.workflow import Workflow

MATCH3_CASES = [
 {'id':'classic','title':'宝石花园','mode':'match3','moves':20,'targetScore':1200,'gemTypes':6,'background':'#f0f4fb','text':'做 match3 宝石三消，8×8 棋盘、20 步达成 1200 分、六种宝石，支持无效交换回退、连锁和重开。'},
 {'id':'relaxed','title':'糖果连锁','mode':'match3','moves':30,'targetScore':1000,'gemTypes':4,'background':'#fcf0f3','text':'做 match3 糖果三消，30 步达成 1000 分、四种糖果、粉色背景，连锁加分。'},
 {'id':'five-gems','title':'五色花园','mode':'match3','moves':25,'targetScore':1500,'gemTypes':5,'background':'#edf6f0','text':'做 match3 五色宝石三消，25 步达成 1500 分、五种宝石、浅绿背景，无可用交换时自动重排。'},
 {'id':'challenge','title':'星夜挑战','mode':'match3','moves':15,'targetScore':1800,'gemTypes':6,'background':'#17233d','text':'做 match3 星夜三消，15 步达成 1800 分、六种宝石、深蓝背景，显示剩余步数与目标。'},
 {'id':'short','title':'午后消消乐','mode':'match3','moves':10,'targetScore':500,'gemTypes':4,'background':'#faf3e6','text':'做 match3 三消短局，10 步达成 500 分、四种宝石、奶油背景，支持鼠标点击和触屏滑动交换。'},
]

CASES = [
 MATCH3_CASES[0],
 {'id':'collector','title':'星光收集站','mode':'collector','lives':3,'duration':60,'background':'#10192b','text':'做 collector 接物游戏，左右移动接金币躲炸弹，3 条生命、60 秒一局，金币得分、碰到炸弹扣命，支持结束和重开。'},
 {'id':'dodger','title':'流星闪避','mode':'dodger','lives':3,'duration':60,'background':'#17233d','text':'做 dodger 躲避游戏，左右移动躲避落下的流星，3 条生命、60 秒一局，生存时间计分，深蓝背景，支持结束和重开。'},
 {'id':'clicker','title':'点亮星星','mode':'clicker','lives':3,'duration':30,'background':'#231a32','text':'做 clicker 点击游戏，点击星星得分，误点炸弹扣命，3 条生命、30 秒一局，紫色背景，支持结束和重开。'},
 MATCH3_CASES[1],
]

def template_for(case):return MATCH3 if case['mode']=='match3' else TEMPLATE


def configure(path, case):
    from studio.parameters import read_config, update_config
    from studio.models import Match3Parameters, Parameters
    source=(path/'src/config.ts').read_text();values=read_config(source)
    cls=Match3Parameters if case['mode']=='match3' else Parameters
    parameters=cls(**{key:case.get(key,values[key]) for key in cls.model_fields})
    updated,_=update_config(source,parameters)
    updated=updated.replace(json.dumps(values['title'],ensure_ascii=False),json.dumps(case['title'],ensure_ascii=False))
    updated=updated.replace('"mode": '+json.dumps(values['mode']), '"mode": '+json.dumps(case['mode']))
    (path/'src/config.ts').write_text(updated)

async def evaluate(out, cases, repeats, runner, gateway=None, source_root=DATA, timeout=900):
    """Run in an isolated output folder. Gate fixtures belong only in tests."""
    from studio.evaluation import (configured_roles, copy_rule_configuration, automatic_checks,
        usage_summary, collect_run, archive_game, digest, persist, human_template, write_json)
    from studio.messages import pending
    from studio.routing import options
    live=gateway is not None
    out=Path(out).resolve()
    if out.exists() and any(out.iterdir()):raise ValueError('输出目录非空，请使用新目录以保留原评测证据')
    if live:
        missing=[r['role'] for r in configured_roles(gateway) if not r['configured']]
        if missing:raise ValueError('这些角色未配置可用模型：'+'、'.join(missing)+'；不使用模板代替真实模型评测')
    if not await runner.available():raise ValueError('Runner unavailable: start Docker and run scripts/build-runner.sh. No results fabricated.')
    out.mkdir(parents=True,exist_ok=True)
    store=Store(out/'live-data') if live else None
    workflow=Workflow(store,gateway,runner) if live else None
    report={'evaluation_id':uid(),'mode':'live-model' if live else 'template-regression','created_at':now(),
        'cases':cases,'cases_sha256':digest(cases),'expected':len(cases)*repeats,'records':[]}
    try:
        if live:
            rules=copy_rule_configuration(source_root,store)
            write_json(out/'rule-configuration.json',rules);report['rule_configuration_sha256']=digest(rules)
        persist(out,report)
        for case in cases:
          for repeat in range(repeats):
            started=time.monotonic();rid=uid();pid=None;version=None;root=None;details={};error=None
            if live:
                pid=uid()
                store.execute('INSERT INTO projects VALUES(?,?,?,?)',(pid,case['title'],None,now()))
                store.execute('INSERT INTO runs(id,project_id,status,requirement,created_at) VALUES(?,?,?,?,?)',(rid,pid,'queued',case['text'],now()))
                store.execute('INSERT INTO run_options VALUES(?,?,?)',(rid,'team8',json.dumps({'requested_type':'feature'})))
                async def execute():
                    await workflow.work(rid,'plan')
                    run=store.run(rid)
                    if run['status']=='waiting_confirmation':
                        if not run['plan'] or pending(store,rid):return
                        plan=Plan.model_validate_json(run['plan'])
                        if plan.clarification or plan.mode!=case['mode']:return
                        if options(store,rid).get('route',{}).get('task_type')!='feature':return
                        # Fixed benchmark briefs only; production approvals remain interactive.
                        store.event(rid,'system','benchmark_approval',message='自动确认固定评测需求；不代表人工试玩验收')
                        store.execute("UPDATE runs SET status='queued' WHERE id=?",(rid,))
                        await workflow.work(rid,'implement')
                try:await asyncio.wait_for(execute(),timeout)
                except TimeoutError:error='评测超时，已停止本轮执行'
                run=store.run(rid)
                status=run['status']
                if status not in ('succeeded','failed','cancelled'):
                    error=error or '需要澄清、玩法模式不匹配或没有可确认的生成方案；未自动进入开发'
                    await workflow.cancel(rid)
                    status='needs_input'
                details=collect_run(store,rid)
                evidence=details['attempts'][-1] if details['attempts'] else {}
                version=store.one('SELECT * FROM versions WHERE run_id=?',(rid,))
                if version:root=Path(version['path'])
                record={'engine':'team8','workflow_status':store.run(rid)['status'],'status':status,
                    'repairs':run['repairs'],'error':error or run['error'],**details}
            else:
                root=out/'candidates'/rid
                copy_source(template_for(case),root);configure(root,case)
                try:evidence=await asyncio.wait_for(runner.run(root,rid),timeout)
                except TimeoutError:evidence={'passed':False,'build':False,'error':'评测超时'}
                except RunnerError as exc:evidence={'passed':False,'build':False,'error':str(exc)}
                record={'status':'succeeded' if evidence.get('passed') else 'failed','repairs':0,
                    'error':evidence.get('error'),'attempts':[evidence],'model_calls':[],'agent_steps':[],
                    'source':'authored-template, not LLM generated'}
            checks=automatic_checks(case,evidence,live,record['agent_steps'],version)
            if record['status']=='succeeded' and not checks['passed']:record['status']='failed'
            record.update(run_id=rid,project_id=pid,version_id=version['id'] if version else None,
                case=case['id'],game_mode=case['mode'],repeat=repeat+1,
                elapsed_seconds=round(time.monotonic()-started,2),human_playability=None,
                evidence=evidence,checks=checks,tokens=usage_summary(record['model_calls']),artifact=None)
            if root and record['status']=='succeeded':
                record['artifact']=archive_game(out,rid,root,evidence,{'case':case,'run_id':rid,'mode':report['mode']})
            report['records'].append(record);persist(out,report)
            write_json(out/'human-ratings.json',human_template(report))
            print(f"{case['id']} #{repeat+1}: {record['status']} ({record['elapsed_seconds']}s)",flush=True)
        return report
    finally:
        if workflow:await workflow.close()
        if store:store.con.close()

async def main(args):
    report=await evaluate(args.output,MATCH3_CASES if args.suite=='match3' else CASES,args.repeats,
        Runner(),Gateway(DATA) if args.live else None,timeout=args.timeout)
    if any(r['status']!='succeeded' for r in report['records']):raise SystemExit(1)

if __name__=='__main__':
    parser=argparse.ArgumentParser()
    parser.add_argument('--live',action='store_true')
    parser.add_argument('--suite',choices=['mixed','match3'],default='mixed')
    parser.add_argument('--repeats',type=int,default=3)
    parser.add_argument('--timeout',type=int,default=900,help='每条需求最长秒数，含所有修复')
    parser.add_argument('--output',default='.studio/evaluation')
    args=parser.parse_args()
    if not 1<=args.repeats<=3:parser.error('repeats must be 1..3')
    if args.timeout<1:parser.error('timeout must be positive')
    try:asyncio.run(main(args))
    except ValueError as exc:raise SystemExit(str(exc)) from None
