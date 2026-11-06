"""Real persisted predecessor DB is produced and reopened in different processes."""
import json
import os
from pathlib import Path
import subprocess
import sys

import pytest


@pytest.mark.parametrize("action,repeat", [("done","once"),("done","repeat"),("correct","once"),
    ("waiting","once"),("snooze","once"),("remind","once"),("archive","once"),("ordinary","once")])
def test_actual_legacy_owner_transition_survives_upgrade(tmp_path, action, repeat):
    legacy = os.environ.get("ES_LEGACY_SOURCE")
    if not legacy:
        pytest.skip("Set ES_LEGACY_SOURCE to an exact git archive of 3efca2b for the production upgrade qualification")
    source = os.environ.get("ES_REPAIR_SOURCE", str(Path(__file__).resolve().parents[1]))
    script = Path(__file__).with_name("legacy_owner_process.py")
    env = dict(os.environ, ES_LEGACY_CASE=str(tmp_path/"persisted-case"), PYTHONDONTWRITEBYTECODE="1")
    for phase, root in (("seed",legacy),("resume",source)):
        env["ES_PHASE_SOURCE"] = root
        argv=[sys.executable,"-B",str(script),phase,action,repeat]
        result=subprocess.run(argv,env=env,cwd=tmp_path,capture_output=True,text=True,timeout=25)
        (tmp_path/(phase+".txt")).write_text(result.stdout+result.stderr)
        (tmp_path/(phase+"-command.json")).write_text(json.dumps({"argv":argv,"cwd":str(tmp_path),"source":root,"exit":result.returncode},indent=2)+"\n")
        assert result.returncode==0, result.stdout+result.stderr
