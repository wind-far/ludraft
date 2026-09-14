"""Reproducible benchmark accounting, separate from human game-quality ratings."""
import hashlib
import json
import os
import sqlite3
import zipfile
from pathlib import Path
from .db import now
from .lineage import decoded_steps
from .team import ROLES
from .verification import evidence_errors

RULE_TABLES=('role_rule_profiles','role_rule_revisions','custom_skills','skill_editions')

def encoded(value):return json.dumps(value,ensure_ascii=False,sort_keys=True)
def digest(value):return hashlib.sha256(encoded(value).encode()).hexdigest()

def write_json(path,value):
    temporary=path.with_suffix(path.suffix+'.tmp');temporary.write_text(json.dumps(value,ensure_ascii=False,indent=2));os.replace(temporary,path)

def configured_roles(gateway):
    return [{'role':r['name'],'configured':bool(gateway.effective(r['name'])['model'])} for r in ROLES]

def copy_rule_configuration(source_root,target):
    """Read configured rules without copying any model credentials or project data."""
    path=source_root.resolve()/'studio.sqlite3';snapshot={table:[] for table in RULE_TABLES}
    if path.exists():
        with sqlite3.connect(path.as_uri()+'?mode=ro',uri=True) as source:
            source.row_factory=sqlite3.Row
            with source:
                for table in RULE_TABLES:
                    snapshot[table]=[dict(r) for r in source.execute('SELECT * FROM '+table+' ORDER BY rowid')]
    with target.lock,target.con:
        for table,rows in snapshot.items():
            for row in rows:
                target.con.execute('INSERT INTO '+table+'('+','.join(row)+') VALUES('+','.join('?' for _ in row)+')',tuple(row.values()))
    return snapshot

def automatic_checks(case,evidence,live=False,steps=(),version=None):
    build=evidence.get('build') is True
    errors=evidence_errors(evidence,case['mode'])
    expected={k:case[k] for k in ('mode','moves','targetScore','gemTypes','speed','lives','duration','spawnMs','fallSpeed') if k in case}
    actual=evidence.get('config',{})
    def matches(value,expected):
        if type(expected) in (int,float):return type(value) in (int,float) and value==expected
        return type(value) is type(expected) and value==expected
    mismatches={k:{'expected':v,'actual':actual.get(k) if isinstance(actual,dict) else None}
                for k,v in expected.items() if not isinstance(actual,dict) or not matches(actual.get(k),v)}
    roles={s['role'] for s in steps if s['status']=='succeeded'}
    missing=[r['name'] for r in ROLES if r['name'] not in roles] if live else []
    if mismatches:errors.append('实际游戏模式或参数未满足固定需求')
    if missing:errors.append('未完成八角色交付：'+'、'.join(missing))
    if live and not version:errors.append('没有实际发布的可玩版本')
    return {'build_passed':build,'interaction_passed':not evidence_errors(evidence,case['mode']),
        'requirement_passed':not mismatches,'mismatches':mismatches,'missing_roles':missing,
        'passed':not errors,'errors':errors,'manual_boundary':'配色语义、难度、趣味性和完整需求符合度仍需人工评价'}

def usage_summary(calls):
    attempted=[c for c in calls if c.get('outcome')=='model_result' or c.get('attempted') is True]
    known=0;unknown=0
    for c in attempted:
        u=c.get('usage') or {};total=u.get('total_tokens')
        if type(total) is not int or total<0:
            a,b=u.get('prompt_tokens'),u.get('completion_tokens')
            total=a+b if type(a) is int and a>=0 and type(b) is int and b>=0 else None
        if total is None:unknown+=1
        else:known+=total
    return {'attempted_calls':len(attempted),'calls_missing_usage':unknown,'known_tokens':known,'total_tokens':None if unknown else known}

def collect_run(store,rid):
    run=store.run(rid);events=store.query('SELECT role,kind,payload,created_at FROM events WHERE run_id=? ORDER BY id',(rid,))
    events=[{**e,'payload':json.loads(e['payload'])} for e in events]
    evidence=[e['payload'] for e in events if e['kind']=='test_result']
    calls=[{'role':e['role'],'outcome':e['kind'],**e['payload']} for e in events if e['kind'] in ('model_result','model_error')]
    steps=decoded_steps(store,rid);rules={}
    for step in steps:
        if step['rules_snapshot']:
            row=store.one('SELECT payload FROM rule_snapshots WHERE id=?',(step['rules_snapshot'],))
            if row:rules[step['rules_snapshot']]=json.loads(row['payload'])
    return {'run':run,'events':events,'attempts':evidence,'model_calls':calls,'agent_steps':steps,'rule_snapshots':rules}

