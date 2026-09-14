"""Environment checks and read-only comparisons. No generated code is executed here."""
import asyncio
import difflib
import json
from pathlib import Path
from urllib.parse import urlparse
import httpx
from fastapi import HTTPException
from .db import now
from .files import source_files
from .models import Parameters, Match3Parameters
from .parameters import read_config


async def preview_status(origin):
    try:
        parsed = urlparse(origin)
    except ValueError:
        return 'unverified'
    if parsed.scheme != 'http' or parsed.hostname not in ('127.0.0.1', 'localhost', '::1') or parsed.username or parsed.password or parsed.query or parsed.fragment or parsed.path not in ('', '/'):
        return 'unverified'
    try:
        async with httpx.AsyncClient(timeout=2, follow_redirects=False, trust_env=False) as client:
            response = await client.get(origin.rstrip('/') + '/health')
            return 'passed' if response.status_code == 200 and response.json() == {'service':'ludraft-preview'} else 'failed'
    except (httpx.HTTPError, ValueError):
        return 'failed'


def compare_versions(before, after):
    old, new = source_files(Path(before['path'])), source_files(Path(after['path']))
    files = []
    for name in sorted(set(old) | set(new)):
        if old.get(name) == new.get(name):
            continue
        old_lines, new_lines = old.get(name, '').splitlines(), new.get(name, '').splitlines()
        added, removed = 0, 0
        for tag, a, b, c, d in difflib.SequenceMatcher(None, old_lines, new_lines, autojunk=False).get_opcodes():
            if tag in ('insert', 'replace'): added += d-c
            if tag in ('delete', 'replace'): removed += b-a
        # Splitlines normalizes final-newline differences but contents still flag the file changed.
        patch = '\n'.join(difflib.unified_diff(old_lines,new_lines,fromfile='before/'+name,tofile='after/'+name,lineterm=''))
        files.append({'path':name,'added':added,'removed':removed,'diff':patch or '仅文件末尾换行不同'})
    def config_for(source):
        try: return read_config(source['src/config.ts'])
        except (ValueError,KeyError): return None
    configs = [config_for(old), config_for(new)]
    keys=dict.fromkeys(['title','mode',*Match3Parameters.model_fields,*Parameters.model_fields])
    params = None if any(c is None for c in configs) else [
        {'key':key,'before':configs[0].get(key),'after':configs[1].get(key)}
        for key in keys if configs[0].get(key) != configs[1].get(key)]
    def summary(v):
        return {k:v[k] for k in ('id','title','created_at','run_id')}
    return {'before':summary(before),'after':summary(after),'files':files,'parameters':params,
            'parameter_note':None if params is not None else '至少一个版本使用动态或自定义配置；请查看源码差异，参数未自动提取。',
            'identical':old == new, 'added':sum(f['added'] for f in files), 'removed':sum(f['removed'] for f in files)}


def model_diagnostics(app,gateway):
    """Read saved test receipts; matching effective connections may share proof."""
    from .team import ROLES
    if not all(hasattr(gateway,name) for name in ('public_connection','role_identity','configuration_id')):
        return [{'role':r['name'],'status':'unverified','checked_at':None,'detail':'当前适配器没有可核对的独立连接测试记录。'} for r in ROLES]
    try:
        profiles={r['name']:gateway.public_connection(r['name']) for r in ROLES}
        identities={r:gateway.role_identity(r) for r in profiles}
        receipts=[]
        default=app.state.connection_check
        if default and default['identity']==gateway.configuration_id():
            receipts.append({**default,'identity':identities['策划'],'source':'策划'})
        for role,record in getattr(app.state,'role_connection_checks',{}).items():
            if record['identity']==identities.get(role):receipts.append({**record,'source':role})
        result=[]
        for role,profile in profiles.items():
            cfg=profile['effective'];local=urlparse(cfg['base_url']).hostname in ('127.0.0.1','localhost','::1')
            configured=bool(cfg['model']) and (local or profile['effective_has_key'])
            candidates=[r for r in receipts if r['identity']==identities[role]]
            record=max(candidates,key=lambda r:r['checked_at']) if candidates else None
            status=record['status'] if configured and record else 'unverified' if configured else 'failed'
            detail='模型或所需凭据未填写。' if not configured else '当前生效连接尚未测试。' if not record else (
                '连接测试失败，请检查设置。' if status!='passed' else '此角色连接已验证。' if record['source']==role else '沿用'+record['source']+'的相同生效连接验证；不代表此角色已执行。')
            result.append({'role':role,'status':status,'detail':detail,'checked_at':record['checked_at'] if record else None,
                'verification_source':record['source'] if record else None})
        return result
    except (ValueError,OSError,TypeError,KeyError):
        return [{'role':r['name'],'status':'failed','checked_at':None,'detail':'模型配置无法读取，请检查本地设置。'} for r in ROLES]


