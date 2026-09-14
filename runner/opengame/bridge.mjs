// Trusted transport supervisor. Runs inside a network=none, read-only container.
// Only two loopback HTTP paths are relayed over the Docker stdio channel.
import http from 'node:http';
import fs from 'node:fs/promises';
import { spawn } from 'node:child_process';
import { once } from 'node:events';

const MAX_BODY = 2 * 1024 * 1024;
const MAX_FRAME = 3_000_000;
const tools = ['project_inventory', 'project_read', 'project_apply', 'project_verify'];
const pending = new Map();
let child, server, sequence = 0, launched = false, stopping = false, finished = false;
let outputChain = Promise.resolve();

function emit(value) {
  outputChain = outputChain.then(async () => {
    const line = JSON.stringify(value) + '\n';
    if (Buffer.byteLength(line) > MAX_FRAME) throw new Error('frame limit');
    if (!process.stdout.write(line)) await once(process.stdout, 'drain');
  });
  return outputChain;
}

async function stop() {
  if (stopping) return;
  stopping = true;
  for (const { response } of pending.values()) response.destroy();
  pending.clear();
  server?.close();
  if (child && child.exitCode === null) child.kill('SIGTERM');
}

async function launch(config) {
  if (launched || typeof config.token !== 'string' || !/^[A-Za-z0-9_-]{32,100}$/.test(config.token)
      || typeof config.model !== 'string' || !config.model || config.model.length > 200
      || typeof config.prompt !== 'string' || !config.prompt || Buffer.byteLength(config.prompt) > 200000) {
    throw new Error('invalid launch');
  }
  launched = true;
  await fs.mkdir('/tmp/home/.qwen', { recursive: true, mode: 0o700 });
  await fs.mkdir('/tmp/project', { recursive: true });
  server = http.createServer(async (request, response) => {
    const path = request.url;
    if (request.headers.origin !== undefined || !['127.0.0.1', 'localhost'].includes((request.headers.host || '').split(':')[0])) {
      response.writeHead(403).end(); return;
    }
    if (!((path === '/mcp' && ['GET', 'POST'].includes(request.method))
          || (path === '/v1/chat/completions' && request.method === 'POST'))) {
      response.writeHead(404).end(); return;
    }
    if (pending.size >= 16 || sequence >= 1000 || stopping) {
      response.writeHead(429).end(); return;
    }
    const id = ++sequence;
    let size = 0;
    const chunks = [];
    try {
      for await (const chunk of request) {
        size += chunk.length;
        if (size > MAX_BODY) { response.writeHead(413).end(); return; }
        chunks.push(chunk);
      }
      if (pending.size >= 16 || stopping) { response.writeHead(429).end(); return; }
      pending.set(id, { response, started: false, bytes: 0 });
      response.on('error', () => {});
      response.on('close', () => {
        if (pending.delete(id)) emit({ kind: 'http_cancel', id }).catch(() => stop());
      });
      const headers = {};
      for (const name of ['authorization', 'accept', 'content-type', 'mcp-protocol-version']) {
        if (typeof request.headers[name] === 'string') headers[name] = request.headers[name];
      }
      await emit({ kind: 'http', id, method: request.method, path, headers,
                   body: Buffer.concat(chunks).toString('base64') });
    } catch {
      pending.delete(id);
      response.destroy();
    }
  });
  server.headersTimeout = 10000;
  server.requestTimeout = 10000;
  server.listen(0, '127.0.0.1');
  await once(server, 'listening');
  const url = `http://127.0.0.1:${server.address().port}`;
  const settings = {
    general: { chatRecording: false }, privacy: { usageStatisticsEnabled: false }, telemetry: { enabled: false },
    tools: { core: ['ludraft_no_builtin_tools'], allowed: tools, useRipgrep: false },
    mcpServers: { ludraft: { httpUrl: `${url}/mcp`, headers: { Authorization: `Bearer ${config.token}` },
                            trust: true, includeTools: tools } },
  };
  await fs.writeFile('/tmp/home/.qwen/settings.json', JSON.stringify(settings), { mode: 0o600 });
  const env = {
    PATH: '/usr/local/bin:/usr/bin:/bin', HOME: '/tmp/home', TMPDIR: '/tmp',
    OPENAI_API_KEY: config.token, OPENAI_BASE_URL: `${url}/v1`, OPENAI_MODEL: config.model,
    QWEN_CODE_SYSTEM_SETTINGS_PATH: '/tmp/absent-system.json', QWEN_CODE_SYSTEM_DEFAULTS_PATH: '/tmp/absent-defaults.json',
  };
  child = spawn(process.execPath, ['/opt/opengame/dist/cli.js', '--auth-type', 'openai',
    '--output-format', 'stream-json', '--approval-mode', 'default', '--max-session-turns', '20',
    '--allowed-mcp-server-names', 'ludraft', '--prompt', config.prompt], {
    cwd: '/tmp/project', env, stdio: ['ignore', 'pipe', 'pipe'],
  });
  const pump = async (source, kind) => {
    for await (const chunk of source) await emit({ kind, data: chunk.toString('base64') });
  };
  const stdout = pump(child.stdout, 'event');
  const stderr = pump(child.stderr, 'stderr');
  child.on('error', () => stop());
  child.on('close', async (code, signal) => {
    try {
      await Promise.all([stdout, stderr]);
      await emit({ kind: 'exit', code, signal });
    } finally {
      finished = true;
      process.exitCode = code === 0 ? 0 : 1;
      await stop();
      process.stdin.destroy();
    }
  });
  await emit({ kind: 'started' });
}

