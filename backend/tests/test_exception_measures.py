"""Atlas activation and payment exception answers render the screens' evidence only."""
import copy
import os

os.environ["USE_SAMPLE_DATA"] = "true"

import pytest
from pydantic import ValidationError

from backend import config
from backend.agent.measure_response import render_measure_response
from backend.agent.measure_scope import MeasureScope
from backend.agent.tool_executor import execute_measure_request
from backend.db.exception_evidence import activation_exceptions_evidence, payment_exceptions_evidence

PAYMENT_DEALER_ANSWER = "\n\n".join([
    "Payment exceptions for dealer 296065, 202606: 1 exception, NGN 594,652.08 outstanding.",
    "\n".join([
        "| Dealer | Payment status | Commission owed | Amount settled | Outstanding | Source flag |",
        "| --- | --- | --- | --- | --- | --- |",
        "| River Isle Ventures (296065) | DISPUTED | NGN 991,086.80 | NGN 396,434.72 | NGN 594,652.08 "
        "| CONFIRMED\\_MISMATCH |",
    ]),
    "Payment exceptions are settlement records that are not fully paid: DISPUTED, "
    "PARTIALLY\\_PAID or PENDING, as on the Payments Exceptions view.",
    "Source: Payment settlement records.",
])

ACTIVATION_DEALER_ANSWER = "\n\n".join([
    "Activation exceptions for dealer 296065, 202606: 1 finding.",
    "\n".join([
        "| Dealer | Highest severity | Findings | Activations | Zero-commission activations |",
        "| --- | --- | --- | --- | --- |",
        "| River Isle Ventures (296065) | LOW | Unusual activation volume | 495 | 50 |",
    ]),
    "Findings come from the existing activation exception rules; they flag an account to inspect "
    "and do not establish a cause.",
    "Source: Activation exception checks.",
])

DEMO_WORDS = ("synthetic", "simulated", "sample", "demo")


@pytest.fixture(autouse=True)
def sample_mode(monkeypatch):
    monkeypatch.setattr(config, "USE_SAMPLE_DATA", True)
    monkeypatch.setattr(config, "PAYMENT_SOURCE", "simulated")


def request(measure, dealer_id=None, period="202606"):
    return {"measures": [measure], "periods": [period], "dealer_id": dealer_id, "operation": "total"}


def envelope(measure, period_evidence, dealer_id=None):
    label = {"activation_exceptions": "Activation exceptions", "payment_exceptions": "Payment exceptions"}[measure]
    return {"requested_periods": [period_evidence["period"]], "dealer_id": dealer_id, "explanations": [],
            "measures": [{"measure": measure, "label": label, "unit": "text",
                          "aggregation": "none", "note": "", "periods": [period_evidence]}]}


def answer(measure, dealer_id=None, period="202606"):
    req = request(measure, dealer_id, period)
    return render_measure_response(req, execute_measure_request(req))


def assert_no_demo_words(text):
    assert not any(word in text.lower() for word in DEMO_WORDS)


# ── Payment ─────────────────────────────────────────────────────────────────

def test_payment_dealer_answer_is_the_oracle():
    text = answer("payment_exceptions", "296065")
    assert text == PAYMENT_DEALER_ANSWER
    assert_no_demo_words(text)


def test_payment_month_answer_leads_with_total_and_bounds_the_table():
    text = answer("payment_exceptions")
    parts = text.split("\n\n")
    assert parts[0] == "Payment exceptions for 202606: 887 dealers, NGN 8,049,638.78 outstanding."
    assert parts[1] == "By payment status: DISPUTED 26; PARTIALLY\\_PAID 83; PENDING 778."
    table = parts[2].split("\n")
    assert len(table) == 2 + 100
    assert table[2].startswith("| River Isle Ventures (296065) | DISPUTED |")
    assert "| PENDING |" in text and "| — |" in text
    assert parts[3] == "Showing 100 of 887."
    assert parts[4] == ("Ordered by outstanding amount, largest first, then dealer code. "
                        "The outstanding total covers all 887 dealers, not only those shown.")
    assert parts[-1] == "Source: Payment settlement records."
    assert_no_demo_words(text)


def test_fully_paid_dealer_has_no_payment_exception():
    text = answer("payment_exceptions", "19630")
    assert text.split("\n\n")[0] == ("Dealer 19630 has no payment exception for 202606; "
                                     "the recorded payment status is FULLY\\_PAID.")
    assert "|" not in text


def test_unknown_payment_dealer_and_month_are_stated():
    missing = answer("payment_exceptions", "NO_SUCH_DEALER")
    assert missing.startswith("Dealer NO\\_SUCH\\_DEALER has no payment record for 202606; check the dealer code.")
    unknown = render_measure_response(request("payment_exceptions", period="209901"),
                                      envelope("payment_exceptions", payment_exceptions_evidence("209901", None)))
    assert unknown.startswith("Payment exceptions unavailable for 209901: no data is recorded for this month")
    assert "Missing evidence is not a clean result." in unknown
    assert "no payment exception" not in unknown.lower()


# ── Activation ──────────────────────────────────────────────────────────────

def test_activation_dealer_answer_is_the_oracle():
    text = answer("activation_exceptions", "296065")
    assert text == ACTIVATION_DEALER_ANSWER
    assert_no_demo_words(text)


