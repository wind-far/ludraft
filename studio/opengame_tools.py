"""Task-scoped tools for the pinned OpenGame executor.

This service owns a candidate, never a user-selected root. It does not launch an
agent or grant shell access. The scheduler must close it when its task ends.
"""
import asyncio
import hashlib
import json
import secrets
import time
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse, Response
from pydantic import Field, ValidationError
from starlette.middleware.trustedhost import TrustedHostMiddleware

from .models import Strict
from .project_files import (ProjectChanges, apply_project_changes, inventory,
                            manifest, safe_name, source_digest)
from .runner import Runner, RunnerError
from .template_registry import get_template

PROTOCOL = '2025-06-18'
MAX_BODY = 2 * 1024 * 1024


class ListFiles(Strict):
    offset: int = Field(default=0, ge=0, le=512, strict=True)
    limit: int = Field(default=100, ge=1, le=100, strict=True)


class ReadFile(Strict):
    path: str = Field(max_length=240)
    offset: int = Field(default=0, ge=0, le=1_000_000, strict=True)
    limit: int = Field(default=16000, ge=1, le=32000, strict=True)


class VerifyProject(Strict):
    base_digest: str = Field(pattern=r'^[a-f0-9]{64}$')


TOOL_MODELS = {
    'project_inventory': (ListFiles, 'List candidate source files, writable scope and current source digest.'),
    'project_read': (ReadFile, 'Read one UTF-8 source file in character ranges; no binary or host files.'),
    'project_apply': (ProjectChanges, 'Atomically apply business-file changes against the current source digest.'),
    'project_verify': (VerifyProject, 'Run the fixed build and checks; returns real diagnostics, not a publication approval.'),
}


class ToolFailure(ValueError):
    pass


def tool_result(data=None, error=None):
    return {'content': [{'type': 'text', 'text': json.dumps(
        {'error': error} if error else data, ensure_ascii=False)}], 'isError': error is not None}


