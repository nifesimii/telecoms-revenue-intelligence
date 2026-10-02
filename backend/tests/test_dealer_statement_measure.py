"""Atlas dealer-statement evidence is the dealer statement composer, projected.

The oracle uses sample data with no mocks of the composer: values match
``GET /dealers/296065/statement?mon_period=202606``. Only the audit store is
pinned, because whether a local audit Postgres is running is environmental.
"""
import asyncio
import os
import re

os.environ["USE_SAMPLE_DATA"] = "true"

import pytest

from backend import config
from backend.agent import agent
from backend.agent.measure_response import render_measure_response
from backend.agent.measure_scope import MeasureScope
from backend.db import audit_store
from backend.db.dealer_statement_evidence import (
    DEALER_STATEMENT_SOURCE,
    DEALER_STATEMENT_TOOL,
    dealer_statement_evidence,
)

ORACLE_ANSWER = "\n\n".join([
    "Dealer statement for River Isle Ventures (296065), 202606.",
    "Amount owed: NGN 994,136.80 (activation and subscription commission).",
    "Amount paid: NGN 397,959.72.",
    "Amount outstanding: NGN 596,177.08.",
    "Payment status: activation commission DISPUTED (statement position: underpaid); "
    "subscription commission NGN 1,525.00 settled of NGN 3,050.00 owed, as reported.",
    "\n".join([
        "| Commission | Owed | Paid | Outstanding |",
        "| --- | --- | --- | --- |",
        "| Activation commission | NGN 991,086.80 | NGN 396,434.72 | NGN 594,652.08 (60% of amount owed) |",
        "| Subscription commission | NGN 3,050.00 | NGN 1,525.00 | NGN 1,525.00 |",
        "| Total | NGN 994,136.80 | NGN 397,959.72 | NGN 596,177.08 |",
    ]),
    "\n".join([
        "| Component | Amount |",
        "| --- | --- |",
        "| Activation commission · 5G ROUTER | NGN 492,948.60 |",
        "| Activation commission · HYNETFLEX | NGN 58,604.70 |",
        "| Activation commission · MIFI | NGN 136,883.29 |",
        "| Activation commission · MIFI\\_1 | NGN 302,650.21 |",
        "| Activation commission (amount owed) | NGN 991,086.80 |",
    ]),
    "Activations: 495 recorded, 445 commission-bearing, 50 zero-commission.",
    "Subscription revenue: NGN 120,266.83 across 2 devices (not part of the amount owed); "
    "0 zero-amount records.",
    "Linked audit conclusions: none returned.",
    "Ask for the verification outcome for full audit results.",
    "Sources: activation commission, subscription commission and subscription revenue records; "
    "Payment records; verification audit trails.",
])


@pytest.fixture(autouse=True)
def sample_mode(monkeypatch):
    monkeypatch.setattr(config, "USE_SAMPLE_DATA", True)
    monkeypatch.setattr(config, "PAYMENT_SOURCE", "simulated")
    monkeypatch.setattr(audit_store, "healthcheck", lambda: True)
    monkeypatch.setattr(audit_store, "get_partner_trail", lambda *args: None)


def request(dealer_id="296065", period="202606"):
    return {"measures": ["dealer_statement"], "periods": [period], "dealer_id": dealer_id,
            "operation": "total"}


def envelope(period_evidence, dealer_id="296065"):
    return {"requested_periods": [period_evidence["period"]], "dealer_id": dealer_id, "explanations": [],
            "measures": [{"measure": "dealer_statement", "label": "Dealer statement", "unit": "text",
                          "aggregation": "none", "note": "", "periods": [period_evidence]}]}


# ── Oracle: real sample data ────────────────────────────────────────────────

