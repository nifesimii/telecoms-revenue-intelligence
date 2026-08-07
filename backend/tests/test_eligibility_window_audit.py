"""Tests for the eligibility-window verification-trail (fourth audit module).

Same three-layer shape as the other audit-module tests:
  1. Pure builder (build_trail) — synthetic inputs, no DB.
  2. Orchestrator (run_period) — against real sample data.
  3. Registry discoverability + coexistence with the other modules.
"""
from __future__ import annotations

import os

import pytest

os.environ["USE_SAMPLE_DATA"] = "true"

from backend.audit import base as audit_base  # noqa: E402
from backend.audit.eligibility_window_audit import (  # noqa: E402
    EligibilityWindowInputs,
    _ELIGIBILITY_WINDOW_DAYS,
    _augment_record_with_gap,
    _parse_activation_date,
    _parse_invoice_date,
    build_trail,
    run_period,
)


def _rec(imei: str, product_code: str, gap_days: int | None = None,
         has_dates: bool = True):
    """Build one augmented zero-commission record for use in inputs."""
    return {
        "imei": imei,
        "product_code": product_code,
        "product_name": f"P {product_code}",
        "invoice_date": "2024-01-01",
        "first_activation_date": "20260101 00:00:00",
        "gap_days": gap_days,
        "has_dates": has_dates,
    }


def _inputs(**over):
    base = dict(
        partner_code="D100",
        partner_name="Test Dealer",
        mon_period="202602",
        account_profile_class="FIXED BROADBAND",
        zero_records=[_rec("i1", "P1", gap_days=200)],  # outside window by default
        products_missing_from_usp=[],
        dates_fully_populated=True,
    )
    base.update(over)
    return EligibilityWindowInputs(**base)


# ---------------------------------------------------------------------------
# Date parsing helpers
# ---------------------------------------------------------------------------

def test_parse_invoice_date_iso():
    d = _parse_invoice_date("2024-02-20")
    assert d is not None and d.year == 2024 and d.month == 2 and d.day == 20


def test_parse_invoice_date_none_and_bad():
    assert _parse_invoice_date(None) is None
    assert _parse_invoice_date("") is None
    assert _parse_invoice_date("nope") is None


def test_parse_activation_date_yyyymmdd_hhmmss():
    d = _parse_activation_date("20260216 13:28:51")
    assert d is not None and d.year == 2026 and d.hour == 13


def test_parse_activation_date_fallbacks():
    # YYYYMMDD with no time
    assert _parse_activation_date("20260101") is not None
    # ISO date variant — should still parse via the fallback formats
    assert _parse_activation_date("2026-01-01") is not None


def test_augment_computes_gap_days():
    row = {
        "imei": "x",
        "product_code": "P1",
        "invoice_date": "2024-01-01",
        "first_activation_date": "20240201 12:00:00",
    }
    out = _augment_record_with_gap(row)
    assert out["has_dates"] is True
    assert out["gap_days"] == 31   # Jan 1 → Feb 1


def test_augment_missing_date_flags_no_dates():
    row = {"imei": "x", "product_code": "P1", "invoice_date": None,
           "first_activation_date": "20240201 12:00:00"}
    out = _augment_record_with_gap(row)
    assert out["has_dates"] is False and out["gap_days"] is None


# ---------------------------------------------------------------------------
# Pure builder — chain structure
# ---------------------------------------------------------------------------

def test_chain_has_six_ordered_steps():
    t = build_trail(_inputs())
    assert [s.step for s in t.steps] == [1, 2, 3, 4, 5, 6]
    assert [s.name for s in t.steps] == [
        "zero_commission_records_present",
        "fetch_dates",
        "compute_gaps",
        "classify_against_window",
        "root_cause_attribution",
        "upstream_completeness",
    ]


def test_data_source_is_activation_table():
    # eligibility audit reads fbb_comm_dev_act, not payment data.
    t = build_trail(_inputs())
    assert t.payment_source == "fbb_comm_dev_act"


# ---------------------------------------------------------------------------
# Pure builder — conclusions
# ---------------------------------------------------------------------------

def test_all_outside_window_is_policy_met_high():
    t = build_trail(_inputs(
        zero_records=[
            _rec("i1", "P1", gap_days=200),
            _rec("i2", "P1", gap_days=365),
        ],
    ))
    assert t.conclusion == "POLICY_MET"
    assert t.confidence == "HIGH"
    assert t.caveat_steps == []


def test_inside_window_without_explanation_is_policy_violated():
    # Record inside 180d, no other zero-comm root cause → underpayment.
    t = build_trail(_inputs(
        zero_records=[_rec("i1", "P1", gap_days=30)],
    ))
    assert t.conclusion == "POLICY_VIOLATED"
    assert "root_cause_attribution" in t.caveat_steps


def test_inside_window_attributed_to_null_profile_is_mixed():
    t = build_trail(_inputs(
        account_profile_class=None,   # NULL profile — KB root cause #3
        zero_records=[_rec("i1", "P1", gap_days=30)],
    ))
    assert t.conclusion == "MIXED_ATTRIBUTION"
    # The unexplained-count caveat should not fire since every inside-window
    # record was attributable to another cause.
    assert "root_cause_attribution" not in t.caveat_steps


