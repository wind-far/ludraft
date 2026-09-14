"""Fixed-response CLI/proxy/tools/Docker integration; never contacts a model.

The CLI runs with a disposable HOME and filtered tools, but is NOT OS-sandboxed.
This probe must not be used as the production executor or with real model input.
"""
import argparse
import asyncio
import json
import os
from pathlib import Path
import signal
import socket
import subprocess
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
import httpx
import uvicorn
from studio.budget import BudgetLedger, connection_key
from studio.db import uid
from studio.files import copy_source
from studio.opengame import OpenGameStream, UPSTREAM_COMMIT
from studio.opengame_proxy import ModelProxy
from studio.opengame_tools import CandidateTools, TOOL_MODELS, create_tool_app
from studio.project_files import source_digest


class FixtureProvider:
    def __init__(self, candidate):
        self.candidate = candidate
        self.original = (candidate / 'src/config.ts').read_text()
        self.steps = []
        self.diagnostics = []
        self.tool_names = []

    def respond(self, request):
        data = json.loads(request.content)
        names = sorted(t['function']['name'] for t in data.get('tools', []))
        self.tool_names = names
        if names != sorted(TOOL_MODELS):
            raise ValueError('CLI exposed tools outside the four-tool contract')
        step = len(self.steps)
        actions = [('project_inventory', {}), ('project_read', {'path': 'src/config.ts'})]
        if step < 2:
            name, arguments = actions[step]
        elif step in (2, 4):
            name, arguments = 'project_apply', {'summary': 'fixed protocol probe',
                'base_digest': source_digest(self.candidate), 'files': [{'operation': 'update',
                'path': 'src/config.ts', 'content': 'export const invalid = ;' if step == 2 else self.original}]}
        elif step in (3, 5):
            name, arguments = 'project_verify', {'base_digest': source_digest(self.candidate)}
        elif step == 6:
            name, arguments = None, None
        else:
            raise ValueError('CLI made unexpected extra model calls')
        if step in (4, 6):
            evidence = json.loads((self.candidate / 'evidence.json').read_text())
            self.diagnostics.append(evidence)
            if evidence.get('passed') is not (step == 6):
                raise ValueError('Actual build outcome differed from fixture sequence')
            if step == 4 and 'TS' not in evidence.get('log', ''):
                raise ValueError('TypeScript diagnostics missing')
        if step > 0 and not any(m['role'] == 'tool' for m in data['messages']):
            raise ValueError('CLI did not return tool feedback to the model')
        self.steps.append(name or 'final_response')
        if name:
            delta = {'tool_calls': [{'index': 0, 'id': f'fixture_call_{step}', 'type': 'function',
                                    'function': {'name': name, 'arguments': json.dumps(arguments)}}]}
        else:
            delta = {'content': 'Fixed-response integration completed.'}
        chunks = [
            {'id': f'fixture_{step}', 'object': 'chat.completion.chunk', 'created': 1, 'model': data['model'],
             'choices': [{'index': 0, 'delta': {'role': 'assistant', **delta}, 'finish_reason': None}]},
            {'id': f'fixture_{step}', 'object': 'chat.completion.chunk', 'created': 1, 'model': data['model'],
             'choices': [{'index': 0, 'delta': {}, 'finish_reason': 'tool_calls' if name else 'stop'}]},
            {'id': f'fixture_{step}', 'object': 'chat.completion.chunk', 'created': 1, 'model': data['model'],
             'choices': [], 'usage': {'prompt_tokens': 100, 'completion_tokens': 20, 'total_tokens': 120}},
        ]
        body = ''.join('data: ' + json.dumps(chunk) + '\n\n' for chunk in chunks) + 'data: [DONE]\n\n'
        return httpx.Response(200, content=body.encode(), headers={'Content-Type': 'text/event-stream'})


