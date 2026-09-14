"""Fixed OpenGame CLI in a disconnected container with scoped HTTP over stdio.

The CLI receives no host mounts or provider credentials. Only the task's MCP
endpoint and model proxy are reachable through the trusted transport supervisor.
"""
import asyncio
import base64
import binascii
import hashlib
import json
from pathlib import Path
import re
import time
import uuid
from contextlib import nullcontext

from .opengame import CLI_SHA256, UPSTREAM_COMMIT, OpenGameStream
from .opengame_tools import create_tool_app

IMAGE = 'gamedev-opengame-runner:1'
BRIDGE = Path(__file__).resolve().parents[1] / 'runner/opengame/bridge.mjs'
MAX_FRAME = 3_000_000
SLOT = asyncio.Lock()


class ExecutorError(RuntimeError):
    def __init__(self, message, *, uncertain=False):
        super().__init__(message)
        self.uncertain = uncertain


def decode64(value, limit):
    if not isinstance(value, str) or len(value) > (limit + 2) // 3 * 4:
        raise ExecutorError('执行器数据超过限制')
    try:
        result = base64.b64decode(value, validate=True)
    except (ValueError, binascii.Error):
        raise ExecutorError('执行器数据编码无效') from None
    if len(result) > limit:
        raise ExecutorError('执行器数据超过限制')
    return result


async def docker(*args, timeout=15):
    process = None
    try:
        process = await asyncio.create_subprocess_exec('docker', *args,
            stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE)
        output, _ = await asyncio.wait_for(process.communicate(), timeout)
        if process.returncode:
            raise ExecutorError('Docker 操作失败，请检查运行环境和镜像')
        if len(output) > 1_000_000:
            raise ExecutorError('Docker 返回内容超过限制')
        return output
    except FileNotFoundError:
        raise ExecutorError('未找到 Docker') from None
    except OSError:
        raise ExecutorError('Docker 进程无法启动或通信失败', uncertain=process is not None) from None
    except TimeoutError:
        raise ExecutorError('Docker 操作超时', uncertain=True) from None
    finally:
        if process and process.returncode is None:
            process.kill()
            await process.wait()


async def verified_image():
    try:
        data = json.loads(await docker('image', 'inspect', IMAGE))[0]
        labels = data['Config'].get('Labels') or {}
        expected = {'com.ludraft.opengame.commit': UPSTREAM_COMMIT,
                    'com.ludraft.opengame.cli-sha256': CLI_SHA256,
                    'com.ludraft.opengame.bridge-sha256': hashlib.sha256(BRIDGE.read_bytes()).hexdigest()}
        if any(labels.get(key) != value for key, value in expected.items()):
            raise ValueError
        if not re.fullmatch(r'sha256:[a-f0-9]{64}', data['Id']):
            raise ValueError
        return data['Id']
    except (ValueError, KeyError, IndexError, TypeError):
        raise ExecutorError('OpenGame 镜像与固定 CLI 或转发程序不匹配，请重建镜像') from None


def create_args(image, name, labels=None):
    return ['create', '-i', '--name', name, '--label', 'com.ludraft.role=opengame-executor',
            '--network', 'none', '--read-only', '--cap-drop', 'ALL',
            '--security-opt', 'no-new-privileges', '--pids-limit', '128',
            '--memory', '1g', '--memory-swap', '1g', '--cpus', '1', '--user', '1000:1000',
            '--tmpfs', '/tmp:rw,nosuid,nodev,noexec,size=256m,mode=1777',
            '--log-driver', 'none',
            *[part for key, value in (labels or {}).items() for part in ('--label', key + '=' + value)], image]