def test_inside_window_attributed_to_usp_miss_is_mixed():
    t = build_trail(_inputs(
        zero_records=[_rec("i1", "P_MISSING", gap_days=30)],
        products_missing_from_usp=["P_MISSING"],
    ))
    assert t.conclusion == "MIXED_ATTRIBUTION"


def test_inside_window_attributed_to_alias_is_mixed():
    # Hynex is in the known-alias group — attribution should fire.
    t = build_trail(_inputs(
        zero_records=[_rec("i1", "Hynex", gap_days=30)],
    ))
    assert t.conclusion == "MIXED_ATTRIBUTION"


def test_partial_attribution_still_violates_when_any_unexplained():
    # Two records inside the window: one attributed to USP miss, one not.
    t = build_trail(_inputs(
        zero_records=[
            _rec("attributed", "P_MISS", gap_days=30),
            _rec("unexplained", "P_OK", gap_days=30),
        ],
        products_missing_from_usp=["P_MISS"],
    ))
    assert t.conclusion == "POLICY_VIOLATED"
    step5 = next(s for s in t.steps if s.step == 5)
    assert step5.detail["attributed_count"] == 1
    assert step5.detail["unexplained_count"] == 1
    assert "unexplained" in step5.detail["unexplained_imeis"]


def test_no_zero_records_is_insufficient_data():
    t = build_trail(_inputs(zero_records=[]))
    assert t.conclusion == "INSUFFICIENT_DATA"
    assert t.confidence == "LOW"


def test_dataset_gap_is_insufficient_data():
    t = build_trail(_inputs(dates_fully_populated=False))
    assert t.conclusion == "INSUFFICIENT_DATA"
    assert t.confidence == "LOW"
    assert "upstream_completeness" in t.caveat_steps


def test_future_dated_record_caveats_but_still_evaluates():
    # Activation predates invoice — surfaces as caveat, doesn't crash.
    t = build_trail(_inputs(
        zero_records=[_rec("i1", "P1", gap_days=-10)],
    ))
    # Not inside the 6-mo window; not outside either — data quality issue.
    step4 = next(s for s in t.steps if s.step == 4)
    assert step4.detail["future_dated_count"] == 1
    assert step4.caveat is not None


def test_step2_missing_dates_caveats_and_drops_high_confidence():
    # 1 with dates + 1 without, still under 20% dataset threshold — step 2
    # caveats but step 6 stays clean.
    t = build_trail(_inputs(
        zero_records=[
            _rec("i1", "P1", gap_days=200),
            _rec("i2", "P1", has_dates=False),
        ],
    ))
    step2 = next(s for s in t.steps if s.step == 2)
    assert step2.caveat is not None
    # With only date-missing caveat present, confidence should be MEDIUM
    # (HIGH gets knocked down by the step-2 rule in _conclude).
    assert t.confidence in {"MEDIUM", "LOW"}


def test_step_details_carry_window_days_and_imei_lists():
    t = build_trail(_inputs(
        zero_records=[
            _rec("inside1", "P1", gap_days=30),
            _rec("outside1", "P1", gap_days=200),
        ],
    ))
    step4 = next(s for s in t.steps if s.step == 4)
    assert step4.detail["window_days"] == _ELIGIBILITY_WINDOW_DAYS
    assert "inside1" in step4.detail["inside_window_imeis"]
    assert "outside1" not in step4.detail["inside_window_imeis"]


def test_trail_is_json_serializable():
    import json
    t = build_trail(_inputs())
    payload = t.to_dict()
    encoded = json.dumps(payload)
    assert "POLICY_MET" in encoded


# ---------------------------------------------------------------------------
# Orchestrator — end-to-end against sample data
# ---------------------------------------------------------------------------

def test_run_period_produces_trails_against_sample_data():
    trails = run_period("202602")
    assert isinstance(trails, list)
    if not trails:
        pytest.skip("No zero-commission partners in sample data for 202602.")
    for t in trails:
        assert len(t.steps) == 6
        assert t.conclusion in {
            "POLICY_MET", "POLICY_VIOLATED", "MIXED_ATTRIBUTION",
            "INSUFFICIENT_DATA",
        }
        assert t.confidence in {"HIGH", "MEDIUM", "LOW"}
        assert t.payment_source == "fbb_comm_dev_act"


def test_run_period_returns_empty_for_unknown_period():
    assert run_period("209912") == []


# ---------------------------------------------------------------------------
# Registry
# ---------------------------------------------------------------------------

def test_module_is_registered_and_discoverable():
    module = audit_base.get_module("eligibility_window")
    assert module is not None
    assert module.label == "Eligibility Window"
    assert module.step_names[0] == "zero_commission_records_present"
    assert module.step_names[-1] == "upstream_completeness"


def test_all_four_modules_coexist_in_registry():
    names = {m.name for m in audit_base.list_modules()}
    assert {
        "zero_commission",
        "inventory_mismatch",
        "payment_reconciliation",
        "eligibility_window",
    }.issubset(names)
