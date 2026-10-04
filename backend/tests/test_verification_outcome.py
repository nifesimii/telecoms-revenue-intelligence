"""Atlas verification-outcome evidence comes from the audit modules' own trails.

Oracle tests run the real audit code on sample data (no mocks except the
audit store, which is forced unreachable or faked so results don't depend
on a local Postgres). Renderer tests use CONTRACT-shaped fakes.
"""
import copy
import os
import re
from datetime import datetime, timezone

os.environ["USE_SAMPLE_DATA"] = "true"

import pytest

from backend import config
from backend.agent.measure_response import render_measure_response
from backend.audit import verification_outcome as vo
from backend.audit.verification_outcome import verification_outcome_evidence
from backend.db import audit_store

DEMO_WORDING = re.compile(r"synthetic|simulated|sample|demo", re.IGNORECASE)


def plain(answer):
    """The answer as a reader sees it once markdown escapes are applied."""
    return re.sub(r"\\(.)", r"\1", answer)


@pytest.fixture(autouse=True)
def sample_mode(monkeypatch):
    monkeypatch.setattr(config, "USE_SAMPLE_DATA", True)
    monkeypatch.setattr(config, "PAYMENT_SOURCE", "simulated")


@pytest.fixture
def no_store(monkeypatch):
    monkeypatch.setattr(audit_store, "healthcheck", lambda: False)
    monkeypatch.setattr(audit_store, "get_period_trails",
                        lambda *a, **k: pytest.fail("store is unreachable"))


def request_for(dealer="296065", period="202606"):
    return {"measures": ["verification_outcome"], "periods": [period], "dealer_id": dealer,
            "operation": "total"}


def wrap(period_evidence, dealer="296065"):
    return {"requested_periods": [period_evidence["period"]], "dealer_id": dealer, "explanations": [],
            "measures": [{"measure": "verification_outcome", "label": "Verification outcome",
                          "unit": "text", "aggregation": "none", "note": "",
                          "periods": [period_evidence]}]}


def modules_by_name(evidence):
    return {m["module"]: m for m in evidence["verification"]["modules"]}


# ── Oracle: real sample data, real audit code ──────────────────────────────

