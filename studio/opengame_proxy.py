"""Bounded OpenAI-compatible model forwarding for one OpenGame task.

Credentials and provider routing are backend-owned. Every actual HTTP attempt
gets a new durable budget reservation, including client retries. No retry is
performed here; incomplete streams keep their reservation for reconciliation.
"""
import asyncio
import json
import re
import time
from urllib.parse import urlparse

import httpx
from fastapi import Request
from fastapi.responses import JSONResponse, StreamingResponse

from .budget import BudgetError
from .connections import validate_url

MAX_REQUEST = 1_000_000
MAX_RESPONSE = 8_000_000
MAX_EVENT = 1_000_000


class ProxyFailure(ValueError):
    pass


def strict_json(data):
    def invalid(value):
        raise ValueError('Non-finite number')
    return json.loads(data, parse_constant=invalid)


def error_body(code, message):
    return {'error': {'type': 'ludraft_proxy_error', 'code': code, 'message': message}}


class SSEDecoder:
    """Incremental SSE data parser accepting LF, CRLF and CR line endings."""
    def __init__(self):
        self.buffer = b''
        self.lines = []
        self.event_size = 0
        self.skip_lf = False
        self.first_line = True

    def feed(self, chunk):
        if self.skip_lf and chunk:
            chunk = chunk[1:] if chunk.startswith(b'\n') else chunk
            self.skip_lf = False
        self.buffer += chunk
        events = []
        while match := re.search(rb'\r\n|\r|\n', self.buffer):
            if match.group() == b'\r' and match.end() == len(self.buffer):
                self.skip_lf = True  # CR is a terminator; swallow a following LF.
            line, self.buffer = self.buffer[:match.start()], self.buffer[match.end():]
            if self.first_line:
                line = line.removeprefix(b'\xef\xbb\xbf')
                self.first_line = False
            self.event_size += len(line) + 1
            if self.event_size > MAX_EVENT:
                raise ProxyFailure('模型流式事件超过大小限制')
            if not line:
                if self.lines:
                    events.append(b'\n'.join(self.lines).decode('utf-8'))
                self.lines, self.event_size = [], 0
            elif line.startswith(b'data:'):
                value = line[5:]
                self.lines.append(value[1:] if value.startswith(b' ') else value)
        if len(self.buffer) + self.event_size > MAX_EVENT:
            raise ProxyFailure('模型流式事件超过大小限制')
        return events


def valid_usage(value):
    if not isinstance(value, dict):
        return None
    counts = {k: value.get(k) for k in ('prompt_tokens', 'completion_tokens')}
    if any(type(v) is not int or not 0 <= v <= 1_000_000_000 for v in counts.values()):
        return None
    total = sum(counts.values())
    if 'total_tokens' in value and (type(value['total_tokens']) is not int or value['total_tokens'] != total):
        return None
    return {**counts, 'total_tokens': total}


class ProxyJob:
    def __init__(self, reservation, ledger):
        self.reservation = reservation
        self.ledger = ledger
        self.started = False
        self.ready = asyncio.get_running_loop().create_future()
        self.queue = asyncio.Queue(maxsize=32)
        self.task = None

    async def close(self):
        if self.task and not self.task.done():
            if not self.task.cancelling():
                self.task.cancel()
            await asyncio.shield(asyncio.gather(self.task, return_exceptions=True))
        if not self.ready.done():
            # A task cancelled before its coroutine starts never enters finally.
            # Unblock the HTTP waiter and preserve its durable reservation.
            if not self.started:
                try:
                    self.ledger.finish_model(self.reservation, {})
                except Exception:
                    pass  # The original reservation is still held.
            self.ready.set_result(('error', error_body('cancelled', '模型请求已取消；原有预留待核账')))

    async def stream(self):
        try:
            while (chunk := await self.queue.get()) is not None:
                yield chunk
        finally:
            await self.close()


class OwnedStream(StreamingResponse):
    def __init__(self, job):
        self.job = job
        super().__init__(job.stream(), media_type='text/event-stream',
                         headers={'Cache-Control': 'no-store', 'X-Accel-Buffering': 'no'})

    async def __call__(self, scope, receive, send):
        try:
            await super().__call__(scope, receive, send)
        finally:
            await self.job.close()


