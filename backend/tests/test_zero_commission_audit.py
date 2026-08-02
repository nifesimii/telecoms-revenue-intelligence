"""Tests for the zero-commission verification-trail (Phase 1).

Three layers:
  1. Pure builder (build_trail) — synthetic inputs, no DB, no query layer.
  2. Orchestrator (run_period) — against real sample data.
  3. Persistence + endpoints — psycopg2 mocked; no live Postgres needed.
"""
from __future__ import annotations

import json
import os
from unittest.mock import MagicMock, patch

import pytest

os.environ["USE_SAMPLE_DATA"] = "true"

from backend.audit.trail import _json_safe  # noqa: E402
from backend.audit.zero_commission_audit import (  # noqa: E402
    ZeroCommissionInputs,
    build_trail,
    run_period,
)


def _inputs(**over):
    base = dict(
        partner_code="74050",
        partner_name="Nestobar",
        mon_period="202602",
        payment_source="simulated",
        total_activations=100,
        zero_commission_count=20,
        account_profile_class="FIXED BROADBAND",
        expected_commission_ngn=5000.0,
        zero_comm_product_codes=["P1"],
        products_missing_from_usp=[],
        payment_found=False,
        amount_paid_ngn=0.0,
        payment_status=None,
        adjacent_period_payments=[],
        period_present_in_payment_data=True,
        known_ingestion_gap=False,
    )
    base.update(over)
    return ZeroCommissionInputs(**base)


# ---------------------------------------------------------------------------
# Pure builder — chain structure + conclusions
# ---------------------------------------------------------------------------

def test_chain_has_six_ordered_steps():
    t = build_trail(_inputs())
    assert [s.step for s in t.steps] == [1, 2, 3, 4, 5, 6]
    assert [s.name for s in t.steps] == [
        "qualifying_activity", "applicable_rate", "expected_commission",
        "payment_record_search", "near_match", "upstream_completeness",
    ]


def test_clean_not_paid_high_confidence():
    # Owed 5000, nothing paid, all steps clean → NOT_PAID / HIGH.
    t = build_trail(_inputs())
    assert t.conclusion == "NOT_PAID"
    assert t.confidence == "HIGH"
    assert t.caveat_steps == []


def test_paid_in_full_is_paid():
    t = build_trail(_inputs(payment_found=True, amount_paid_ngn=5000.0,
                            payment_status="FULLY_PAID"))
    assert t.conclusion == "PAID"


def test_nothing_owed_all_zero_is_paid_with_caveat():
    # All activations zero-commission → expected 0 → correctly PAID, but
    # step 3 raises a caveat about the fully-zero situation.
    t = build_trail(_inputs(total_activations=40, zero_commission_count=40,
                            expected_commission_ngn=0.0))
    assert t.conclusion == "PAID"
    assert "expected_commission" in t.caveat_steps


def test_upstream_gap_forces_insufficient_data_low():
    t = build_trail(_inputs(period_present_in_payment_data=False,
                            known_ingestion_gap=True))
    assert t.conclusion == "INSUFFICIENT_DATA"
    assert t.confidence == "LOW"
    assert "upstream_completeness" in t.caveat_steps


def test_no_activity_is_insufficient_data():
    t = build_trail(_inputs(total_activations=0, zero_commission_count=0,
                            expected_commission_ngn=0.0))
    assert t.conclusion == "INSUFFICIENT_DATA"
    assert t.step(1).passed is False


def test_null_profile_raises_step2_caveat():
    t = build_trail(_inputs(account_profile_class=None))
    s2 = t.step(2)
    assert s2.passed is False
    assert "NULL account_profile_class" in s2.caveat


def test_usp_miss_raises_step2_caveat():
    t = build_trail(_inputs(products_missing_from_usp=["P1", "P2"]))
    s2 = t.step(2)
    assert s2.passed is False
    assert "USP snapshot miss" in s2.caveat


def test_partial_payment_flags_near_match():
    t = build_trail(_inputs(payment_found=True, amount_paid_ngn=1000.0,
                            expected_commission_ngn=5000.0))
    assert t.step(5).passed is False  # near-match caveat raised
    assert "near_match" in t.caveat_steps


def test_adjacent_period_payment_flags_near_match():
    t = build_trail(_inputs(adjacent_period_payments=[
        {"period": "202601", "amount_paid_ngn": 5000.0, "status": "FULLY_PAID"}
    ]))
    assert t.step(5).passed is False


