# Reproducing the synthetic Desktop tests

These tests exercise the shipped ESM UI using real React/React Query and a
synthetic SDK presentation/host adapter. The production bridge calls the actual
router, service and SQLite store with synthetic Gmail and trusted-host identity.
They do not establish actual Hermes Desktop, OAuth or mobile acceptance.

Prerequisites: Node 22.12+ (22.x) or 24.x, npm, Python 3.14 for the pinned SDK qualification, the backend
dependencies from tracked `requirements.lock`, and a runnable Chromium. Native
attachment tests also need the Linux tools listed in `docs/EXTRACTION.md`.
Nothing here installs into Hermes or changes a running profile.

From the checkout root:

```bash
mkdir -p .local/tmp .local/evidence/desktop
export TMPDIR="$PWD/.local/tmp"
# Backend setup is documented in the root README. This explicit equivalent
# creates a task-owned Python instead of assuming any pre-existing venv:
python3 -m venv .local/desktop/python
.local/desktop/python/bin/python -m pip install -r requirements.lock
export ES_PYTHON="$PWD/.local/desktop/python/bin/python"

# Tracked exact direct versions and transitive integrity lock, installed only
# under .local/desktop; --browser downloads the pinned Playwright Chromium there.
node tests/desktop/setup.mjs --browser
# Omit --browser if supplying an existing Chromium explicitly:
# export ES_BROWSER_EXECUTABLE="/absolute/path/to/chromium"
# Discovery also accepts Chromium/Chrome on PATH. No personal cache is assumed.

node --test tests/desktop/environment.test.mjs
node --experimental-loader ./tests/desktop/loader.mjs tests/desktop/rules.test.mjs
# One command starts its own host, runs the actual router/store browser suite,
# and stops that host. Chromium's sandbox remains enabled.
node tests/desktop/run-browser.mjs
# Or run the individual host and driver for manual inspection:
# Start in one task-owned terminal; reads the interpreter override above:
node tests/desktop/serve.mjs --production
# In a second terminal with the same TMPDIR and optional browser override:
node tests/desktop/browser.test.mjs
# Stop only the server you started with Ctrl-C after the test. It closes its bridge.
```

`setup.mjs` copies the tracked package manifest/lock to `.local/desktop` and uses
`npm ci`; its npm cache, browser downloads and temporary files remain under
`.local/`. `--offline` uses an already populated task-owned npm cache. Network
or browser OS-library failures are setup failures, not test passes. The pinned
browser may need platform libraries already installed; inspect the Playwright
diagnostic. This script never installs OS packages or disables browser security.
`PLAYWRIGHT_BROWSERS_PATH` can explicitly select another prepared browser cache;
`ES_BROWSER_EXECUTABLE` takes precedence and a broken override fails visibly.
`ES_UI_EVIDENCE` may name a separate task-owned output directory for a new run,
preserving earlier screenshots/receipts.
`ES_UI_TMPDIR=.local/tmp` (from the checkout root) keeps Chromium's socket path
short in deeply nested isolated qualification copies; it still resolves inside
that copy's ignored task state. The default is its absolute `.local/tmp` path.

Tests write synthetic fixtures/screenshots/logs under `.local/desktop` and
`.local/evidence/desktop`; never point the bridge at a real Hermes profile.
The host chooses a free loopback port and records it in
`.local/desktop/server.json`. Unavailable preview/save injection is host-only.
