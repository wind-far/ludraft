import asyncio
import io
import json
import os
import re
import zipfile
from contextlib import asynccontextmanager
from pathlib import Path
from urllib.parse import urlparse
from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.exceptions import RequestValidationError
from fastapi.responses import FileResponse, StreamingResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from .db import Store, ACTIVE, now, uid
from .llm import Gateway, ModelError
from .models import Requirement, Decision, ModelSettings, Rollback, Plan
from .runner import Runner
from .workflow import Workflow
from .uploads import Extractor,material_references,run_materials

ROOT = Path(__file__).resolve().parents[1]
DATA = Path(os.getenv('STUDIO_DATA_DIR', str(ROOT / '.studio'))).resolve()
PREVIEW_ORIGIN = os.getenv('STUDIO_PREVIEW_ORIGIN', 'http://127.0.0.1:8081')


def create_app(data=DATA, gateway=None, runner=None, pages=None):
    store = Store(Path(data))
    gateway = gateway or Gateway(Path(data))
    runner = runner or Runner()
    workflow = Workflow(store, gateway, runner)
    from .opengame_executor import OpenGameExecutor
    workflow.opengame = OpenGameExecutor(store)
    from .web_sources import PublicPages,checked_url
    workflow.pages=pages or PublicPages()
    extractor = Extractor()

    @asynccontextmanager
    async def lifespan(app):
        try:
            app.state.executor_recovery = await workflow.opengame.recover()
            if app.state.executor_recovery.get('busy'):
                # Do not rewrite the live owner's runs or recover its file transactions.
                raise RuntimeError('此数据目录已有 OpenGame 执行，请停止重复启动的服务')
            store.recover()
            yield
        finally:
            await extractor.close()
            await workflow.close()
            store.con.close()

    app = FastAPI(title='Ludraft · 游芽', lifespan=lifespan)
    @app.exception_handler(RequestValidationError)
    async def validation_error(request,exc):
        # Pydantic's default response includes invalid input, including submitted keys.
        return JSONResponse({'detail':[{'loc':e['loc'],'msg':e['msg'],'type':e['type']} for e in exc.errors()]},status_code=422)

    app.state.store, app.state.workflow = store, workflow
    app.state.connection_check = None

    @app.get('/api/settings/opengame/executions')
    async def opengame_executions():
        from .opengame_diagnostics import execution_status
        return execution_status(workflow.opengame)

    @app.get('/api/settings/opengame/diagnostics')
    async def opengame_diagnostics():
        from .opengame_diagnostics import diagnostics
        return await diagnostics(workflow.opengame, gateway)

    @app.post('/api/settings/opengame/recover')
    async def recover_opengame():
        result = await workflow.opengame.recover()
        app.state.executor_recovery = result
        return result

    @app.get('/api/settings/budget')
    async def budget_status():
        from .budget import BudgetLedger
        return BudgetLedger(Path(data)).summary()

    @app.get('/api/templates')
    async def templates():
        from .template_registry import public_templates
        return public_templates()

    allowed = ['http://127.0.0.1:5173', 'http://localhost:5173', 'http://127.0.0.1:8080', 'http://localhost:8080']
    app.add_middleware(CORSMiddleware, allow_origins=allowed, allow_methods=['GET', 'POST', 'PUT'], allow_headers=['Content-Type'])

    @app.middleware('http')
    async def local_boundary(request, call_next):
        # Host validation + Origin guard prevent a generated page/foreign site from controlling the local API.
        if request.url.hostname not in ('127.0.0.1', 'localhost', 'testserver'):
            return JSONResponse({'detail':'Host not allowed'}, status_code=403)
        origin = request.headers.get('origin')
        if request.url.path.startswith('/api') and origin and origin not in allowed:
            return JSONResponse({'detail':'Origin not allowed'}, status_code=403)
        response = await call_next(request)
        response.headers['X-Content-Type-Options'] = 'nosniff'
        response.headers['Cache-Control'] = 'no-store'
        return response

    def project(pid):
        p = store.one("SELECT p.*, COALESCE(m.display_name,p.title) AS display_title, COALESCE(m.state,'active') AS state, m.last_opened FROM projects p LEFT JOIN project_meta m ON p.id=m.project_id WHERE p.id=?", (pid,))
        if p:
            p['title'] = p.pop('display_title')
        if not p:
            raise HTTPException(404, '项目不存在')
        return p

    def run(rid):
        value = store.run(rid)
        if not value:
            raise HTTPException(404, '任务不存在')
        return value

    def version(vid):
        value = store.one('SELECT * FROM versions WHERE id=?', (vid,))
        if not value:
            raise HTTPException(404, '版本不存在')
        return value

    def writable(pid):
        p = project(pid)
        if p['state'] != 'active':
            raise HTTPException(409, '请先恢复项目，再执行修改')
        return p

    def idle(pid):
        if store.one("SELECT id FROM runs WHERE project_id=? AND status IN ('queued','running','waiting_confirmation','testing')", (pid,)):
            raise HTTPException(409, '请先完成或取消当前任务')

    from .project_routes import register
    register(app, store, workflow, runner, project, run, version, writable, idle)

    from .discovery import register as register_discovery
    register_discovery(app, store, gateway, runner, project, version, PREVIEW_ORIGIN)

    from .team_routes import register as register_team
    register_team(app, store, gateway, run)

    from .messages import register as register_messages, pending as pending_questions, history as message_history, revision as message_revision, check_revision
    register_messages(app, store, workflow, run, writable)

    from .rule_routes import register as register_rules
    register_rules(app, store)

    from .uploads import register as register_uploads
    register_uploads(app, store, extractor, run)

    from .reports import register as register_reports
    register_reports(app, store, run)

    def model_identity():
        return gateway.configuration_id() if hasattr(gateway, 'configuration_id') else json.dumps(gateway.public(),sort_keys=True)

    def new_run(pid, text, task_type='auto', materials=(), code_review_id=None, research_urls=(), research_choice=None):
        p = writable(pid)
        if research_urls and task_type!='research':raise HTTPException(400,'公开网页来源只用于方向调研任务')
        try:urls=list(dict.fromkeys(str(checked_url(url)) for url in research_urls))
        except ValueError as exc:raise HTTPException(400,str(exc)) from None
        if research_choice:
            if task_type!='feature':raise HTTPException(400,'调研方向只用于发起功能开发')
            row=store.one("""SELECT p.payload FROM run_reports p JOIN runs r ON r.id=p.run_id
                WHERE r.id=? AND r.project_id=? AND r.base_version IS ? AND r.status='succeeded' AND p.kind='research'""",(research_choice.run_id,pid,p['active_version']))
            if not row or research_choice.direction_id not in [d['id'] for d in json.loads(row['payload'])['result']['directions']]:
                raise HTTPException(409,'调研报告、所选方向或基准版本不匹配，请重新选择')
        if code_review_id:
            if task_type!='bugfix':raise HTTPException(400,'指定审查报告只用于修复问题任务')
            report=store.one("""SELECT r.id FROM runs r JOIN run_reports p ON p.run_id=r.id
                WHERE r.id=? AND r.project_id=? AND r.base_version=? AND r.status='succeeded' AND p.kind='review'""",(code_review_id,pid,p['active_version']))
            if not report:raise HTTPException(409,'审查报告不属于当前可玩版本或未通过报告门禁，请重新选择')
        if task_type=='review' and not p['active_version']:
            raise HTTPException(409,'代码审查需要已有可玩版本，请先创建游戏')
        if task_type=='test' and not p['active_version']:
            raise HTTPException(409,'独立测试需要已有可玩版本，请先创建游戏')
        if task_type=='config' and not p['active_version']:
            raise HTTPException(409,'配置调整需要已有可玩版本，请先创建游戏')
        if store.one("SELECT id FROM runs WHERE project_id=? AND status IN ('queued','running','waiting_confirmation','testing')", (pid,)):
            raise HTTPException(409, '该项目已有执行中或等待确认的任务，请先完成或取消')
        rid = uid()
        store.execute('INSERT INTO runs(id,project_id,status,requirement,base_version,created_at) VALUES(?,?,?,?,?,?)',
                      (rid, pid, 'queued', text, p['active_version'], now()))
        config={'requested_type':task_type}
        if urls:config['research_urls']=urls
        if research_choice:config.update(research_source=research_choice.run_id,research_choice=research_choice.model_dump())
        if code_review_id:config['code_review_source']=code_review_id
        store.execute('INSERT INTO run_options VALUES(?,?,?)', (rid,'team8',json.dumps(config)))
        for material in materials:
            store.execute('INSERT INTO run_materials VALUES(?,?,?)',(rid,material['upload_id'],json.dumps(material,ensure_ascii=False)))
        if materials:store.event(rid,'user','materials_attached',message=f'已引用 {len(materials)} 份核对后的需求材料',materials=[{'name':m['name'],'upload_id':m['upload_id'],'reviewed_sha256':m['reviewed_sha256']} for m in materials])
        store.event(rid, 'system', 'queued', message='需求已进入八角色协作，先明确范围与玩法')
        workflow.launch(rid, 'plan')
        return {'project_id':pid, 'run_id':rid}

    @app.get('/api/health')
    async def health():
        return {'status':'ok', 'runner_available':await runner.available(), 'model':gateway.public()}

    @app.get('/api/settings/model')
    async def settings():
        return gateway.public()

    @app.put('/api/settings/model')
    async def save_settings(settings: ModelSettings):
        try:
            saved = gateway.save(settings)
            app.state.connection_check = None
            return saved
        except ValueError as e:
            raise HTTPException(400, str(e))

    @app.post('/api/settings/model/test')
    async def test_settings():
        identity = model_identity()
        try:
            result, metadata = await gateway.call('策划', '为 match3 三消游戏生成玩法方案：相邻交换、消除连锁、20 步达成目标分数。', Plan)
            if identity != model_identity():
                raise HTTPException(409, '模型配置已改变，请重新测试当前配置')
            app.state.connection_check = {'identity':identity, 'status':'passed', 'checked_at':now()}
            return {'ok':True, 'title':result.title, **metadata}
        except ModelError as e:
            if identity == model_identity():
                app.state.connection_check = {'identity':identity, 'status':'failed', 'checked_at':now()}
            raise HTTPException(400, str(e))

    @app.get('/api/projects')
    async def projects():
        rows = store.query("""SELECT p.*, COALESCE(m.display_name,p.title) AS display_title,
            COALESCE(m.state,'active') AS state, m.last_opened,
            (SELECT status FROM runs r WHERE r.project_id=p.id ORDER BY r.created_at DESC LIMIT 1) AS last_status
            FROM projects p LEFT JOIN project_meta m ON m.project_id=p.id
            ORDER BY COALESCE(m.last_opened,p.created_at) DESC""")
        for row in rows:
            row['title'] = row.pop('display_title')
        return rows

    @app.post('/api/projects', status_code=201)
    async def create_project(req: Requirement):
        if req.research_choice:raise HTTPException(400,'采用调研方向需要在来源项目内发起')
        if req.research_urls and req.task_type!='research':raise HTTPException(400,'公开网页来源只用于方向调研任务')
        try:
            for url in req.research_urls:checked_url(url)
        except ValueError as exc:raise HTTPException(400,str(exc)) from None
        if req.code_review_id:raise HTTPException(400,'引用代码审查修复需要在来源项目内发起')
        if req.task_type=='review':raise HTTPException(400,'代码审查需要已有可玩版本，请在作品内发起')
        if req.task_type=='test':raise HTTPException(400,'独立测试需要已有可玩版本，请在作品内发起')
        if req.task_type=='config':raise HTTPException(400,'配置调整需要已有可玩版本，请在作品内发起修改')
        materials=material_references(store,req.materials)
        pid = uid()
        store.execute('INSERT INTO projects VALUES(?,?,?,?)', (pid, req.text[:32], None, now()))
        return new_run(pid, req.text, req.task_type, materials, research_urls=req.research_urls)

    @app.get('/api/projects/{pid}')
    async def get_project(pid: str):
        p = project(pid)
        runs = store.query("SELECT r.*,COALESCE(o.kind,'legacy') AS engine FROM runs r LEFT JOIN run_options o ON r.id=o.run_id WHERE project_id=? ORDER BY created_at DESC", (pid,))
        versions = store.query('SELECT id,run_id,title,created_at FROM versions WHERE project_id=? ORDER BY created_at DESC', (pid,))
        from .routing import options
        for r in runs:
            r['approval_revision']=message_revision(store,r['id'])
            r['task_type']=options(store,r['id']).get('route',{}).get('task_type')
            r['has_report']=bool(store.one('SELECT run_id FROM run_reports WHERE run_id=?',(r['id'],)))
        return {**p, 'runs':runs, 'versions':versions, 'preview_origin':PREVIEW_ORIGIN}

    @app.post('/api/projects/{pid}/runs', status_code=201)
    async def modify(pid: str, req: Requirement):
        return new_run(pid, req.text, req.task_type, material_references(store,req.materials),req.code_review_id,req.research_urls,req.research_choice)

    @app.post('/api/runs/{rid}/decision')
    async def decide(rid: str, req: Decision):
        async with workflow.control(rid):
            r = run(rid)
            writable(r['project_id'])
            if r['status'] != 'waiting_confirmation' or not r['plan'] or pending_questions(store,rid):
                raise HTTPException(409, '该任务不处于等待确认状态')
            if req.approve:
                check_revision(store,rid,req.expected_revision)
                from .routing import options
                config=options(store,rid)
                if config.get('route',{}).get('task_type')=='config' and req.expected_config_revision!=config.get('config_revision'):
                    raise HTTPException(409,'参数提案已改变或未核对，请重新查看后确认')
                if config.get('route',{}).get('task_type') in ('test','doc','review','research') and req.expected_scope_revision!=config.get('scope_revision'):
                    raise HTTPException(409,'任务范围已改变或尚未核对，请重新查看后确认')
                # Planner task may still be completing its callback on the same event loop.
                task = workflow.tasks.get(rid)
                if task:
                    await task
                changed = store.execute("UPDATE runs SET status='queued' WHERE id=? AND status='waiting_confirmation' AND plan IS NOT NULL AND (? IS NULL OR plan=?)", (rid, req.expected_plan, req.expected_plan))
                if changed != 1:
                    raise HTTPException(409, '任务状态已改变，请刷新后重试')
                store.event(rid, 'user', 'approved', message='用户已确认任务范围')
                workflow.launch(rid, 'implement')
            else:
                await workflow.cancel(rid)
                store.event(rid, 'user', 'rejected', message='已拒绝本轮范围，可输入修改意见重新提交任务')
            return run(rid)

    @app.post('/api/runs/{rid}/cancel')
    async def cancel(rid: str):
        async with workflow.control(rid):
            r = run(rid)
            if r['status'] in ACTIVE:
                await workflow.cancel(rid)
            return run(rid)

    @app.get('/api/runs/{rid}/events')
    async def events(rid: str, request: Request, after: int = 0):
        run(rid)
        try:
            cursor = max(after, int(request.headers.get('last-event-id', '0')))
        except ValueError:
            raise HTTPException(400, '无效的事件游标')
        async def stream():
            nonlocal cursor
            while not await request.is_disconnected():
                rows = store.query('SELECT * FROM events WHERE run_id=? AND id>? ORDER BY id', (rid, cursor))
                for row in rows:
                    cursor = row['id']
                    row['payload'] = json.loads(row['payload'])
                    yield f'id: {cursor}\ndata: {json.dumps(row, ensure_ascii=False)}\n\n'
                yield ': heartbeat\n\n'
                await asyncio.sleep(1)
        return StreamingResponse(stream(), media_type='text/event-stream', headers={'X-Accel-Buffering':'no'})

    @app.get('/api/runs/{rid}/evidence')
    async def evidence(rid: str):
        run(rid)
        return [{**row, 'payload':json.loads(row['payload'])} for row in store.query('SELECT * FROM events WHERE run_id=? ORDER BY id', (rid,))]

    @app.get('/api/versions/{vid}')
    async def get_version(vid: str):
        v = version(vid)
        from .files import source_files
        from .parameters import read_config
        files = source_files(Path(v['path']))
        try:
            config = read_config(files['src/config.ts'])
            parameter_error = None
        except (ValueError,KeyError):
            config = None
            parameter_error = '当前配置含动态表达式或自定义结构，请通过自然语言修改'
        return {key:value for key,value in {**v, 'evidence':json.loads(v['evidence']), 'files':files,
                    'parameters':config,'parameter_error':parameter_error}.items() if key != 'path'}

    @app.get('/api/versions/{vid}/files')
    async def version_files(vid: str):
        from .project_files import inventory, manifest
        from .template_registry import get_template, LEGACY_EDITABLE
        from .file_transactions import workspace_lock
        root=Path(version(vid)['path'])
        try:
            with workspace_lock(root):
                project=manifest(root)
                template=get_template(project.template_id,project.template_version) if project else None
                return {'project':project.model_dump() if project else None,
                        'files':[{**entry,'editable':template.editable(entry['path']) if template else entry['path'] in LEGACY_EDITABLE}
                                 for entry in inventory(root)]}
        except (ValueError,OSError):
            raise HTTPException(409,'版本文件清单无效，请检查版本完整性') from None

    @app.get('/api/versions/{vid}/file')
    async def version_file(vid: str, path: str):
        from .project_files import inventory, safe_name
        from .file_transactions import workspace_lock
        root=Path(version(vid)['path'])
        try:
            safe_name(path)
            with workspace_lock(root):
                entry=next((f for f in inventory(root) if f['path']==path),None)
                if entry is None or not entry['text']:raise HTTPException(404,'文本文件不存在')
                if entry['size']>200_000:raise HTTPException(413,'文件过大，请导出后查看')
                return {**entry,'content':(root/path).read_text(encoding='utf-8')}
        except (ValueError,OSError):
            raise HTTPException(404,'文本文件不可读取') from None

    @app.post('/api/projects/{pid}/rollback')
    async def rollback(pid: str, req: Rollback):
        writable(pid)
        if store.one("SELECT id FROM runs WHERE project_id=? AND status IN ('queued','running','waiting_confirmation','testing')", (pid,)):
            raise HTTPException(409, '请先完成或取消当前任务，再回退版本')
        v = version(req.version_id)
        if v['project_id'] != pid:
            raise HTTPException(400, '版本不属于该项目')
        store.execute('UPDATE projects SET active_version=?,title=? WHERE id=?', (v['id'], v['title'], pid))
        store.event(v['run_id'], 'user', 'rollback', message='用户将此版本设为当前可玩版本', version_id=v['id'])
        return {'active_version':v['id']}

    @app.get('/api/versions/{vid}/export')
    async def export(vid: str):
        v = version(vid)
        base = Path(v['path'])
        from .project_files import manifest, inventory
        from .artifacts import binding_errors, read_artifacts, BUILD_MANIFEST
        try:
            project = manifest(base)
            if project is not None:
                errors = binding_errors(base, json.loads(v['evidence']))
                if errors:
                    raise ValueError('；'.join(errors))
                export_names = [entry['path'] for entry in inventory(base)]
                export_names += ['dist/' + name for name in read_artifacts(base)['files']]
                export_names += [BUILD_MANIFEST]
            else:
                export_names = [f.relative_to(base).as_posix() for f in sorted(base.rglob('*')) if f.is_file() and not f.is_symlink()]
        except (ValueError, OSError):
            raise HTTPException(409, '版本文件与验证记录不一致，无法导出；请重新验证') from None
        buffer = io.BytesIO()
        with zipfile.ZipFile(buffer, 'w', zipfile.ZIP_DEFLATED) as archive:
            for name in export_names:
                archive.writestr(name, (base/name).read_bytes())
            archive.writestr('verification.json', v['evidence'])
            from .exporting import write_startup_files
            write_startup_files(archive, engine=project and project.template_id.split('-')[0])
            from .lineage import resolve
            lineage = resolve(store, vid)
            if lineage['steps']:
                archive.writestr('collaboration.json', json.dumps(lineage['steps'], ensure_ascii=False, indent=2))
            rule_snapshots={}
            for step in lineage['steps']:
                row=store.one('SELECT r.id,r.payload FROM step_rules s JOIN rule_snapshots r ON r.id=s.snapshot_id WHERE s.step_id=?',(step['id'],))
                if row:rule_snapshots[row['id']]=json.loads(row['payload'])
            if rule_snapshots:
                archive.writestr('rules.json',json.dumps(rule_snapshots,ensure_ascii=False,indent=2))
            message_runs={v['run_id'],*(step['run_id'] for step in lineage['steps'])}
            exported_messages={rid:message_history(store,rid) for rid in sorted(message_runs)}
            if any(exported_messages.values()):archive.writestr('messages.json',json.dumps(exported_messages,ensure_ascii=False,indent=2))
            material_runs={v['run_id'],*(step['run_id'] for step in lineage['steps']),*(item['run_id'] for item in lineage['chain'])}
            materials={rid:run_materials(store,rid) for rid in sorted(material_runs)}
            if any(materials.values()):archive.writestr('requirements.json',json.dumps(materials,ensure_ascii=False,indent=2))
            from .reports import referenced_reports
            test_reports=referenced_reports(store,material_runs)
            if test_reports:archive.writestr('test-reports.json',json.dumps(test_reports,ensure_ascii=False,indent=2))
            from .documents import referenced_documents
            doc_reports=referenced_documents(store,material_runs)
            if doc_reports:archive.writestr('document-history.json',json.dumps(doc_reports,ensure_ascii=False,indent=2))
            from .code_review import referenced_reviews
            code_reviews=referenced_reviews(store,material_runs)
            if code_reviews:archive.writestr('code-reviews.json',json.dumps(code_reviews,ensure_ascii=False,indent=2))
            from .research import referenced_research
            research=referenced_research(store,material_runs)
            if research:archive.writestr('research-history.json',json.dumps(research,ensure_ascii=False,indent=2))
            from .routing import options
            selections={rid:options(store,rid)['research_choice'] for rid in material_runs if options(store,rid).get('research_choice')}
            if selections:archive.writestr('research-selections.json',json.dumps(selections,ensure_ascii=False,indent=2))
            archive.writestr('provenance.json', json.dumps({'chain':lineage['chain'], 'plan':lineage['plan'],
                'note':'来源协作记录不代表复制或调参时重新执行；实际版本验证见 verification.json'}, ensure_ascii=False, indent=2))
        buffer.seek(0)
        return StreamingResponse(buffer, media_type='application/zip', headers={'Content-Disposition':f'attachment; filename="game-{vid[:8]}.zip"'})

    if (ROOT / 'frontend/dist').exists():
        app.mount('/', StaticFiles(directory=ROOT / 'frontend/dist', html=True), name='frontend')
    return app


