"""Separate-process old-production seed / successor resume. Synthetic wire only."""
from contextlib import ExitStack
import json
import os
from pathlib import Path
import socket
import sys
import time
from unittest.mock import patch

SOURCE = Path(os.environ["ES_PHASE_SOURCE"])
os.environ["ES_REPAIR_SOURCE"] = str(SOURCE)
sys.path[:0] = [str(SOURCE), str(Path(__file__).resolve().parent)]
from repair_wire import AccountWire, compose
from email_steward.service import Steward
from email_steward.security import Access, Settings
from email_steward.store import Store
from email_steward.worker import Worker
from email_steward.synthetic import SyntheticModel, SyntheticDelivery
import email_steward
assert Path(email_steward.__file__).resolve().is_relative_to(SOURCE.resolve())

root = Path(os.environ["ES_LEGACY_CASE"])
phase, action, repeat = sys.argv[1:]
network = []
def deny(*args, **kwargs):
    network.append(True)
    raise AssertionError("Real network is forbidden")

with ExitStack() as stack:
    for name in ("connect", "connect_ex"):
        stack.enter_context(patch.object(socket.socket, name, deny))
    for name in ("getaddrinfo", "create_connection"):
        stack.enter_context(patch.object(socket, name, deny))
    wire = AccountWire()
    with wire.stack():
        if phase == "seed":
            root.mkdir()
            s, a, w, delivery = compose(root/"home")
            wire.add("a-pending", "t", "Please approve obsolete quote today.", "Notice")
            wire.add("m2", "t", "Please approve disputed renewal by Friday at 17:00.", "Question")
            wire.boxes["A"]["messages"]["a-pending"]["internalDate"] = "1003000"
            wire.boxes["A"]["messages"]["m2"]["internalDate"] = "1001000"
            hit = []
            def once(point):
                if point == "after_triaged" and not hit:
                    hit.append(True)
                    raise RuntimeError("Synthetic old production interruption")
            w.crash = once
            w.tick(1100)
            if action == "correct":
                s.correct(a,"ax1",{"version":s.store.item("ax1")["version"],"classification":"needs_review","always":False})
            elif action != "ordinary":
                s.action(a,"ax1",action,at=time.time()+3600 if action in {"waiting","snooze","remind"} else None)
            before=s.store.item("ax1")
            assert "owner_queue" not in before and "owner_received" not in before
            for m in wire.boxes["A"]["messages"].values():
                m["labelIds"]=sorted(set(m["labelIds"])|{"INBOX"})
            (root/"seed.json").write_text(json.dumps({"source":str(SOURCE),"before":before,"boxes":wire.boxes,"jobs":s.store.rows("SELECT * FROM jobs")},indent=2)+"\n")
        else:
            saved=json.loads((root/"seed.json").read_text());wire.boxes=saved["boxes"]
            settings=Settings(home=root/"home",profile="synthetic-repair",owner="owner",destination="private",private_confirmed=True,timezone="UTC")
            s=Steward(Store(settings.home/"state"),settings,model=SyntheticModel())
            a=Access(settings.home,"owner","synthetic-owner");delivery=SyntheticDelivery();w=Worker(s,delivery)
            if repeat == "repeat":
                s.action(a,"ax1","done")
                assert "owner_queue" in s.store.item("ax1"), "Repeated Done must initialise a durable fence"
            w.tick(1200)
            after=s.store.item("ax1")
            observed={"source":str(SOURCE),"before":saved["before"],"after":after,"jobs":s.store.rows("SELECT * FROM jobs"),"outbox":s.store.rows("SELECT * FROM outbox"),"wire":wire.calls}
            (root/"resume.json").write_text(json.dumps(observed,indent=2)+"\n")
            if action != "ordinary":
                for key in ("classification","summary","deadline","reason","latest_message","reminder_at","snooze_until"):
                    assert after[key] == saved["before"][key], (action,key)
                assert not s.store.rows("SELECT id FROM outbox WHERE id LIKE 'urgent:%'")
                assert not any("INBOX" in (c["body"] or {}).get("removeLabelIds",[]) for c in wire.calls)
                assert "owner_queue" in after
                fence=after["owner_queue"]
                w.tick(1250)
                assert s.store.item("ax1")["owner_queue"] == fence
            else:
                assert after["latest_message"] == "a-pending" and "owner_queue" not in after
            assert all(j["status"] == "done" for j in s.store.rows("SELECT * FROM jobs"))
            assert all("Label_A" in m["labelIds"] and "UNREAD" in m["labelIds"] for m in wire.boxes["A"]["messages"].values())
            wire.add("new", "t", "Please approve replacement agreement by Monday at 17:00.", "New question")
            wire.boxes["A"]["messages"]["new"]["internalDate"]="1004000"
            w.tick(1300)
            assert s.store.item("ax1")["latest_message"]=="new"
            assert s.store.item("ax1")["classification"]=="needs_action"
            assert "Monday" in s.store.item("ax1")["deadline"]
        assert wire.foreign()==[] and network==[]
        print(json.dumps({"phase":phase,"control":action,"repeat":repeat,"source":str(SOURCE),"network_attempts":0,"status":"passed"}))