def register(app, store, gateway, runner, project, version, preview_origin):
    @app.get('/api/diagnostics')
    async def diagnostics():
        async def docker_status():
            if hasattr(runner,'diagnostics'):
                return await runner.diagnostics()
            # Test doubles or custom runners must not fabricate individual Docker checks.
            return {'cli':None,'daemon':None,'image':await runner.available()}
        docker, preview = await asyncio.gather(docker_status(), preview_status(preview_origin))
        checks = [{'id':'api','label':'工作台 API','status':'passed','detail':'当前管理服务可访问。'}]
        def state(value): return 'unverified' if value is None else 'passed' if value else 'failed'
        checks.extend([
            {'id':'docker_cli','label':'Docker 命令','status':state(docker['cli']),
             'detail':'命令已安装。' if docker['cli'] else '安装 Docker Desktop 后重新检查。',
             'url':'https://docs.docker.com/get-started/get-docker/'},
            {'id':'docker_daemon','label':'Docker 服务','status':state(docker['daemon']),
             'detail':'服务可访问。' if docker['daemon'] else '启动 Docker Desktop，等待服务就绪后重新检查。'},
            {'id':'runner','label':'游戏验证镜像','status':state(docker['image']),
             'detail':'gamedev-runner:1 可用。' if docker['image'] else '先启动 Docker，再在项目根目录执行构建命令。',
             'command':'./scripts/build-runner.sh'},
            {'id':'preview','label':'独立预览服务','status':preview,
             'detail':'已收到独立预览服务的身份响应。' if preview=='passed' else '检查预览配置与端口；默认使用 8081。如需重启，请先结束任务并停止原服务，再执行下方命令。非本机 HTTP 来源不会被自动探测。',
             'command':'.studio-venv/bin/python scripts/start.py'},
        ])
        model_roles=model_diagnostics(app,gateway)
        model_state='failed' if any(r['status']=='failed' for r in model_roles) else 'unverified' if any(r['status']!='passed' for r in model_roles) else 'passed'
        dates=[r['checked_at'] for r in model_roles if r['checked_at']]
        checked_at=max(dates) if dates else None
        count=sum(r['status']=='passed' for r in model_roles)
        remaining='、'.join(r['role'] for r in model_roles if r['status']!='passed')
        detail=f'{count} / 8 个角色的生效连接已验证。'+('共享相同连接时沿用连接证据；角色协议和生成质量需另行验证。' if count==8 else '仍需配置或测试：'+remaining+'。可在模型设置中测试全部角色。')
        checks.append({'id':'model','label':'八角色模型连接','status':model_state,'detail':detail,'checked_at':checked_at,'action':'settings'})
        return {'checked_at':now(),'checks':checks,'ready':all(c['status']=='passed' for c in checks),
                'model_called':False,'model_roles':model_roles}

    @app.get('/api/projects/{pid}/compare')
    async def compare(pid: str, before: str, after: str):
        project(pid)
        a,b=version(before),version(after)
        if a['project_id'] != pid or b['project_id'] != pid:
            raise HTTPException(400,'只能对比同一项目内的版本')
        return compare_versions(a,b)
