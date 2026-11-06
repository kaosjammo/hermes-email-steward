// JSON-lines transport to actual production router; only host identity, provider
// and state paths are synthetic. No shell, live host, mailbox or credentials.
import { spawn } from 'node:child_process';
import { createInterface } from 'node:readline';
import { bridgePython } from './environment.mjs';
export class ProductionFixture {
  constructor() {
    this.calls = []; this.fail = null; this.delay = 0; this.denied = false; this.queue = [];
    const root = new URL('../../', import.meta.url).pathname;
    this.child = spawn(bridgePython(), ['-B', `${root}tests/desktop/production_bridge.py`], { cwd: root, env: { ...process.env, PYTHONDONTWRITEBYTECODE: '1' }, stdio: ['pipe', 'pipe', 'inherit'] });
    createInterface({ input: this.child.stdout }).on('line', line => this.queue.shift()?.resolve(JSON.parse(line)));
    this.child.on('exit', code => { for (const pending of this.queue.splice(0)) pending.reject(new Error(`Production bridge exited ${code}`)); });
  }
  request(command) { return new Promise((resolve, reject) => { this.queue.push({ resolve, reject }); this.child.stdin.write(JSON.stringify(command) + '\n'); }); }
  async reset() { await this.request({ op: 'reset' }); this.calls = []; this.denied = false; this.fail = null; this.delay = 0; }
  conflict() { return this.request({ op: 'conflict' }); }
  restart() { return this.request({ op: 'restart' }); }
  async rest(path, { method = 'GET', body } = {}) {
    this.calls.push({ path, method, body: body || null });
    if (this.delay) await new Promise(resolve => setTimeout(resolve, this.delay));
    if (this.fail && method !== 'GET') { this.fail = null; const error = new Error('{"error":{"code":"unavailable","message":"Synthetic service unavailable; try reloading."}}'); error.status = 503; throw error; }
    const response = await this.request({ path, method, body, denied: this.denied });
    if (response.status >= 400) { const error = new Error(JSON.stringify(response.body)); error.status = response.status; throw error; }
    return response.body;
  }
  close() { this.child.stdin.end(); }
}
