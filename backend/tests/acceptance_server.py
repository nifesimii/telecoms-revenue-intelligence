"""The real API for the rendered acceptance suite, on its own port and logins.

Run only by frontend/playwright.config.js. Configuration is set on the loaded
module, because loading it applies a developer's .env. The route added here lets
a test start from known records and exists in no other server.
"""
from __future__ import annotations

import json
import os
import secrets

from backend import config

config.CORS_ORIGINS = [os.environ["ACCEPTANCE_ORIGIN"]]
config.DEMO_SESSION_SECRET = secrets.token_urlsafe(32)
config.DEMO_LOGINS = json.dumps([
    {"username": "finance", "password": os.environ["ACCEPTANCE_PASSWORD"], "role": "internal"},
    {"username": "partner-296065", "password": os.environ["ACCEPTANCE_PASSWORD"], "role": "partner", "account_code": "296065"},
    {"username": "partner-353072", "password": os.environ["ACCEPTANCE_PASSWORD"], "role": "partner", "account_code": "353072"},
])

from backend.main import app  # noqa: E402
from backend.sales.simulation import _draft_key, simulation  # noqa: E402


@app.put("/__acceptance__/simulation", status_code=204)
def replace_simulation(state: dict) -> None:
    with simulation._lock:
        simulation._next_sequence = state["next_sequence"]
        simulation._next_collection_sequence = state["next_collection_sequence"]
        simulation._drafts = {_draft_key(draft["account_code"], draft["period"]): draft for draft in state["drafts"]}
        simulation._invoices = state["invoices"]
        simulation._collections = state["collections"]
        simulation._next_order_sequence = state.get("next_order_sequence", 1)
        simulation._order_drafts = {draft["account_code"]: draft for draft in state.get("order_drafts", [])}
        simulation._deleted_order_tokens = {}
        simulation._orders = state.get("orders", [])


# Ahead of the application's catch-all route, which would otherwise answer first.
app.router.routes.insert(0, app.router.routes.pop())