def test_single_non_step6_caveat_is_medium():
    # Only a step-2 caveat, nothing else → MEDIUM.
    t = build_trail(_inputs(account_profile_class=None,
                            products_missing_from_usp=[]))
    assert t.confidence == "MEDIUM"


def test_trail_serializes_to_json():
    t = build_trail(_inputs())
    blob = json.dumps(t.to_dict())
    assert "qualifying_activity" in blob


def test_json_safe_coerces_numpy_like():
    class FakeNp:
        def item(self):
            return 42
    out = _json_safe({"a": FakeNp(), "b": [FakeNp()], "c": "x"})
    assert out == {"a": 42, "b": [42], "c": "x"}
    json.dumps(out)  # must not raise


# ---------------------------------------------------------------------------
# Orchestrator — real sample data
# ---------------------------------------------------------------------------

def test_run_period_produces_trails_for_flagged_partners():
    trails = run_period("202602", "simulated")
    assert len(trails) > 0
    # Every trail is a flagged partner (had zero-commission activity).
    for t in trails[:20]:
        assert t.step(1).detail["zero_commission_count"] > 0
        # Serializable end to end.
        json.dumps(t.to_dict())


def test_run_period_conclusions_are_valid():
    trails = run_period("202602", "simulated")
    valid = {"NOT_PAID", "PAID", "INSUFFICIENT_DATA"}
    assert all(t.conclusion in valid for t in trails)


# ---------------------------------------------------------------------------
# Persistence + endpoints — psycopg2 mocked
# ---------------------------------------------------------------------------

def test_replace_period_trails_row_mapping():
    """_trail_to_row maps a trail into the insert params without hitting a DB."""
    from backend.db.audit_store import _trail_to_row
    from datetime import datetime, timezone

    t = build_trail(_inputs())
    row = _trail_to_row(t, "run-123", datetime.now(timezone.utc), "zero_commission")
    assert row["partner_code"] == "74050"
    assert row["module"] == "zero_commission"
    assert row["conclusion"] == "NOT_PAID"
    assert row["caveat_steps"] == []
    assert row["step1_record_count"] == 100
    # steps is JSON text, decodable
    steps = json.loads(row["steps"])
    assert len(steps) == 6


def test_run_endpoint_503_when_audit_db_down():
    """The run endpoint surfaces a clean 503 when the audit DB is unreachable."""
    from fastapi.testclient import TestClient
    from backend.main import app

    with patch(
        "backend.db.audit_store.replace_period_trails",
        side_effect=Exception("connection refused"),
    ):
        c = TestClient(app)
        r = c.post("/assurance/zero-commission/run?mon_period=202602")
    assert r.status_code == 503
    assert "audit Postgres unreachable" in r.json()["detail"]


def test_run_endpoint_happy_path_with_mocked_store():
    """End-to-end run with the persistence layer mocked — confirms the trail
    generation + response shape without a live Postgres."""
    from fastapi.testclient import TestClient
    from backend.main import app

    captured = {}

    def _fake_replace(period, source, trails, **kw):
        captured["period"] = period
        captured["count"] = len(trails)
        return {
            "run_id": "run-abc",
            "mon_period": period,
            "payment_source": source,
            "trail_count": len(trails),
            "started_at": "2026-06-24T00:00:00+00:00",
        }

    with patch("backend.db.audit_store.replace_period_trails", side_effect=_fake_replace):
        c = TestClient(app)
        r = c.post("/assurance/zero-commission/run?mon_period=202602")

    assert r.status_code == 200, r.text
    body = r.json()
    assert body["run_id"] == "run-abc"
    assert body["trail_count"] > 0
    assert captured["count"] == body["trail_count"]


def test_trails_endpoint_caveat_filter_calls_right_store_fn():
    from fastapi.testclient import TestClient
    from backend.main import app

    with patch(
        "backend.db.audit_store.get_trails_with_caveat_step",
        return_value=[{"partner_code": "X", "caveat_steps": ["upstream_completeness"]}],
    ) as m:
        c = TestClient(app)
        r = c.get("/assurance/zero-commission/trails"
                  "?mon_period=202602&caveat_step=upstream_completeness")
    assert r.status_code == 200
    m.assert_called_once_with("upstream_completeness", "202602")
