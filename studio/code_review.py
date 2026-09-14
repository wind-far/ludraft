"""Read-only code audit with source evidence and programmer/lead adjudication."""
import hashlib
import json
from pathlib import Path
from .db import uid
from .models import Plan
from .team_models import ReviewScope, CodeAudit, AuditResponse, AuditVerdict
from .routing import options,save
from .documents import catalog,numbered
from .test_flow import manifest
from .reports import finish,reference_closure
from .llm import ModelError


def previous_review(store,run):
    if not run.get('id') or not run.get('base_version'):return None
    config=options(store,run['id'])
    if 'code_review_source' not in config:
        row=store.one("""SELECT p.run_id FROM run_reports p JOIN runs r ON r.id=p.run_id
            WHERE p.kind='review' AND r.project_id=? AND r.base_version=? AND r.id!=? AND r.status='succeeded'
            ORDER BY p.created_at DESC,p.rowid DESC LIMIT 1""",(run['project_id'],run['base_version'],run['id']))
        config['code_review_source']=row['run_id'] if row else None;save(store,run['id'],config)
    row=store.one('SELECT payload FROM run_reports WHERE run_id=?',(config['code_review_source'],)) if config['code_review_source'] else None
    if not row:return None
    result=json.loads(row['payload'])
    return {k:result[k] for k in ('run_id','base_version','scope','audit','response','verdict','open_findings','input_hashes','sha256','boundary')}


def referenced_reviews(store,runs):
    return {rid:report for rid,report in reference_closure(store,runs).items() if report.get('kind')=='review'}


def citation_errors(citations,sources,allowed):
    errors=[]
    for c in citations:
        source=sources.get(c.source_id)
        if c.source_id not in allowed or not source:errors.append('引用不在确认的代码文件范围');continue
        lines=source['text'].splitlines()
        if c.end<c.start or c.end>len(lines) or c.end-c.start>=20:errors.append('引用行号无效');continue
        if not c.quote.strip() or c.quote not in '\n'.join(lines[c.start-1:c.end]):errors.append('引文与代码原文不一致')
    return errors


def audit_errors(scope,audit,sources):
    errors=[];paths=[x.path for x in audit.coverage];allowed={'file:'+p for p in scope.files}
    if not audit.summary.strip() or any(not x.summary.strip() for x in audit.coverage):errors.append('审查摘要与覆盖说明不能为空')
    if len(paths)!=len(scope.files) or set(paths)!=set(scope.files):errors.append('逐文件审查记录没有完整覆盖确认范围或存在重复')
    ids=[f.id for f in audit.findings]
    if len(ids)!=len(set(ids)):errors.append('问题编号重复')
    for coverage in audit.coverage:
        errors.extend(citation_errors(coverage.citations,sources,{'file:'+coverage.path}&allowed))
    for f in audit.findings:
        if any(not value.strip() for value in (f.title,f.description,f.impact,f.recommendation)):errors.append('问题描述、影响与建议不能为空')
        errors.extend(citation_errors(f.citations,sources,allowed))
    return list(dict.fromkeys(errors))


def response_errors(items,audit,scope,sources):
    errors=[];ids=[x.finding_id for x in items]
    if len(ids)!=len(audit.findings) or set(ids)!={x.id for x in audit.findings}:errors.append('必须逐条回应所有问题，不能遗漏、重复或新增编号')
    for item in items:
        if not item.reason.strip() or (hasattr(item,'suggestion') and not item.suggestion.strip()):errors.append('回应或复核依据不能为空')
        errors.extend(citation_errors(item.citations,sources,{'file:'+p for p in scope.files}))
    return list(dict.fromkeys(errors))


