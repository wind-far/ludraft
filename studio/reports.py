"""Immutable task reports, independent from playable version publication."""
import hashlib
import io
import json
import zipfile
from pathlib import Path
from fastapi import HTTPException
from fastapi.responses import StreamingResponse
from .db import now,TERMINAL
from .lineage import decoded_steps,resolve
from .messages import history
from .uploads import run_materials
from .routing import options,save


def encoded(value):return json.dumps(value,ensure_ascii=False,sort_keys=True)


def previous_test(store,run):
    """Bind a same-project/base report once; never silently replace it mid-run."""
    if not run.get('base_version') or not run.get('id'):return None
    config=options(store,run['id'])
    if 'test_report_source' not in config:
        row=store.one('''SELECT p.run_id FROM run_reports p JOIN runs r ON r.id=p.run_id
            WHERE p.kind='test' AND r.project_id=? AND r.base_version=? AND r.id!=?
            ORDER BY p.created_at DESC LIMIT 1''',(run['project_id'],run['base_version'],run['id']))
        config['test_report_source']=row['run_id'] if row else None;save(store,run['id'],config)
    if not config['test_report_source']:return None
    row=store.one('SELECT payload FROM run_reports WHERE run_id=?',(config['test_report_source'],))
    if not row:return None
    report=json.loads(row['payload'])
    return {key:report[key] for key in ('run_id','base_version','passed','scope','input_hashes','tool_evidence','qa_report','analysis_error','manual_checks','sha256')}


def reference_closure(store,runs):
    """Follow cross-kind provenance too: a document can cite an earlier audit/test."""
    result={};pending=[]
    for rid in runs:
        config=options(store,rid)
        pending.extend(config.get(key) for key in ('test_report_source','document_source','code_review_source','research_source'))
    while pending:
        source=pending.pop()
        if not source or source in result:continue
        row=store.one('SELECT payload FROM run_reports WHERE run_id=?',(source,))
        if row:
            result[source]=json.loads(row['payload'])
            pending.extend(result[source].get(key) for key in ('previous_test_report','previous_document','previous_code_review','previous_research_report'))
    return result


def referenced_reports(store,runs):
    return {rid:report for rid,report in reference_closure(store,runs).items() if report.get('kind')=='test'}


def finish(store,run,report):
    rid=run['id']
    if store.run(rid)['status'] in TERMINAL:return
    timestamp=now();state='succeeded' if report['passed'] else 'failed'
    payload={**report,'run_id':rid,'project_id':run['project_id'],'requirement':run['requirement'],
        'started_at':run['created_at'],'finished_at':timestamp,'steps':decoded_steps(store,rid),
        'previous_test_report':options(store,rid).get('test_report_source'),
        'previous_document':options(store,rid).get('document_source'),
        'previous_code_review':options(store,rid).get('code_review_source'),
        'previous_research_report':options(store,rid).get('research_source'),'research_choice':options(store,rid).get('research_choice'),'rule_snapshots':{}}
    for step in payload['steps']:
        row=store.one('SELECT r.id,r.payload FROM step_rules s JOIN rule_snapshots r ON r.id=s.snapshot_id WHERE s.step_id=?',(step['id'],))
        if row:payload['rule_snapshots'][row['id']]=json.loads(row['payload'])
    payload['sha256']=hashlib.sha256(encoded(payload).encode()).hexdigest()
    success_messages={'doc':'文档已生成，结构、引用校验与 PM 审阅通过','review':'审查报告已完成；发现的问题需另行修复与验证','test':'测试报告已生成，固定检查与报告门禁通过'}
    failure_messages={'doc':'文档校验或审阅未通过；草稿已保留','review':'审查报告门禁未通过；草稿与原可玩版本已保留','test':'独立测试或报告门禁未通过；报告与原可玩版本已保留'}
    success_messages['research']='调研报告已完成，可比较方向后再决定是否开发'
    failure_messages['research']='调研报告门禁未通过；来源与草稿已保留'
    error=None if report['passed'] else report.get('analysis_error') or failure_messages[report['kind']]
    with store.lock,store.con:
        store.con.execute('INSERT INTO run_reports VALUES(?,?,?,?)',(rid,report['kind'],encoded(payload),timestamp))
        store.con.execute('UPDATE runs SET status=?,error=?,finished_at=? WHERE id=?',(state,error,timestamp,rid))
        store.con.execute('INSERT INTO events(run_id,role,kind,payload,created_at) VALUES(?,?,?,?,?)',
            (rid,'system','report_ready',encoded({'message':success_messages[report['kind']] if report['passed'] else error,
                'passed':report['passed'],'report_kind':report['kind'],'base_version':run['base_version'],'sha256':payload['sha256']}),timestamp))


