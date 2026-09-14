"""Scoped, cited document artifacts. Never publish documents as game versions."""
import hashlib
import json
from .db import uid
from .models import Plan
from .team_models import DocumentScope, DocumentBundle, DocumentReview
from .routing import options, save
from .reports import finish,reference_closure
from .messages import history
from .llm import ModelError


def previous_documents(store, run):
    if not run.get('id'):return None
    config=options(store,run['id'])
    if 'document_source' not in config:
        row=store.one("""SELECT p.run_id FROM run_reports p JOIN runs r ON r.id=p.run_id
            WHERE p.kind='doc' AND r.project_id=? AND r.id!=? AND r.status='succeeded'
            ORDER BY p.created_at DESC,p.rowid DESC LIMIT 1""",(run['project_id'],run['id']))
        config['document_source']=row['run_id'] if row else None
        save(store,run['id'],config)
    row=store.one('SELECT payload FROM run_reports WHERE run_id=?',(config['document_source'],)) if config['document_source'] else None
    if not row:return None
    report=json.loads(row['payload'])
    return {k:report[k] for k in ('run_id','base_version','documents','sha256','boundary')}


def referenced_documents(store,runs):
    return {rid:report for rid,report in reference_closure(store,runs).items() if report.get('kind')=='doc'}


def catalog(store,run,context):
    sources={}
    def add(key,label,text):
        if not isinstance(text,str):text=json.dumps(text,ensure_ascii=False,indent=2)
        sources[key]={'label':label,'text':text,'sha256':hashlib.sha256(text.encode()).hexdigest()}
    add('requirement','本轮用户需求（目标，不等于已实现）',run['requirement'])
    add('messages','本轮沟通记录（包含意见与待确认内容）',history(store,run['id']))
    for i,item in enumerate(context['requirement_materials']):
        add('material:'+str(i),'用户核对材料（参考内容，不等于实现证据）',item['reviewed_text'])
    if run['base_version']:
        for path,text in context['files'].items():add('file:'+path,'版本 '+run['base_version']+' / '+path,text)
        add('plan','来源版本确认玩法（目标）',context['previous_plan'])
        add('tests','来源版本工具证据（仅覆盖记录的检查）',context['previous_evidence'])
    previous=context.get('previous_documents')
    if previous:
        for doc in previous['documents']:
            add('document:'+doc['id'],'历史文档 '+previous['run_id']+'（可能基于旧版本）',render_document(doc))
    return sources


def numbered(sources):
    return {key:{**value,'text':'\n'.join(f'{i}: {line}' for i,line in enumerate(value['text'].splitlines(),1))}
            for key,value in sources.items()}


def validate_bundle(scope,bundle,sources):
    errors=[];docs=bundle.documents
    if [d.id for d in docs]!=[d.id for d in scope.documents]:errors.append('文档编号与顺序必须与确认范围一致')
    targets={d.id:d for d in scope.documents}
    for doc in docs:
        target=targets.get(doc.id)
        if not target:continue
        if doc.title!=target.title:errors.append(doc.id+'：标题不符合确认范围')
        if [s.heading for s in doc.sections]!=target.sections:errors.append(doc.id+'：章节不符合确认范围')
        for section in doc.sections:
            prefix=doc.id+'/'+section.heading+'：'
            if not section.body.strip():errors.append(prefix+'正文不能为空')
            if section.kind=='fact' and not section.citations:errors.append(prefix+'事实章节必须有引用依据')
            for citation in section.citations:
                source=sources.get(citation.source_id)
                if not source:
                    errors.append(prefix+'引用来源不存在');continue
                lines=source['text'].splitlines()
                if citation.end<citation.start or citation.end>len(lines) or citation.end-citation.start>=20:
                    errors.append(prefix+'引用行范围无效');continue
                if not citation.quote.strip() or citation.quote not in '\n'.join(lines[citation.start-1:citation.end]):
                    errors.append(prefix+'引文与来源行不一致')
    return list(dict.fromkeys(errors))