# Verified by running the audit modules on sample data for dealer 296065, 202606
# (shown here with markdown escapes removed).
ORACLE_ANSWER = (
    'Verification outcome for dealer 296065, 202606: 4 audit modules — 4 with a verdict, 0 with no subject, 0 unavailable.\n'
    '\n'
    '**Payment Reconciliation**: UNDERPAID (confidence MEDIUM). Checked on request with the current audit code; nothing was saved.\n'
    '- Step 2, expected commission: Expected commission NGN 991,086.80.\n'
    '- Step 3, payment record search: Payment record found: NGN 396,434.72 (DISPUTED).\n'
    '- Step 4, amount comparison: Paid NGN 594,652.08 less than expected (short by 60.00% of expected).\n'
    '- Step 5, near match: 1 payment(s) to this partner in adjacent periods.\n'
    '- Caveat: Amount classified as UNDERPAID — see step-4 detail.\n'
    '- Caveat: Possible payment posted under an adjacent period reference; reconcile before finalising the amount bucket.\n'
    '\n'
    '**Zero-Commission**: NOT_PAID (confidence LOW). Checked on request with the current audit code; nothing was saved.\n'
    "- Step 2, applicable rate: Profile class 'ENTERPRISE BUSINESS'; 445 of 495 activations carry a non-zero rate; 3 zero-comm product(s) missing from USP.\n"
    '- Step 3, expected commission: Expected commission NGN 991,086.80 from 445 qualified activations.\n'
    '- Step 4, payment record search: Payment record found: NGN 396,434.72 (DISPUTED).\n'
    '- Step 5, near match: 1 payment(s) to this partner in adjacent periods. Partial payment detected (paid &lt; expected).\n'
    "- Caveat: 3 zero-commission product(s) absent from the USP rate card — 'USP snapshot miss' root cause.\n"
    "- Caveat: Possible payment under a different period/reference, or a partial settlement. Manual review before finalising 'not paid'.\n"
    '\n'
    'Demo policy · 180 days: Invoice date to first activation date, calendar days 0–180 inclusive. '
    'Day 181 onwards is outside. Activation before invoice is a date-quality issue; missing or invalid dates '
    'remain unclassified. Being inside the window alone does not establish commission entitlement.\n'
    '\n'
    'Recorded audit labels describe the implemented check. Attributions to other zero-commission causes are candidate '
    'explanations requiring source evidence; labels and confidence do not independently establish entitlement. '
    'Date-quality issues remain unclassified even when a recorded verdict says POLICY_MET.\n'
    '\n'
    '**Eligibility Window**: MIXED_ATTRIBUTION (confidence HIGH). Checked on request with the current audit code; nothing was saved.\n'
    '- Step 1, zero commission records present: 50 zero-commission record(s) found.\n'
    '- Step 4, classify against window: 2 outside window (zero-commission CORRECT), 48 inside window (other eligibility checks required), 0 future-dated (data quality issue).\n'
    '- Step 5, root cause attribution: 48 of 48 inside-window record(s) attributable to other root causes; 0 unexplained.\n'
    '- Caveat: 48 record(s) inside the eligibility window — step 5 will check for other zero-commission root causes.\n'
    '\n'
    '**Inventory Mismatch**: 12 subjects — EXCESS_ACTIVATION 1, INSUFFICIENT_DATA 11. Checked on request with the current audit code; nothing was saved.\n'
    '- Product 1299801: EXCESS_ACTIVATION (confidence HIGH). Flagged as CONFIRMED_MISMATCH. 42 activations (0 qualified) vs 20 purchased. IFS invoice record found: 20 units purchased. Gap = 22 units, 110.0% over allocation.\n'
    '- Product 1186254: INSUFFICIENT_DATA (confidence LOW), unverified. Flagged as NO_INVOICE_RECORD. 109 activations (109 qualified) vs no invoice record. No IFS invoice record found for this dealer+product. Cannot compute gap without an invoice record.\n'
    '- Product 1220431: INSUFFICIENT_DATA (confidence LOW), unverified. Flagged as NO_INVOICE_RECORD. 6 activations (0 qualified) vs no invoice record. No IFS invoice record found for this dealer+product. Cannot compute gap without an invoice record.\n'
    '- Product 1229866: INSUFFICIENT_DATA (confidence LOW), unverified. Flagged as NO_INVOICE_RECORD. 10 activations (10 qualified) vs no invoice record. No IFS invoice record found for this dealer+product. Cannot compute gap without an invoice record.\n'
    '- Product 1231872: INSUFFICIENT_DATA (confidence LOW), unverified. Flagged as NO_INVOICE_RECORD. 2 activations (2 qualified) vs no invoice record. No IFS invoice record found for this dealer+product. Cannot compute gap without an invoice record.\n'
    '- Showing 5 of 12 subjects.\n'
    '- Caveat: No IFS invoice — cannot distinguish over-activation from an invoice that lives outside the available data window.\n'
    '- INSUFFICIENT_DATA means the audit could not verify the claim; it is not a pass.\n'
    '\n'
    'Source: Audit trails.'
)


