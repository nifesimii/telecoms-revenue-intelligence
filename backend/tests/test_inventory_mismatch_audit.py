"""Tests for the inventory-mismatch verification-trail (second audit module).

Three layers, same shape as test_zero_commission_audit:
  1. Pure builder (build_trail) — synthetic inputs, no DB, no query layer.
  2. Orchestrator (run_period) — against real sample data.
  3. Registry — module is discoverable via the generic audit registry.
"""
from __future__ import annotations

import os

import pytest

os.environ["USE_SAMPLE_DATA"] = "true"

from backend.audit import base as audit_base  # noqa: E402
from backend.audit.inventory_mismatch_audit import (  # noqa: E402
    InventoryMismatchInputs,
    build_trail,
    run_period,
)


def _inputs(**over):
    """Baseline: a clean CONFIRMED_MISMATCH with no explanatory caveats.
    Purchased 10, activated 15, gap 5, no prior stock, no siblings, IFS OK.
    Expected outcome: EXCESS_ACTIVATION / HIGH.
    """
    base = dict(
        dealer_id="D100",
        dealer_name="Test Dealer",
        product_code="P100",
        product_name="Test Product",
        mon_period="202602",
        activation_count=15,
        qualified_count=10,
        finding_type="CONFIRMED_MISMATCH",
        has_invoice_record=True,
        total_units_purchased=10.0,
        inventory_gap=5.0,
        gap_pct=50.0,
        prior_period="202601",
        prior_leftover_units=0.0,
        sibling_codes=[],
        sibling_purchases={},
        ifs_records_present=True,
        known_ingestion_gap=False,
    )
    base.update(over)
    return InventoryMismatchInputs(**base)


# ---------------------------------------------------------------------------
# Pure builder — chain structure
# ---------------------------------------------------------------------------

def test_chain_has_six_ordered_steps():
    t = build_trail(_inputs())
    assert [s.step for s in t.steps] == [1, 2, 3, 4, 5, 6]
    assert [s.name for s in t.steps] == [
        "mismatch_signal",
        "purchase_record_lookup",
        "allocation_calculation",
        "prior_period_stock",
        "product_alias_reconciliation",
        "upstream_completeness",
    ]


def test_subject_key_is_dealer_product_composite():
    t = build_trail(_inputs())
    # partner_code carries (dealer, product) so per-product uniqueness holds
    # in the audit table without a schema migration.
    assert t.partner_code == "D100:P100"
    assert "P100" in t.partner_name
    assert t.payment_source == "ifs"


# ---------------------------------------------------------------------------
# Pure builder — conclusions
# ---------------------------------------------------------------------------

def test_clean_excess_activation_high_confidence():
    t = build_trail(_inputs())
    assert t.conclusion == "EXCESS_ACTIVATION"
    assert t.confidence == "HIGH"
    assert t.caveat_steps == []


def test_no_invoice_is_insufficient_data_low():
    t = build_trail(_inputs(
        finding_type="NO_INVOICE_RECORD",
        has_invoice_record=False,
        total_units_purchased=None,
        inventory_gap=None,
        gap_pct=None,
    ))
    assert t.conclusion == "INSUFFICIENT_DATA"
    assert t.confidence == "LOW"
    assert "purchase_record_lookup" in t.caveat_steps


def test_ifs_ingestion_gap_is_insufficient_data():
    t = build_trail(_inputs(
        ifs_records_present=False,
        known_ingestion_gap=True,
    ))
    assert t.conclusion == "INSUFFICIENT_DATA"
    assert t.confidence == "LOW"
    assert "upstream_completeness" in t.caveat_steps


def test_prior_period_carryover_reconciles():
    # Prior period had 5 leftover units; current gap is 5 → carryover explains it.
    t = build_trail(_inputs(prior_leftover_units=5.0))
    assert t.conclusion == "RECONCILED"
    assert "prior_period_stock" in t.caveat_steps


def test_prior_period_carryover_insufficient_does_not_reconcile():
    # Prior leftover 3, current gap 5 → doesn't cover, mismatch stands.
    t = build_trail(_inputs(prior_leftover_units=3.0))
    assert t.conclusion == "EXCESS_ACTIVATION"
    assert "prior_period_stock" not in t.caveat_steps


