// Task-local Node resolution; no project dependency or loader changes.
import { createRequire } from 'node:module';
import { pathToFileURL } from 'node:url';
const resolveLocal = createRequire(new URL('../../.local/desktop/package.json', import.meta.url));
export async function resolve(specifier, context, next) {
  if (specifier === '@hermes/plugin-sdk') return { url: new URL('./sdk-host.mjs', import.meta.url).href, shortCircuit: true };
  if (!specifier.startsWith('.') && !specifier.startsWith('/') && !specifier.startsWith('node:')) {
    try { return { url: pathToFileURL(resolveLocal.resolve(specifier)).href, shortCircuit: true }; } catch {}
  }
  return next(specifier, context);
}
