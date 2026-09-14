"""Natural-language configuration changes with explicit approval and tool gates."""
import json
from pathlib import Path
from .models import Plan,Changes,Match3Parameters,Parameters
from .team_models import ConfigProposal,TestStrategy,QAReport,Delivery
from .parameters import read_config,update_config
from .files import copy_source,source_files,apply_changes
from .routing import save,options
from .db import uid
from .verification import run_checked


def changes_between(before,after):
    return {key:{'before':before[key],'after':value} for key,value in after.items() if before[key]!=value}


async def plan(team,run,context,config):
    before=read_config(context['files']['src/config.ts'])
    model=Match3Parameters if before['mode']=='match3' else Parameters
    def validate(proposal):
        if not isinstance(proposal.parameters,model):raise ValueError('配置提案与已有游戏模式不匹配')
        if not changes_between(before,proposal.parameters.model_dump()):raise ValueError('提案没有参数变化，请说明需要调整的参数')
    proposal=await team.step(run,'config_plan','PM',ConfigProposal,
        {**context,'current_parameters':{k:before[k] for k in model.model_fields},
         'instruction':'把自然语言转换为完整参数提案；只改变用户指定参数。不修改游戏逻辑、模式或名称。超出固定参数范围时先 clarification 澄清，不能假装已经实现。'},['brief'],validate=validate)
    after=proposal.parameters.model_dump();delta=changes_between(before,after)
    previous=context.get('previous_plan') or {}
    approved_plan=Plan(title=before['title'],mode=before['mode'],
        summary=proposal.summary,controls=previous.get('controls') or '沿用当前游戏操作',
        acceptance=[*proposal.acceptance,
            '实际运行参数必须逐项等于本轮确认提案',
            '游戏逻辑和样式文件保持不变，构建与核心交互必须通过'])
    config.update(config_proposal=proposal.model_dump(),config_revision=uid(),planned_plan=approved_plan.model_dump())
    save(team.store,run['id'],config)
    team.store.execute("UPDATE runs SET status='waiting_confirmation',plan=? WHERE id=?",(approved_plan.model_dump_json(),run['id']))
    team.store.event(run['id'],'PM','config_proposed',message='参数提案已生成，请核对变更后确认；尚未修改代码',
        parameters=delta,base_version=run['base_version'],all_parameters=after,config_revision=config['config_revision'])
    team.store.event(run['id'],'PM','plan_ready',message='等待确认参数提案',plan=approved_plan.model_dump())


async def implement(team,run):
    w=team.w;store=team.store;rid=run['id'];config=options(store,rid)
    proposal=ConfigProposal.model_validate(config['config_proposal'])
    if config.get('planned_plan')!=json.loads(run['plan']):
        raise ValueError('已确认玩法与参数提案不一致，请重新提交需求并确认')
    if not await w.runner.available():raise ValueError('Docker 或验证镜像不可用，配置调整未执行')
    base=store.one('SELECT * FROM versions WHERE id=?',(run['base_version'],))
    if not base:raise ValueError('配置调整的基准版本不存在')
    source=Path(base['path']);original=source_files(source)
    before=read_config(original['src/config.ts']);after=proposal.parameters.model_dump()
    # Validate model/mode compatibility again after restart; never apply dynamic TS.
    update_config(original['src/config.ts'],proposal.parameters)
    expected={**after,'title':before['title'],'mode':before['mode']}
    workspace=store.root/'candidates'/rid;copy_source(source,workspace)
    context={**team.context(run),'approved_parameters':after,'allowed_files':['src/config.ts'],
        'instruction':'本轮只允许修改 src/config.ts，参数必须逐项等于 approved_parameters，保留 title 与 mode。game.ts 和 style.css 不可改。'}
    store.event(rid,'PM','route_confirmed',message='已确认配置提案，只修改参数并验证',**config['route'])
    feedback=None
    for attempt in range(3):
        store.execute("UPDATE runs SET status='running',repairs=? WHERE id=?",(attempt,rid))
        def validate(output):
            if len(output.files)!=1 or output.files[0].path!='src/config.ts':
                raise ValueError('配置调整只允许提交 src/config.ts；未写入越界文件')
            if read_config(output.files[0].content)!=expected:
                raise ValueError('程序交付参数与确认提案不一致；未写入候选文件')
        shared={**context,'files':source_files(workspace),'feedback':feedback,'repair_round':attempt}
        changes=await team.step(run,'code','程序',Changes,shared,['config_plan'],validate=validate)
        apply_changes(workspace,changes)
        store.event(rid,'程序','files_changed',message=changes.summary,files=['src/config.ts'],parameters=changes_between(before,after),attempt=attempt)
        strategy=await team.step(run,'test_strategy','QA',TestStrategy,
            {**shared,'files':source_files(workspace)},['config_plan','code'])
        store.execute("UPDATE runs SET status='testing' WHERE id=?",(rid,))
        store.event(rid,'QA','testing',message='在隔离容器中验证配置与对应玩法的核心交互')
        evidence=await run_checked(w.runner,workspace,rid,before['mode'])
        actual=evidence.get('config')
        evidence['parameter_match']=isinstance(actual,dict) and all(actual.get(k)==v for k,v in expected.items())
        evidence['unchanged_sources']=all(source_files(workspace)[k]==v for k,v in original.items() if k!='src/config.ts')
        if not evidence['parameter_match'] or not evidence['unchanged_sources']:
            evidence['passed']=False;evidence['error']='实际配置或非配置文件与确认范围不一致'
        store.event(rid,'QA','test_result',**evidence)
        report=await team.step(run,'qa_report','QA',QAReport,
            {**shared,'files':source_files(workspace),'tool_evidence':evidence},['config_plan','code','test_strategy'])
        issues=[i.model_dump() for i in report.issues]
        if not evidence.get('passed'):
            issues.append({'owner':'程序','severity':'blocking','description':'实际工具测试未通过','evidence':'本轮 test_result'})
        blocked=[i for i in issues if i['severity']=='blocking']
        if not blocked:
            delivery=await team.step(run,'delivery','制作人',Delivery,
                {**context,'tool_evidence':evidence,'manual_checks':[*strategy.manual_checks,*report.manual_checks]},['config_plan','qa_report'])
            if not delivery.ready:raise ValueError('制作人未接受配置交付，上一可玩版本保持不变')
            evidence['team']={'mode':'team8','task_type':'config','config_step':team.latest(rid,'config_plan')['id'],
                'qa_step':team.latest(rid,'qa_report')['id'],'delivery':delivery.model_dump(),
                'manual_checks':[*strategy.manual_checks,*report.manual_checks]}
            w.publish(run,workspace,original,evidence)
            return
        if any(i['owner']!='程序' for i in blocked):
            raise ValueError('QA 发现超出配置范围的设计问题，请查看报告并通过功能开发重新提交。上一版已保留。')
        feedback={'issues':issues,'tool_evidence':evidence}
        store.event(rid,'PM','revision_requested',message='配置验证未通过，交回程序修复；确认参数保持不变',issues=issues,repair_round=attempt+1)
    raise ValueError('配置调整初次执行及两轮修复均未通过；已保留上一可玩版本')