def test_oracle_dealer_month_runs_every_audit_on_request(no_store):
    evidence = verification_outcome_evidence("202606", "296065")
    assert evidence["status"] == "available"
    assert evidence["source"] == "Audit trails" and evidence["tool"] == "audit_trails"
    assert evidence["total"] is None and evidence["truncated"] is False
    modules = evidence["verification"]["modules"]
    assert [m["module"] for m in modules] == [
        "payment_reconciliation", "zero_commission", "eligibility_window", "inventory_mismatch"]
    assert all(m["status"] == "verified" and m["basis"] == "on_request" and m["run_at"] is None
               for m in modules)
    by = modules_by_name(evidence)

    pay = by["payment_reconciliation"]["trails"][0]
    assert (pay["conclusion"], pay["confidence"]) == ("UNDERPAID", "MEDIUM")
    assert [e["result"] for e in pay["evidence"]] == [
        "Expected commission NGN 991,086.80.",
        "Payment record found: NGN 396,434.72 (DISPUTED).",
        "Delta = NGN -594,652.08 (-60.00% of expected).",
        "1 payment(s) to this partner in adjacent periods."]

    zero = by["zero_commission"]["trails"][0]
    assert (zero["conclusion"], zero["confidence"]) == ("NOT_PAID", "LOW")
    assert zero["caveats"] == [
        "3 zero-commission product(s) absent from the USP rate card — 'USP snapshot miss' root cause.",
        "Possible payment under a different period/reference, or a partial settlement. "
        "Manual review before finalising 'not paid'."]

    window = by["eligibility_window"]["trails"][0]
    assert (window["conclusion"], window["confidence"]) == ("MIXED_ATTRIBUTION", "HIGH")
    assert ("2 outside window (zero-commission CORRECT), 48 inside window (other eligibility checks "
            "required), 0 future-dated (data quality issue).") in [e["result"] for e in window["evidence"]]

    inventory = by["inventory_mismatch"]
    assert inventory["subject_count"] == 12
    assert inventory["conclusions"] == [{"conclusion": "EXCESS_ACTIVATION", "count": 1},
                                        {"conclusion": "INSUFFICIENT_DATA", "count": 11}]
    assert len(inventory["trails"]) == vo.MAX_TRAILS
    first = inventory["trails"][0]
    assert (first["product_code"], first["conclusion"]) == ("1299801", "EXCESS_ACTIVATION")
    assert "Gap = 22 units, 110.0% over allocation." in [e["result"] for e in first["evidence"]]

    assert [(r["dimension"], r["value"]) for r in evidence["rows"]] == [
        ("Payment Reconciliation", "UNDERPAID 1"), ("Zero-Commission", "NOT_PAID 1"),
        ("Eligibility Window", "MIXED_ATTRIBUTION 1"),
        ("Inventory Mismatch", "EXCESS_ACTIVATION 1, INSUFFICIENT_DATA 11")]
    assert all(r["dealer_id"] == "296065" for r in evidence["rows"])


def test_oracle_trails_equal_the_full_period_run(no_store):
    """The single-dealer check is the module's own computation: same trail as run_period."""
    from backend.audit.base import get_module
    evidence = verification_outcome_evidence("202606", "296065")
    full = [t.to_dict() for t in get_module("payment_reconciliation").build_trails("202606", "simulated")
            if t.partner_code == "296065"]
    assert len(full) == 1
    built = vo._ON_REQUEST["payment_reconciliation"]("202606", "296065", "simulated")
    assert [t.to_dict() for t in built] == full
    assert modules_by_name(evidence)["payment_reconciliation"]["trails"][0] == \
        vo._trail_summary("payment_reconciliation", full[0])


def test_oracle_rendered_answer(no_store):
    raw = render_measure_response(request_for(), wrap(verification_outcome_evidence("202606", "296065")))
    answer = plain(raw)
    assert answer == ORACLE_ANSWER
    # Bullets stay real markdown list items; only their content is escaped.
    assert "\n- Step 2, expected commission: Expected commission NGN 991,086\\.80\\.\n" in raw
    assert answer.startswith("Verification outcome for dealer 296065, 202606: 4 audit modules")
    assert "**Payment Reconciliation**: UNDERPAID (confidence MEDIUM)." in answer
    assert "Checked on request with the current audit code; nothing was saved." in answer
    assert 'Demo policy · 180 days:' in answer
    assert answer.endswith("Source: Audit trails.")


def test_dealer_without_zero_commission_records_is_no_subject_not_unavailable(no_store):
    evidence = verification_outcome_evidence("202606", "311059")
    by = modules_by_name(evidence)
    assert by["zero_commission"]["status"] == "no_subject"
    assert by["eligibility_window"]["status"] == "no_subject"
    assert by["payment_reconciliation"]["status"] == "verified"
    answer = plain(render_measure_response(request_for("311059"), wrap(evidence, "311059")))
    assert "**Zero-Commission**: no audit subject" in answer
    assert "dealers with zero-commission records in the month" in answer
    assert "with no subject, 0 unavailable." in answer
    assert ": unavailable" not in answer