class ModelProxy:
    def __init__(self, config, ledger, *, allowed_tools, deadline, active, transport=None):
        self.config = {k: config.get(k) for k in ('provider', 'base_url', 'model', 'api_key', 'max_tokens')}
        if self.config['provider'] not in ('openai', 'deepseek', 'custom'):
            raise ValueError('OpenGame 代理当前需要 OpenAI 兼容连接')
        self.config['base_url'] = validate_url(self.config['base_url'] or '')
        if not isinstance(self.config['model'], str) or not 0 < len(self.config['model']) <= 200:
            raise ValueError('需要配置有效的编码模型名称')
        if self.config['max_tokens'] is None:
            self.config['max_tokens'] = 12000
        if type(self.config['max_tokens']) is not int or not 256 <= self.config['max_tokens'] <= 64000:
            raise ValueError('模型输出上限无效')
        key = self.config['api_key'] or ''
        if not isinstance(key, str) or len(key) > 1000 or '\n' in key or '\r' in key:
            raise ValueError('模型凭据格式无效')
        if not key and urlparse(self.config['base_url']).hostname not in ('localhost', '127.0.0.1', '::1'):
            raise ValueError('需要在后端配置模型凭据')
        self.config['api_key'] = key
        self.ledger = ledger
        self.allowed_tools = frozenset(allowed_tools)
        self.deadline = deadline
        self.active = active
        self.transport = transport  # Backend-only injection for offline protocol tests.
        self.jobs = []
        self.closed = False

    async def close(self):
        self.closed = True
        await asyncio.gather(*(job.close() for job in self.jobs))

    def prepare(self, data):
        if not isinstance(data, dict):
            raise ProxyFailure('模型请求必须是 JSON 对象')
        allowed = {'model', 'messages', 'stream', 'stream_options', 'max_tokens', 'tools',
                   'tool_choice', 'parallel_tool_calls', 'temperature', 'top_p', 'top_k',
                   'repetition_penalty', 'presence_penalty', 'frequency_penalty', 'reasoning_effort', 'n'}
        if data.keys() - allowed:
            raise ProxyFailure('模型请求包含尚未支持的参数')
        if data.get('model') != self.config['model']:
            raise ProxyFailure('请求模型与任务绑定的模型不一致')
        if 'n' in data and (type(data['n']) is not int or data['n'] != 1):
            raise ProxyFailure('每次只允许生成一个结果')
        output = data.get('max_tokens', self.config['max_tokens'])
        if type(output) is not int or not 1 <= output <= self.config['max_tokens']:
            raise ProxyFailure('请求超出任务输出上限')
        if type(data.get('stream', False)) is not bool:
            raise ProxyFailure('stream 参数无效')
        for key in ('temperature', 'top_p', 'top_k', 'repetition_penalty', 'presence_penalty', 'frequency_penalty'):
            if key in data and type(data[key]) not in (int, float):
                raise ProxyFailure('采样参数必须是数字')
        if 'parallel_tool_calls' in data and type(data['parallel_tool_calls']) is not bool:
            raise ProxyFailure('并行工具参数无效')
        if 'reasoning_effort' in data and (not isinstance(data['reasoning_effort'], str) or not re.fullmatch(r'[a-z_]{1,30}', data['reasoning_effort'])):
            raise ProxyFailure('推理参数无效')
        messages = data.get('messages')
        if not isinstance(messages, list) or not 1 <= len(messages) <= 2000:
            raise ProxyFailure('消息数量无效')
        for message in messages:
            if not isinstance(message, dict) or message.get('role') not in ('system', 'developer', 'user', 'assistant', 'tool'):
                raise ProxyFailure('消息角色无效')
            if message.keys() - {'role', 'content', 'name', 'tool_call_id', 'tool_calls', 'reasoning_content'}:
                raise ProxyFailure('消息包含尚未支持的字段')
            content = message.get('content')
            if isinstance(content, list):
                if any(not isinstance(b, dict) or set(b) != {'type', 'text'} or b['type'] != 'text' or not isinstance(b['text'], str) for b in content):
                    raise ProxyFailure('此阶段仅支持文本内容，不支持图片或音频模型输入')
            elif content is not None and not isinstance(content, str):
                raise ProxyFailure('消息文本无效')
            for key in ('name', 'tool_call_id', 'reasoning_content'):
                if message.get(key) is not None and not isinstance(message[key], str):
                    raise ProxyFailure('消息字段无效')
            calls = message.get('tool_calls', [])
            if not isinstance(calls, list) or len(calls) > 100:
                raise ProxyFailure('历史工具调用格式无效')
            for call in calls:
                if not isinstance(call, dict) or call.get('type') != 'function' or not isinstance(call.get('id'), str) or not isinstance(call.get('function'), dict):
                    raise ProxyFailure('历史工具调用格式无效')
                if call['function'].get('name') not in self.allowed_tools or not isinstance(call['function'].get('arguments'), str):
                    raise ProxyFailure('历史工具调用超出任务范围')
        tools = data.get('tools', [])
        if not isinstance(tools, list) or len(tools) > len(self.allowed_tools):
            raise ProxyFailure('工具数量超出任务范围')
        for tool in tools:
            if not isinstance(tool, dict) or tool.get('type') != 'function' or not isinstance(tool.get('function'), dict) or tool['function'].get('name') not in self.allowed_tools:
                raise ProxyFailure('模型请求包含未授权工具')
        choice = data.get('tool_choice', 'auto')
        if isinstance(choice, dict):
            if choice.get('type') != 'function' or not isinstance(choice.get('function'), dict) or choice['function'].get('name') not in self.allowed_tools:
                raise ProxyFailure('指定工具超出任务范围')
        elif choice not in ('auto', 'required', 'none'):
            raise ProxyFailure('指定工具参数无效')
        result = {**data, 'max_tokens': output}
        if data.get('stream'):
            result['stream_options'] = {'include_usage': True}
        elif 'stream_options' in result:
            raise ProxyFailure('非流式请求不能设置 stream_options')
        # Includes framing and tool schemas; overestimates ordinary text tokens.
        size = len(json.dumps(result, ensure_ascii=False, allow_nan=False).encode('utf-8'))
        if size > MAX_REQUEST:
            raise ProxyFailure('模型请求超过大小限制')
        return result, size + 2048

    async def handle(self, request: Request):
        if self.closed or not self.active() or time.monotonic() >= self.deadline:
            return JSONResponse(error_body('ended', '任务已结束'), status_code=410)
        if self.jobs and not self.jobs[-1].task.done():
            return JSONResponse(error_body('busy', '该任务已有模型请求执行中'), status_code=409)
        if len(self.jobs) >= 20:
            return JSONResponse(error_body('limit', '模型请求已达二十次上限'), status_code=429)
        if request.url.query:
            return JSONResponse(error_body('parameters', '模型接口不接受查询参数'), status_code=400)
        if request.headers.get('content-type', '').split(';')[0].strip() != 'application/json':
            return JSONResponse(error_body('parameters', '模型请求必须使用 JSON'), status_code=415)
        body = bytearray()
        async for chunk in request.stream():
            body.extend(chunk)
            if len(body) > MAX_REQUEST:
                return JSONResponse(error_body('parameters', '模型请求超过大小限制'), status_code=413)
        try:
            payload, inputs = self.prepare(strict_json(body))
        except (ValueError, UnicodeError, RecursionError, TypeError):
            return JSONResponse(error_body('parameters', '模型请求不符合任务的文本、工具或输出限制'), status_code=400)
        # Recheck after reading a potentially slow request body. No await separates
        # admission and reservation, so two incoming requests cannot both enter.
        if self.closed or not self.active() or time.monotonic() >= self.deadline:
            return JSONResponse(error_body('ended', '任务已结束'), status_code=410)
        if self.jobs and not self.jobs[-1].task.done():
            return JSONResponse(error_body('busy', '该任务已有模型请求执行中'), status_code=409)
        if len(self.jobs) >= 20:
            return JSONResponse(error_body('limit', '模型请求已达二十次上限'), status_code=429)
        try:
            reservation = self.ledger.reserve_model(self.config, inputs, payload['max_tokens'], 'OpenGame')
        except BudgetError as exc:
            return JSONResponse(error_body('budget', str(exc)), status_code=402)
        job = ProxyJob(reservation, self.ledger)
        job.task = asyncio.create_task(self._forward(job, payload))
        self.jobs.append(job)
        try:
            mode, result = await asyncio.shield(job.ready)
        except BaseException:
            await job.close()
            raise
        if mode == 'stream':
            return OwnedStream(job)
        return JSONResponse(result, status_code=200 if mode == 'json' else 502)

    async def _forward(self, job, payload):
        job.started = True
        usage, complete, result = None, False, None
        streaming = payload.get('stream', False)
        failed = False
        try:
            async with asyncio.timeout(min(120, max(0, self.deadline - time.monotonic()))):
                async with httpx.AsyncClient(timeout=httpx.Timeout(120, connect=15),
                        follow_redirects=False, trust_env=False, transport=self.transport) as client:
                    headers = {'Accept-Encoding': 'identity'}
                    if self.config['api_key']:
                        headers['Authorization'] = 'Bearer ' + self.config['api_key']
                    async with client.stream('POST', self.config['base_url'] + '/chat/completions',
                                             headers=headers, json=payload) as response:
                        if response.status_code != 200:
                            raise ProxyFailure(f'模型服务返回 HTTP {response.status_code}')
                        if response.headers.get('content-encoding', 'identity') != 'identity':
                            raise ProxyFailure('模型服务忽略了未压缩响应要求')
                        if streaming:
                            if response.headers.get('content-type', '').split(';')[0] != 'text/event-stream':
                                raise ProxyFailure('模型服务没有返回流式响应')
                            job.ready.set_result(('stream', None))
                            decoder, total, events, done, finished = SSEDecoder(), 0, 0, False, False
                            async for chunk in response.aiter_bytes():
                                total += len(chunk)
                                if total > MAX_RESPONSE:
                                    raise ProxyFailure('模型响应超过大小限制')
                                for event in decoder.feed(chunk):
                                    events += 1
                                    if events > 20000:
                                        raise ProxyFailure('模型流式事件数量超限')
                                    if event == '[DONE]':
                                        done = True
                                        break
                                    item = strict_json(event)
                                    cleaned = self.clean_response(item, stream=True)
                                    if any(c.get('finish_reason') for c in item['choices']):
                                        finished = True
                                    if item.get('usage') is not None:
                                        current = valid_usage(item['usage'])
                                        if current is None or (usage is not None and current != usage):
                                            raise ProxyFailure('模型用量格式无效或多次返回不一致')
                                        usage = current
                                    await job.queue.put(('data: ' + json.dumps(cleaned, ensure_ascii=False) + '\n\n').encode())
                                if done:
                                    break
                            if not done or events < 2 or not finished:
                                raise ProxyFailure('模型流式响应中断或缺少结束标记')
                            complete = True
                        else:
                            body = bytearray()
                            async for chunk in response.aiter_bytes(chunk_size=8192):
                                body.extend(chunk)
                                if len(body) > MAX_RESPONSE:
                                    raise ProxyFailure('模型响应超过大小限制')
                            item = strict_json(body)
                            cleaned = self.clean_response(item, stream=False)
                            usage = valid_usage(item.get('usage'))
                            complete = True
                            result = cleaned
        except asyncio.CancelledError:
            failed = True
            message = '模型请求已取消；未确认费用保留待核账'
        except (httpx.HTTPError, TimeoutError):
            failed = True
            message = '模型连接失败或超时；未确认费用保留待核账'
        except ProxyFailure as exc:
            failed = True
            message = str(exc) + '；未确认费用保留待核账'
        except (ValueError, TypeError, KeyError, RecursionError):
            failed = True
            message = '模型响应不符合协议；未确认费用保留待核账'
        except Exception:
            failed = True
            message = '模型代理执行异常；未确认费用保留待核账'
        finally:
            try:
                self.ledger.finish_model(job.reservation, usage if complete and usage else {})
            except Exception:
                failed = True
                message = '模型用量记录失败；请核查原有预留记录'
            if failed:
                sanitized = error_body('upstream', message)
                if not job.ready.done():
                    job.ready.set_result(('error', sanitized))
                else:
                    # A stalled/disconnected consumer must not trap cleanup.
                    while not job.queue.empty():
                        job.queue.get_nowait()
                    job.queue.put_nowait(('data: ' + json.dumps(sanitized, ensure_ascii=False) + '\n\n').encode())
            if streaming:
                if failed:
                    job.queue.put_nowait(None)
                else:
                    await job.queue.put(b'data: [DONE]\n\n')
                    await job.queue.put(None)
            elif not failed:
                job.ready.set_result(('json', result))

    def clean_response(self, item, *, stream):
        if not isinstance(item, dict) or 'error' in item or not isinstance(item.get('choices'), list):
            raise ProxyFailure('模型响应内容无效')
        choices = item['choices']
        if len(choices) > 1 or (not stream and len(choices) != 1):
            raise ProxyFailure('模型必须返回单个结果')
        for choice in choices:
            field = 'delta' if stream else 'message'
            if not isinstance(choice, dict) or not isinstance(choice.get(field), dict) or choice.get('index', 0) != 0:
                raise ProxyFailure('模型消息结构无效')
            reason = choice.get('finish_reason')
            if reason is not None and reason not in ('stop', 'length', 'tool_calls', 'content_filter', 'function_call'):
                raise ProxyFailure('模型结束原因无效')
            if not stream and reason is None:
                raise ProxyFailure('模型响应缺少结束原因')
        # Never forward provider error bodies, response headers or extra metadata.
        result = {k: item[k] for k in ('id', 'object', 'created', 'model', 'choices') if k in item}
        if item.get('usage') is not None:
            result['usage'] = valid_usage(item['usage'])
        return result
