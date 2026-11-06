#!/usr/bin/env python3
"""Validate/discover copied plugin using actual read-only upstream SDK and isolated home."""
import argparse
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--upstream", type=Path, default=ROOT.parent)
    args = parser.parse_args()
    task = ROOT / ".local/backend/native"
    home, runtime, cwd = task / "home", task / "runtime", task / "cwd"
    for path in (task, home, runtime, cwd, ROOT / ".local/tmp", task / "empty-bundled"):
        path.mkdir(parents=True, exist_ok=True, mode=0o700)
    plugin = home / "plugins/email-steward"
    plugin.mkdir(parents=True, exist_ok=True)
    for name in ("email_steward", "dashboard", "desktop"):
        if (ROOT / name).exists():
            shutil.copytree(ROOT / name, plugin / name, dirs_exist_ok=True,
                            ignore=shutil.ignore_patterns("__pycache__", "*.pyc"))
    for name in ("plugin.yaml", "__init__.py", "pyproject.toml"):
        shutil.copyfile(ROOT / name, plugin / name)
    (home / "config.yaml").write_text("plugins:\n  enabled: [email-steward]\n  isolation: in_process\n  load_timeout_seconds: 0\n")
    code = '''
import importlib.util, json, os
from pathlib import Path
from hermes_cli.plugin_validate import validate_plugin_dir
from hermes_cli.plugins import get_plugin_manager
from tools.registry import registry
plugin=Path(os.environ['HERMES_HOME'])/'plugins/email-steward'
report=validate_plugin_dir(plugin)
print(json.dumps({'validation':report.to_dict()}))
assert report.ok, report.failures
manager=get_plugin_manager()
manager.discover_and_load()
found=next(p for p in manager.list_plugins() if p['name']=='email-steward')
assert found['enabled'] and not found.get('error'), found
assert registry.get_entry('email_steward',scope=manager.scope_key)
assert 'email-steward' in manager._plugin_commands
assert 'email-steward' in manager._cli_commands
spec=importlib.util.spec_from_file_location('synthetic_native_backend',plugin/'dashboard/plugin_api.py')
module=importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)
assert any(r.path=='/rules' for r in module.router.routes)
from hermes_cli.plugin_oauth import parse_oauth_clients
import hermes_yaml
clients,problems=parse_oauth_clients(hermes_yaml.safe_load((plugin/'plugin.yaml').read_text()))
assert not problems and {c.id for c in clients}=={'gmail-1','gmail-2','gmail-3','gmail-4'}
print(json.dumps({'discovery':found,'tool':True,'slash_command':True,'cli':True,'rest_router':True,'distinct_declared_oauth_grants':[c.id for c in clients],'live_gmail':'UNRUN'}))
manager.unload()
'''
    env = {"PATH": os.environ.get("PATH", "/usr/bin:/bin"), "LANG": "C.UTF-8", "TMPDIR": str(ROOT / ".local/tmp"),
           "PYTHONDONTWRITEBYTECODE": "1", "PYTHONPATH": str(args.upstream.resolve()),
           "HERMES_HOME": str(home), "HERMES_RUNTIME_DIR": str(runtime),
           "HERMES_BUNDLED_PLUGINS": str(task / "empty-bundled")}
    result = subprocess.run([sys.executable, "-c", code], cwd=cwd, env=env, timeout=60)
    return result.returncode


if __name__ == "__main__":
    raise SystemExit(main())
