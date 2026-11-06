import { accessSync, constants } from 'node:fs';
import { delimiter, isAbsolute, join } from 'node:path';
import { fileURLToPath } from 'node:url';
export const root = fileURLToPath(new URL('../../', import.meta.url));

function executable(path) {
  if (!path || !isAbsolute(path)) return false;
  try { accessSync(path, constants.X_OK); return true; } catch { return false; }
}

export function browserExecutable(chromium, env = process.env) {
  if (env.ES_BROWSER_EXECUTABLE) {
    if (!executable(env.ES_BROWSER_EXECUTABLE)) throw new Error('ES_BROWSER_EXECUTABLE must name an existing absolute executable.');
    return env.ES_BROWSER_EXECUTABLE;
  }
  const bundled = chromium.executablePath();
  if (executable(bundled)) return bundled;
  for (const directory of (env.PATH || '').split(delimiter).filter(isAbsolute)) {
    for (const name of ['chromium', 'chromium-browser', 'google-chrome', 'google-chrome-stable']) {
      const candidate = join(directory, name);
      if (executable(candidate)) return candidate;
    }
  }
  throw new Error('No Chromium found. Run node tests/desktop/setup.mjs --browser, or set ES_BROWSER_EXECUTABLE to an absolute Chromium executable.');
}

export function bridgePython(env = process.env) {
  const python = env.ES_PYTHON || join(root, '.local/backend/venv/bin/python');
  if (!executable(python)) throw new Error('No backend test Python found. Run the backend setup documented in README.md, or set ES_PYTHON to an absolute Python with requirements.lock installed.');
  return python;
}
