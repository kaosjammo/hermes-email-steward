#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."
export TMPDIR="$PWD/.local/tmp"
export PYTHONDONTWRITEBYTECODE=1
mkdir -p .local/tmp .local/backend/dist
PYTHON="${ES_PYTHON:-$PWD/.local/backend/venv/bin/python}"
"$PYTHON" - <<'PY'
from pathlib import Path
import shutil, subprocess, sys, tarfile
root=Path.cwd()
stage=root/'.local/backend/package-src'
if stage.is_symlink():
    raise SystemExit('Refusing symlink package stage')
if stage.exists():
    shutil.rmtree(stage)
stage.mkdir(mode=0o700)
for name in ('email_steward','dashboard','desktop','docs','scripts','tests'):
    if (root/name).exists():
        shutil.copytree(root/name,stage/name,ignore=shutil.ignore_patterns('__pycache__','*.pyc','node_modules'))
for name in ('__init__.py','plugin.yaml','pyproject.toml','requirements.lock','MANIFEST.in','README.md'):
    shutil.copyfile(root/name,stage/name)
output=root/'.local/backend/dist'
# Native directory bundle includes the three plugin surfaces and source/package docs.
with tarfile.open(output/'email-steward-plugin-0.1.0.tar.gz','w:gz') as archive:
    archive.add(stage,arcname='email-steward')
subprocess.run([sys.executable,'-m','build','--no-isolation','--outdir',str(output)],cwd=stage,check=True)
print('Package outputs:', output)
PY
