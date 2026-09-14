"""Exercise real MCP HTTP + upstream SDK + Docker, without a model or provider key."""
import argparse
import asyncio
import json
import os
from pathlib import Path
import socket
import subprocess
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
import uvicorn
from studio.db import uid
from studio.files import copy_source
from studio.opengame import UPSTREAM_COMMIT
from studio.opengame_tools import CandidateTools, create_tool_app


async def verify(args):
    upstream = args.upstream.resolve()
    commit = subprocess.check_output(['git', '-C', str(upstream), 'rev-parse', 'HEAD'], text=True).strip()
    if commit != UPSTREAM_COMMIT:
        raise ValueError('OpenGame checkout differs from pinned commit')
    candidate = args.output.resolve() / uid()
    copy_source(ROOT / 'templates/phaser/tower_defense', candidate)
    session = CandidateTools(candidate, writable_paths={'src/config.ts'})
    sock = socket.socket()
    server_task = process = None
    report = {'passed': False, 'scope': 'mcp-sdk-and-fixed-phaser-integration',
              'workspace': str(candidate), 'upstream_commit': commit,
              'live_model_verified': False, 'gameplay_verified': False}
    try:
        sock.bind(('127.0.0.1', 0))
        sock.listen(128)
        server = uvicorn.Server(uvicorn.Config(create_tool_app(session), log_level='warning', access_log=False))
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
        with tempfile.TemporaryDirectory(prefix='opengame-sdk-home-') as home:
            env = {'PATH': str(args.node.resolve().parent) + os.pathsep + '/usr/bin:/bin', 'HOME': home,
                   'LUDRAFT_TOOL_URL': f'http://127.0.0.1:{sock.getsockname()[1]}/mcp',
                   'LUDRAFT_TOOL_TOKEN': session.token}
            process = await asyncio.create_subprocess_exec(str(args.node.resolve()), str(ROOT / 'scripts/opengame_tools_probe.mjs'),
                str(upstream), cwd=home, env=env, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE)
            stdout, stderr = await asyncio.wait_for(process.communicate(), 360)
            if process.returncode != 0:
                report['error'] = 'Upstream MCP SDK probe failed'
                report['diagnostics'] = stderr.decode(errors='replace')[-4000:].replace(session.token, '[redacted]')
            else:
                report.update(json.loads(stdout))
    finally:
        await session.close()
        if process and process.returncode is None:
            process.kill()
            await process.wait()
        if server_task:
            server.should_exit = True
            await server_task
        sock.close()
        (candidate / 'mcp-integration.json').write_text(json.dumps(report, ensure_ascii=False, indent=2))
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0 if report['passed'] else 1


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--upstream', type=Path, required=True)
    parser.add_argument('--node', type=Path, required=True)
    parser.add_argument('--output', type=Path, default=ROOT / '.studio/opengame-tool-integration')
    raise SystemExit(asyncio.run(verify(parser.parse_args())))