def test_unknown_month_is_unavailable_never_a_pass(no_store):
    evidence = verification_outcome_evidence("209912", "296065")
    assert evidence["status"] == "unavailable" and evidence["verification"] is None
    answer = plain(render_measure_response(request_for(period="209912"), wrap(evidence)))
    assert answer.startswith("Verification outcome unavailable for 209912")
    assert "Missing evidence is not a pass." in answer


def test_missing_dealer_is_unavailable(no_store):
    evidence = verification_outcome_evidence("202606", None)
    assert evidence["status"] == "unavailable" and evidence["verification"] is None


def test_module_that_fails_is_unavailable_while_others_answer(no_store, monkeypatch):
    def boom(*args):
        raise RuntimeError("source down")
    monkeypatch.setitem(vo._ON_REQUEST, "zero_commission", boom)
    evidence = verification_outcome_evidence("202606", "296065")
    zero = modules_by_name(evidence)["zero_commission"]
    assert zero["status"] == "unavailable" and zero["trails"] == [] and zero["basis"] is None
    answer = plain(render_measure_response(request_for(), wrap(evidence)))
    assert "**Zero-Commission**: unavailable" in answer
    assert "missing evidence is not a pass" in answer
    assert "NOT_PAID" not in answer


def test_saved_trails_are_preferred_and_dated(monkeypatch):
    """A module with a saved run answers from its LATEST run only, never re-running."""
    real = vo._ON_REQUEST["zero_commission"]("202606", "296065", "simulated")[0].to_dict()
    older = {**copy.deepcopy(real), "conclusion": "PAID", "run_id": "run-a",
             "generated_at": datetime(2026, 8, 1, 9, 0, tzinfo=timezone.utc), "payment_source": "simulated"}
    latest = {**copy.deepcopy(real), "run_id": "run-b",
              "generated_at": datetime(2026, 8, 7, 17, 3, tzinfo=timezone.utc), "payment_source": "apdp"}
    other = {**copy.deepcopy(real), "partner_code": "999", "run_id": "run-b",
             "generated_at": datetime(2026, 8, 7, 17, 3, tzinfo=timezone.utc)}
    saved = {"zero_commission": [older, latest, other]}
    monkeypatch.setattr(audit_store, "healthcheck", lambda: True)
    monkeypatch.setattr(audit_store, "get_period_trails", lambda period, module: saved.get(module, []))
    monkeypatch.setitem(vo._ON_REQUEST, "zero_commission", lambda *a: pytest.fail("saved run exists"))
    by = modules_by_name(verification_outcome_evidence("202606", "296065"))
    zero = by["zero_commission"]
    assert (zero["status"], zero["basis"], zero["run_at"]) == ("verified", "saved", "2026-08-07 17:03 UTC")
    assert zero["subject_count"] == 1 and zero["trails"][0]["conclusion"] == "NOT_PAID"
    assert zero["caveats"] == ["The saved run used a different payment source from the current setting."]
    assert by["payment_reconciliation"]["basis"] == "on_request"


def test_saved_trails_come_from_the_latest_run_only(monkeypatch):
    """Subjects present only in an older run are not mixed into the latest run's answer."""
    def inv(product, run_id, at, conclusion="EXCESS_ACTIVATION"):
        return {"partner_code": f"296065:{product}", "conclusion": conclusion, "confidence": "HIGH",
                "run_id": run_id, "generated_at": at, "payment_source": "simulated", "steps": []}
    old_at = datetime(2026, 8, 1, 9, 0, tzinfo=timezone.utc)
    new_at = datetime(2026, 8, 7, 17, 3, tzinfo=timezone.utc)
    saved = {"inventory_mismatch": [inv("P1", "run-a", old_at), inv("P2", "run-a", old_at),
                                    inv("P1", "run-b", new_at, "RECONCILED")]}
    monkeypatch.setattr(audit_store, "healthcheck", lambda: True)
    monkeypatch.setattr(audit_store, "get_period_trails", lambda period, module: saved.get(module, []))
    monkeypatch.setitem(vo._ON_REQUEST, "inventory_mismatch", lambda *a: pytest.fail("saved run exists"))
    inventory = modules_by_name(verification_outcome_evidence("202606", "296065"))["inventory_mismatch"]
    assert (inventory["basis"], inventory["run_at"], inventory["subject_count"]) == (
        "saved", "2026-08-07 17:03 UTC", 1)
    assert inventory["conclusions"] == [{"conclusion": "RECONCILED", "count": 1}]