def test_statement_evidence_matches_the_composer_for_a_real_dealer_month():
    evidence = dealer_statement_evidence("202606", "296065")
    assert evidence["status"] == "available"
    assert evidence["source"] == DEALER_STATEMENT_SOURCE == "Dealer statement"
    assert evidence["tool"] == DEALER_STATEMENT_TOOL == "dealer_statement"
    assert evidence["total"] is None and evidence["truncated"] is False
    statement = evidence["statement"]
    assert statement["dealer_name"] == "River Isle Ventures"
    assert statement["commission"] == {
        "expected_ngn": 991086.8, "total_activations": 495, "qualified_activation_count": 445,
        "zero_commission_count": 50, "by_denomination": {
            "5G ROUTER": 492948.6, "HYNETFLEX": 58604.7, "MIFI": 136883.29, "MIFI_1": 302650.21}}
    assert statement["orsc"] == {"device_count": 2, "total_subscription_amount_ngn": 120266.83,
                                 "zero_amount_count": 0}
    assert statement["payment"] == {"source": "Payment records", "payment_found": True,
                                    "amount_paid_ngn": 396434.72, "payment_status": "DISPUTED"}
    assert statement["position"]["expected_ngn"] == 991086.8
    assert statement["audit"] == {"readable": True, "trails": []}
    assert statement["orsc_status"] == "recorded"
    assert statement["subscription_commission"] == {
        "status": "recorded", "owed_ngn": 3050.0, "paid_ngn": 1525.0, "outstanding_ngn": 1525.0,
        "record_count": 2}
    assert statement["combined"] == {"includes_subscription": True, "owed_ngn": 994136.8,
                                     "paid_ngn": 397959.72, "outstanding_ngn": 596177.08}
    assert all(row["dealer_id"] == "296065" for row in evidence["rows"])
    assert [row["dimension"] for row in evidence["rows"][4:]] == [
        "Activation commission (amount owed)", "Activation commission paid",
        "Activation commission outstanding", "Subscription commission (amount owed)",
        "Subscription commission paid", "Subscription commission outstanding",
        "Total amount owed", "Total amount paid", "Total amount outstanding",
        "Subscription revenue (not part of amount owed)"]
    assert evidence["rows"][-4]["value"] == "NGN 994,136.80"
    assert evidence["total_rows"] == len(evidence["rows"]) == 14


def test_oracle_answer_is_rendered_from_the_statement():
    from backend.agent.tool_executor import execute_measure_request
    answer = render_measure_response(request(), execute_measure_request(request()))
    assert answer == ORACLE_ANSWER


def test_dealer_without_activity_is_no_recorded_activity_not_unavailable():
    evidence = dealer_statement_evidence("202606", "NO_SUCH_DEALER")
    assert evidence["status"] == "available"
    assert evidence["statement"] == {"found": False} and evidence["rows"] == []
    answer = render_measure_response(request("NO_SUCH_DEALER"), envelope(evidence, "NO_SUCH_DEALER"))
    assert answer == "Dealer NO\\_SUCH\\_DEALER has no recorded activity in 202606; check the dealer code."


def test_unknown_month_and_missing_dealer_are_unavailable():
    unknown = dealer_statement_evidence("209901", "296065")
    assert unknown["status"] == "unavailable" and unknown["statement"] is None
    answer = render_measure_response(request(period="209901"), envelope(unknown))
    assert answer.startswith("Dealer statement unavailable for dealer 296065, 209901: no data is recorded")
    assert "Missing evidence is not zero." in answer
    assert dealer_statement_evidence("202606", None)["status"] == "unavailable"


def test_payment_source_outage_is_stated_not_zero(monkeypatch):
    from backend.db import apdp
    monkeypatch.setattr(config, "PAYMENT_SOURCE", "apdp")

    def offline(*_args):
        raise ConnectionError("offline")
    monkeypatch.setattr(apdp, "get_partner_settlements", offline)
    monkeypatch.setattr(apdp, "healthcheck", lambda: False)
    evidence = dealer_statement_evidence("202606", "296065")
    assert evidence["status"] == "unavailable" and evidence["statement"] is None
    assert "payment source (APDP settlement records) could not be read" in evidence["note"]
    answer = render_measure_response(request(), envelope(evidence))
    assert "NGN" not in answer and "Missing evidence is not zero." in answer


def test_audit_store_offline_is_stated_separately(monkeypatch):
    monkeypatch.setattr(audit_store, "healthcheck", lambda: False)
    evidence = dealer_statement_evidence("202606", "296065")
    assert evidence["statement"]["audit"] == {"readable": False, "trails": []}
    answer = render_measure_response(request(), envelope(evidence))
    assert "Linked audit trails: unavailable — the audit store could not be read." in answer
    assert "Ask for the verification outcome for full audit results." in answer
    assert "Amount owed: NGN 994,136.80" in answer