def test_activation_month_answer_counts_findings_and_bounds_the_table():
    text = answer("activation_exceptions")
    parts = text.split("\n\n")
    assert parts[0] == "Activation exceptions for 202606: 155 dealers, 190 findings."
    assert parts[1] == ("By finding: All activations have zero commission (HIGH): 35 dealers; "
                        "More than half have zero commission (MEDIUM): 123 dealers; "
                        "Unusual activation volume (LOW): 32 dealers.")
    table = parts[2].split("\n")
    assert len(table) == 2 + 100
    assert table[2] == ("| Harbor Moon Communications (19398) | HIGH | All activations have zero commission; "
                        "More than half have zero commission | 9 | 9 |")
    assert parts[3] == "Showing 100 of 155."
    assert parts[4] == "Ordered by highest finding severity, then dealer code."
    assert parts[-1] == "Source: Activation exception checks."
    assert_no_demo_words(text)


def test_activation_dealer_without_findings_has_none():
    evidence = copy.deepcopy(activation_exceptions_evidence("202606", "296065"))
    body = evidence["activation_exceptions"]
    body.update(dealer_count=0, finding_count=0, by_finding=[], dealers=[])
    evidence.update(rows=[], total_rows=0)
    text = render_measure_response(request("activation_exceptions", "296065"),
                                   envelope("activation_exceptions", evidence, "296065"))
    assert text.split("\n\n")[0] == ("Dealer 296065 has no activation exception for 202606 under the "
                                     "existing exception rules. This does not certify every record as correct.")


def test_unknown_activation_dealer_and_unreadable_month_are_stated(monkeypatch):
    missing = answer("activation_exceptions", "NO_SUCH_DEALER")
    assert missing.startswith("Dealer NO\\_SUCH\\_DEALER has no recorded activations in 202606; check the dealer code.")
    from backend.db import activation_workspace
    monkeypatch.setattr(activation_workspace, "execute_query", lambda *a, **k: (_ for _ in ()).throw(RuntimeError()))
    text = answer("activation_exceptions", "296065")
    assert text.startswith("Activation exceptions unavailable for dealer 296065, 202606: "
                           "the activation exception checks could not be read")
    assert "Missing evidence is not a clean result." in text
    assert "no activation exception" not in text.lower()


# ── Malformed evidence ──────────────────────────────────────────────────────

@pytest.mark.parametrize("change", [
    lambda b: b.update(dealer_count=99),
    lambda b: b.update(finding_count=-1),
    lambda b: b["dealers"][0].update(findings=[]),
    lambda b: b["dealers"][0]["findings"][0].update(severity="CRITICAL"),
    lambda b: b.update(found="yes"),
    lambda b: b["by_finding"].append({"type": "X", "label": "X", "severity": "LOW", "dealer_count": 5}),
])
def test_malformed_activation_evidence_is_rejected(change):
    evidence = copy.deepcopy(activation_exceptions_evidence("202606", "296065"))
    change(evidence["activation_exceptions"])
    with pytest.raises(ValueError):
        render_measure_response(request("activation_exceptions", "296065"),
                                envelope("activation_exceptions", evidence, "296065"))


@pytest.mark.parametrize("change", [
    lambda b: b.update(outstanding_ngn=1.0),
    lambda b: b.update(dealer_count=2),
    lambda b: b["dealers"][0].update(payment_status="FULLY_PAID"),
    lambda b: b["dealers"][0].update(amount_unpaid="lots"),
    lambda b: b.update(dealer_status="PENDING"),
    lambda b: b["status_counts"].append({"status": "PENDING", "dealer_count": 1}),
])
def test_malformed_payment_evidence_is_rejected(change):
    evidence = copy.deepcopy(payment_exceptions_evidence("202606", "296065"))
    change(evidence["payment_exceptions"])
    with pytest.raises(ValueError):
        render_measure_response(request("payment_exceptions", "296065"),
                                envelope("payment_exceptions", evidence, "296065"))


def test_unavailable_evidence_cannot_carry_exceptions():
    evidence = payment_exceptions_evidence("209901", None)
    evidence["payment_exceptions"] = payment_exceptions_evidence("202606", None)["payment_exceptions"]
    with pytest.raises(ValueError):
        render_measure_response(request("payment_exceptions", period="209901"),
                                envelope("payment_exceptions", evidence))


def test_one_measure_payload_cannot_be_rendered_as_the_other():
    evidence = payment_exceptions_evidence("202606", "296065")
    with pytest.raises(ValueError):
        render_measure_response(request("activation_exceptions", "296065"),
                                envelope("activation_exceptions", evidence, "296065"))


# ── Scope ───────────────────────────────────────────────────────────────────

@pytest.mark.parametrize("measure", ["activation_exceptions", "payment_exceptions"])
def test_scope_is_one_month_alone_with_an_optional_dealer(measure):
    base = {"kind": "measure", "measures": [measure], "periods": ["202606"], "operation": "total"}
    assert MeasureScope.model_validate(base).dealer_id is None
    assert MeasureScope.model_validate({**base, "dealer_id": "296065"}).dealer_id == "296065"
    for change in ({"periods": ["202605", "202606"]}, {"operation": "breakdown"},
                   {"filter": "unpaid"}, {"measures": [measure, "payment_outstanding"]}):
        with pytest.raises(ValidationError):
            MeasureScope.model_validate({**base, **change})


@pytest.mark.parametrize("measure,tool", [("activation_exceptions", "activation_exceptions"),
                                          ("payment_exceptions", "payment_exceptions")])
def test_executor_routes_to_the_exception_reader(measure, tool):
    evidence = execute_measure_request(request(measure, "296065"))
    assert evidence["dealer_id"] == "296065" and evidence["requested_periods"] == ["202606"]
    [entry] = evidence["measures"]
    assert entry["measure"] == measure and entry["unit"] == "text"
    assert [p["tool"] for p in entry["periods"]] == [tool]