def test_dealer_absent_from_the_latest_saved_run_is_checked_on_request(monkeypatch):
    """Not a subject of the latest saved run: check on request, never 'no subject' stamped with that run."""
    other = {"partner_code": "999", "conclusion": "PAID", "confidence": "HIGH", "run_id": "run-b",
             "generated_at": datetime(2026, 8, 7, 17, 3, tzinfo=timezone.utc), "steps": []}
    older_self = {**other, "partner_code": "296065", "run_id": "run-a",
                  "generated_at": datetime(2026, 8, 1, 9, 0, tzinfo=timezone.utc)}
    monkeypatch.setattr(audit_store, "healthcheck", lambda: True)
    monkeypatch.setattr(audit_store, "get_period_trails",
                        lambda period, module: [older_self, other] if module == "eligibility_window" else [])
    window = modules_by_name(verification_outcome_evidence("202606", "296065"))["eligibility_window"]
    assert (window["status"], window["basis"], window["run_at"]) == ("verified", "on_request", None)
    assert window["trails"][0]["conclusion"] == "MIXED_ATTRIBUTION"


def test_unknown_dealer_code_is_no_recorded_activity_not_four_no_subjects(no_store, monkeypatch):
    for name in list(vo._ON_REQUEST):
        monkeypatch.setitem(vo._ON_REQUEST, name, lambda *a: pytest.fail("no audit for an unknown dealer"))
    evidence = verification_outcome_evidence("202606", " NO_SUCH_DEALER ")
    assert evidence["status"] == "available"
    assert evidence["verification"] == {"found": False} and evidence["rows"] == []
    answer = plain(render_measure_response(request_for("NO_SUCH_DEALER"), wrap(evidence, "NO_SUCH_DEALER")))
    assert answer == "Dealer NO_SUCH_DEALER has no recorded activity in 202606; check the dealer code."


def test_scenario_trail_text_is_withheld_and_disclosed_neutrally():
    trail = {"partner_code": "1:2", "conclusion": "INSUFFICIENT_DATA", "confidence": "LOW", "steps": [
        {"step": 1, "name": "mismatch_signal", "result": "Flagged as CONFIRMED_MISMATCH.", "passed": True,
         "caveat": "Synthetic comparison scenario S1: x. Shared demonstration evidence.",
         "detail": {"scenario_id": "S1"}},
        {"step": 2, "name": "purchase_record_lookup", "result": "Synthetic shared purchase quantity: 5 units.",
         "passed": False, "caveat": None, "detail": {"scenario_id": "S1"}},
        {"step": 6, "name": "upstream_completeness", "result": "Date fields are reliably populated across "
         "the sampled records.", "passed": False, "caveat": None, "detail": {}}]}
    summary = vo._trail_summary("inventory_mismatch", trail)
    assert summary["limited"] is True and summary["caveats"] == []
    assert summary["withheld"] == 3
    assert [e["result"] for e in summary["evidence"]] == ["Flagged as CONFIRMED_MISMATCH."]


def test_historical_eligibility_wording_is_qualified_as_the_audit_tab_does():
    trail = {"partner_code": "296065", "conclusion": "MIXED_ATTRIBUTION", "confidence": "HIGH", "steps": [
        {"step": 4, "name": "classify_against_window", "passed": False, "caveat": None, "detail": {},
         "result": "2 outside window (zero-commission CORRECT), 48 inside window (should have earned commission)."}]}
    summary = vo._trail_summary("eligibility_window", trail)
    assert summary["evidence"][0]["result"] == (
        "2 outside window (zero-commission CORRECT), 48 inside window (other eligibility checks required).")


# ── Renderer: CONTRACT-shaped fakes ──────────────────────────────────────

