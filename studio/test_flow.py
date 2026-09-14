"""Read-only version testing. A report is never published as a playable version."""
import hashlib
import json
from pathlib import Path
from .db import uid
from .files import copy_source
from .models import Plan
from .team_models import TestScope,TestStrategy,QAReport,Delivery
from .routing import save,options
from .llm import ModelError
from .reports import finish

from .verification import required_checks, evidence_errors, run_checked


def manifest(root):
    fixed=['index.html','style.css','tsconfig.json','package.json','README.md']
    paths=[root/name for name in fixed]+sorted((root/'src').rglob('*'))
    result={}
    for path in paths:
        if path.is_symlink() or not path.resolve().is_relative_to(root.resolve()):
            raise ValueError('测试输入包含不允许的文件链接')
        if path.is_dir():continue
        try:result[path.relative_to(root).as_posix()]=hashlib.sha256(path.read_bytes()).hexdigest()
        except OSError:raise ValueError('无法读取完整测试输入，请检查待测版本文件') from None
    if not {'src/main.ts','src/game.ts','src/config.ts'}<=result.keys():raise ValueError('待测版本缺少必要源文件')
    return result




async def plan(team,run,context,config):
    base=team.store.one('SELECT * FROM versions WHERE id=?',(run['base_version'],))
    if not base:raise ValueError('待测版本不存在')
    before=manifest(Path(base['path']))
    previous=context['previous_plan'] or {}
    mode=previous.get('mode') or json.loads(base['evidence']).get('config',{}).get('mode')
    runtime=json.loads(base['evidence']).get('runtime')
    scope=await team.step(run,'test_scope','PM',TestScope,
        {**context,'base_version':base['id'],'available_checks':required_checks(mode,runtime),
         'instruction':'仅规划已有版本的测试，不生成新玩法或安排修复。focus 是关注点；固定工具以 available_checks 为准，无法自动验证的个性化需求明确列入 manual_checks。'},['brief'])
    p=Plan(title=base['title'],mode=mode,summary=scope.summary,
        controls='保持已有操作；本轮只生成测试报告，不修改或发布游戏',
        acceptance=[*scope.acceptance,'固定工具检查必须完整执行；缺失结果不算通过','未覆盖的个性化验收与可玩性另行人工检查'])
    config.update(test_scope=scope.model_dump(),scope_revision=uid(),input_hashes=before,planned_plan=p.model_dump())
    save(team.store,run['id'],config)
    team.store.execute("UPDATE runs SET status='waiting_confirmation',plan=? WHERE id=?",(p.model_dump_json(),run['id']))
    team.store.event(run['id'],'PM','test_scope_ready',message='请确认待测版本与范围；尚未运行测试',
        base_version=base['id'],scope=scope.model_dump(),available_checks=required_checks(mode,runtime),scope_revision=config['scope_revision'])
    team.store.event(run['id'],'PM','plan_ready',message='测试范围已生成，等待用户确认',plan=p.model_dump())


async def implement(team,run):
    store=team.store;w=team.w;rid=run['id'];config=options(store,rid)
    if config.get('planned_plan')!=json.loads(run['plan']):raise ValueError('测试范围与已确认内容不一致，请重新确认')
    scope=TestScope.model_validate(config['test_scope']);mode=json.loads(run['plan'])['mode']
    base=store.one('SELECT * FROM versions WHERE id=?',(run['base_version'],))
    if not base:raise ValueError('待测版本不存在')
    source=Path(base['path'])
    if manifest(source)!=config['input_hashes']:raise ValueError('待测版本文件在确认前后发生变化，请重新提交测试')
    if not await w.runner.available():raise ValueError('Docker 或验证镜像不可用，未执行测试')
    workspace=store.root/'candidates'/rid;copy_source(source,workspace)
    if manifest(workspace)!=config['input_hashes']:raise ValueError('测试副本与确认版本不一致，已停止执行')
    context={**team.context(run),'available_checks':required_checks(mode,json.loads(base['evidence']).get('runtime')),'test_scope':scope.model_dump(),
        'instruction':'只测试已有版本并形成报告，不修改代码，不声称已修复问题。根据实际工具证据区分通过、失败、未执行和待人工验证。'}
    store.event(rid,'PM','route_confirmed',message='已确认测试范围；不修改游戏或生成新版本',**config['route'])
    strategy=await team.step(run,'test_strategy','QA',TestStrategy,context,['test_scope'])
    store.execute("UPDATE runs SET status='testing' WHERE id=?",(rid,))
    store.event(rid,'QA','testing',message='对确认版本的临时副本执行完整隔离构建与交互测试')
    evidence=await run_checked(w.runner,workspace,rid,mode)
    gates=evidence['gate_errors']
    try:evidence['input_unchanged']=manifest(workspace)==config['input_hashes'] and manifest(source)==config['input_hashes']
    except ValueError:evidence['input_unchanged']=False
    if not evidence['input_unchanged']:gates.append('测试输入文件发生变化')
    evidence['gate_errors']=gates
    if gates:evidence['passed']=False
    store.event(rid,'QA','test_result',**evidence)
    report=None;delivery=None;analysis_error=None
    try:
        report=await team.step(run,'qa_report','QA',QAReport,{**context,'tool_evidence':evidence},['test_scope','test_strategy'])
        if evidence.get('passed') and not any(i.severity=='blocking' for i in report.issues):
            delivery=await team.step(run,'test_delivery','策划',Delivery,
                {**context,'tool_evidence':evidence,'manual_checks':[*scope.manual_checks,*strategy.manual_checks,*report.manual_checks],
                 'instruction':'审阅测试报告交付。ready 仅表示报告可交付，不能代表未测试玩法通过，不更新游戏或文档。'},['test_scope','qa_report'])
    except (ModelError,ValueError):
        # Tool evidence remains usable even when a later model output is invalid.
        analysis_error='测试证据已保存，但 QA 分析或交付响应失败；查看角色日志后重新发起测试'
    # NeedsInput and cancellation deliberately propagate; no final report before renewed approval.
    passed=bool(evidence.get('passed') and report and not any(i.severity=='blocking' for i in report.issues) and delivery and delivery.ready and not analysis_error)
    manual=list(dict.fromkeys([*scope.manual_checks,*strategy.manual_checks,*(report.manual_checks if report else []),'自动检查仅覆盖固定核心交互，人工可玩性评价尚未完成']))
    finish(store,run,{'kind':'test','title':base['title']+' · 测试报告','base_version':base['id'],
        'scope':scope.model_dump(),'input_hashes':config['input_hashes'],'tool_evidence':evidence,
        'qa_report':report.model_dump() if report else None,'delivery':delivery.model_dump() if delivery else None,
        'analysis_error':analysis_error,'manual_checks':manual,'passed':passed,
        'boundary':'本轮没有修改代码、自动修复问题或发布游戏版本。通过只表示固定检查及本轮报告门禁通过。'})