class CandidateTools:
    def __init__(self, root: Path, *, writable_paths: set[str], runner=None):
        root = Path(root).absolute()
        if any(p.is_symlink() for p in (root, *root.parents)):
            raise ValueError('候选工程路径不能包含符号链接')
        project = manifest(root)
        if project is None:
            raise ValueError('执行工具需要已登记的候选工程')
        self.template = get_template(project.template_id, project.template_version)
        self.writable_paths = frozenset(safe_name(p) for p in writable_paths)
        if not self.writable_paths or any(not self.template.editable(p) for p in self.writable_paths):
            raise ValueError('任务文件范围必须属于模板允许修改的业务文件')
        inventory(root)
        self.root = root
        self.runner = runner or Runner()
        self.token = secrets.token_urlsafe(32)
        self.deadline = time.monotonic() + 600
        self.closed = False
        self.lock = asyncio.Lock()
        self.calls = 0
        self.diagnostics = 0
        # Retain bounded replies for retransmissions; request IDs cannot execute twice.
        self.requests = {}
        self.on_close = []

    def active(self):
        return not self.closed and time.monotonic() < self.deadline

    async def close(self):
        self.closed = True
        tasks = [task for _, task in self.requests.values() if not task.done()]
        for task in tasks:
            if not task.cancelling():
                task.cancel()
        if tasks:
            await asyncio.gather(*tasks, return_exceptions=True)
        for cleanup in self.on_close:
            await cleanup()

    def cancel_request(self, request_id):
        entry = self.requests.get((type(request_id), request_id))
        if entry and not entry[1].done() and not entry[1].cancelling():
            entry[1].cancel()

    async def call(self, request_id, name, arguments):
        if not self.active():
            return tool_result(error='任务已结束或超过执行时限')
        key = (type(request_id), request_id)
        fingerprint = hashlib.sha256(json.dumps([name, arguments], sort_keys=True,
                                               separators=(',', ':')).encode()).hexdigest()
        previous = self.requests.get(key)
        if previous:
            if previous[0] != fingerprint:
                return tool_result(error='请求标识已用于其他工具或参数')
            task = previous[1]
        else:
            if len(self.requests) >= 200:
                return tool_result(error='工具调用次数已达上限')
            task = asyncio.create_task(self._bounded_execute(name, arguments))
            self.requests[key] = (fingerprint, task)
        # HTTP disconnection is not permission to cancel a running build.
        try:
            return await asyncio.shield(task)
        except asyncio.CancelledError:
            if task.cancelled():
                return tool_result(error='工具执行已取消')
            raise

    async def _bounded_execute(self, name, arguments):
        try:
            async with asyncio.timeout(max(0, self.deadline - time.monotonic())):
                async with self.lock:
                    if not self.active():
                        raise ToolFailure('任务已结束或超过执行时限')
                    self.calls += 1
                    if name not in TOOL_MODELS:
                        raise ToolFailure('工具未授权')
                    args = TOOL_MODELS[name][0].model_validate(arguments)
                    return tool_result(await self._execute(name, args))
        except asyncio.CancelledError:
            return tool_result(error='工具执行已取消')
        except TimeoutError:
            return tool_result(error='任务超过执行时限')
        except ValidationError:
            # Pydantic's default error embeds arbitrary caller input.
            return tool_result(error='工具参数无效，请按输入协议修正')
        except (ToolFailure, RunnerError) as exc:
            return tool_result(error=str(exc))
        except (OSError, UnicodeError):
            return tool_result(error='候选工程读取或写入失败，请检查文件状态')
        except ValueError as exc:
            # File contract errors are controlled, but never forward source bodies.
            return tool_result(error=str(exc)[:300])

    async def _execute(self, name, args):
        if name == 'project_inventory':
            files = inventory(self.root)
            page = files[args.offset:args.offset + args.limit]
            return {'source_digest': source_digest(self.root), 'total': len(files),
                    'files': [{**f, 'writable': f['path'] in self.writable_paths} for f in page],
                    'writable_paths': sorted(self.writable_paths),
                    'next_offset': args.offset + len(page) if args.offset + len(page) < len(files) else None}
        if name == 'project_read':
            safe_name(args.path)
            entry = next((f for f in inventory(self.root) if f['path'] == args.path), None)
            if not entry or not entry['text']:
                raise ToolFailure('只能读取工程清单中的文本源文件')
            if entry['size'] > 1_000_000:
                raise ToolFailure('文件超过文本读取上限')
            content = (self.root / args.path).read_text(encoding='utf-8')
            chunk = content[args.offset:args.offset + args.limit]
            return {'path': args.path, 'sha256': entry['sha256'], 'content': chunk,
                    'next_offset': args.offset + len(chunk) if args.offset + len(chunk) < len(content) else None}
        if name == 'project_apply':
            if any(f.path not in self.writable_paths for f in args.files):
                raise ToolFailure('修改超出本次任务分配的文件范围')
            apply_project_changes(self.root, args)
            return {'source_digest': source_digest(self.root),
                    'changed': [{'path': f.path, 'operation': f.operation} for f in args.files]}
        if source_digest(self.root) != args.base_digest:
            raise ToolFailure('项目已变化，请重新读取后再验证')
        if self.diagnostics >= 6:
            raise ToolFailure('诊断构建已达六次上限')
        self.diagnostics += 1
        evidence = await self.runner.run(self.root, 'opengame-' + secrets.token_hex(12))
        # Diagnostics never masquerade as full gameplay acceptance or publication.
        return {'diagnostic_attempt': self.diagnostics, 'remaining': 6 - self.diagnostics,
                'source_digest': source_digest(self.root), 'passed': evidence.get('passed') is True,
                'scope': evidence.get('scope', 'diagnostic'), 'publication_approved': False,
                'checks': evidence.get('checks', []), 'error': str(evidence.get('error', ''))[:2000],
                'log': str(evidence.get('log', ''))[-12000:]}