def fake_trail(subject="296065", conclusion="UNDERPAID", confidence="HIGH", **extra):
    return {"subject": subject, "product_code": subject.split(":", 1)[1] if ":" in subject else None,
            "conclusion": conclusion, "confidence": confidence,
            "evidence": [{"step": 4, "name": "amount comparison", "result": "Delta = NGN -10.00."}],
            "caveats": ["Amount classified as UNDERPAID."], "limited": False, "withheld": 0, **extra}


def fake_module(module="payment_reconciliation", label="Payment Reconciliation", status="verified",
                basis="on_request", run_at=None, trails=None, note=None, caveats=None, subject_count=None):
    trails = [fake_trail()] if trails is None and status == "verified" else (trails or [])
    count = len(trails) if subject_count is None else subject_count
    conclusions = {}
    for trail in trails:
        conclusions[trail["conclusion"]] = conclusions.get(trail["conclusion"], 0) + 1
    if count > len(trails):
        conclusions[trails[-1]["conclusion"]] += count - len(trails)
    return {"module": module, "label": label, "status": status, "basis": basis, "run_at": run_at,
            "subjects": "dealers with activations in the month", "subject_count": count,
            "conclusions": [{"conclusion": c, "count": n} for c, n in sorted(conclusions.items())],
            "trails": trails, "caveats": caveats or [], "note": note}


def fake_period(*modules, dealer="296065"):
    modules = list(modules) or [fake_module()]
    return {"period": "202606", "status": "available", "source": "Audit trails", "tool": "audit_trails",
            "total": None, "truncated": False, "total_rows": len(modules), "note": "",
            "rows": [{"dealer_id": dealer, "dimension": m["label"], "value": "x"} for m in modules],
            "verification": {"modules": modules}}


def render(*modules):
    return plain(render_measure_response(request_for(), wrap(fake_period(*modules))))


def test_render_single_verdict_with_step_evidence_and_caveat():
    answer = render()
    parts = answer.split("\n\n")
    assert parts[0] == ("Verification outcome for dealer 296065, 202606: 1 audit module — "
                        "1 with a verdict, 0 with no subject, 0 unavailable.")
    assert parts[1].splitlines() == [
        "**Payment Reconciliation**: UNDERPAID (confidence HIGH). "
        "Checked on request with the current audit code; nothing was saved.",
        "- Step 4, amount comparison: Paid NGN 10.00 less than expected.",
        "- Caveat: Amount classified as UNDERPAID.",
    ]
    assert parts[-1] == "Source: Audit trails."


def test_render_insufficient_data_reads_as_unverified():
    answer = render(fake_module(trails=[fake_trail(conclusion="INSUFFICIENT_DATA", confidence="LOW")]))
    assert "INSUFFICIENT_DATA (confidence LOW): unverified, not a pass." in answer
    assert "PASS" not in answer.upper().replace("NOT A PASS", "")


def test_render_saved_run_states_timestamp():
    answer = render(fake_module(basis="saved", run_at="2026-08-07 17:03 UTC",
                                caveats=["The saved run used a different payment source."]))
    assert "From the saved audit run of 2026-08-07 17:03 UTC." in answer
    assert "- Caveat: The saved run used a different payment source." in answer


def test_render_multi_subject_module_is_bounded_with_counts():
    trails = [fake_trail("296065:P1", "EXCESS_ACTIVATION"),
              fake_trail("296065:P2", "INSUFFICIENT_DATA", "LOW", limited=True)]
    module = fake_module("inventory_mismatch", "Inventory Mismatch", trails=trails, subject_count=7)
    answer = render(module)
    assert ("**Inventory Mismatch**: 7 subjects — EXCESS_ACTIVATION 1, INSUFFICIENT_DATA 6.") in answer
    assert "- Product P1: EXCESS_ACTIVATION (confidence HIGH). Paid NGN 10.00 less than expected." in answer
    assert "- Product P2: INSUFFICIENT_DATA (confidence LOW), unverified." in answer
    assert ("This product's comparison evidence is not authentic invoice or stock data; no purchase, "
            "carryover or alias conclusion is established.") in answer
    assert "- Showing 2 of 7 subjects." in answer
    assert "- INSUFFICIENT_DATA means the audit could not verify the claim; it is not a pass." in answer
    assert answer.count("Caveat: Amount classified as UNDERPAID") == 1


