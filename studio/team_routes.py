import time
from fastapi import HTTPException
from .models import RoleName
from .connections import RoleConnection, ConnectionProbe, PROVIDERS
from .llm import ModelError
from .db import now
from .team import ROLES
from .team_models import TeamModels
from .lineage import decoded_steps, resolve
from .routing import options


def register(app, store, gateway, run):
    checks={}
    app.state.role_connection_checks=checks

    def record_failure(role,identity):
        try:
            if identity and identity==gateway.role_identity(role):checks[role]={'identity':identity,'status':'failed','checked_at':now()}
        except (ValueError,OSError,TypeError):pass

    def require_connections():
        if not hasattr(gateway,'public_connection'):raise HTTPException(400,'当前适配器不支持独立连接')

    def checked(role):
        record=checks.get(role)
        return {k:v for k,v in record.items() if k!='identity'} if record and record['identity']==gateway.role_identity(role) else {'status':'unverified'}

    @app.get('/api/settings/connections')
    async def connections():
        require_connections()
        try:return {'providers':PROVIDERS,'roles':{r['name']:{**gateway.public_connection(r['name']),'check':checked(r['name'])} for r in ROLES}}
        except (ValueError,OSError,TypeError):raise HTTPException(400,'角色连接配置无法读取') from None

    @app.put('/api/settings/connections/{role}')
    async def save_connection(role:RoleName,settings:RoleConnection):
        require_connections()
        try:return gateway.save_connection(role,settings)
        except (ValueError,OSError,TypeError) as exc:
            raise HTTPException(400,str(exc) if isinstance(exc,ValueError) and not hasattr(exc,'errors') else '角色连接无法保存，请检查配置') from None

    @app.post('/api/settings/connections/{role}/test')
    async def test_connection(role:RoleName):
        require_connections();started=time.monotonic();identity=None
        try:
            async with app.state.workflow.model_limit:
                identity=gateway.role_identity(role)
                result,metadata=await gateway.call(role,'连接检查：用 summary 简短说明你在网页游戏团队中的职责，不声称完成生成或测试。',ConnectionProbe)
                ConnectionProbe.model_validate(result.model_dump())
                if identity!=gateway.role_identity(role):raise HTTPException(409,'测试期间配置已改变，请重新测试当前连接')
                checks[role]={'identity':identity,'status':'passed','checked_at':now(),'elapsed_seconds':round(time.monotonic()-started,2)}
                return {'ok':True,'role':role,**checked(role),'model':metadata.get('model'),'usage':metadata.get('usage',{})}
        except ModelError as exc:
            record_failure(role,identity)
            raise HTTPException(400,str(exc)) from None
        except (ValueError,OSError,TypeError,AttributeError):
            record_failure(role,identity)
            raise HTTPException(400,'连接配置或测试响应不符合协议，未标记测试通过') from None

    @app.get('/api/settings/team')
    async def settings():
        try:
            models=gateway.team_models() if hasattr(gateway,'team_models') else {}
        except (ValueError,OSError):
            raise HTTPException(400,'角色模型配置无法读取')
        return {'roles':ROLES,'models':models,'default_model':gateway.public()['model']}

    @app.put('/api/settings/team')
    async def save(settings:TeamModels):
        if not hasattr(gateway,'save_team_models'):
            raise HTTPException(400,'当前模型适配器不支持角色模型设置')
        result=gateway.save_team_models(settings)
        app.state.connection_check=None
        return {'models':result}

    @app.get('/api/runs/{rid}/team')
    async def team(rid:str):
        r=run(rid)
        option=store.one('SELECT kind FROM run_options WHERE run_id=?',(rid,))
        steps=decoded_steps(store,rid)
        version=store.one('SELECT id FROM versions WHERE run_id=?',(rid,))
        lineage=resolve(store,version['id']) if version else resolve(store,r['base_version']) if r['base_version'] else None
        inherited=[{**step,'inherited':True} for step in lineage['steps'] if step['run_id']!=rid] if lineage else []
        return {'mode':option['kind'] if option else 'legacy','status':r['status'],'roles':ROLES,'steps':steps,
                'route':options(store,rid).get('route'),'inherited_steps':inherited,'lineage':lineage['chain'] if lineage else []}
