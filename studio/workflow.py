import asyncio
import json
import os
import shutil
import time
from pathlib import Path
from .db import ACTIVE, TERMINAL, now, uid
from .files import TEMPLATE, copy_source, source_files, apply_changes, diff_sources
from .models import Plan, Changes
from .runner import RunnerError
from .messages import NeedsInput
from .verification import run_checked, evidence_errors

CONTRACT = '''固定 Canvas 模板。只能修改 src/config.ts、src/game.ts、style.css，输出完整文件内容。
不要修改 main.ts、index.html、构建配置、测试或依赖。不得引入外部依赖、网络请求或动态执行代码。
config 必须保留 title,mode,speed,lives,spawnMs,fallSpeed,duration,background,playerColor,targetColor,hazardColor。
mode 是 collector/dodger/clicker。speed (0,1500]；lives 整数[1,10]；spawnMs[100,10000]；fallSpeed(0,1000]；duration[5,600]。
保留 Game 导出与字段 x,score,lives,status,items,elapsed 和 start/spawn/click/tick 签名，使不可修改的 main.ts 正常运行。
当前新版入口支持按住画布左右拖动和键盘移动，点击模式点按目标；elapsed 为已用秒数，用于剩余时间显示。不得删除新模板的触屏和倒计时能力。
根据已确认玩法修改；优先通过 config 调整。只返回实际有变化的文件。不要说测试通过，测试由工具执行。'''


MATCH3_CONTRACT = """固定 TypeScript Canvas 三消模板，mode 必须为 match3。只能修改 src/config.ts、src/game.ts、style.css。
不能修改 main.ts、index.html、测试、构建或依赖；不得引入网络请求和动态执行代码。
配置保留 title,mode,moves,targetScore,gemTypes,background,playerColor,targetColor,hazardColor。
moves 整数[5,100]，targetScore 整数[100,20000]，gemTypes 整数[4,6]，颜色使用六位十六进制。
Game 固定 8×8 board 数组（宝石编号0..gemTypes-1），保留 score,moves,status(ready/playing/over),outcome(won/lost/null),selected,cursor,phase,phaseClock,matches,cascade,maxCascade,shuffles,message,random 属性。
保留 start(),select(index),swap(a,b),adjacent(a,b),findMatches(board?),legalMoves(),ensurePlayable(),tick(dt) 方法。
相邻交换形成三个以上同色才消耗一步，无效交换回退；消除后下落补位并结算连锁；死局重排不额外加分扣步；目标达成判胜，步数耗尽判负，重开清空状态。
只返回实际变更文件，不宣称已测试。试玩和验证由固定 main.ts 与隔离工具完成。"""


PLANNING_CONTRACT = '''本地 TypeScript Canvas 网页游戏工作台，当前支持四种玩法，按用户需求选择而非默认三消：
collector 接物：左右移动接金币、躲炸弹，得分、生命与倒计时。
dodger 躲避：左右移动躲落下的危险物，生存计分、生命与倒计时。
clicker 点击：点击目标得分，误点危险物扣命，生命与倒计时。
match3 三消：8×8 相邻交换、消除连锁、步数和目标分数。
先明确玩法类型、操作、规则和可观察验收，确认后再选择对应固定模板。
不把未支持的其他玩法强行改成三消；超出模板能力时说明差距并请求澄清。
仅可改 src/config.ts、src/game.ts、style.css；不得修改固定入口、构建、测试或引入外部依赖。'''