def test_render_no_subject_and_unavailable_are_distinct():
    answer = render(fake_module("zero_commission", "Zero-Commission", status="no_subject"),
                    fake_module("eligibility_window", "Eligibility Window", status="no_subject",
                                basis="saved", run_at="2026-08-08 19:39 UTC"),
                    fake_module("inventory_mismatch", "Inventory Mismatch", status="unavailable",
                                basis=None, note="the audit could not be run for this dealer and month."))
    assert answer.startswith("Verification outcome for dealer 296065, 202606: 3 audit modules — "
                             "0 with a verdict, 2 with no subject, 1 unavailable.")
    assert ("**Zero-Commission**: no audit subject. This audit covers only dealers with activations in "
            "the month, and dealer 296065 is not one; nothing to verify (not a pass or a failure).") in answer
    assert "**Eligibility Window**: no audit subject in the saved audit run of 2026-08-08 19:39 UTC." in answer
    assert ("**Inventory Mismatch**: unavailable: the audit could not be run for this dealer and month. "
            "Not verified; missing evidence is not a pass.") in answer


def test_render_overpaid_delta_has_no_negative_or_signed_amounts():
    trail = fake_trail("296065", "OVERPAID", evidence=[
        {"step": 4, "name": "amount comparison", "result": "Delta = NGN +2,500.00 (+2.50% of expected)."}])
    answer = render(fake_module(trails=[trail]))
    assert "- Step 4, amount comparison: Overpaid by NGN 2,500.00 (overpaid by 2.50% of expected)." in answer
    assert not re.search(r"[+-]\s?\d|NGN [+-]", answer)


def test_render_underpaid_delta_states_shortfall_in_words():
    trail = fake_trail(evidence=[
        {"step": 4, "name": "amount comparison", "result": "Delta = NGN -991,086.80 (-100.00% of expected)."}])
    answer = render(fake_module(trails=[trail]))
    assert "Paid NGN 991,086.80 less than expected (short by 100.00% of expected)." in answer
    assert "NGN -" not in answer and "(-" not in answer


def test_render_discloses_withheld_trail_details_neutrally():
    trails = [fake_trail("296065:P1", "EXCESS_ACTIVATION", withheld=2),
              fake_trail("296065:P2", "INSUFFICIENT_DATA", "LOW", withheld=1)]
    answer = render(fake_module("inventory_mismatch", "Inventory Mismatch", trails=trails))
    assert "- 3 trail detail(s) not shown." in answer
    assert not DEMO_WORDING.search(answer)
    assert "not shown" not in render()


def test_render_escapes_trail_text():
    trail = fake_trail(evidence=[{"step": 1, "name": "x", "result": "<b>*bold*</b> | pipe"}], caveats=[])
    answer = render_measure_response(request_for(), wrap(fake_period(fake_module(trails=[trail]))))
    assert "<b>" not in answer and "&lt;b&gt;\\*bold\\*&lt;/b&gt; \\| pipe" in answer


@pytest.mark.parametrize("mutate", [
    lambda p: p.update(verification=None),
    lambda p: p["verification"].update(modules=[]),
    lambda p: p["verification"]["modules"][0].update(status="passed"),
    lambda p: p["verification"]["modules"][0].update(basis=None),
    lambda p: p["verification"]["modules"][0].update(run_at="2026-08-07"),
    lambda p: p["verification"]["modules"][0].update(subject_count=3),
    lambda p: p["verification"]["modules"][0]["trails"][0].update(conclusion="PASSED"),
    lambda p: p["verification"]["modules"][0]["trails"][0].update(confidence=None),
    lambda p: p["verification"]["modules"][0]["trails"][0].update(subject="777"),
    lambda p: p["verification"]["modules"][0]["trails"][0].update(evidence=[{"step": 1}]),
    lambda p: p["verification"]["modules"][0]["trails"][0].pop("caveats"),
    lambda p: p["verification"]["modules"][0].update(trails=[]),
    lambda p: p["verification"]["modules"][0].update(status="unavailable", basis=None, note=None),
    lambda p: p["verification"]["modules"][0].pop("label"),
    lambda p: p["verification"]["modules"][0]["trails"][0].update(withheld=-1),
    lambda p: p.update(verification={"found": False}),
    lambda p: p.update(verification={"found": "no"}, rows=[]),
    lambda p: p.update(status="unavailable"),
])
def test_malformed_verification_payload_raises_value_error(mutate):
    period = fake_period()
    mutate(period)
    with pytest.raises(ValueError):
        render_measure_response(request_for(), wrap(period))


