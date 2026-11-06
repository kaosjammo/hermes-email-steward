import test from 'node:test';
import assert from 'node:assert/strict';
import { browserExecutable, bridgePython } from './environment.mjs';

test('browser discovery accepts an explicit executable and refuses a broken override', () => {
  const chromium = { executablePath: () => '/missing/pinned-chromium' };
  assert.equal(browserExecutable(chromium, { ES_BROWSER_EXECUTABLE: process.execPath }), process.execPath);
  assert.throws(() => browserExecutable(chromium, { ES_BROWSER_EXECUTABLE: '/missing/browser' }), /existing absolute executable/);
  assert.throws(() => browserExecutable(chromium, { PATH: '' }), /setup.mjs --browser/);
  assert.equal(browserExecutable({ executablePath: () => process.execPath }, {}), process.execPath);
});

test('bridge dependency selection supports an explicit interpreter and actionable failure', () => {
  assert.equal(bridgePython({ ES_PYTHON: process.execPath }), process.execPath);
  assert.throws(() => bridgePython({ ES_PYTHON: '/missing/python' }), /backend setup/);
});
