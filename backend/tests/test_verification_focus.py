"""Eligibility answers must distinguish recorded audit classifications from policy certainty."""
import copy
import re

from backend.agent.measure_response import render_measure_response
from backend.tests.test_verification_outcome import (
    fake_module, fake_period, fake_trail, request_for, wrap,
)


def evidence():
    trail = fake_trail("296065", "MIXED_ATTRIBUTION", "HIGH")
    trail["evidence"] = [{"step": 4, "name": "classify against window", "result":
                         "50 outside window (zero-commission CORRECT), 54 inside window."}]
    return wrap(fake_period(
        fake_module(),
        fake_module("eligibility_window", "Eligibility Window", basis="saved",
                    run_at="2026-08-07 17:03 UTC", trails=[trail]),
        fake_module("inventory_mismatch", "Inventory Mismatch"),
    ))


def answer(request, payload):
    return re.sub(r"\\(.)", r"\1", render_measure_response(request, payload))


def test_eligibility_focus_limits_answer_without_mutating_audit_evidence():
    payload = evidence()
    before = copy.deepcopy(payload)
    rendered = answer({**request_for(), "verification_focus": "eligibility_window"}, payload)
    assert "**Eligibility Window**" in rendered
    assert "Payment Reconciliation" not in rendered
    assert "Inventory Mismatch" not in rendered
    assert "1 audit module" in rendered
    assert payload == before


def test_eligibility_claim_is_qualified_before_saved_high_confidence_result():
    rendered = answer({**request_for(), "verification_focus": "eligibility_window"}, evidence())
    assert "180" in rendered
    assert "reporting" in rendered.lower()
    assert "confirmed" in rendered.lower() or "authoritative" in rendered.lower()
    assert rendered.index("180") < rendered.index("confidence HIGH")
    assert "recorded audit" in rendered.lower()
    assert "50 outside window" in rendered
    assert "2026-08-07 17:03 UTC" in rendered


def test_broad_verification_also_discloses_eligibility_uncertainty():
    rendered = answer(request_for(), evidence())
    assert "Payment Reconciliation" in rendered
    assert "180" in rendered
    assert "recorded audit" in rendered.lower()


def test_focused_reader_only_checks_eligibility_and_returns_matching_rows(monkeypatch):
    from backend.audit import verification_outcome as vo
    from backend.db import audit_store
    monkeypatch.setattr(audit_store, "healthcheck", lambda: False)

    def unrelated(*args, **kwargs):
        raise AssertionError("An eligibility question must not run another audit")

    for module in ("payment_reconciliation", "zero_commission", "inventory_mismatch"):
        monkeypatch.setitem(vo._ON_REQUEST, module, unrelated)
    result = vo.verification_outcome_evidence("202606", "296065", focus="eligibility_window")
    assert result["total_rows"] == 1
    assert len(result["rows"]) == 1
    assert result["rows"][0]["dimension"] == "Eligibility Window"
    assert [m["module"] for m in result["verification"]["modules"]] == ["eligibility_window"]
    assert result["verification"]["modules"][0]["status"] == "verified"
