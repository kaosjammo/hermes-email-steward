// One-command synthetic SDK/actual service integration, with owned-host cleanup.
import { spawn } from 'node:child_process';
import { mkdirSync } from 'node:fs';
import { once } from 'node:events';
import { join } from 'node:path';
import { root } from './environment.mjs';
const temp = process.env.ES_UI_TMPDIR || join(root, '.local/tmp');
mkdirSync(temp, { recursive: true, mode: 0o700 });
const env = { ...process.env, TMPDIR: temp, PYTHONDONTWRITEBYTECODE: '1' };
const server = spawn(process.execPath, [join(root, 'tests/desktop/serve.mjs'), '--production'],
  { cwd: root, env, stdio: ['ignore', 'pipe', 'inherit'] });
const stopped = once(server, 'exit');
let ready;
const readiness = new Promise((resolve, reject) => {
  let output = '';
  server.stdout.on('data', chunk => {
    process.stdout.write(chunk); output += chunk;
    if (output.includes('SYNTHETIC SDK host http://127.0.0.1:')) { ready = true; resolve(); }
  });
  server.on('error', reject);
  server.on('exit', code => { if (!ready) reject(new Error(`UI fixture host exited ${code} before ready`)); });
});
const timeout = setTimeout(() => server.kill('SIGTERM'), 30000);
let exit = 1;
try {
  await readiness; clearTimeout(timeout);
  const test = spawn(process.execPath, [join(root, 'tests/desktop/browser.test.mjs')],
    { cwd: root, env, stdio: 'inherit' });
  const [code] = await once(test, 'exit'); exit = code ?? 1;
} finally {
  clearTimeout(timeout);
  if (server.exitCode === null) server.kill('SIGINT');
  await stopped;
}
process.exitCode = exit;