async def plan(team,run,context,config):
    base=team.store.one('SELECT * FROM versions WHERE id=?',(run['base_version'],))
    if not base:raise ValueError('待审查版本不存在')
    root=Path(base['path']);before=manifest(root);sources=catalog(team.store,run,context)
    # Review includes read-only integration files, not just files the coder may change.
    for path,sha in before.items():
        text=(root/path).read_text()
        if hashlib.sha256(text.encode()).hexdigest()!=sha:raise ValueError('审查源码读取时发生变化，请重新发起')
        sources['file:'+path]={'label':base['id']+' / '+path,'text':text,'sha256':sha}
    def validate(scope):
        if len(scope.files)!=len(set(scope.files)) or not set(scope.files)<=before.keys():raise ValueError('审查文件必须来自当前版本，不能重复或引用外部路径')
        if any(not x.strip() for x in [scope.summary,*scope.focus,*scope.acceptance]):raise ValueError('审查范围与验收不能为空')
    scope=await team.step(run,'review_scope','PM',ReviewScope,
        {'available_files':list(before),'sources':numbered(sources),'previous_code_review':context.get('previous_code_review'),
         'instruction':'只规划已有代码的静态审查文件、关注点和验收。检查三消规则、边界、状态与交互实现。files 只能选 available_files。此轮不修改代码或执行游戏测试。'},['brief'],validate)
    mode=(context['previous_plan'] or {}).get('mode') or json.loads(base['evidence'])['config']['mode']
    suffix=' · 代码审查'
    p=Plan(title=base['title'][:80-len(suffix)]+suffix,mode=mode,summary=scope.summary,controls='主程审查、程序逐项回应、主程复核；结果独立保存',acceptance=scope.acceptance)
    config.update(review_scope=scope.model_dump(),review_sources=sources,input_hashes=before,scope_revision=uid(),planned_plan=p.model_dump())
    save(team.store,run['id'],config)
    team.store.execute("UPDATE runs SET status='waiting_confirmation',plan=? WHERE id=?",(p.model_dump_json(),run['id']))
    team.store.event(run['id'],'PM','review_scope_ready',message='请确认审查版本、文件与关注点',base_version=base['id'],scope=scope.model_dump(),scope_revision=config['scope_revision'])
    team.store.event(run['id'],'PM','plan_ready',message='审查范围已生成，等待用户确认',plan=p.model_dump())


