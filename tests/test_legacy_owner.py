"""Real persisted predecessor DB is produced and reopened in different processes."""
import json
import os
from pathlib import Path
import subprocess
import sqlite3
import sys

import pytest


@pytest.mark.parametrize("action,repeat", [("done","once"),("done","repeat"),("correct","once"),
    ("waiting","once"),("snooze","once"),("remind","once"),("archive","once"),("ordinary","once")])
def test_actual_legacy_owner_transition_survives_upgrade(tmp_path, action, repeat):
    legacy = os.environ.get("ES_LEGACY_SOURCE")
    source = os.environ.get("ES_REPAIR_SOURCE", str(Path(__file__).resolve().parents[1]))
    script = Path(__file__).with_name("legacy_owner_process.py")
    env = dict(os.environ, ES_LEGACY_CASE=str(tmp_path/"persisted-case"), PYTHONDONTWRITEBYTECODE="1")
    phases = [("resume", source)]
    if legacy:
        phases.insert(0, ("seed", legacy))
    else:
        # Public CI reopens actual predecessor-produced synthetic databases.
        # Local qualification also reruns the exact predecessor in a subprocess.
        case = tmp_path / "persisted-case"
        home = case / "home"
        state = home / "state"
        state.mkdir(parents=True)
        text = (Path(__file__).parent / "fixtures/legacy-owner" / (action + ".json")).read_text()
        fixture = json.loads(text.replace("{{CASE_HOME}}", str(home)))
        assert fixture["predecessor"] == "3efca2b3f3831f1d45cd06c4647a4bf5555893f7"
        with sqlite3.connect(state / fixture["database_name"]) as db:
            db.executescript(fixture["sql"])
        (case / "seed.json").write_text(json.dumps(fixture["seed"]))
    for phase, root in phases:
        env["ES_PHASE_SOURCE"] = root
        argv=[sys.executable,"-B",str(script),phase,action,repeat]
        result=subprocess.run(argv,env=env,cwd=tmp_path,capture_output=True,text=True,timeout=25)
        (tmp_path/(phase+".txt")).write_text(result.stdout+result.stderr)
        (tmp_path/(phase+"-command.json")).write_text(json.dumps({"argv":argv,"cwd":str(tmp_path),"source":root,"exit":result.returncode},indent=2)+"\n")
        assert result.returncode==0, result.stdout+result.stderr
