"""Tests for the payment-reconciliation verification-trail (third module).

Three layers, same shape as test_zero_commission_audit /
test_inventory_mismatch_audit:
  1. Pure builder (build_trail) — synthetic inputs, no DB.
  2. Orchestrator (run_period) — against real sample data.
  3. Registry — module is discoverable via the generic audit registry.
"""
from __future__ import annotations

import os

import pytest

os.environ["USE_SAMPLE_DATA"] = "true"

from backend.audit import base as audit_base  # noqa: E402
from backend.audit.payment_reconciliation_audit import (  # noqa: E402
    PaymentReconciliationInputs,
    _classify_amount,
    build_trail,
    run_period,
)


def _inputs(**over):
    """Baseline: partner owed 10,000, paid 10,000 — clean PAID_IN_FULL/HIGH."""
    base = dict(
        partner_code="74050",
        partner_name="Nestobar",
        mon_period="202602",
        payment_source="simulated",
        total_activations=100,
        qualified_count=95,
        expected_commission_ngn=10000.0,
        payment_found=True,
        amount_paid_ngn=10000.0,
        payment_status="FULLY_PAID",
        adjacent_period_payments=[],
        period_present_in_payment_data=True,
        known_ingestion_gap=False,
    )
    base.update(over)
    return PaymentReconciliationInputs(**base)


# ---------------------------------------------------------------------------
# _classify_amount — the amount-bucket function tested in isolation
# ---------------------------------------------------------------------------

class TestClassifyAmount:
    def test_exact_match_is_paid_in_full(self):
        assert _classify_amount(10000.0, 10000.0) == "PAID_IN_FULL"

    def test_within_one_ngn_is_paid_in_full(self):
        assert _classify_amount(10000.0, 10000.50) == "PAID_IN_FULL"

    def test_small_absolute_delta_is_rounding(self):
        # Off by 50 NGN, within 100 NGN abs tolerance.
        assert _classify_amount(10000.0, 9950.0) == "DISPUTED_ROUNDING"

    def test_small_relative_delta_is_rounding(self):
        # Off by 500 NGN on 10M expected — 0.005%, within 1% tolerance.
        assert _classify_amount(10_000_000.0, 9_999_500.0) == "DISPUTED_ROUNDING"

    def test_large_underpayment(self):
        assert _classify_amount(10000.0, 5000.0) == "UNDERPAID"

    def test_large_overpayment(self):
        assert _classify_amount(10000.0, 15000.0) == "OVERPAID"

    def test_zero_paid_owed_is_underpaid(self):
        assert _classify_amount(10000.0, 0.0) == "UNDERPAID"

    def test_paid_but_nothing_owed_is_overpaid(self):
        assert _classify_amount(0.0, 500.0) == "OVERPAID"

    def test_zero_owed_zero_paid_is_paid_in_full(self):
        assert _classify_amount(0.0, 0.0) == "PAID_IN_FULL"


# ---------------------------------------------------------------------------
# Pure builder — chain structure
# ---------------------------------------------------------------------------

def test_chain_has_six_ordered_steps():
    t = build_trail(_inputs())
    assert [s.step for s in t.steps] == [1, 2, 3, 4, 5, 6]
    assert [s.name for s in t.steps] == [
        "partner_activity",
        "expected_commission",
        "payment_record_search",
        "amount_comparison",
        "near_match",
        "upstream_completeness",
    ]


# ---------------------------------------------------------------------------
# Pure builder — conclusions
# ---------------------------------------------------------------------------

def test_paid_in_full_high_confidence():
    t = build_trail(_inputs())
    assert t.conclusion == "PAID_IN_FULL"
    assert t.confidence == "HIGH"
    # step-4 didn't raise a caveat because bucket == PAID_IN_FULL.
    assert "amount_comparison" not in t.caveat_steps


def test_partial_payment_is_underpaid():
    """The core PROGRESS.md open question: partial payments here become
    a first-class UNDERPAID verdict, not a NOT_PAID/LOW conflation."""
    t = build_trail(_inputs(amount_paid_ngn=3000.0))
    assert t.conclusion == "UNDERPAID"
    # step-4 raises a caveat, but it's excluded from confidence weighting.
    assert t.confidence == "HIGH"


def test_overpayment_is_overpaid():
    t = build_trail(_inputs(amount_paid_ngn=15000.0))
    assert t.conclusion == "OVERPAID"


def test_rounding_delta_is_disputed_rounding():
    t = build_trail(_inputs(amount_paid_ngn=9975.0))
    assert t.conclusion == "DISPUTED_ROUNDING"