def markdown(report):
    lines=['# '+report['title'],'',report['boundary'],'',
        '- 结果：'+('固定检查与报告门禁通过' if report['passed'] else '未通过'),
        '- 待测版本：'+report['base_version'],'- 运行：'+report['run_id'],
        '- 开始：'+report['started_at'],'- 结束：'+report['finished_at'],'',
        '## 用户需求','',report['requirement'],'','## 测试范围','',report['scope']['summary'],'']
    lines.extend('- '+x for x in report['scope']['focus'])
    lines+=['','## 实际工具检查','']
    for check in report['tool_evidence'].get('checks',[]):
        if isinstance(check,dict):lines.append('- '+str(check.get('name','未知检查'))+'：'+('通过' if check.get('passed') is True else '失败/未通过'))
    for error in report['tool_evidence'].get('gate_errors',[]):lines.append('- 门禁：'+error)
    if report['tool_evidence'].get('error'):lines+=['',str(report['tool_evidence']['error'])]
    lines+=['','## QA 分析','',report['qa_report']['summary'] if report['qa_report'] else '未形成有效 QA 分析']
    for issue in (report['qa_report'] or {}).get('issues',[]):
        lines+=['','- '+issue['severity']+' / '+issue['owner']+'：'+issue['description'],'  依据：'+issue['evidence']]
    if report['analysis_error']:lines+=['',report['analysis_error']]
    lines+=['','## 交付审阅','',report['delivery']['summary'] if report['delivery'] else '未接受交付或未执行交付审阅']
    lines+=['','## 待人工检查','']+['- '+x for x in report['manual_checks']]
    lines+=['','## 完整证据','', 'report.json 保留实际日志、输入文件 SHA-256、角色步骤、用量和结果摘要。报告摘要：'+report['sha256'],'']
    return '\n'.join(lines)


def register(app,store,run):
    def get(rid):
        run(rid)
        row=store.one('SELECT payload FROM run_reports WHERE run_id=?',(rid,))
        if not row:raise HTTPException(404,'本轮尚未生成最终产物；已有执行证据可在阶段日志中查看')
        return json.loads(row['payload'])

    @app.get('/api/runs/{rid}/report')
    async def report(rid:str):return get(rid)

    @app.get('/api/runs/{rid}/report/export')
    async def export(rid:str):
        result=get(rid);buffer=io.BytesIO();lineage=resolve(store,result['base_version'])
        steps=[*result['steps'],*lineage['steps']];rules={}
        for step in steps:
            row=store.one('SELECT r.id,r.payload FROM step_rules s JOIN rule_snapshots r ON r.id=s.snapshot_id WHERE s.step_id=?',(step['id'],))
            if row:rules[row['id']]=json.loads(row['payload'])
        runs={rid,*(s['run_id'] for s in steps),*(s['run_id'] for s in lineage['chain'])}
        with zipfile.ZipFile(buffer,'w',zipfile.ZIP_DEFLATED) as archive:
            archive.writestr('report.json',json.dumps(result,ensure_ascii=False,indent=2))
            if result['kind']=='doc':
                from .documents import render_document
                for doc in result['documents']:
                    archive.writestr('documents/'+doc['id']+'.md',render_document(doc))
                archive.writestr('sources.json',json.dumps(result['sources'],ensure_ascii=False,indent=2))
                archive.writestr('README.md','# '+result['title']+'\n\n'+('已通过文档门禁' if result['passed'] else '未通过文档门禁；documents 中是未接受的草稿')+'\n\n'+result['boundary']+'\n\n完整审阅、错误与来源摘要见 report.json。')
            elif result['kind']=='research':
                from .research import markdown as research_markdown
                archive.writestr('research.md',research_markdown(result))
                archive.writestr('sources.json',json.dumps(result['sources'],ensure_ascii=False,indent=2))
            elif result['kind']=='review':
                from .code_review import markdown as review_markdown
                archive.writestr('code-review.md',review_markdown(result))
                archive.writestr('sources.json',json.dumps(result['sources'],ensure_ascii=False,indent=2))
            else:archive.writestr('test-report.md',markdown(result))
            archive.writestr('collaboration.json',json.dumps(steps,ensure_ascii=False,indent=2))
            archive.writestr('provenance.json',json.dumps(lineage,ensure_ascii=False,indent=2))
            archive.writestr('messages.json',json.dumps({r:history(store,r) for r in sorted(runs)},ensure_ascii=False,indent=2))
            archive.writestr('requirements.json',json.dumps({r:run_materials(store,r) for r in sorted(runs)},ensure_ascii=False,indent=2))
            selections={r:options(store,r)['research_choice'] for r in runs if options(store,r).get('research_choice')}
            if selections:archive.writestr('research-selections.json',json.dumps(selections,ensure_ascii=False,indent=2))
            prior=referenced_reports(store,runs)
            if prior:archive.writestr('test-reports.json',json.dumps(prior,ensure_ascii=False,indent=2))
            from .documents import referenced_documents
            prior_docs=referenced_documents(store,runs)
            if prior_docs:archive.writestr('document-history.json',json.dumps(prior_docs,ensure_ascii=False,indent=2))
            from .code_review import referenced_reviews
            prior_reviews=referenced_reviews(store,runs)
            if prior_reviews:archive.writestr('code-reviews.json',json.dumps(prior_reviews,ensure_ascii=False,indent=2))
            from .research import referenced_research
            research=referenced_research(store,runs)
            if research:archive.writestr('research-history.json',json.dumps(research,ensure_ascii=False,indent=2))
            if rules:
                archive.writestr('rules.json',json.dumps(rules,ensure_ascii=False,indent=2))
                archive.writestr('licenses/upstream-MIT.txt',(Path(__file__).resolve().parents[1]/'LICENSE').read_text())
        buffer.seek(0)
        prefix={'doc':'documents','review':'code-review','test':'test-report','research':'research'}[result['kind']]
        return StreamingResponse(buffer,media_type='application/zip',headers={'Content-Disposition':f'attachment; filename="{prefix}-{rid[:8]}.zip"'})
