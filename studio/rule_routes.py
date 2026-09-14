import json
from typing import Annotated
from fastapi import HTTPException,Path
from .models import RoleName
from .role_rules import RuleBook,RulesEdit,RulesRestore,SkillEdit,Conflict,HEADS,STAGES


def register(app,store):
    book=RuleBook(store)

    def guarded(action):
        try:return action()
        except Conflict as exc:raise HTTPException(409,str(exc)) from None
        except ValueError as exc:raise HTTPException(400,str(exc) if not hasattr(exc,'errors') else '规则内容不符合协议') from None
        except (OSError,UnicodeError):raise HTTPException(400,'规则文件无法读取') from None

    @app.get('/api/settings/rules')
    async def settings():
        from .team import RULES
        return guarded(lambda:{'roles':{role:{**book.profile(role),'builtin':RULES[role],
            'upstream':'upstream/agents/'+HEADS[role]+'.md'} for role in HEADS},'catalog':book.catalog(),
            'stages':{key:{'role':role,'source':'upstream/agents/'+HEADS[role]+'/'+filename} for key,(role,filename) in STAGES.items()}})

    @app.get('/api/settings/rules/source')
    async def source(key:str):return guarded(lambda:book.source(key))

    @app.put('/api/settings/rules/{role}')
    async def save(role:RoleName,edit:RulesEdit):return guarded(lambda:book.save(role,edit))

    @app.post('/api/settings/rules/{role}/restore')
    async def restore(role:RoleName,req:RulesRestore):return guarded(lambda:book.restore(role,req))

    @app.get('/api/settings/rules/{role}/history')
    async def history(role:RoleName):
        return [{**r,'config':json.loads(r['config'])} for r in store.query('SELECT * FROM role_rule_revisions WHERE role=? ORDER BY rowid DESC LIMIT 50',(role,))]

    @app.put('/api/settings/skills/{key}')
    async def save_skill(key:Annotated[str,Path(pattern=r'^[a-z][a-z0-9_-]{0,63}$')],edit:SkillEdit):
        return guarded(lambda:book.save_skill('custom/'+key,edit))

    @app.get('/api/steps/{sid}/rules')
    async def snapshot(sid:str):
        row=store.one('SELECT r.id,r.payload,r.created_at FROM step_rules s JOIN rule_snapshots r ON r.id=s.snapshot_id WHERE s.step_id=?',(sid,))
        if not row:raise HTTPException(404,'此步骤没有规则快照；历史记录不补造加载记录')
        return {**row,'payload':json.loads(row['payload'])}