class Workflow:
    contract = CONTRACT
    def contract_for(self,run):
        plan=json.loads(run['plan']) if run.get('plan') else None
        mode=plan['mode'] if plan else None
        # Report scopes use Plan for approval storage, not for selecting a game.
        from .routing import options
        route=options(self.store,run['id']).get('route',{}) if run.get('id') else {}
        if route.get('task_type') in ('research','doc','review','test'):
            mode=None
        if mode is None and run.get('base_version'):
            base=self.store.one('SELECT evidence FROM versions WHERE id=?',(run['base_version'],))
            if base:mode=json.loads(base['evidence']).get('config',{}).get('mode')
        return PLANNING_CONTRACT if mode is None else MATCH3_CONTRACT if mode=='match3' else CONTRACT
    def __init__(self, store, gateway, runner):
        self.store, self.gateway, self.runner = store, gateway, runner
        from .web_sources import PublicPages
        self.pages=PublicPages()
        self.tasks = {}
        self.controls = {}
        self.paused = set()
        self.limit = asyncio.Semaphore(2)
        self.model_limit = asyncio.Semaphore(3)

    def control(self, run_id):
        return self.controls.setdefault(run_id, asyncio.Lock())

    def launch(self, run_id, phase):
        if run_id in self.tasks and not self.tasks[run_id].done():
            raise ValueError('任务正在执行')
        task = asyncio.create_task(self.work(run_id, phase))
        self.tasks[run_id] = task
        task.add_done_callback(lambda finished: self.tasks.pop(run_id, None) if self.tasks.get(run_id) is finished else None)

    async def cancel(self, run_id):
        self.store.execute("UPDATE runs SET status='cancelled',finished_at=? WHERE id=? AND status NOT IN ('succeeded','failed','cancelled')", (now(), run_id))
        task = self.tasks.get(run_id)
        if task and not task.done():
            task.cancel()
            try:
                await task
            except asyncio.CancelledError:
                pass
        self.store.event(run_id, 'system', 'cancelled', message='任务已取消，上一可玩版本保持不变')

    async def close(self):
        tasks = list(self.tasks.values())
        for task in tasks:
            task.cancel()
        await asyncio.gather(*tasks, return_exceptions=True)

    async def call(self, run_id, role, prompt, schema):
        started = time.monotonic()
        self.store.event(run_id, role, 'model_start', message='正在请求模型')
        try:
            result, metadata = await self.gateway.call(role, prompt, schema)
        except Exception as exc:
            self.store.event(run_id, role, 'model_error', message='模型调用失败，未生成有效交付物',
                             elapsed_seconds=round(time.monotonic()-started, 2), **getattr(exc,'metadata',{}))
            raise
        self.store.event(run_id, role, 'model_result', elapsed_seconds=round(time.monotonic()-started, 2), **metadata)
        return result

    async def work(self, run_id, phase):
        try:
            async with self.limit:
                run = self.store.run(run_id)
                if not run or run['status'] != 'queued':
                    return
                self.store.execute("UPDATE runs SET status='running' WHERE id=?", (run_id,))
                options = self.store.one('SELECT * FROM run_options WHERE run_id=?', (run_id,))
                if options and options['kind']=='team8':
                    from .team import Team
                    team = Team(self)
                    if phase == 'plan':
                        await team.plan(run)
                    else:
                        await team.implement(run)
                elif phase == 'plan':
                    base = self.store.one('SELECT * FROM versions WHERE id=?', (run['base_version'],)) if run['base_version'] else None
                    previous = ''
                    if base:
                        previous_run = self.store.run(base['run_id'])
                        previous = json.dumps({'plan': json.loads(previous_run['plan']), 'files': source_files(Path(base['path'])),
                                               'evidence': json.loads(base['evidence'])}, ensure_ascii=False)
                    prompt = ('为本地单人 2D 网页小游戏形成简洁中文玩法方案。仅支持 collector 接物、dodger 躲避、clicker 点击目标。'
                              '验收条件具体可观察，明确超出模板的需求不纳入本版。\n用户需求：'+run['requirement']+'\n已有版本：'+previous)
                    plan = await self.call(run_id, '策划', prompt, Plan)
                    self.store.execute("UPDATE runs SET status='waiting_confirmation',plan=? WHERE id=?", (plan.model_dump_json(), run_id))
                    self.store.execute('UPDATE projects SET title=? WHERE id=?', (plan.title, run['project_id']))
                    self.store.event(run_id, '策划', 'plan_ready', message='玩法已生成，等待你确认后才开始编码', plan=plan.model_dump())
                elif phase == 'parameters':
                    await self.adjust_parameters(run)
                else:
                    await self.implement(run)
        except NeedsInput:
            self.store.execute("UPDATE runs SET status='waiting_confirmation',plan=NULL,error=NULL WHERE id=? AND status NOT IN ('cancelled','failed','succeeded')", (run_id,))
            self.store.event(run_id, 'system', 'input_required', message='团队需要你补充信息；答复后会重新策划并确认玩法')
        except asyncio.CancelledError:
            if run_id not in self.paused and self.store.run(run_id)['status'] not in TERMINAL:
                self.store.execute("UPDATE runs SET status='cancelled',finished_at=? WHERE id=?", (now(), run_id))
            raise
        except Exception as exc:
            # External exception strings may contain model credentials; never persist them verbatim.
            from .llm import ModelError
            message = str(exc) if isinstance(exc, (ModelError, ValueError, RunnerError)) else '执行工具失败，请检查 Docker、运行日志或服务端控制台后重试。'
            self.store.execute("UPDATE runs SET status='failed',error=?,finished_at=? WHERE id=? AND status != 'cancelled'", (message, now(), run_id))
            self.store.event(run_id, 'system', 'failed', message=message)

    async def implement(self, run):
        run_id = run['id']
        if not await self.runner.available():
            raise ValueError('Docker 或 gamedev-runner:1 镜像不可用。请启动 Docker 并运行 scripts/build-runner.sh。')
        workspace = self.store.root / 'candidates' / run_id
        base = self.store.one('SELECT * FROM versions WHERE id=?', (run['base_version'],)) if run['base_version'] else None
        source = Path(base['path']) if base else TEMPLATE
        copy_source(source, workspace)
        original = source_files(source)
        last_evidence = json.loads(base['evidence']) if base else None
        plan = json.loads(run['plan'])
        for attempt in range(3):
            self.store.execute("UPDATE runs SET status='running',repairs=? WHERE id=?", (attempt, run_id))
            prompt = CONTRACT + '\n需求：'+run['requirement']+'\n确认玩法：'+run['plan']
            prompt += '\n当前源文件：'+json.dumps(source_files(workspace), ensure_ascii=False)
            prompt += '\n最近实际测试结果：'+json.dumps(last_evidence, ensure_ascii=False)
            if attempt:
                prompt += '\n上次验证失败。这是第 '+str(attempt)+' 次修复，请针对错误修复，保留其他玩法。'
            changes = await self.call(run_id, '程序', prompt, Changes)
            apply_changes(workspace, changes)
            self.store.event(run_id, '程序', 'files_changed', message=changes.summary, files=[f.path for f in changes.files], attempt=attempt)
            self.store.execute("UPDATE runs SET status='testing' WHERE id=?", (run_id,))
            self.store.event(run_id, 'QA', 'testing', message='在隔离容器中构建并执行浏览器交互测试')
            last_evidence = await run_checked(self.runner,workspace,run_id,plan['mode'])
            self.store.event(run_id, 'QA', 'test_result', **last_evidence)
            if last_evidence.get('passed'):
                self.publish(run, workspace, original, last_evidence)
                return
        raise ValueError('初次生成及两轮修复均未通过验证。已保留失败证据和上一可玩版本。')

    async def adjust_parameters(self, run):
        from .models import Parameters, Match3Parameters
        from .parameters import update_config, read_config
        base = self.store.one('SELECT * FROM versions WHERE id=?', (run['base_version'],))
        options = self.store.one('SELECT * FROM run_options WHERE run_id=?', (run['id'],))
        parameter_model = Match3Parameters if read_config((Path(base['path'])/'src/config.ts').read_text())['mode']=='match3' else Parameters
        requested = parameter_model.model_validate_json(options['payload'])
        workspace = self.store.root / 'candidates' / run['id']
        copy_source(Path(base['path']), workspace)
        original = source_files(workspace)
        content, before = update_config(original['src/config.ts'], requested)
        (workspace / 'src/config.ts').write_text(content)
        changes = {key: {'before': before[key], 'after': value} for key, value in requested.model_dump().items() if before[key] != value}
        self.store.event(run['id'], '程序', 'files_changed', message='已生成参数变更，等待真实验证；未调用模型',
                         files=['src/config.ts'], parameters=changes)
        self.store.execute("UPDATE runs SET status='testing' WHERE id=?", (run['id'],))
        self.store.event(run['id'], 'QA', 'testing', message='在隔离容器中验证参数变更')
        evidence = await run_checked(self.runner,workspace,run['id'],json.loads(run['plan'])['mode'])
        if evidence.get('passed'):
            config = evidence.get('config', {})
            evidence['parameter_match'] = all(config.get(k) == v for k, v in requested.model_dump().items())
            if not evidence['parameter_match'] or config.get('mode') != json.loads(run['plan'])['mode']:
                evidence['passed'] = False
                evidence['error'] = '实际运行参数或玩法与本轮确认内容不一致'
        self.store.event(run['id'], 'QA', 'test_result', **evidence)
        if not evidence.get('passed'):
            raise ValueError('参数调整未通过验证，上一可玩版本已保留。请查看测试结果。')
        self.publish(run, workspace, original, evidence)

    def publish(self, run, workspace, original, evidence):
        # An await-free publication and SQLite transaction prevent cancellation/rollback races.
        current=self.store.run(run['id'])
        if current['status'] == 'cancelled':
            return
        if current['status'] not in ('running','testing'):
            raise ValueError('当前任务不在可发布阶段，不能创建可玩版本')
        errors=evidence_errors(evidence,json.loads(current['plan'])['mode'])
        from .project_files import manifest
        from .artifacts import binding_errors, copy_build_manifest
        if manifest(workspace) is not None:
            errors.extend(binding_errors(workspace,evidence))
        if errors:
            self.store.event(run['id'],'system','publish_rejected',message='发布门禁拒绝：实际验证证据不完整或未通过',errors=errors)
            raise ValueError('发布门禁未通过：'+'；'.join(errors))
        version_id = uid()
        dest = self.store.root / 'versions' / version_id
        copy_source(workspace, dest)
        shutil.copytree(workspace / 'dist', dest / 'dist')
        copy_build_manifest(workspace, dest)
        for file in dest.rglob('*'):
            if file.is_file():
                file.chmod(0o444)
        diff = diff_sources(original, source_files(dest))
        with self.store.lock, self.store.con:
            self.store.con.execute('INSERT INTO versions VALUES(?,?,?,?,?,?,?,?)',
                (version_id, run['project_id'], run['id'], json.loads(run['plan'])['title'], str(dest), json.dumps(evidence, ensure_ascii=False), diff, now()))
            self.store.con.execute('UPDATE projects SET active_version=? WHERE id=?', (version_id, run['project_id']))
            self.store.con.execute("UPDATE runs SET status='succeeded',finished_at=? WHERE id=?", (now(), run['id']))
        self.store.event(run['id'], 'system', 'published', message='构建与核心交互测试通过；可试玩并人工评价玩法', version_id=version_id)
