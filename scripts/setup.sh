#!/usr/bin/env bash
# Standalone development only; never alters a Hermes-managed environment.
set -euo pipefail
cd "$(dirname "$0")/.."
umask 077
mkdir -p .local/tmp .local/backend/pip-cache .local/evidence/backend
export TMPDIR="$PWD/.local/tmp"
export PIP_CACHE_DIR="$PWD/.local/backend/pip-cache"
export PYTHONDONTWRITEBYTECODE=1
BOOTSTRAP="${ES_BOOTSTRAP_PYTHON:-python3}"
VENV_NAME="${ES_VENV_NAME:-venv}"
if [[ ! "$VENV_NAME" =~ ^[A-Za-z0-9_-]+$ ]]; then
  printf '%s\n' 'ES_VENV_NAME must be a simple task-directory name.' >&2
  exit 2
fi
TASK_VENV="$PWD/.local/backend/$VENV_NAME"
if [[ ! -x "$TASK_VENV/bin/python" ]]; then
  "$BOOTSTRAP" -m venv "$TASK_VENV"
fi
"$TASK_VENV/bin/python" -m pip install --cache-dir "$PIP_CACHE_DIR" -r requirements.lock
"$TASK_VENV/bin/python" -m pip check
printf '%s\n' 'Task venv ready. Install the native Linux parser prerequisites listed in docs/EXTRACTION.md before tests.' 'Run scripts/test.sh; run scripts/validate_hermes.py with a read-only upstream SDK checkout.'