async def verify(args):
    upstream = args.upstream.resolve()
    commit = subprocess.check_output(['git', '-C', str(upstream), 'rev-parse', 'HEAD'], text=True).strip()
    if commit != UPSTREAM_COMMIT:
        raise ValueError('OpenGame checkout differs from pinned commit')
    run = args.output.resolve() / uid()
    candidate = run / 'candidate'
    copy_source(ROOT / 'templates/phaser/tower_defense', candidate)
    session = CandidateTools(candidate, writable_paths={'src/config.ts'})
    config = {'provider': 'openai', 'base_url': 'https://fixture.invalid/v1', 'model': 'ludraft-fixture',
              'api_key': 'local-fixture-only', 'max_tokens': 12000}
    ledger = BudgetLedger(run / 'fixture-budget')
    ledger.configure('100')
    ledger.set_price(connection_key(config), '1', '2', 'synthetic protocol test rates; no paid model')
    fixture = FixtureProvider(candidate)
    proxy = ModelProxy(config, ledger, allowed_tools=TOOL_MODELS, deadline=session.deadline,
                       active=session.active, transport=httpx.MockTransport(fixture.respond))
    sock = socket.socket()
    server_task = process = None
    stderr_tail = bytearray()
    report = {'passed': False, 'scope': 'fixed-response-cli-proxy-tools-docker', 'upstream_commit': commit,
              'live_model_verified': False, 'process_isolation_verified': False, 'gameplay_verified': False,
              'workspace': str(run), 'paid_model_calls': 0, 'image_calls': 0}
    try:
        sock.bind(('127.0.0.1', 0))
        sock.listen(128)
        url = f'http://127.0.0.1:{sock.getsockname()[1]}'
        server = uvicorn.Server(uvicorn.Config(create_tool_app(session, model_proxy=proxy), log_level='warning', access_log=False))
        server_task = asyncio.create_task(server.serve(sockets=[sock]))
        for _ in range(100):
            if server.started:
                break
            if server_task.done():
                await server_task
                raise RuntimeError('Tool server stopped before startup')
            await asyncio.sleep(0.01)
        if not server.started:
            raise RuntimeError('Tool server did not start')
        with tempfile.TemporaryDirectory(prefix='opengame-proxy-home-', dir='/private/tmp' if sys.platform == 'darwin' else None) as home:
            settings_dir = Path(home) / '.qwen'
            settings_dir.mkdir(mode=0o700)
            settings = {'general': {'chatRecording': False}, 'privacy': {'usageStatisticsEnabled': False},
                'telemetry': {'enabled': False}, 'tools': {'core': ['ludraft_no_builtin_tools'],
                'allowed': list(TOOL_MODELS), 'useRipgrep': False},
                'mcpServers': {'ludraft': {'httpUrl': url + '/mcp', 'headers': {'Authorization': 'Bearer ' + session.token},
                                         'trust': True, 'includeTools': list(TOOL_MODELS)}}}
            (settings_dir / 'settings.json').write_text(json.dumps(settings))
            env = {'PATH': str(args.node.resolve().parent) + os.pathsep + '/usr/bin:/bin', 'HOME': home,
                   'OPENAI_API_KEY': session.token, 'OPENAI_BASE_URL': url + '/v1', 'OPENAI_MODEL': config['model'],
                   'QWEN_CODE_SYSTEM_SETTINGS_PATH': str(Path(home) / 'absent-system.json'),
                   'QWEN_CODE_SYSTEM_DEFAULTS_PATH': str(Path(home) / 'absent-defaults.json')}
            process = await asyncio.create_subprocess_exec(str(args.node.resolve()), str(upstream / 'dist/cli.js'),
                '--auth-type', 'openai', '--output-format', 'stream-json', '--approval-mode', 'default',
                '--max-session-turns', '20', '--allowed-mcp-server-names', 'ludraft',
                '--prompt', 'Run the fixed protocol exercise through the available project tools.',
                cwd=home, env=env, start_new_session=True, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE)
            stream = OpenGameStream()
            async def read_stdout():
                while chunk := await process.stdout.read(65536):
                    stream.feed(chunk)
            async def read_stderr():
                while chunk := await process.stderr.read(65536):
                    stderr_tail.extend(chunk)
                    del stderr_tail[:-4000]
            await asyncio.wait_for(asyncio.gather(read_stdout(), read_stderr(), process.wait()), 360)
            report['execution'] = stream.finish(process.returncode)
            report['passed'] = (report['execution']['execution_completed'] and len(fixture.steps) == 7
                                and session.diagnostics == 2 and len(proxy.jobs) == 7)
    except Exception as exc:
        report['error'] = str(exc)[:1000].replace(session.token, '[redacted]')
    finally:
        await session.close()
        if process and process.returncode is None:
            os.killpg(process.pid, signal.SIGTERM)
            try:
                await asyncio.wait_for(process.wait(), 3)
            except TimeoutError:
                os.killpg(process.pid, signal.SIGKILL)
                await process.wait()
        if server_task:
            server.should_exit = True
            await server_task
        sock.close()
        report.update(fixture_steps=fixture.steps, exposed_tools=fixture.tool_names,
                      fixture_ledger=ledger.summary(), diagnostics=fixture.diagnostics)
        if not report['passed']:
            report['stderr'] = stderr_tail.decode(errors='replace').replace(session.token, '[redacted]')
        (run / 'proxy-integration.json').write_text(json.dumps(report, ensure_ascii=False, indent=2))
    print(json.dumps({k: v for k, v in report.items() if k != 'diagnostics'}, ensure_ascii=False, indent=2))
    return 0 if report['passed'] else 1


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--upstream', type=Path, required=True)
    parser.add_argument('--node', type=Path, required=True)
    parser.add_argument('--output', type=Path, default=ROOT / '.studio/opengame-proxy-integration')
    raise SystemExit(asyncio.run(verify(parser.parse_args())))