def test_no_payment_with_expected_is_underpaid():
    t = build_trail(_inputs(payment_found=False, amount_paid_ngn=0.0))
    assert t.conclusion == "UNDERPAID"


def test_paid_when_nothing_owed_is_overpaid():
    t = build_trail(_inputs(
        expected_commission_ngn=0.0,
        qualified_count=0,
        amount_paid_ngn=500.0,
    ))
    assert t.conclusion == "OVERPAID"


def test_zero_owed_zero_paid_is_paid_in_full():
    t = build_trail(_inputs(
        expected_commission_ngn=0.0,
        qualified_count=0,
        payment_found=False,
        amount_paid_ngn=0.0,
    ))
    assert t.conclusion == "PAID_IN_FULL"


def test_no_activity_is_insufficient_data():
    t = build_trail(_inputs(
        total_activations=0,
        qualified_count=0,
        expected_commission_ngn=0.0,
    ))
    assert t.conclusion == "INSUFFICIENT_DATA"
    assert t.confidence == "LOW"


def test_upstream_gap_is_insufficient_data():
    t = build_trail(_inputs(
        period_present_in_payment_data=False,
        known_ingestion_gap=True,
    ))
    assert t.conclusion == "INSUFFICIENT_DATA"
    assert t.confidence == "LOW"
    assert "upstream_completeness" in t.caveat_steps


def test_adjacent_period_payment_lowers_confidence_but_keeps_conclusion():
    # Underpaid + adjacent-period near-match → still UNDERPAID, but confidence
    # drops (near_match raised a caveat that counts).
    t = build_trail(_inputs(
        amount_paid_ngn=3000.0,
        adjacent_period_payments=[{"period": "202601", "amount_paid_ngn": 7000.0, "status": "FULLY_PAID"}],
    ))
    assert t.conclusion == "UNDERPAID"
    assert t.confidence == "MEDIUM"
    assert "near_match" in t.caveat_steps


def test_amount_comparison_caveat_excluded_from_confidence():
    """A pure UNDERPAID trail should read HIGH confidence — the step-4 caveat
    is expected for non-PAID_IN_FULL and would double-count otherwise."""
    t = build_trail(_inputs(amount_paid_ngn=3000.0))
    assert "amount_comparison" in t.caveat_steps
    assert t.confidence == "HIGH"


def test_trail_is_json_serializable():
    import json
    t = build_trail(_inputs(amount_paid_ngn=15000.0))
    encoded = json.dumps(t.to_dict())
    assert "OVERPAID" in encoded


def test_step4_detail_carries_delta_and_tolerances():
    t = build_trail(_inputs(amount_paid_ngn=3000.0))
    step4 = next(s for s in t.steps if s.step == 4)
    assert step4.detail["bucket"] == "UNDERPAID"
    assert step4.detail["delta_ngn"] == -7000.0
    assert step4.detail["rounding_abs_ngn_tolerance"] == 100.0
    assert step4.detail["rounding_rel_pct_tolerance"] == 0.01


# ---------------------------------------------------------------------------
# Orchestrator — end-to-end against sample data
# ---------------------------------------------------------------------------

def test_run_period_produces_trails_against_sample_data():
    trails = run_period("202602")
    assert isinstance(trails, list)
    if not trails:
        pytest.skip("No active partners in sample data for 202602 — "
                    "orchestrator returned empty (not a failure).")
    for t in trails:
        assert len(t.steps) == 6
        assert t.conclusion in {
            "PAID_IN_FULL", "UNDERPAID", "OVERPAID",
            "DISPUTED_ROUNDING", "INSUFFICIENT_DATA",
        }
        assert t.confidence in {"HIGH", "MEDIUM", "LOW"}
    # Broader net than zero_commission — should include every active partner,
    # not just the zero-comm-flagged subset.
    assert len(trails) >= 1


def test_run_period_returns_empty_for_unknown_period():
    """Unknown period shouldn't blow up — returns [] like zero_commission."""
    trails = run_period("209912")
    assert trails == []


# ---------------------------------------------------------------------------
# Registry
# ---------------------------------------------------------------------------

def test_module_is_registered_and_discoverable():
    module = audit_base.get_module("payment_reconciliation")
    assert module is not None
    assert module.label == "Payment Reconciliation"
    assert module.step_names[0] == "partner_activity"
    assert module.step_names[3] == "amount_comparison"


def test_all_three_modules_registered_together():
    """None of the three modules should displace the others."""
    names = {m.name for m in audit_base.list_modules()}
    assert names == {"zero_commission", "inventory_mismatch", "payment_reconciliation"}