def test_linked_audit_trails_show_module_and_conclusion_only(monkeypatch):
    def trail(dealer_id, period, module):
        if module == "zero_commission":
            return {"trail_id": "t1", "conclusion": "ROOT_CAUSE_IDENTIFIED", "confidence": 0.9,
                    "caveat_count": 1, "generated_at": None}
        return None
    monkeypatch.setattr(audit_store, "get_partner_trail", trail)
    evidence = dealer_statement_evidence("202606", "296065")
    trails = evidence["statement"]["audit"]["trails"]
    assert [set(t) for t in trails] == [{"module", "label", "conclusion"}]
    answer = render_measure_response(request(), envelope(evidence))
    assert trails[0]["module"] == "zero_commission"
    assert "Linked audit conclusions: " in answer and ": ROOT\\_CAUSE\\_IDENTIFIED." in answer
    assert "t1" not in answer and "0.9" not in answer
    assert "Ask for the verification outcome for full audit results." in answer


# ── Renderer with fakes ─────────────────────────────────────────────────────

def paid_period(**changes):
    period = {
        "period": "202606", "status": "available", "source": "Dealer statement", "tool": "dealer_statement",
        "total": None, "truncated": False, "total_rows": 0, "note": "", "rows": [],
        "statement": {
            "found": True, "dealer_name": "River Isle Ventures", "account_profile_class": "ENTERPRISE BUSINESS",
            "commission": {"expected_ngn": 991086.8, "total_activations": 495, "qualified_activation_count": 445,
                           "zero_commission_count": 50, "by_denomination": {"MIFI": 991086.8}},
            "orsc": None,
            "orsc_status": "unavailable",
            "subscription_commission": {"status": "unavailable", "owed_ngn": None, "paid_ngn": None,
                                        "outstanding_ngn": None, "record_count": 0},
            "combined": {"includes_subscription": False, "owed_ngn": 991086.8, "paid_ngn": 396434.72,
                         "outstanding_ngn": 594652.08},
            "payment": {"source": "Payment records", "payment_found": True, "amount_paid_ngn": 396434.72,
                        "payment_status": "DISPUTED"},
            "position": {"expected_ngn": 991086.8, "paid_ngn": 396434.72, "outstanding_ngn": 594652.08,
                         "variance_pct": 60.0, "headline": "UNDERPAID"},
            "audit": {"readable": True, "trails": []},
        },
    }
    for key, value in changes.items():
        period["statement"][key] = value
    return period


def test_paid_statement_leads_with_owed_paid_outstanding_and_status():
    answer = render_measure_response(request(), envelope(paid_period()))
    parts = answer.split("\n\n")
    assert parts[1:5] == [
        "Amount owed: NGN 991,086.80 (activation commission only).",
        "Amount paid: NGN 396,434.72.",
        "Amount outstanding: NGN 594,652.08.",
        "Payment status: activation commission DISPUTED (statement position: underpaid).",
    ]
    assert ("| Activation commission | NGN 991,086.80 | NGN 396,434.72 | "
            "NGN 594,652.08 (60% of amount owed) |") in answer
    # Missing subscription evidence is unavailable, never a zero line.
    assert "Subscription commission: unavailable for this month — missing is not zero." in answer
    assert "Subscription revenue: unavailable for this month — missing is not zero." in answer
    assert "| Subscription" not in answer


def test_linked_audit_conclusions_render_only_what_was_read():
    answer = render_measure_response(request(), envelope(paid_period()))
    assert "Linked audit conclusions: none returned." in answer
    assert "Linked audit trails: none recorded" not in answer
    assert "Ask for the verification outcome for full audit results." in answer