async def implement(team,run):
    store=team.store;rid=run['id'];config=options(store,rid)
    if config.get('planned_plan')!=json.loads(run['plan']):raise ValueError('审查范围与确认内容不一致，请重新确认')
    scope=ReviewScope.model_validate(config['review_scope']);sources=config['review_sources']
    base=store.one('SELECT * FROM versions WHERE id=?',(run['base_version'],))
    if not base or manifest(Path(base['path']))!=config['input_hashes']:raise ValueError('待审查版本输入发生变化，请重新发起审查')
    if any(hashlib.sha256(v['text'].encode()).hexdigest()!=v['sha256'] for v in sources.values()):raise ValueError('审查引用快照不一致，请重新确认')
    context={'scope':scope.model_dump(),'sources':numbered(sources),'base_version':base['id'],
        'instruction':'本轮只读静态代码审查，不写文件、不声称执行测试或修复。只检查确认范围，逐文件 coverage 引用该文件的原始行号和代码原文。发现具体问题才填写 findings，每项包含触发条件、影响、建议与代码引用。引用只允许已确认文件，quote 不包含行号前缀。不得捏造问题或把测试证据当作本轮实测。'}
    store.event(rid,'PM','route_confirmed',message='确认范围后开始静态代码审查；原可玩版本保留',**config['route'])
    audit=None;response=None;verdict=None;errors=[];attempts=[];analysis_error=None
    for attempt in range(3):
        store.execute('UPDATE runs SET repairs=? WHERE id=?',(attempt,rid))
        try:
            audit=await team.step(run,'code_audit','主程',CodeAudit,{**context,'previous_draft':audit.model_dump() if audit else None,'feedback':errors,'repair_round':attempt},['review_scope'])
            response=None;verdict=None;errors=audit_errors(scope,audit,sources)
            if not errors:
                response=await team.step(run,'audit_response','程序',AuditResponse,
                    {**context,'instruction':'逐条复核主程 findings。agree 或 dispute 均需引用确认范围的代码解释原因，给出建议但不执行修改。不删除/新增问题编号；没有问题则 responses=[]。'},['review_scope','code_audit'])
                errors=response_errors(response.responses,audit,scope,sources)
            if not errors:
                verdict=await team.step(run,'audit_verdict','主程',AuditVerdict,
                    {**context,'instruction':'结合原代码和程序回应逐条复核。confirmed 表示问题成立，dismissed 表示有依据地排除，unresolved 表示仍需人工判断。不能因程序反对就撤销问题。每条有代码引用。accepted 只表示本报告完整可信、可交付，不表示代码无问题或测试通过；问题未修复也可交付报告。'},['review_scope','code_audit','audit_response'])
                errors=response_errors(verdict.decisions,audit,scope,sources)
                if not verdict.accepted:errors.append('主程未接受本轮审查报告')
            attempts.append({'repair_round':attempt,'errors':errors.copy()})
            store.event(rid,'system','review_validation',message='审查报告覆盖、引用与回应门禁'+('未通过' if errors else '通过'),passed=not errors,errors=errors,repair_round=attempt)
            if not errors:break
            if attempt<2:store.event(rid,'主程','review_revision',message='修订审查报告；不修改游戏代码',errors=errors,repair_round=attempt+1)
        except (ModelError,ValueError):
            analysis_error='审查或回应模型输出失败；已有报告草稿保留，请查看角色日志'
            break
    try:unchanged=manifest(Path(base['path']))==config['input_hashes']
    except ValueError:unchanged=False
    if not unchanged:errors.append('审查期间源文件发生变化，结果不可作为当前版本依据')
    passed=bool(audit and response and verdict and verdict.accepted and not errors and not analysis_error)
    # Missing or invalid verdicts cannot silently dismiss findings in draft reports.
    decisions={d.finding_id:d.decision for d in verdict.decisions} if passed else {}
    open_findings=[f.model_dump() for f in audit.findings if decisions.get(f.id)!='dismissed'] if audit else []
    finish(store,run,{'kind':'review','title':json.loads(run['plan'])['title'],'base_version':base['id'],
        'scope':scope.model_dump(),'sources':sources,'input_hashes':config['input_hashes'],'input_unchanged':unchanged,
        'audit':audit.model_dump() if audit else None,'response':response.model_dump() if response else None,
        'verdict':verdict.model_dump() if verdict else None,'open_findings':open_findings,
        'validation':{'passed':passed,'errors':errors,'attempts':attempts},'analysis_error':analysis_error,'passed':passed,
        'boundary':'这是确认范围内的静态代码审查；本轮没有执行游戏测试或修复。审查完成只表示覆盖、引用、逐项回应及报告复核门禁通过，发现的问题仍需另行修复与验证；未发现问题不证明代码无缺陷。'})


def markdown(report):
    lines=['# '+report['title'],'',report['boundary'],'','报告状态：'+('已完成' if report['passed'] else '未通过门禁的草稿'),'',
        '来源版本：'+report['base_version'],'','## 审查范围','',report['scope']['summary'],'']
    lines+=['- '+p for p in report['scope']['files']]
    for finding in (report['audit'] or {}).get('findings',[]):
        lines+=['','## '+finding['id']+' · '+finding['title'],'','级别：'+finding['severity'],'',finding['description'],'','影响：'+finding['impact'],'','建议：'+finding['recommendation']]
        for c in finding['citations']:lines+=['',f"来源：{c['source_id']} 第 {c['start']}–{c['end']} 行",'',*['> '+v for v in c['quote'].splitlines()]]
        response=next((r for r in (report['response'] or {}).get('responses',[]) if r['finding_id']==finding['id']),None)
        decision=next((r for r in (report['verdict'] or {}).get('decisions',[]) if r['finding_id']==finding['id']),None)
        if response:lines+=['','程序回应：'+response['position']+' · '+response['reason'],'',response['suggestion']]
        if decision:lines+=['','主程复核：'+decision['decision']+' · '+decision['reason']]
    lines+=['','## 限制与错误','']+['- '+x for x in [*(report['audit'] or {}).get('limitations',[]),*(report['verdict'] or {}).get('limitations',[]),*report['validation']['errors']]]
    if report['analysis_error']:lines+=['',report['analysis_error']]
    lines+=['','完整逐文件审查、引用快照、角色回应、用量、规则和摘要见 report.json 与 sources.json。','']
    return '\n'.join(lines)