def create_preview_app(data=DATA):
    # Separate origin: no management APIs or secrets in this application.
    app = FastAPI(docs_url=None, redoc_url=None, openapi_url=None)
    root = Path(data) / 'versions'

    @app.get('/health')
    async def preview_health():
        return {'service':'ludraft-preview'}

    @app.get('/v/{vid}/{file:path}')
    async def preview(vid: str, file: str, request: Request):
        if not re.fullmatch('[a-f0-9]{32}', vid):
            raise HTTPException(404)
        file = file or 'index.html'
        from .project_files import manifest, MANIFEST
        project_root=root/vid
        if (project_root/MANIFEST).exists() or (project_root/MANIFEST).is_symlink():
            from .artifacts import artifact_file
            try:
                target,media_type=artifact_file(project_root,file)
            except (ValueError,OSError,TypeError):
                raise HTTPException(404) from None
            # Sandboxed iframes have opaque origins. Grant read-only resource
            # loading to this exact version URL, never the management origin.
            # Phaser creates tiny built-in texture images as data URLs. Only
            # image data is allowed; script/connect destinations remain scoped.
            if request.url.hostname not in ('127.0.0.1','localhost','testserver'):
                raise HTTPException(403)
            base=str(request.base_url).rstrip('/')+f'/v/{vid}/'
            policy=(f"sandbox allow-scripts; default-src 'none'; script-src {base}; "
                    f"style-src {base} 'unsafe-inline'; img-src {base} data:; connect-src {base}; "
                    "base-uri 'none'; form-action 'none'; frame-ancestors http://127.0.0.1:8080 http://localhost:8080 http://127.0.0.1:5173 http://localhost:5173")
            return FileResponse(target,media_type=media_type,headers={
                'Content-Security-Policy':policy,'Access-Control-Allow-Origin':'*',
                'X-Content-Type-Options':'nosniff','Cache-Control':'public, max-age=31536000, immutable'})
        if file not in ('index.html', 'style.css', 'dist/main.js', 'dist/game.js', 'dist/config.js'):
            raise HTTPException(404)
        target = root / vid / file
        if not target.is_file() or target.is_symlink():
            raise HTTPException(404)
        return FileResponse(target, headers={
            'Content-Security-Policy':"sandbox allow-scripts; default-src 'none'; script-src 'self'; style-src 'self'; connect-src 'none'; img-src 'none'; base-uri 'none'; form-action 'none'; frame-ancestors http://127.0.0.1:8080 http://localhost:8080 http://127.0.0.1:5173 http://localhost:5173",
            'Access-Control-Allow-Origin':'*', 'X-Content-Type-Options':'nosniff',
            'Cache-Control':'public, max-age=31536000, immutable'})
    return app