def test_linked_insufficient_data_is_unverified_not_a_pass():
    audit = {"readable": True, "trails": [
        {"module": "payment_reconciliation", "label": "Payment Reconciliation", "conclusion": "INSUFFICIENT_DATA"},
        {"module": "zero_commission", "label": "Zero-Commission", "conclusion": "NOT_PAID"}]}
    answer = render_measure_response(request(), envelope(paid_period(audit=audit)))
    assert ("Linked audit conclusions: Payment Reconciliation: INSUFFICIENT\\_DATA (unverified — not a pass); "
            "Zero\\-Commission: NOT\\_PAID.") in answer


def test_overpaid_statement_has_no_negative_amount_or_percentage():
    period = paid_period()
    period["statement"]["payment"].update(amount_paid_ngn=991586.8, payment_status="PAID")
    period["statement"]["position"].update(paid_ngn=991586.8, outstanding_ngn=-500.0, variance_pct=-0.05,
                                           headline="OVERPAID")
    period["statement"]["combined"].update(paid_ngn=991586.8, outstanding_ngn=-500.0)
    answer = render_measure_response(request(), envelope(period))
    assert "Amount outstanding: none — overpaid by NGN 500.00." in answer
    assert "| none — overpaid by NGN 500.00 (overpaid by 0.05% of amount owed) |" in answer
    assert not re.search(r"-\s?\d|NGN \\?-", answer)
    assert "Payment status: activation commission PAID (statement position: overpaid)." in answer


def test_statement_answers_carry_no_demo_wording():
    answers = [render_measure_response(request(), envelope(paid_period())),
               render_measure_response(request(), envelope(dealer_statement_evidence("202606", "296065")))]
    for answer in answers:
        for word in ("synthetic", "simulated", "sample", "demo"):
            assert word not in answer.lower()


@pytest.mark.parametrize("mutate", [
    lambda p: p["statement"].pop("payment"),
    lambda p: p["statement"]["commission"].update(total_activations="495"),
    lambda p: p["statement"]["commission"].update(zero_commission_count=600),
    lambda p: p["statement"]["position"].update(expected_ngn=1.0),
    lambda p: p["statement"]["position"].update(headline="FINE"),
    lambda p: p["statement"]["position"].update(outstanding_ngn=float("nan")),
    lambda p: p["statement"]["audit"].update(readable=False, trails=[
        {"module": "m", "label": "M", "conclusion": "X"}]),
    lambda p: p["statement"].update(orsc={"device_count": 1}),
    lambda p: p["statement"].update(orsc_status="maybe"),
    lambda p: p["statement"].update(orsc_status="recorded"),
    lambda p: p["statement"].pop("subscription_commission"),
    lambda p: p["statement"]["subscription_commission"].update(status="guess"),
    lambda p: p["statement"].update(**_recorded_subscription()) or
    p["statement"]["subscription_commission"].update(owed_ngn="3050"),
    lambda p: p["statement"].update(**_recorded_subscription()) or
    p["statement"]["subscription_commission"].update(paid_ngn=None),
    lambda p: p["statement"]["subscription_commission"].update(owed_ngn=10.0),
    lambda p: p["statement"].pop("combined"),
    lambda p: p["statement"]["combined"].update(owed_ngn=1.0),
    lambda p: p["statement"]["combined"].update(includes_subscription=True),
    lambda p: p["statement"]["combined"].update(paid_ngn=None),
    lambda p: p.update(status="unavailable"),
    lambda p: p.update(statement=None),
    lambda p: p.update(statement={"found": False}, rows=[{"dealer_id": "296065", "value": "x"}]),
])
def test_malformed_statement_evidence_raises_value_error(mutate):
    period = paid_period()
    mutate(period)
    with pytest.raises(ValueError):
        render_measure_response(request(), envelope(period))


def test_statement_payload_belongs_only_to_its_measure():
    from backend.tests.test_measure_scope import fake_priority_evidence
    period = fake_priority_evidence("202606", "296065")
    period["statement"] = None
    priority_request = {**request(), "measures": ["investigation_priority"]}
    evidence = envelope(period)
    evidence["measures"][0]["measure"] = "investigation_priority"
    with pytest.raises(ValueError):
        render_measure_response(priority_request, evidence)


# ── Scope ───────────────────────────────────────────────────────────────────