async def relay_request(app, frame, emit):
    path, method = frame.get('path'), frame.get('method')
    if not ((path == '/mcp' and method in ('GET', 'POST'))
            or (path == '/v1/chat/completions' and method == 'POST')):
        raise ExecutorError('执行器请求了未授权接口')
    headers = frame.get('headers')
    allowed = {'authorization', 'accept', 'content-type', 'mcp-protocol-version'}
    if not isinstance(headers, dict) or headers.keys() - allowed:
        raise ExecutorError('执行器请求头无效')
    if any(not isinstance(v, str) or len(v) > 4000 or '\r' in v or '\n' in v for v in headers.values()):
        raise ExecutorError('执行器请求头无效')
    try:
        encoded_headers = [(k.encode('ascii'), v.encode('latin-1')) for k, v in headers.items()]
    except UnicodeError:
        raise ExecutorError('执行器请求头编码无效') from None
    encoded_headers.append((b'host', b'localhost'))
    body = decode64(frame.get('body'), 2 * 1024 * 1024)
    delivered = False
    started = False

    async def receive():
        nonlocal delivered
        if not delivered:
            delivered = True
            return {'type': 'http.request', 'body': body, 'more_body': False}
        await asyncio.Future()

    async def send(message):
        nonlocal started
        if message['type'] == 'http.response.start':
            if started:
                raise ExecutorError('重复的 HTTP 响应头')
            started = True
            safe = {k.decode(): v.decode('latin-1') for k, v in message.get('headers', [])
                    if k in (b'content-type', b'cache-control', b'allow', b'x-accel-buffering')}
            await emit({'kind': 'http_start', 'id': frame['id'], 'status': message['status'], 'headers': safe})
        elif message['type'] == 'http.response.body':
            if not started:
                raise ExecutorError('HTTP 响应缺少头部')
            data = message.get('body', b'')
            for offset in range(0, len(data), 60000):
                await emit({'kind': 'http_body', 'id': frame['id'],
                            'data': base64.b64encode(data[offset:offset+60000]).decode()})
            if not message.get('more_body', False):
                await emit({'kind': 'http_end', 'id': frame['id']})

    scope = {'type': 'http', 'asgi': {'version': '3.0', 'spec_version': '2.4'},
             'http_version': '1.1', 'scheme': 'http', 'method': method, 'path': path,
             'raw_path': path.encode(), 'root_path': '', 'query_string': b'', 'headers': encoded_headers,
             'client': ('127.0.0.1', 1), 'server': ('localhost', 80)}
    await app(scope, receive, send)


