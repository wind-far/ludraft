"""Project organization and explicit, verified editing operations."""
import json
import shutil
from pathlib import Path
from fastapi import HTTPException
from .db import now, uid
from .files import copy_source
from .models import ProjectUpdate, PlanEdit, ParameterEdit, Plan
from .parameters import update_config
from .lineage import resolve


def register(app, store, workflow, runner, project, run, version, writable, idle):
    @app.post('/api/projects/{pid}/open')
    async def opened(pid: str):
        project(pid)
        store.execute("INSERT INTO project_meta(project_id,last_opened) VALUES(?,?) ON CONFLICT(project_id) DO UPDATE SET last_opened=excluded.last_opened", (pid, now()))
        return {'ok': True}

    @app.put('/api/projects/{pid}')
    async def update_project(pid: str, req: ProjectUpdate):
        project(pid)
        idle(pid)
        if req.title is not None and not req.title.strip():
            raise HTTPException(422, '项目名称不能为空')
        store.execute('INSERT OR IGNORE INTO project_meta(project_id) VALUES(?)', (pid,))
        if req.title is not None:
            store.execute('UPDATE project_meta SET display_name=? WHERE project_id=?', (req.title.strip(), pid))
        if req.state is not None:
            store.execute('UPDATE project_meta SET state=? WHERE project_id=?', (req.state, pid))
        return project(pid)

    @app.post('/api/projects/{pid}/duplicate', status_code=201)
    async def duplicate(pid: str):
        original = project(pid)
        if original['state'] == 'trash':
            raise HTTPException(409, '请先恢复项目')
        if not original['active_version']:
            raise HTTPException(409, '只有可玩版本可以复制')
        base = version(original['active_version'])
        if not json.loads(base['evidence']).get('passed'):
            raise HTTPException(409, '来源版本缺少通过的验证证据')
        from .project_files import manifest
        from .artifacts import binding_errors
        if manifest(Path(base['path'])) is not None and binding_errors(Path(base['path']),json.loads(base['evidence'])):
            raise HTTPException(409,'来源版本的源码、素材或构建证据已变化，不能复制')
        new_pid, rid, vid = uid(), uid(), uid()
        dest = store.root / 'versions' / vid
        try:
            copy_source(Path(base['path']), dest)
            shutil.copytree(Path(base['path']) / 'dist', dest / 'dist')
            from .artifacts import copy_build_manifest
            copy_build_manifest(Path(base['path']), dest)
            for file in dest.rglob('*'):
                if file.is_file():
                    file.chmod(0o444)
            title = original['title'][:75] + ' · 副本'
            timestamp = now()
            with store.lock, store.con:
                store.con.execute('INSERT INTO projects VALUES(?,?,?,?)', (new_pid, title, vid, timestamp))
                store.con.execute('INSERT INTO project_meta(project_id,display_name,last_opened) VALUES(?,?,?)', (new_pid,title,timestamp))
                store.con.execute('INSERT INTO runs(id,project_id,status,requirement,base_version,plan,created_at,finished_at) VALUES(?,?,?,?,?,?,?,?)',
                    (rid,new_pid,'succeeded','复制已验证版本；沿用来源测试证据，未重新调用模型或测试',base['id'],json.dumps(resolve(store,base['id'])['plan'],ensure_ascii=False),timestamp,timestamp))
                store.con.execute('INSERT INTO versions VALUES(?,?,?,?,?,?,?,?)', (vid,new_pid,rid,base['title'],str(dest),base['evidence'],'',timestamp))
                store.con.execute('INSERT INTO events(run_id,role,kind,payload,created_at) VALUES(?,?,?,?,?)',
                    (rid,'system','duplicated',json.dumps({'message':'已复制可玩版本。验证证据来自原版，未重新运行测试。',
                     'source_version':base['id'],'version_id':vid},ensure_ascii=False),timestamp))
        except Exception:
            if dest.exists():
                shutil.rmtree(dest)
            raise
        return {'project_id':new_pid,'run_id':rid}

    @app.put('/api/runs/{rid}/plan')
    async def edit_plan(rid: str, req: PlanEdit):
        async with workflow.control(rid):
            from .messages import check_revision
            check_revision(store,rid,req.expected_revision)
            r = run(rid)
            writable(r['project_id'])
            from .routing import options
            if options(store,rid).get('route',{}).get('task_type')=='research':
                raise HTTPException(409,'调研范围请通过补充需求重新生成，不能用玩法编辑覆盖')
            if options(store,rid).get('route',{}).get('task_type')=='review':
                raise HTTPException(409,'审查范围请通过补充需求重新生成，不能用玩法编辑覆盖')
            if options(store,rid).get('route',{}).get('task_type')=='doc':
                raise HTTPException(409,'文档范围请通过补充需求重新生成，不能用玩法编辑覆盖')
            if options(store,rid).get('route',{}).get('task_type')=='test':
                raise HTTPException(409,'测试范围请通过补充需求重新生成，不能用玩法编辑覆盖')
            if options(store,rid).get('route',{}).get('task_type')=='config':
                raise HTTPException(409,'配置提案请通过补充需求重新生成，不能用玩法编辑覆盖已展示参数')
            if r['status'] != 'waiting_confirmation':
                raise HTTPException(409, '只有等待确认的玩法可以编辑')
            task = workflow.tasks.get(rid)
            if task:
                await task
            changed = store.execute("UPDATE runs SET plan=? WHERE id=? AND status='waiting_confirmation' AND plan=?",
                                    (req.plan.model_dump_json(), rid, req.expected_plan))
            if changed != 1:
                raise HTTPException(409, '玩法或任务状态已改变，请刷新后重试')
            store.execute('UPDATE projects SET title=? WHERE id=?', (req.plan.title, r['project_id']))
            store.event(rid,'user','plan_edited',message='玩法已修改，等待重新确认',plan=req.plan.model_dump())
            return run(rid)

    @app.post('/api/projects/{pid}/parameters', status_code=201)
    async def parameters(pid: str, req: ParameterEdit):
        p = writable(pid)
        idle(pid)
        if p['active_version'] != req.base_version:
            raise HTTPException(409, '当前版本已改变，请重新载入参数')
        base = version(req.base_version)
        try:
            _, before = update_config((Path(base['path'])/'src/config.ts').read_text(), req.parameters)
        except ValueError:
            raise HTTPException(409, '当前配置无法安全调参，请通过自然语言修改')
        changes = {k: v for k, v in req.parameters.model_dump().items() if before[k] != v}
        if not changes:
            raise HTTPException(422, '参数没有变化')
        if not await runner.available():
            raise HTTPException(409, 'Docker 或验证镜像尚未就绪')
        p = writable(pid)
        idle(pid)
        if p['active_version'] != req.base_version:
            raise HTTPException(409, '当前版本已改变，请重新载入参数')
        rid = uid()
        previous = resolve(store,base['id'])['plan']
        summary = '参数调整：' + json.dumps(changes, ensure_ascii=False)
        plan = Plan.model_validate(previous)
        with store.lock, store.con:
            store.con.execute('INSERT INTO runs(id,project_id,status,requirement,base_version,plan,created_at) VALUES(?,?,?,?,?,?,?)',
                              (rid,pid,'queued',summary,base['id'],plan.model_dump_json(),now()))
            store.con.execute('INSERT INTO run_options VALUES(?,?,?)', (rid,'parameters',req.parameters.model_dump_json()))
        store.event(rid,'user','parameters_confirmed',message='用户确认参数调整，创建候选版本并验证；不调用模型',parameters=changes)
        workflow.launch(rid,'parameters')
        return {'project_id':pid,'run_id':rid}