@pytest.mark.parametrize("plan", [
    {"measures": ["dealer_statement", "payment_paid"], "periods": ["202606"], "dealer_id": "296065"},
    {"measures": ["dealer_statement"], "periods": ["202605", "202606"], "dealer_id": "296065"},
    {"measures": ["dealer_statement"], "periods": ["202606"]},
    {"measures": ["dealer_statement"], "periods": ["202606"], "dealer_id": "296065", "operation": "breakdown"},
])
def test_statement_scope_stands_alone_for_one_dealer_month(plan):
    with pytest.raises(ValueError):
        MeasureScope.model_validate({"kind": "measure", **plan})


def test_statement_question_answers_through_the_agent(monkeypatch):
    from backend.tests.test_measure_scope import install_plan
    install_plan(monkeypatch, {"kind": "measure", "measures": ["dealer_statement"],
                               "periods": ["202606"], "dealer_id": "296065"})
    result = asyncio.run(agent.run_agent("what does MTN owe this dealer, what was paid and what is outstanding"))
    assert result["response"] == ORACLE_ANSWER
    assert result["tools_called"] == ["dealer_statement"]
    assert "999,999,999" not in result["response"]


def test_scope_contract_routes_statement_questions():
    from backend.agent.measure_scope import SCOPE_TOOL
    assert "['dealer_statement']" in SCOPE_TOOL["description"]
    assert "dealer_statement" in str(SCOPE_TOOL["input_schema"])


# ── Subscription commission alongside activation ────────────────────────────

def test_composer_adds_subscription_commission_and_plain_sum_totals():
    from backend.db.dealer_statement import compose_dealer_statement
    composed = compose_dealer_statement("296065", "202606")
    assert composed["subscription_commission"] == {
        "status": "recorded", "owed_ngn": 3050.0, "paid_ngn": 1525.0, "outstanding_ngn": 1525.0,
        "record_count": 2}
    assert composed["orsc_status"] == "recorded"
    # Activation position is unchanged; the combined total is a plain sum of the two types.
    assert composed["position"]["expected_ngn"] == 991086.8
    assert composed["position"]["paid_ngn"] == 396434.72
    assert composed["position"]["outstanding_ngn"] == 594652.08
    assert composed["combined"] == {"includes_subscription": True, "owed_ngn": 994136.8,
                                    "paid_ngn": 397959.72, "outstanding_ngn": 596177.08}
    assert "DEMO" not in str(composed)


def test_subscription_source_without_month_coverage_is_unavailable_not_zero(monkeypatch):
    from backend.db import dealer_statement, queries
    monkeypatch.setattr(queries, "has_source_period",
                        lambda source, period: source not in {"subscription_commission_demo", "fbb_comm_orsc"})
    monkeypatch.setattr(dealer_statement, "_orsc_rows", lambda *args: None)
    evidence = dealer_statement_evidence("202606", "296065")
    statement = evidence["statement"]
    assert statement["subscription_commission"]["status"] == "unavailable"
    assert statement["subscription_commission"]["owed_ngn"] is None
    assert statement["orsc_status"] == "unavailable"
    assert statement["combined"] == {"includes_subscription": False, "owed_ngn": 991086.8,
                                     "paid_ngn": 396434.72, "outstanding_ngn": 594652.08}
    answer = render_measure_response(request(), envelope(evidence))
    assert "Subscription commission: unavailable for this month — missing is not zero." in answer
    assert "| Total (activation only) | NGN 991,086.80 | NGN 396,434.72 | NGN 594,652.08 |" in answer
    assert "Subscription revenue: unavailable for this month — missing is not zero." in answer
    assert "| Subscription commission |" not in answer


def test_covered_month_without_dealer_subscription_record_says_none_recorded(monkeypatch):
    from backend.db import dealer_statement, subscription_evidence
    monkeypatch.setattr(subscription_evidence, "summaries", lambda period: {})
    monkeypatch.setattr(dealer_statement, "_orsc_rows", lambda *args: None)
    evidence = dealer_statement_evidence("202606", "296065")
    statement = evidence["statement"]
    assert statement["subscription_commission"]["status"] == "not_recorded"
    assert statement["orsc_status"] == "not_recorded"
    assert statement["combined"]["includes_subscription"] is False
    answer = render_measure_response(request(), envelope(evidence))
    assert "Subscription commission: none recorded for this dealer in 202606." in answer
    assert "Subscription revenue: none recorded for this dealer in 202606." in answer
    assert "| Total (activation only) |" in answer
    assert "unavailable for this month" not in answer