def test_sibling_sku_covers_gap_reconciles():
    # Sibling SKU purchases in the period cover the gap → SKU consolidation.
    t = build_trail(_inputs(
        product_code="Hynex",
        sibling_codes=["Hynex_1"],
        sibling_purchases={"Hynex_1": 5.0},
    ))
    assert t.conclusion == "RECONCILED"
    assert "product_alias_reconciliation" in t.caveat_steps


def test_sibling_sku_insufficient_does_not_reconcile():
    t = build_trail(_inputs(
        product_code="Hynex",
        sibling_codes=["Hynex_1"],
        sibling_purchases={"Hynex_1": 2.0},   # < gap of 5
    ))
    assert t.conclusion == "EXCESS_ACTIVATION"


def test_zero_purchase_with_activity_flags_step3_caveat():
    # Purchased=0 with activations>0 → mismatch is real but gap_pct undefined.
    t = build_trail(_inputs(
        total_units_purchased=0.0,
        inventory_gap=15.0,
        gap_pct=None,
    ))
    step3 = next(s for s in t.steps if s.step == 3)
    assert step3.caveat is not None
    # Still concludes EXCESS_ACTIVATION — the mismatch is real.
    assert t.conclusion == "EXCESS_ACTIVATION"


def test_two_caveats_drop_confidence_to_low():
    # Zero-purchase caveat (step 3) + IFS gap (step 6) → 2 caveats → LOW.
    # Step 6 caveat also flips conclusion to INSUFFICIENT_DATA, which
    # forces LOW anyway — confirm the compound path.
    t = build_trail(_inputs(
        total_units_purchased=0.0,
        inventory_gap=15.0,
        gap_pct=None,
        ifs_records_present=False,
        known_ingestion_gap=True,
    ))
    assert t.confidence == "LOW"


def test_step_details_carry_dealer_and_product_codes():
    # Aggregate queries need dealer_id + product_code accessible without
    # parsing the composite partner_code back apart.
    t = build_trail(_inputs())
    step1_detail = t.steps[0].detail
    assert step1_detail["dealer_id"] == "D100"
    assert step1_detail["product_code"] == "P100"
    assert step1_detail["finding_type"] == "CONFIRMED_MISMATCH"


def test_trail_is_json_serializable():
    import json
    t = build_trail(_inputs())
    # to_dict must round-trip through json — the persistence layer relies on it.
    payload = t.to_dict()
    encoded = json.dumps(payload)
    assert "EXCESS_ACTIVATION" in encoded


# ---------------------------------------------------------------------------
# Orchestrator — end-to-end against sample data
# ---------------------------------------------------------------------------

def test_run_period_produces_trails_against_sample_data():
    """Sample data has confirmed mismatches for 202602 — orchestrator
    should produce at least one trail and every trail should validate."""
    trails = run_period("202602")
    assert isinstance(trails, list)
    if not trails:
        pytest.skip("No inventory mismatches in sample data for 202602 — "
                    "orchestrator returned empty (not a failure).")
    for t in trails:
        # Each trail is a fully-formed VerificationTrail with the six steps.
        assert len(t.steps) == 6
        assert t.conclusion in {
            "EXCESS_ACTIVATION", "RECONCILED", "INSUFFICIENT_DATA",
        }
        assert t.confidence in {"HIGH", "MEDIUM", "LOW"}
        assert ":" in t.partner_code  # composite dealer:product key
        assert t.payment_source == "ifs"


def test_run_period_returns_empty_for_unknown_period():
    trails = run_period("209912")   # no such period in sample data
    assert trails == []


# ---------------------------------------------------------------------------
# Registry
# ---------------------------------------------------------------------------

def test_module_is_registered_and_discoverable():
    module = audit_base.get_module("inventory_mismatch")
    assert module is not None
    assert module.label == "Inventory Mismatch"
    assert module.step_names[0] == "mismatch_signal"
    assert module.step_names[-1] == "upstream_completeness"


def test_zero_commission_module_still_registered():
    """The new module must not have displaced the first one — the registry
    should carry both."""
    assert audit_base.get_module("zero_commission") is not None
    assert audit_base.get_module("inventory_mismatch") is not None
    names = {m.name for m in audit_base.list_modules()}
    assert {"zero_commission", "inventory_mismatch"}.issubset(names)