def archive_game(out,rid,root,evidence,details):
    folder=out/'artifacts'/rid;folder.mkdir(parents=True,exist_ok=True)
    target=folder/'game.zip'
    with zipfile.ZipFile(target,'x',zipfile.ZIP_DEFLATED) as z:
        for file in sorted(root.rglob('*')):
            if file.is_symlink():raise ValueError('评测游戏包含文件链接，已拒绝导出')
            if file.is_file():z.write(file,file.relative_to(root).as_posix())
        z.writestr('verification.json',json.dumps(evidence,ensure_ascii=False,indent=2))
        from .exporting import write_startup_files
        write_startup_files(z)
        z.writestr('evaluation.json',json.dumps(details,ensure_ascii=False,indent=2))
    return {'path':target.relative_to(out).as_posix(),'sha256':hashlib.sha256(target.read_bytes()).hexdigest()}

def summary(report):
    records=report['records'];n=len(records)
    known=sum(r['tokens']['known_tokens'] for r in records)
    unknown=sum(r['tokens']['calls_missing_usage'] for r in records)
    return {'completed':n,'expected':report['expected'],'all_runs_completed':n==report['expected'],
        **{k:sum(r['checks'][k] for r in records) for k in ('build_passed','interaction_passed','requirement_passed')},
        'delivery_passed':sum(r['status']=='succeeded' for r in records),
        'repair_rounds':sum(r['repairs'] for r in records),'elapsed_seconds':round(sum(r['elapsed_seconds'] for r in records),2),
        'tokens':{'known_tokens':known,'calls_missing_usage':unknown,'total_tokens':None if unknown else known},
        'human_reviewed':sum(r.get('human_playability') is not None for r in records)}

def human_template(report):
    return {'evaluation_id':report['evaluation_id'],'instructions':'请实际解压并试玩对应 game.zip 后填写。每项 1–5 分；不要将编译通过当作可玩性。空值表示尚未评价。',
        'reviews':[{'run_id':r['run_id'],'artifact_sha256':r['artifact']['sha256'],'reviewer':None,'reviewed_at':None,
                    'playability':None,'rule_clarity':None,'feedback':None,'difficulty':None,'notes':None}
                   for r in report['records'] if r['status']=='succeeded' and r.get('artifact')]}

def apply_human_reviews(report,ratings):
    if ratings.get('evaluation_id')!=report['evaluation_id']:raise ValueError('人工评价不属于这次评测')
    records={r['run_id']:r for r in report['records']};seen=set();accepted={}
    for review in ratings.get('reviews',[]):
        rid=review.get('run_id');record=records.get(rid)
        if rid in seen or not record or not record.get('artifact') or record['status']!='succeeded':raise ValueError('人工评价包含重复或不可评价的运行')
        seen.add(rid)
        if review.get('artifact_sha256')!=record['artifact']['sha256']:raise ValueError('人工评价的游戏 ZIP 摘要不一致')
        fields=('reviewer','reviewed_at','playability','rule_clarity','feedback','difficulty','notes')
        if all(review.get(k) is None for k in fields):continue
        if any(type(review.get(k)) is not int or not 1<=review[k]<=5 for k in ('playability','rule_clarity','feedback','difficulty')):raise ValueError('人工评分必须全部为 1–5 的整数，不能用空值或布尔值代替')
        if any(not isinstance(review.get(k),str) or not review[k].strip() for k in ('reviewer','reviewed_at','notes')):raise ValueError('人工评价需要填写评价者、时间和试玩说明')
        accepted[rid]={k:review[k] for k in (*fields,'artifact_sha256')}
    for rid,value in accepted.items():records[rid]['human_playability']=value
    return report

def persist(out,report):
    report['updated_at']=now();report['summary']=summary(report)
    write_json(out/'results.json',report)
    lines=['# 网页游戏评测结果','',f"模式：{report['mode']}；进度 {len(report['records'])}/{report['expected']}",'',
        '自动结果只覆盖固定交互与明确参数；人工评分单独记录。','',
        '| 用例 | 次数 | 交付 | 构建 | 交互 | 参数 | 修复 | 秒 | 人工评价 |','|---|---:|---|---|---|---|---:|---:|---|']
    for r in report['records']:
        checks=r['checks'];lines.append(f"| {r['case']} | {r['repeat']} | {r['status']} | {checks['build_passed']} | {checks['interaction_passed']} | {checks['requirement_passed']} | {r['repairs']} | {r['elapsed_seconds']} | {'已填写' if r['human_playability'] else '待评价'} |")
    lines+=['','完整步骤、所有修复轮次、用量、错误和游戏 ZIP 摘要见 results.json 与 artifacts/。','']
    (out/'results.md').write_text('\n'.join(lines))