def test_unreadable_subscription_source_is_unavailable_not_none(monkeypatch):
    from backend.db import dealer_statement, subscription_evidence

    def broken(*_args):
        raise OSError("unreadable")
    monkeypatch.setattr(subscription_evidence, "summaries", broken)
    monkeypatch.setattr(dealer_statement, "_orsc_rows", broken)
    evidence = dealer_statement_evidence("202606", "296065")
    statement = evidence["statement"]
    assert statement["subscription_commission"]["status"] == "unavailable"
    assert statement["orsc_status"] == "unavailable" and statement["orsc"] is None
    answer = render_measure_response(request(), envelope(evidence))
    assert "Subscription commission: unavailable for this month — missing is not zero." in answer
    assert "Subscription revenue: unavailable for this month — missing is not zero." in answer
    assert "none recorded" not in answer


def test_incomplete_dealer_subscription_records_are_unavailable(monkeypatch):
    from backend.db import subscription_evidence
    monkeypatch.setattr(subscription_evidence, "summaries", lambda period: {"296065": {
        "subscription_commission_ngn": None, "subscription_settled_ngn": None,
        "subscription_outstanding_ngn": None, "subscription_commission_record_count": 1,
        "subscription_commission_complete": False}})
    statement = dealer_statement_evidence("202606", "296065")["statement"]
    assert statement["subscription_commission"]["status"] == "unavailable"
    assert statement["combined"]["includes_subscription"] is False


def _recorded_subscription():
    return {"subscription_commission": {"status": "recorded", "owed_ngn": 3050.0, "paid_ngn": 1525.0,
                                        "outstanding_ngn": 1525.0, "record_count": 2},
            "combined": {"includes_subscription": True, "owed_ngn": 994136.8, "paid_ngn": 397959.72,
                         "outstanding_ngn": 596177.08}}


def test_statement_answers_never_name_orsc_or_references():
    evidence = dealer_statement_evidence("202606", "296065")
    answers = [render_measure_response(request(), envelope(evidence)),
               render_measure_response(request(), envelope(paid_period())),
               render_measure_response(request(), envelope(paid_period(**_recorded_subscription())))]
    for text in answers + [str(evidence["rows"])]:
        assert "orsc" not in text.lower() and "orc " not in text.lower()
        assert "DEMO-" not in text and "reference" not in text.lower()
        for word in ("synthetic", "simulated", "sample", "demo"):
            assert word not in text.lower()


def test_recorded_subscription_renders_per_type_rows_and_combined_total():
    answer = render_measure_response(request(), envelope(paid_period(**_recorded_subscription())))
    assert ("| Commission | Owed | Paid | Outstanding |\n| --- | --- | --- | --- |\n"
            "| Activation commission | NGN 991,086.80 | NGN 396,434.72 | NGN 594,652.08 (60% of amount owed) |\n"
            "| Subscription commission | NGN 3,050.00 | NGN 1,525.00 | NGN 1,525.00 |\n"
            "| Total | NGN 994,136.80 | NGN 397,959.72 | NGN 596,177.08 |") in answer
    assert "Amount owed: NGN 994,136.80 (activation and subscription commission)." in answer
    assert ("Payment status: activation commission DISPUTED (statement position: underpaid); "
            "subscription commission NGN 1,525.00 settled of NGN 3,050.00 owed, as reported.") in answer


def test_missing_activation_payment_leaves_combined_paid_unavailable():
    period = paid_period(**_recorded_subscription())
    period["statement"]["payment"].update(payment_found=False, amount_paid_ngn=0.0, payment_status=None)
    period["statement"]["combined"].update(paid_ngn=None, outstanding_ngn=None)
    answer = render_measure_response(request(), envelope(period))
    assert "| Activation commission | NGN 991,086.80 | unavailable | unavailable |" in answer
    assert "| Total | NGN 994,136.80 | unavailable | unavailable |" in answer
    assert "Missing is not zero." in answer
