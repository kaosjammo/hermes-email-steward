// Installs only into ignored task-owned state. Never touches a Hermes install.
import { copyFileSync, mkdirSync } from 'node:fs';
import { execFileSync } from 'node:child_process';
import { fileURLToPath } from 'node:url';
import { join } from 'node:path';
const root = fileURLToPath(new URL('../../', import.meta.url));
const major = Number(process.versions.node.split('.')[0]);
if (![22, 24].includes(major) || (major === 22 && Number(process.versions.node.split('.')[1]) < 12)) {
  throw new Error('Desktop tests require Node 22.12+ (22.x) or 24.x; see tests/desktop/README.md.');
}
const local = join(root, '.local/desktop');
const temp = join(root, '.local/tmp');
mkdirSync(local, { recursive: true, mode: 0o700 });
mkdirSync(temp, { recursive: true, mode: 0o700 });
for (const name of ['package.json', 'package-lock.json']) copyFileSync(new URL(name, import.meta.url), join(local, name));
const env = { ...process.env, TMPDIR: temp, npm_config_cache: join(local, 'npm-cache'), PLAYWRIGHT_BROWSERS_PATH: join(local, 'browsers') };
execFileSync('npm', ['ci', '--prefix', local, '--no-audit', '--no-fund', ...(process.argv.includes('--offline') ? ['--offline'] : [])], { cwd: root, env, stdio: 'inherit' });
if (process.argv.includes('--browser')) {
  execFileSync(process.execPath, [join(local, 'node_modules/playwright-core/cli.js'), 'install', 'chromium'], { cwd: root, env, stdio: 'inherit' });
}
console.log('Scoped Desktop dependencies ready. Use --browser to install the pinned Chromium under .local/desktop/browsers.');