def create_tool_app(session: CandidateTools, *, allowed_hosts=('127.0.0.1', 'localhost'), model_proxy=None):
    """Internal single-candidate MCP endpoint, JSON response transport only.

No tools or URL in a generated project can change the root, runner or grant.
Bind to loopback or a dedicated container network, never the preview service.
"""
    @asynccontextmanager
    async def lifespan(app):
        try:
            yield
        finally:
            await session.close()

    app = FastAPI(openapi_url=None, docs_url=None, redoc_url=None, lifespan=lifespan)
    app.add_middleware(TrustedHostMiddleware, allowed_hosts=list(allowed_hosts))
    if model_proxy is not None:
        session.on_close.append(model_proxy.close)

        @app.post('/v1/chat/completions')
        async def model_completion(request: Request):
            return await model_proxy.handle(request)

    @app.middleware('http')
    async def authorize(request, call_next):
        if 'origin' in request.headers:
            return Response(status_code=403)
        supplied = request.headers.get('authorization', '')
        if not secrets.compare_digest(supplied.encode(), ('Bearer ' + session.token).encode()):
            return Response(status_code=401)
        if not session.active():
            return Response(status_code=410)
        response = await call_next(request)
        response.headers['Cache-Control'] = 'no-store'
        return response

    def error(request_id, code, message, status=200):
        return JSONResponse({'jsonrpc': '2.0', 'id': request_id,
                             'error': {'code': code, 'message': message}}, status_code=status)

    @app.get('/mcp')
    async def no_sse():
        return Response(status_code=405, headers={'Allow': 'POST'})

    @app.post('/mcp')
    async def rpc(request: Request):
        if request.headers.get('content-type', '').split(';')[0].strip() != 'application/json':
            return Response(status_code=415)
        accepted = {p.split(';')[0].strip() for p in request.headers.get('accept', '').split(',')}
        if not {'application/json', 'text/event-stream'} <= accepted:
            return Response(status_code=406)
        version = request.headers.get('mcp-protocol-version')
        if version is not None and version != PROTOCOL:
            return Response(status_code=400)
        body = bytearray()
        async for chunk in request.stream():
            body.extend(chunk)
            if len(body) > MAX_BODY:
                return Response(status_code=413)
        def reject_constant(value):
            raise ValueError('Non-finite JSON number')

        try:
            data = json.loads(body, parse_constant=reject_constant)
        except (ValueError, UnicodeError, RecursionError):
            return error(None, -32700, 'Invalid JSON', 400)
        if not isinstance(data, dict) or data.get('jsonrpc') != '2.0':
            return error(None, -32600, 'Invalid Request', 400)
        request_id = data.get('id')
        has_id = 'id' in data
        if has_id and not (type(request_id) is int or isinstance(request_id, str) and len(request_id) <= 128):
            return error(None, -32600, 'Invalid request ID', 400)
        method, params = data.get('method'), data.get('params', {})
        if not isinstance(method, str) or not isinstance(params, dict):
            return error(request_id, -32600, 'Invalid Request', 400)
        if not has_id:
            if method == 'notifications/cancelled':
                target = params.get('requestId')
                if type(target) not in (int, str):
                    return Response(status_code=400)
                session.cancel_request(target)
            elif method != 'notifications/initialized':
                return Response(status_code=400)
            return Response(status_code=202)
        if method != 'initialize' and version != PROTOCOL:
            return error(request_id, -32600, 'Negotiated protocol header required', 400)
        if method == 'initialize':
            if not isinstance(params.get('protocolVersion'), str) or not isinstance(params.get('capabilities'), dict) or not isinstance(params.get('clientInfo'), dict):
                return error(request_id, -32602, 'Invalid initialization parameters')
            result = {'protocolVersion': PROTOCOL, 'capabilities': {'tools': {'listChanged': False}},
                      'serverInfo': {'name': 'ludraft-candidate-tools', 'version': '0.1.0'}}
        elif method == 'ping':
            result = {}
        elif method == 'tools/list':
            if params.get('cursor'):
                return error(request_id, -32602, 'Tool list does not require pagination')
            result = {'tools': [{'name': name, 'description': description,
                                 'inputSchema': model.model_json_schema()}
                                for name, (model, description) in TOOL_MODELS.items()]}
        elif method == 'tools/call':
            name, arguments = params.get('name'), params.get('arguments', {})
            if not isinstance(name, str) or not isinstance(arguments, dict):
                return error(request_id, -32602, 'Invalid tool parameters')
            result = await session.call(request_id, name, arguments)
        else:
            return error(request_id, -32601, 'Method not found')
        return JSONResponse({'jsonrpc': '2.0', 'id': request_id, 'result': result})

    return app
