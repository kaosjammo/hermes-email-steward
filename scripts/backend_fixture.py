#!/usr/bin/env python3
"""SYNTHETIC ONLY fixture app for local integration; never loads Hermes config or real Gmail."""
from pathlib import Path
import os
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from fastapi import FastAPI
from email_steward.api import create_router
from email_steward.security import Settings, Access
from email_steward.service import Steward
from email_steward.store import Store, private_dir
from email_steward.synthetic import SyntheticGmail, SyntheticModel


def create_app(state_root=None):
    home = private_dir(state_root or ROOT / ".local/backend/desktop-fixture")
    settings = Settings(home=home, profile="synthetic", owner="synthetic-owner", destination="synthetic-private",
                        destination_type="dm", private_confirmed=True, desktop_subject="desktop:synthetic", timezone="UTC")
    providers = {"gmail-1": SyntheticGmail("alex@example.test"), "gmail-2": SyntheticGmail("work@example.test")}
    service = Steward(Store(home / "state"), settings, lambda account: providers[account["id"]], SyntheticModel())
    access = Access(settings.home, settings.owner, "synthetic-fixture")
    if not service.store.accounts():
        for slot, name in (("gmail-1", "Synthetic personal"), ("gmail-2", "Synthetic work")):
            service.connect(access, slot, providers[slot].address, name)
    app = FastAPI(title="SYNTHETIC Email Steward fixture — no real mail")
    @app.middleware("http")
    async def trusted_synthetic_host(request, call_next):
        # This app has ONLY synthetic providers. Binding test identity is never part of native registration.
        request.state.native_http_principal = dict(profile_id=str(settings.home), subject=settings.desktop_subject,
            purpose="native-http", scope="profile", capabilities=frozenset({"http:owner"}))
        response = await call_next(request)
        response.headers["X-Email-Steward-Fixture"] = "synthetic-only"
        return response
    app.include_router(create_router(lambda: service), prefix="/api/plugins/email-steward")
    app.state.steward = service
    return app


if __name__ == "__main__":
    import argparse
    import uvicorn
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--port", type=int, default=8766)
    args = parser.parse_args()
    tmp = private_dir(ROOT / ".local/tmp")
    os.environ["TMPDIR"] = str(tmp)
    uvicorn.run(create_app(), host="127.0.0.1", port=args.port)
