"""Eligibility answers must distinguish recorded audit classifications from policy certainty."""
import copy
import re

from backend import config
from backend.agent.measure_response import render_measure_response
from backend.tests.test_verification_outcome import (
    fake_module, fake_period, fake_trail, request_for, wrap,
)


def evidence():
    trail = fake_trail("296065", "MIXED_ATTRIBUTION", "HIGH")
    trail["evidence"] = [{"step": 4, "name": "classify against window", "result":
                         "50 outside window (zero-commission CORRECT), 54 inside window."}]
    trail["eligibility_counts"] = {"total": 104, "outside": 50, "inside": 54,
                                   "unknown": 0, "future": 0, "window_days": 180}
    return wrap(fake_period(
        fake_module(),
        fake_module("eligibility_window", "Eligibility Window", basis="saved",
                    run_at="2026-08-07 17:03 UTC", trails=[trail]),
        fake_module("inventory_mismatch", "Inventory Mismatch"),
    ))


def answer(request, payload):
    return re.sub(r"\\(.)", r"\1", render_measure_response(request, payload))


def test_eligibility_focus_limits_answer_without_mutating_audit_evidence(monkeypatch):
    monkeypatch.setattr(config, "USE_SAMPLE_DATA", True)
    payload = evidence()
    before = copy.deepcopy(payload)
    rendered = answer({**request_for(), "verification_focus": "eligibility_window"}, payload)
    assert "**Eligibility Window**" in rendered
    assert "Payment Reconciliation" not in rendered
    assert "Inventory Mismatch" not in rendered
    assert rendered.startswith("**50 of 104 zero-commission records were outside the 180-day window; 54 were inside.**")
    summary, details = rendered.split("### Verification evidence", 1)
    assert "Dealer 296065 · 202606" in summary
    assert "audit_trails" in summary
    assert "confidence" not in summary and "MIXED_ATTRIBUTION" not in summary
    assert "candidate explanations" in details
    assert payload == before


def test_eligibility_claim_is_qualified_before_saved_high_confidence_result(monkeypatch):
    monkeypatch.setattr(config, "USE_SAMPLE_DATA", True)
    rendered = answer({**request_for(), "verification_focus": "eligibility_window"}, evidence())
    assert "180" in rendered
    assert "Demo policy · 180 days" in rendered
    assert "calendar days 0–180 inclusive" in rendered
    assert "does not establish commission entitlement" in rendered
    assert "eligibility definition is unresolved" not in rendered
    assert rendered.index("180") < rendered.index("confidence HIGH")
    assert "recorded audit" in rendered.lower()
    assert "50 outside window" in rendered
    assert "2026-08-07 17:03 UTC" in rendered.split("### Verification evidence", 1)[0]


def test_broad_verification_also_discloses_eligibility_uncertainty(monkeypatch):
    monkeypatch.setattr(config, "USE_SAMPLE_DATA", False)
    rendered = answer(request_for(), evidence())
    assert "Payment Reconciliation" in rendered
    assert "180" in rendered
    assert "recorded audit" in rendered.lower()
    assert "eligibility definition is unresolved" in rendered
    assert "Demo policy" not in rendered


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
    trail = result["verification"]["modules"][0]["trails"][0]
    assert trail["eligibility_counts"] == {"total": 50, "outside": 2, "inside": 48,
                                           "future": 0, "unknown": 0, "window_days": 180}
