"""Read the pinned OpenGame headless protocol without trusting generated prose.

This is a protocol adapter, not a sandbox or a gameplay verifier. Executing the
CLI will additionally require the isolated runner and per-call budget proxy.
"""
import json
import re

UPSTREAM_COMMIT = 'c9bea37786af524bf3bbe802f2b67d23816fa5c0'
CLI_SHA256 = '10d1201f0b1ad1415360c1d7cd9ca3ac307deef4c9e10d696931abc174e6b0bb'


class OpenGameProtocolError(ValueError):
    pass


class OpenGameStream:
    def __init__(self, max_bytes=8_000_000, max_line=1_000_000, max_turns=20):
        self.max_bytes, self.max_line, self.max_turns = max_bytes, max_line, max_turns
        self.buffer = b''
        self.bytes = 0
        self.session = None
        self.result = None
        self.tools = []
        self.tool_errors = 0
        self.messages = 0
        self.closed = False

    def feed(self, chunk: bytes):
        if self.closed:
            raise OpenGameProtocolError('执行事件流已结束')
        self.bytes += len(chunk)
        if self.bytes > self.max_bytes:
            raise OpenGameProtocolError('执行事件流超过大小限制')
        self.buffer += chunk
        while b'\n' in self.buffer:
            line, self.buffer = self.buffer.split(b'\n', 1)
            self._line(line)
        if len(self.buffer) > self.max_line:
            raise OpenGameProtocolError('单条执行事件超过大小限制')

    def _line(self, line):
        if len(line) > self.max_line:
            raise OpenGameProtocolError('单条执行事件超过大小限制')
        if not line.strip():
            return
        try:
            event = json.loads(line)
        except (ValueError, UnicodeError):
            raise OpenGameProtocolError('执行器未返回有效的 JSON 事件') from None
        if not isinstance(event, dict) or event.get('type') not in ('system', 'user', 'assistant', 'stream_event', 'result'):
            raise OpenGameProtocolError('执行器返回未知事件类型')
        session = event.get('session_id')
        if not isinstance(session, str) or not session or len(session) > 200:
            raise OpenGameProtocolError('执行事件缺少有效会话标识')
        if self.session is not None and self.session != session:
            raise OpenGameProtocolError('执行事件混入了其他会话')
        self.session = session
        if self.result is not None:
            raise OpenGameProtocolError('最终结果后仍收到执行事件')
        self.messages += 1
        if self.messages > 2000:
            raise OpenGameProtocolError('执行事件数量超过限制')
        if event['type'] in ('assistant', 'user'):
            message = event.get('message')
            if not isinstance(message, dict):
                raise OpenGameProtocolError('执行消息结构无效')
            blocks = message.get('content', [])
            if isinstance(blocks, str):
                return
            if not isinstance(blocks, list):
                raise OpenGameProtocolError('执行消息内容结构无效')
            for block in blocks:
                if not isinstance(block, dict):
                    raise OpenGameProtocolError('执行消息内容结构无效')
                if block.get('type') == 'tool_use':
                    name = block.get('name', '')
                    if not isinstance(name, str) or not re.fullmatch(r'[a-zA-Z0-9_.:-]{1,128}', name):
                        raise OpenGameProtocolError('执行工具名称无效')
                    self.tools.append(name)
                elif block.get('type') == 'tool_result' and block.get('is_error') is True:
                    self.tool_errors += 1
        elif event['type'] == 'result':
            if event.get('parent_tool_use_id') is not None:
                raise OpenGameProtocolError('不能将子任务结果作为主任务完成依据')
            turns = event.get('num_turns')
            subtype = event.get('subtype')
            if type(turns) is not int or turns < 0 or turns > self.max_turns:
                raise OpenGameProtocolError('执行轮数无效或超过限制')
            if subtype not in ('success', 'error_max_turns', 'error_during_execution'):
                raise OpenGameProtocolError('最终结果类型无效')
            if event.get('is_error') is not (subtype != 'success'):
                raise OpenGameProtocolError('最终结果状态相互矛盾')
            denials = event.get('permission_denials')
            if not isinstance(denials, list):
                raise OpenGameProtocolError('最终结果缺少工具权限报告')
            usage = event.get('usage')
            if not isinstance(usage, dict):
                raise OpenGameProtocolError('最终结果用量结构无效')
            safe_usage = {}
            for key in ('input_tokens', 'output_tokens', 'cache_creation_input_tokens', 'cache_read_input_tokens', 'total_tokens'):
                if key in usage:
                    if type(usage[key]) is not int or usage[key] < 0:
                        raise OpenGameProtocolError('最终结果用量无效')
                    safe_usage[key] = usage[key]
            # Do not expose generated prose, reasoning, tool arguments or errors.
            self.result = {'subtype': subtype, 'num_turns': turns, 'usage': safe_usage,
                           'permission_denials': len(denials)}

    def finish(self, exit_code):
        if self.closed:
            raise OpenGameProtocolError('执行事件流已结束')
        self._line(self.buffer)
        self.buffer = b''
        self.closed = True
        if self.result is None:
            raise OpenGameProtocolError('执行器退出但没有返回最终结果，不能判定完成')
        return {**self.result, 'exit_code': exit_code, 'tool_calls': list(self.tools),
                'tool_errors': self.tool_errors, 'events': self.messages,
                'execution_completed': type(exit_code) is int and exit_code == 0
                    and self.result['subtype'] == 'success' and not self.result['permission_denials'],
                'gameplay_verified': False, 'upstream_commit': UPSTREAM_COMMIT}
