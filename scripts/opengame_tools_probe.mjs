// Uses the MCP SDK installed in the pinned OpenGame checkout; no model calls.
import assert from 'node:assert/strict';
import { createRequire } from 'node:module';
import { pathToFileURL } from 'node:url';
import path from 'node:path';

const require = createRequire(path.join(process.argv[2], 'package.json'));
const { Client } = await import(pathToFileURL(require.resolve('@modelcontextprotocol/sdk/client/index.js')));
const { StreamableHTTPClientTransport } = await import(pathToFileURL(require.resolve('@modelcontextprotocol/sdk/client/streamableHttp.js')));
const client = new Client({ name: 'ludraft-integration-probe', version: '0.1.0' });
const transport = new StreamableHTTPClientTransport(new URL(process.env.LUDRAFT_TOOL_URL), {
  requestInit: { headers: { Authorization: `Bearer ${process.env.LUDRAFT_TOOL_TOKEN}` } },
});
const steps = [];
async function call(name, args = {}, expectedError = false) {
  const response = await client.callTool({ name, arguments: args }, undefined, { timeout: 180000 });
  assert.equal(Boolean(response.isError), expectedError, `Unexpected tool status: ${name}`);
  return JSON.parse(response.content[0].text);
}
try {
  await client.connect(transport);
  assert.equal((await client.listTools()).tools.length, 4);
  steps.push('sdk_initialize_and_list_four_tools');
  const listed = await call('project_inventory');
  const original = await call('project_read', { path: 'src/config.ts', limit: 32000 });
  assert.equal(original.next_offset, null);
  steps.push('inventory_and_read');
  await call('project_read', { path: '../outside.ts' }, true);
  await call('project_apply', { summary: 'denied protected edit', base_digest: listed.source_digest,
    files: [{ operation: 'update', path: 'package.json', content: '{}' }] }, true);
  steps.push('deny_path_escape_and_protected_edit');
  const changed = await call('project_apply', { summary: 'controlled syntax failure', base_digest: listed.source_digest,
    files: [{ operation: 'update', path: 'src/config.ts', content: 'export const invalid = ;' }] });
  const failure = await call('project_verify', { base_digest: changed.source_digest });
  assert.equal(failure.passed, false);
  assert.match(failure.log, /TS\d+/);
  steps.push('real_typescript_failure_feedback');
  const repaired = await call('project_apply', { summary: 'restore source after diagnostics', base_digest: changed.source_digest,
    files: [{ operation: 'update', path: 'src/config.ts', content: original.content }] });
  assert.equal(repaired.source_digest, listed.source_digest);
  const verified = await call('project_verify', { base_digest: repaired.source_digest });
  assert.equal(verified.passed, true);
  assert.equal(verified.scope, 'phaser-integration-smoke');
  assert.equal(verified.publication_approved, false);
  steps.push('repair_and_real_phaser_smoke');
  process.stdout.write(JSON.stringify({ passed: true, steps, diagnostic_attempts: verified.diagnostic_attempt,
    scope: 'mcp-sdk-and-fixed-phaser-integration', live_model_verified: false, gameplay_verified: false }) + '\n');
} finally {
  await client.close();
}
