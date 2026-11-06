#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."
mkdir -p .local/tmp .local/backend .local/evidence/backend
export TMPDIR="$PWD/.local/tmp"
export PYTHONDONTWRITEBYTECODE=1
export HERMES_HOME="$PWD/.local/backend/test-hermes-home"
export HERMES_RUNTIME_DIR="$PWD/.local/backend/test-hermes-runtime"
export HERMES_UPSTREAM="${HERMES_UPSTREAM:-$PWD/..}"
PYTHON="${ES_PYTHON:-${EMAIL_STEWARD_PYTHON:-$PWD/.local/backend/venv/bin/python}}"
if [[ ! -x "$PYTHON" ]]; then
  printf '%s\n' 'Missing task Python. Run scripts/setup.sh, or set ES_PYTHON to a prepared interpreter.' >&2
  exit 2
fi
exec "$PYTHON" -m pytest -q --tb=short --basetemp="$PWD/.local/backend/pytest-tmp" "$@"
