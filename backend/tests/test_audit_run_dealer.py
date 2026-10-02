"""Each audit module's per-dealer entry point equals its full-period run.

``run_dealer(period, dealer_id, source)`` must select subjects with the very
code ``run_period`` uses, so its trails are exactly that dealer's slice of a
full run. Real sample data, real audit code; nothing is persisted.
"""
from __future__ import annotations

import os

os.environ["USE_SAMPLE_DATA"] = "true"

import pytest  # noqa: E402

from backend import config  # noqa: E402
from backend.audit import (  # noqa: E402
    eligibility_window_audit,
    inventory_mismatch_audit,
    payment_reconciliation_audit,
    zero_commission_audit,
)
from backend.db import audit_store  # noqa: E402

PERIOD = "202606"
DEALER = "296065"
SOURCE = "simulated"

MODULES = {
    "zero_commission": zero_commission_audit,
    "eligibility_window": eligibility_window_audit,
    "payment_reconciliation": payment_reconciliation_audit,
    "inventory_mismatch": inventory_mismatch_audit,
}


@pytest.fixture(autouse=True)
def sample_mode_and_no_writes(monkeypatch):
    monkeypatch.setattr(config, "USE_SAMPLE_DATA", True)
    monkeypatch.setattr(config, "PAYMENT_SOURCE", SOURCE)
    monkeypatch.setattr(audit_store, "replace_period_trails",
                        lambda *a, **k: pytest.fail("run_dealer must never persist"))


def _dealer_of(trail) -> str:
    # inventory_mismatch subjects are "dealer:product"; the rest are the dealer.
    return str(trail.partner_code).split(":")[0]


@pytest.mark.parametrize("name", list(MODULES))
def test_run_dealer_equals_run_period_filtered_to_the_dealer(name):
    audit = MODULES[name]
    full = [t.to_dict() for t in audit.run_period(PERIOD, SOURCE) if _dealer_of(t) == DEALER]
    assert full, f"{name}: oracle dealer should be a subject in {PERIOD}"
    mine = [t.to_dict() for t in audit.run_dealer(PERIOD, DEALER, SOURCE)]
    assert [(t["conclusion"], t["confidence"]) for t in mine] == \
        [(t["conclusion"], t["confidence"]) for t in full]
    assert [t["steps"] for t in mine] == [t["steps"] for t in full]
    assert mine == full


@pytest.mark.parametrize("name", list(MODULES))
def test_run_dealer_for_a_dealer_with_no_subjects_is_empty(name):
    assert MODULES[name].run_dealer(PERIOD, "NO_SUCH_DEALER", SOURCE) == []


@pytest.mark.parametrize("name", ["zero_commission", "eligibility_window"])
def test_active_dealer_without_zero_commission_records_is_not_a_subject(name):
    # 311059 has activations in 202606 but no zero-commission records.
    assert MODULES[name].run_dealer(PERIOD, "311059", SOURCE) == []


@pytest.mark.parametrize("name", list(MODULES))
def test_run_dealer_for_an_unknown_month_is_empty(name):
    assert MODULES[name].run_dealer("209912", DEALER, SOURCE) == []