class OpenGameExecutor:
    def __init__(self, store=None):
        from .executor_records import ExecutorRecords
        self.records = ExecutorRecords(store) if store is not None else None
        self.container_name = None
        self.last_container_name = None
        self.cleanup_errors = []

    async def run(self, session, proxy, prompt, *, run_id=None):
        with self.records.lease() if self.records else nullcontext():
            if self.records:
                if self.records.pending():
                    raise ExecutorError('仍有 OpenGame 资源待确认清理，请先恢复执行环境')
                self.cleanup_errors.clear()
            return await self._run(session, proxy, prompt, run_id=run_id)

    async def recover(self):
        if self.records is None:
            return {'pending_cleanup': 0, 'can_start': True, 'attempts': []}
        try:
            with self.records.lease():
                return await self.records.recover(docker)
        except RuntimeError:
            return {**self.records.summary(), 'can_start': False, 'busy': True}

    async def _run(self, session, proxy, prompt, *, run_id=None):
        if not isinstance(prompt, str) or not prompt.strip() or len(prompt.encode()) > 200000:
            raise ExecutorError('执行任务说明无效或超过限制')
        async with SLOT:
            if self.cleanup_errors:
                raise ExecutorError('上次执行资源未清理，请先检查 Docker 状态')
            if session.closed or proxy.closed or session.requests or proxy.jobs:
                raise ExecutorError('隔离执行需要新的任务工具与模型会话')
            session.deadline = time.monotonic() + 600
            proxy.deadline = session.deadline
            image = await verified_image()
            record = self.records.begin(image, run_id) if self.records else None
            name = record['container_name'] if record else 'gamedev-opengame-' + uuid.uuid4().hex
            self.container_name = name
            self.last_container_name = name
            app = create_tool_app(session, model_proxy=proxy)
            process = None
            creation = None
            requests = {}
            output = OpenGameStream()
            stderr = bytearray()
            seen_ready = started = exited = False
            child_code = None
            seen_requests = set()
            write_lock = asyncio.Lock()

            async def emit(frame):
                data = json.dumps(frame, ensure_ascii=False).encode() + b'\n'
                if len(data) > MAX_FRAME:
                    raise ExecutorError('内部控制消息超过限制')
                async with write_lock:
                    process.stdin.write(data)
                    await process.stdin.drain()

            async def serve(frame):
                try:
                    await relay_request(app, frame, emit)
                except asyncio.CancelledError:
                    raise
                except Exception:
                    try:
                        await emit({'kind': 'http_abort', 'id': frame['id']})
                    except (OSError, RuntimeError):
                        pass  # The managed Docker attachment may already be gone.
                finally:
                    requests.pop(frame['id'], None)

            async def dispatch(frame):
                nonlocal seen_ready, started, exited, child_code
                if not isinstance(frame, dict):
                    raise ExecutorError('执行器返回无效控制消息')
                kind = frame.get('kind')
                if kind == 'ready':
                    if seen_ready or frame.get('protocol') != 1:
                        raise ExecutorError('执行器控制协议不匹配')
                    seen_ready = True
                    await emit({'kind': 'launch', 'token': session.token, 'model': proxy.config['model'], 'prompt': prompt})
                elif kind == 'started':
                    if not seen_ready or started:
                        raise ExecutorError('执行器启动顺序无效')
                    started = True
                    if record:
                        self.records.state(record['id'], 'running')
                elif kind == 'http':
                    request_id = frame.get('id')
                    if not started or exited or type(request_id) is not int or not 1 <= request_id <= 1000 or request_id in seen_requests or len(requests) >= 16:
                        raise ExecutorError('执行器 HTTP 请求序列无效或超过限制')
                    seen_requests.add(request_id)
                    requests[request_id] = asyncio.create_task(serve(frame))
                elif kind == 'http_cancel':
                    request_id = frame.get('id')
                    if type(request_id) is not int:
                        raise ExecutorError('执行器取消请求无效')
                    task = requests.get(request_id)
                    if task and not task.cancelling():
                        task.cancel()
                elif kind in ('event', 'stderr'):
                    if not started or exited:
                        raise ExecutorError('执行器事件顺序无效')
                    data = decode64(frame.get('data'), 100000)
                    if kind == 'event':
                        output.feed(data)
                    else:
                        stderr.extend(data)
                        del stderr[:-12000]
                elif kind == 'exit':
                    if not started or exited or frame.get('code') is not None and type(frame.get('code')) is not int:
                        raise ExecutorError('执行器退出状态无效')
                    exited, child_code = True, frame.get('code')
                else:
                    raise ExecutorError('执行器控制通道失败')

            async def read_frames():
                buffer, total = bytearray(), 0
                while chunk := await process.stdout.read(65536):
                    buffer.extend(chunk); total += len(chunk)
                    if total > 128_000_000:
                        raise ExecutorError('执行器控制流超过总量限制')
                    while (end := buffer.find(b'\n')) >= 0:
                        if end > MAX_FRAME:
                            raise ExecutorError('执行器控制消息超过限制')
                        frame = json.loads(buffer[:end]); del buffer[:end+1]
                        await dispatch(frame)
                    if len(buffer) > MAX_FRAME:
                        raise ExecutorError('执行器控制消息超过限制')
                if buffer:
                    raise ExecutorError('执行器控制流不完整')

            async def read_stderr():
                while chunk := await process.stderr.read(65536):
                    stderr.extend(chunk); del stderr[:-12000]

            async def cleanup():
                creation_uncertain = False
                if creation is not None:
                    try:
                        # Let a dispatched create receive its daemon result before
                        # removal; cancelling the CLI client does not cancel Docker.
                        await creation
                        if record:
                            self.records.store.execute('UPDATE executor_attempts SET create_ack=1 WHERE id=?', (record['id'],))
                    except Exception as exc:
                        creation_uncertain = getattr(exc, 'uncertain', True)
                        if record and not creation_uncertain:
                            self.records.store.execute('UPDATE executor_attempts SET create_ack=1 WHERE id=?', (record['id'],))
                try:
                    await asyncio.wait_for(session.close(), 20)
                except Exception:
                    self.cleanup_errors.append('任务工具或代理未能及时关闭')
                try:
                    await asyncio.wait_for(proxy.close(), 15)
                except Exception:
                    self.cleanup_errors.append('模型代理未能及时关闭')
                tasks = list(requests.values())
                for task in tasks:
                    if not task.cancelling():
                        task.cancel()
                if tasks:
                    await asyncio.gather(*tasks, return_exceptions=True)
                if record:
                    recovered = await self.records.recover(docker)
                    if recovered['pending_cleanup']:
                        self.cleanup_errors.append('无法确认 OpenGame 容器是否已移除')
                else:
                    await cleanup_untracked(creation_uncertain)
                if process and process.returncode is None:
                    process.kill()
                    await process.wait()
                if not self.cleanup_errors:
                    self.container_name = None
                if record and self.cleanup_errors:
                    self.records.cleanup(record['id'], 'unknown', '执行资源清理未确认')

            async def cleanup_untracked(creation_uncertain):
                try:
                    await docker('rm', '-f', name)
                except ExecutorError:
                    # A failed create may leave no container, but daemon failure
                    # is not evidence of absence. Preserve the handle if unknown.
                    try:
                        remaining = await docker('ps', '-aq', '--filter', 'name=^/' + name + '$')
                    except ExecutorError:
                        self.cleanup_errors.append('无法确认 OpenGame 容器是否已移除')
                    else:
                        if remaining.strip():
                            self.cleanup_errors.append('OpenGame 容器仍存在')
                        elif creation_uncertain:
                            self.cleanup_errors.append('容器创建结果未确认，尚不能确认清理完成')

            from .executor_records import ACTIVE_EXECUTION
            resource_token = ACTIVE_EXECUTION.set((self.records, record['id']) if record else None)
            try:
                if record:
                    self.records.state(record['id'], 'creating')
                creation = asyncio.create_task(docker(*create_args(image, name,
                    self.records.labels(record) if record else None), timeout=30))
                await asyncio.shield(creation)
                if record:
                    self.records.state(record['id'], 'created')
                process = await asyncio.create_subprocess_exec('docker', 'start', '-ai', name,
                    stdin=asyncio.subprocess.PIPE, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE)
                async with asyncio.timeout(max(0, session.deadline - time.monotonic())):
                    await asyncio.gather(read_frames(), read_stderr(), process.wait())
                if not exited:
                    raise ExecutorError('容器退出但未返回 CLI 退出状态')
                result = output.finish(child_code)
                result.update(container_exit_code=process.returncode, image_id=image,
                              network_mode='none', host_mounts=False, model_credentials_in_container=False)
                result['execution_completed'] = result['execution_completed'] and process.returncode == 0
                if record:
                    self.records.state(record['id'], 'succeeded' if result['execution_completed'] else 'failed')
                    result['execution_id'] = record['id']
            except asyncio.CancelledError:
                if record:
                    self.records.state(record['id'], 'cancelled')
                raise
            except Exception:
                if record:
                    self.records.state(record['id'], 'failed')
                raise
            finally:
                finishing = asyncio.create_task(cleanup())
                while not finishing.done():
                    try:
                        await asyncio.shield(finishing)
                    except asyncio.CancelledError:
                        continue
                try:
                    await finishing
                finally:
                    ACTIVE_EXECUTION.reset(resource_token)
            if self.cleanup_errors:
                raise ExecutorError('执行结束但资源清理未通过')
            return result
