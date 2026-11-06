// Loopback-only, task-owned synthetic fixture API + rendering host.
import { createServer } from 'node:http';
import { mkdirSync, readFileSync, writeFileSync } from 'node:fs';
import { createRequire } from 'node:module';
import { Fixture } from './fixture.mjs';
import { ProductionFixture } from './production-fixture.mjs';
const require = createRequire(new URL('../../.local/desktop/package.json', import.meta.url));
const { build } = require('esbuild');
const root = new URL('../../', import.meta.url).pathname;
const evidence = process.env.ES_UI_EVIDENCE || `${root}.local/evidence/desktop`;
mkdirSync(evidence, { recursive: true, mode: 0o700 });
await build({ entryPoints: [`${root}tests/desktop/browser-host.mjs`], bundle: true, format: 'esm', outfile: `${root}.local/desktop/browser.js`, nodePaths: [`${root}.local/desktop/node_modules`], alias: { '@hermes/plugin-sdk': `${root}tests/desktop/sdk-host.mjs` } });
const production = process.argv.includes('--production');
const fixture = production ? new ProductionFixture() : new Fixture(`${root}.local/desktop/server-state.json`);
const html = `<!doctype html><html lang="en"><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1"><title>Email Steward — synthetic SDK host</title><style>
:root{--ui-text-primary:#d9e0eb;--ui-text-secondary:#a7b3c6;--ui-text-quaternary:#8191a8;--ui-stroke-secondary:#384358;--ui-accent:#79adfa;--ui-bg-secondary:#202938;--ui-bg-quaternary:#2b3546;font-family:system-ui,sans-serif;color:var(--ui-text-primary);background:#171e2a}body{margin:0}button,input,textarea,select{font:inherit}button{cursor:pointer}button:disabled{cursor:default;opacity:.5}[data-slot=button]{border:1px solid var(--ui-stroke-secondary);border-radius:3px;padding:7px 12px;background:var(--ui-bg-quaternary);color:var(--ui-text-primary)}[data-variant=default]{background:var(--ui-accent);color:var(--ui-bg-secondary)}[data-slot=input],[data-slot=textarea]{border:1px solid var(--ui-stroke-secondary);border-radius:4px;background:var(--ui-bg-secondary);color:var(--ui-text-primary);padding:7px 9px}[data-slot=switch]{min-width:42px;border:1px solid var(--ui-stroke-secondary);border-radius:20px;padding:4px 9px;background:var(--ui-bg-quaternary);color:var(--ui-text-primary)}[aria-checked=true]{border-color:var(--ui-accent)}[data-slot=badge]{padding:2px 6px;background:var(--ui-bg-quaternary);font-size:11px;border-radius:3px}[data-slot=skeleton]{background:var(--ui-bg-quaternary)}.test-controls{border-bottom:1px solid var(--ui-stroke-secondary);padding:12px 20px;display:flex;gap:10px;align-items:center;flex-wrap:wrap;font-size:12px}.test-controls button{background:var(--ui-bg-secondary);color:var(--ui-text-primary);border:1px solid var(--ui-stroke-secondary);border-radius:3px;padding:5px 8px}.test-controls strong{margin-right:auto}
</style><div class="test-controls"><strong>Synthetic SDK host · fixture data only · not Hermes Desktop</strong><button data-control="reset">Reset fixture</button><button data-control="fail">Fail next write</button><button data-control="conflict">Change first rule externally</button><button data-control="slow">Slow reads</button><button data-control="deny">Reject host identity</button><button data-control="restore">Restore service</button><button data-control="restart">Restart shared service</button><span id="control-status" role="status"></span></div><div id="root"></div><script type="module" src="/browser.js"></script></html>`;
const server = createServer(async (req, res) => {
  try {
    if (req.url === '/') { res.setHeader('Content-Type', 'text/html'); res.end(html); return; }
    if (req.url === '/browser.js') { res.setHeader('Content-Type', 'text/javascript'); res.end(readFileSync(`${root}.local/desktop/browser.js`)); return; }
    if (req.method === 'POST' && req.url.startsWith('/control/')) {
      const action = req.url.slice('/control/'.length);
      if (action === 'reset') await fixture.reset();
      else if (action === 'fail') fixture.fail = 'write';
      else if (action === 'conflict') await fixture.conflict();
      else if (action === 'restart' && production) await fixture.restart();
      else if (action === 'slow') fixture.delay = 2500;
      else if (action === 'deny') fixture.denied = true;
      else if (action === 'restore') { fixture.denied = false; fixture.delay = 0; fixture.fail = null; }
      else throw new Error('Unknown control');
      res.end(`Fixture control: ${action}`); return;
    }
    if (!req.url.startsWith('/api/plugins/email-steward/')) { res.statusCode = 404; res.end(); return; }
    const chunks = []; for await (const chunk of req) chunks.push(chunk);
    const body = chunks.length ? JSON.parse(Buffer.concat(chunks).toString()) : undefined;
    const data = await fixture.rest(req.url.slice('/api/plugins/email-steward'.length), { method: req.method, body });
    res.setHeader('Content-Type', 'application/json'); res.end(JSON.stringify(data));
  } catch (error) { res.statusCode = error.status || 500; res.setHeader('Content-Type', 'application/json'); res.end(error.status ? error.message : JSON.stringify({ error: { code: 'host_error', message: 'Synthetic host error.' } })); }
});
server.listen(0, '127.0.0.1', () => { const port = server.address().port; writeFileSync(`${root}.local/desktop/server.json`, JSON.stringify({ port, pid: process.pid, production })); console.log(`SYNTHETIC SDK host http://127.0.0.1:${port} — fixture data only`); });
function stop() { fixture.close?.(); writeFileSync(`${evidence}/browser-api-calls.json`, JSON.stringify(fixture.calls, null, 2)); server.close(() => process.exit(0)); server.closeAllConnections(); }
process.on('SIGTERM', stop); process.on('SIGINT', stop);
