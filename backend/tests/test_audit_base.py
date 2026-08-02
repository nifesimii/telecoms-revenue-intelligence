"""Tests for the generic audit-module base + module-aware endpoints.

Confirms:
  * the registry resolves and lists zero_commission,
  * zero-commission still produces identical trails through the generic path,
  * the module column threads through _trail_to_row,
  * generic endpoints exist and route correctly (persistence mocked).
"""
from __future__ import annotations

import os
from datetime import datetime, timezone
from unittest.mock import patch

os.environ["USE_SAMPLE_DATA"] = "true"

from fastapi.testclient import TestClient  # noqa: E402

from backend.audit import base  # noqa: E402
from backend.audit.zero_commission_audit import run_period  # noqa: E402
from backend.main import app  # noqa: E402


# ---------------------------------------------------------------------------
# Registry
# ---------------------------------------------------------------------------

def test_registry_lists_zero_commission():
    mods = base.list_modules()
    names = [m.name for m in mods]
    assert "zero_commission" in names


def test_get_module_resolves():
    m = base.get_module("zero_commission")
    assert m is not None
    assert m.label == "Zero-Commission"
    assert m.step_names[0] == "qualifying_activity"
    assert len(m.step_names) == 6


def test_get_unknown_module_returns_none():
    assert base.get_module("does_not_exist") is None


def test_module_build_matches_direct_run_period():
    m = base.get_module("zero_commission")
    via_module = m.build_trails("202602", "simulated")
    via_direct = run_period("202602", "simulated")
    # Same number of trails, same partners, same conclusions.
    assert len(via_module) == len(via_direct) > 0
    a = {(t.partner_code, t.conclusion) for t in via_module}
    b = {(t.partner_code, t.conclusion) for t in via_direct}
    assert a == b


# ---------------------------------------------------------------------------
# Persistence row mapping carries the module
# ---------------------------------------------------------------------------

def test_trail_to_row_includes_module():
    from backend.db.audit_store import _trail_to_row
    trails = run_period("202602", "simulated")
    row = _trail_to_row(trails[0], "run-x", datetime.now(timezone.utc), "zero_commission")
    assert row["module"] == "zero_commission"


# ---------------------------------------------------------------------------
# Generic endpoints
# ---------------------------------------------------------------------------

def test_modules_endpoint_lists_registry():
    c = TestClient(app)
    r = c.get("/assurance/audit/modules")
    assert r.status_code == 200
    names = [m["name"] for m in r.json()]
    assert "zero_commission" in names


def test_run_unknown_module_404():
    c = TestClient(app)
    r = c.post("/assurance/audit/run?module=nope&mon_period=202602")
    assert r.status_code == 404
    assert "Unknown audit module" in r.json()["detail"]


def test_generic_run_happy_path_with_mocked_store():
    captured = {}

    def _fake_replace(period, source, trails, *, module="zero_commission", **kw):
        captured["module"] = module
        captured["count"] = len(trails)
        return {
            "run_id": "run-generic",
            "module": module,
            "mon_period": period,
            "payment_source": source,
            "trail_count": len(trails),
            "started_at": "2026-07-06T00:00:00+00:00",
        }

    with patch("backend.db.audit_store.replace_period_trails", side_effect=_fake_replace):
        c = TestClient(app)
        r = c.post("/assurance/audit/run?module=zero_commission&mon_period=202602")

    assert r.status_code == 200, r.text
    body = r.json()
    assert body["module"] == "zero_commission"
    assert body["trail_count"] > 0
    assert captured["module"] == "zero_commission"


def test_generic_trails_read_503_when_db_down():
    with patch(
        "backend.db.audit_store.get_period_trails",
        side_effect=Exception("connection refused"),
    ):
        c = TestClient(app)
        r = c.get("/assurance/audit/trails?module=zero_commission&mon_period=202602")
    assert r.status_code == 503
    assert "audit Postgres unreachable" in r.json()["detail"]


def test_generic_trails_caveat_filter_calls_store():
    with patch(
        "backend.db.audit_store.get_trails_with_caveat_step",
        return_value=[{"partner_code": "X"}],
    ) as m:
        c = TestClient(app)
        r = c.get("/assurance/audit/trails"
                  "?module=zero_commission&mon_period=202602&caveat_step=near_match")
    assert r.status_code == 200
    m.assert_called_once_with("near_match", "202602", "zero_commission")