async function dispatch(message) {
  if (message.kind === 'launch') return launch(message);
  if (message.kind === 'stop') return stop();
  if (!Number.isSafeInteger(message.id)) throw new Error('invalid response id');
  const entry = pending.get(message.id);
  if (!entry) return; // The HTTP client may already have disconnected.
  if (message.kind === 'http_start') {
    if (entry.started || !Number.isInteger(message.status) || message.status < 200 || message.status > 599) throw new Error('invalid HTTP status');
    const headers = {};
    for (const name of ['content-type', 'cache-control', 'allow', 'x-accel-buffering']) {
      const value = message.headers?.[name];
      if (typeof value === 'string' && value.length <= 300 && !/[\r\n]/.test(value)) headers[name] = value;
    }
    entry.response.writeHead(message.status, headers);
    entry.started = true;
  } else if (message.kind === 'http_body') {
    if (!entry.started || typeof message.data !== 'string' || message.data.length > 100000) throw new Error('invalid HTTP body');
    const chunk = Buffer.from(message.data, 'base64');
    entry.bytes += chunk.length;
    if (entry.bytes > 10_000_000) throw new Error('HTTP response limit');
    if (!entry.response.write(chunk)) {
      await new Promise((resolve) => {
        const finish = () => { entry.response.off('drain', finish); entry.response.off('close', finish); resolve(); };
        entry.response.once('drain', finish);
        entry.response.once('close', finish);
      });
    }
  } else if (message.kind === 'http_end') {
    pending.delete(message.id);
    entry.response.end();
  } else if (message.kind === 'http_abort') {
    pending.delete(message.id);
    entry.response.destroy();
  } else throw new Error('unknown control message');
}

process.on('SIGTERM', () => stop());
try {
  await emit({ kind: 'ready', protocol: 1 });
  let buffer = '';
  process.stdin.setEncoding('utf8');
  for await (const chunk of process.stdin) {
    buffer += chunk;
    let end;
    while ((end = buffer.indexOf('\n')) >= 0) {
      if (end > MAX_FRAME) throw new Error('control frame limit');
      const line = buffer.slice(0, end); buffer = buffer.slice(end + 1);
      await dispatch(JSON.parse(line));
    }
    if (Buffer.byteLength(buffer) > MAX_FRAME) throw new Error('control frame limit');
  }
} catch {
  if (!finished) {
    await emit({ kind: 'fatal', message: 'OpenGame bridge protocol failed' }).catch(() => {});
    process.exitCode = 1;
  }
} finally {
  await stop();
}