async def plan(team,run,context,config):
    sources=catalog(team.store,run,context)
    scope=await team.step(run,'document_scope','PM',DocumentScope,
        {'sources':numbered(sources),'previous_documents':context.get('previous_documents'),
         'instruction':'只规划 1 至 3 份 Markdown 文档及精确章节顺序。新项目没有代码事实，规划内容标记为建议。引用历史文档不能证明当前实现。不得安排游戏代码生成。'},['brief'])
    mode=(context['previous_plan'] or {}).get('mode','match3')
    p=Plan(title=scope.title,mode=mode,summary=scope.summary,controls='编写、校验引用并审阅文档；不创建游戏版本',acceptance=scope.acceptance)
    config.update(document_scope=scope.model_dump(),document_sources=sources,scope_revision=uid(),planned_plan=p.model_dump())
    save(team.store,run['id'],config)
    team.store.execute("UPDATE runs SET status='waiting_confirmation',plan=? WHERE id=?",(p.model_dump_json(),run['id']))
    if not run['base_version']:team.store.execute('UPDATE projects SET title=? WHERE id=?',(scope.title,run['project_id']))
    team.store.event(run['id'],'PM','document_scope_ready',message='请确认文档与章节范围',scope=scope.model_dump(),scope_revision=config['scope_revision'],sources=[{'id':k,'label':v['label'],'sha256':v['sha256']} for k,v in sources.items()])
    team.store.event(run['id'],'PM','plan_ready',message='文档范围已生成，等待用户确认',plan=p.model_dump())


async def implement(team,run):
    store=team.store;rid=run['id'];config=options(store,rid)
    if config.get('planned_plan')!=json.loads(run['plan']):raise ValueError('文档范围与已确认内容不一致，请重新确认')
    scope=DocumentScope.model_validate(config['document_scope']);sources=config['document_sources']
    if any(hashlib.sha256(v['text'].encode()).hexdigest()!=v['sha256'] for v in sources.values()):raise ValueError('文档引用快照不一致，请重新确认')
    context={'scope':scope.model_dump(),'sources':numbered(sources),'base_version':run['base_version'],
        'instruction':'严格按已确认文档编号、标题、章节顺序编写。fact 是有依据的陈述，必须引用 source_id、原始行号 start/end 和原文 quote（不包含行号前缀）。proposal 是建议，不能声称已实现。引用需求仅证明需求存在。历史文档不证明当前实现。正文用普通文本，不插入 HTML、图片或外部链接。只编写文档，不修改游戏。'}
    store.event(rid,'PM','route_confirmed',message='已确认文档范围，开始编写与审阅',**config['route'])
    bundle=None;review=None;errors=[];attempts=[];analysis_error=None
    for attempt in range(3):
        store.execute('UPDATE runs SET repairs=? WHERE id=?',(attempt,rid))
        try:
            bundle=await team.step(run,'documents','主程',DocumentBundle,{**context,'previous_draft':bundle.model_dump() if bundle else None,'feedback':errors,'repair_round':attempt},['document_scope'])
            review=None;errors=validate_bundle(scope,bundle,sources)
            store.event(rid,'system','document_validation',message='文档结构与引用校验'+('未通过' if errors else '通过'),passed=not errors,errors=errors,repair_round=attempt)
            if not errors:
                review=await team.step(run,'document_review','PM',DocumentReview,
                    {**context,'instruction':'根据 sources 逐条检查陈述是否被引用内容支持，检查事实与建议区分、验收覆盖。格式校验不等于内容真实；引用存在但不支持结论也必须拒绝。accepted=true 必须没有阻断 issues；人工内容准确性检查写 limitations。'},['document_scope','documents'])
                if not review.accepted or review.issues:errors=review.issues or ['PM 未接受文档交付']
            attempts.append({'repair_round':attempt,'errors':errors.copy(),'review':review.model_dump() if review else None})
            if not errors:break
            if attempt<2:store.event(rid,'PM','document_repair',message='将校验与审阅问题交回主程修订',errors=errors,repair_round=attempt+1)
        except (ModelError,ValueError):
            analysis_error='文档编写或审阅响应失败；已有草稿与引用快照已保留，请查看角色日志'
            break
    passed=bool(bundle and review and review.accepted and not errors and not analysis_error)
    finish(store,run,{'kind':'doc','title':scope.title,'base_version':run['base_version'],'scope':scope.model_dump(),
        'sources':sources,'documents':[d.model_dump() for d in bundle.documents] if bundle else [],
        'review':review.model_dump() if review else None,'validation':{'passed':passed,'errors':errors,'attempts':attempts},
        'analysis_error':analysis_error,'passed':passed,
        'boundary':'文档通过表示结构、引文校验与 PM 审阅通过；内容准确性仍需人工复核，建议不代表已实现。来源绑定本轮快照，历史文档可能对应旧版本。'})


def render_document(doc):
    lines=['# '+doc['title'],'']
    for section in doc['sections']:
        lines+=['## '+section['heading'],'','类型：'+('依据陈述' if section['kind']=='fact' else '设计建议'),'',section['body'],'']
        for citation in section['citations']:
            lines+=['来源：'+citation['source_id']+f"，第 {citation['start']}–{citation['end']} 行",'',*['> '+line for line in citation['quote'].splitlines()],'']
    return '\n'.join(lines)