def test_verification_payload_is_exclusive_to_its_measure():
    from backend.tests.test_measure_scope import fake_priority_evidence
    period = fake_priority_evidence("202606", "296065")
    period["verification"] = {"modules": []}
    request = {"measures": ["investigation_priority"], "periods": ["202606"], "dealer_id": "296065",
               "operation": "total"}
    evidence = wrap(period)
    evidence["measures"][0].update(measure="investigation_priority", label="Investigation priority")
    with pytest.raises(ValueError):
        render_measure_response(request, evidence)


# ── Scope contract, executor routing and the agent seam ────────────────────

def install_verification(monkeypatch):
    """Stand in for the reader at the module the executor resolves at call time."""
    calls = []

    def fake(period, dealer_id):
        calls.append((period, dealer_id))
        return fake_period(dealer=dealer_id)

    monkeypatch.setattr(vo, "verification_outcome_evidence", fake)
    return calls


def test_scope_contract_routes_audit_questions_to_the_verification_measure():
    from backend.agent import agent
    description = agent.SCOPE_TOOL["description"]
    assert "['verification_outcome']" in description and "paid correctly" in description
    alone = agent.MeasureScope.model_validate({"kind": "measure", "measures": ["verification_outcome"],
                                               "periods": ["202606"], "dealer_id": "296065"})
    assert alone.measures == ["verification_outcome"]


@pytest.mark.parametrize("plan", [
    {"measures": ["verification_outcome"], "periods": ["202606"]},
    {"measures": ["verification_outcome"], "periods": ["202605", "202606"], "dealer_id": "296065"},
    {"measures": ["verification_outcome", "payment_status"], "periods": ["202606"], "dealer_id": "296065"},
    {"measures": ["verification_outcome"], "periods": ["202606"], "dealer_id": "296065",
     "operation": "compare"},
])
def test_verification_scope_stands_alone_for_one_dealer_month(plan):
    from backend.agent import agent
    with pytest.raises(ValueError):
        agent.MeasureScope.model_validate({"kind": "measure", **plan})


def test_executor_routes_verification_to_the_audit_reader(monkeypatch):
    from backend.agent import tool_executor
    from backend.db import measure_evidence
    calls = install_verification(monkeypatch)
    monkeypatch.setattr(measure_evidence, "collect_measure_evidence",
                        lambda request: pytest.fail("no other measures were requested"))
    evidence = tool_executor.execute_measure_request(
        {"measures": ["verification_outcome"], "periods": ["202606"], "dealer_id": "296065"})
    assert calls == [("202606", "296065")]
    measure = evidence["measures"][0]
    assert (measure["measure"], measure["label"], measure["unit"]) == (
        "verification_outcome", "Verification outcome", "text")
    assert measure["periods"][0]["verification"]["modules"][0]["module"] == "payment_reconciliation"


def test_agent_answers_verification_from_audit_evidence_not_model_prose(monkeypatch):
    import asyncio
    from backend.agent import agent
    from backend.tests.test_measure_scope import install_plan
    calls = install_verification(monkeypatch)
    install_plan(monkeypatch, {"kind": "measure", "measures": ["verification_outcome"],
                               "periods": ["202606"], "dealer_id": "296065"},
                 draft="Yes, the dealer was paid correctly.")
    result = asyncio.run(agent.run_agent("was this dealer paid correctly, can you prove it?"))
    response = plain(result["response"])
    assert calls == [("202606", "296065")]
    assert "below the recorded amount owed" in response
    assert "296065" in response and "202606" in response
    assert "UNDERPAID" in str(result["raw_data"])
    assert "confidence HIGH" not in response
    assert "paid correctly" not in response
    assert result["tools_called"] == ["audit_trails"]
