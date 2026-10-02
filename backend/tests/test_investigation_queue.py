"""Atlas month-wide investigation queue: the Overview queue, filtered and bounded.

Sample data, no mocks for the reader oracle: the queue below must be the one
the Overview tab shows for the same month (see the route equality test).
"""
import copy
import os

os.environ["USE_SAMPLE_DATA"] = "true"

import pytest
from fastapi.testclient import TestClient
from pydantic import ValidationError

from backend import config
from backend.agent.measure_response import render_measure_response
from backend.agent.measure_scope import MeasureScope
from backend.agent.tool_executor import execute_measure_request
from backend.assurance import overview
from backend.assurance.overview import (
    INVESTIGATION_QUEUE_SOURCE,
    INVESTIGATION_QUEUE_TOOL,
    investigation_queue_evidence,
)

DEMO_WORDS = ("synthetic", "simulated", "sample", "demo")
TOP_THREE = [
    (1, "296065", "River Isle Ventures", "HIGH", "payment", "COMMISSION_DISPUTE",
     ["payment", "inventory", "commission", "activation"], 594652.08),
    (2, "19562", "Indigo Arc Communications", "HIGH", "payment", "COMMISSION_DISPUTE",
     ["payment", "inventory", "commission", "activation"], 253998.88),
    (3, "369075", "Coral Sky Communications", "HIGH", "payment", "COMMISSION_DISPUTE",
     ["payment", "commission", "inventory"], 190672.57),
]


@pytest.fixture(autouse=True)
def sample_mode(monkeypatch):
    monkeypatch.setattr(config, "USE_SAMPLE_DATA", True)
    monkeypatch.setattr(config, "PAYMENT_SOURCE", "simulated")


def summary(dealer):
    return (dealer["rank"], dealer["dealer_id"], dealer["dealer_name"], dealer["severity"],
            dealer["lead_module"], dealer["lead_type"], dealer["modules"], dealer["amount_outstanding"])


def assert_no_demo_words(text):
    assert not any(word in text.lower() for word in DEMO_WORDS)


# ── Reader oracle (real sample data) ────────────────────────────────────────

def test_unfiltered_queue_lists_the_top_ten_and_totals_every_dealer():
    evidence = investigation_queue_evidence("202606", None)

    assert evidence["status"] == "available"
    assert evidence["source"] == INVESTIGATION_QUEUE_SOURCE
    assert evidence["tool"] == INVESTIGATION_QUEUE_TOOL
    body = evidence["queue"]
    assert body["queue_size"] == 922 and body["match_count"] == 922
    assert body["severity"] is None and body["modules"] == [] and body["limit"] == 10
    assert len(body["dealers"]) == 10 and evidence["truncated"] is True
    assert [summary(d) for d in body["dealers"][:3]] == TOP_THREE
    assert [d["rank"] for d in body["dealers"]] == list(range(1, 11))
    assert body["outstanding_ngn"] == 8049638.78
    assert body["payment_dealer_count"] == 922
    assert body["unchecked_modules"] == []
    assert len(evidence["rows"]) == evidence["total_rows"] == 10


def test_high_filter_keeps_full_queue_ranks():
    body = investigation_queue_evidence("202606", None, severity="HIGH")["queue"]

    assert body["queue_size"] == 922 and body["match_count"] == 61
    assert all(d["severity"] == "HIGH" for d in body["dealers"])
    assert [summary(d) for d in body["dealers"][:3]] == TOP_THREE
    assert body["outstanding_ngn"] == 2737023.81
    assert body["payment_dealer_count"] == 61


def test_module_filter_requires_findings_in_every_listed_module():
    evidence = investigation_queue_evidence("202606", None, modules=["payment", "inventory"], limit=5)
    body = evidence["queue"]

    assert body["match_count"] == 31 and len(body["dealers"]) == 5
    assert body["modules"] == ["payment", "inventory"] and body["limit"] == 5
    assert all({"payment", "inventory"} <= set(d["modules"]) for d in body["dealers"])
    assert body["outstanding_ngn"] == 3065571.04
    # Ranks are positions in the full queue, not in the filtered list.
    assert [d["rank"] for d in body["dealers"]][:3] == [1, 2, 3]
    ranks = [d["rank"] for d in body["dealers"]]
    assert ranks == sorted(ranks)


def test_filter_matching_nothing_is_an_answer_not_unavailable():
    evidence = investigation_queue_evidence("202606", None, severity="LOW", modules=["inventory"])

    assert evidence["status"] == "available"
    body = evidence["queue"]
    assert body["match_count"] == 0 and body["dealers"] == [] and body["queue_size"] == 922
    assert body["outstanding_ngn"] == 0 and body["payment_dealer_count"] == 0
    assert evidence["truncated"] is False


def test_unfiltered_top_ten_equals_the_overview_first_page():
    from backend.main import app

    with TestClient(app) as client:
        response = client.get("/assurance/overview", params={"mon_period": "202606", "limit": 10})
    assert response.status_code == 200
    page = response.json()
    body = investigation_queue_evidence("202606", None)["queue"]
    assert page["total"] == body["queue_size"]
    assert [(i["dealer_id"], i["severity"]) for i in page["items"]] == [
        (d["dealer_id"], d["severity"]) for d in body["dealers"]]


def test_unknown_month_is_unavailable():
    evidence = investigation_queue_evidence("209901", None)
    assert evidence["status"] == "unavailable" and evidence["queue"] is None
    assert "no data is recorded" in evidence["note"]


def test_overview_failure_is_unavailable(monkeypatch):
    async def broken(period):
        raise RuntimeError("boom")
    monkeypatch.setattr(overview, "overview_snapshot", broken)
    evidence = investigation_queue_evidence("202606", None)
    assert evidence["status"] == "unavailable" and evidence["queue"] is None


def test_no_module_checked_is_unavailable_not_an_empty_queue(monkeypatch):
    async def nothing(period):
        modules = [{"module": m, "status": "UNAVAILABLE"} for m in
                   ("commission", "activation", "inventory", "payment")]
        return {"modules": modules}, [], []
    monkeypatch.setattr(overview, "overview_snapshot", nothing)
    evidence = investigation_queue_evidence("202606", None)
    assert evidence["status"] == "unavailable"
    assert "no assurance module could be checked" in evidence["note"]


def test_reader_rejects_a_dealer():
    with pytest.raises(ValueError):
        investigation_queue_evidence("202606", "296065")


# ── Rendered answers (real sample data) ─────────────────────────────────────

def request(**extra):
    return {"measures": ["investigation_queue"], "periods": ["202606"], "dealer_id": None,
            "operation": "total", **extra}


def answer(**extra):
    req = request(**extra)
    return render_measure_response(req, execute_measure_request(req))


HIGH_ANSWER_HEAD = (
    "Investigation queue for 202606: 61 dealers match HIGH severity (of 922 in the queue); "
    "showing the top 10."
)


def test_high_answer_leads_with_headline_table_and_aggregate():
    text = answer(queue_severity="HIGH")
    parts = text.split("\n\n")
    assert parts[0] == HIGH_ANSWER_HEAD
    table = parts[1].split("\n")
    assert table[0] == "| Rank | Dealer | Severity | Lead finding | Modules | Amount outstanding |"
    assert table[2] == ("| 1 | River Isle Ventures (296065) | HIGH | Payment · COMMISSION\\_DISPUTE | "
                        "Payment, Inventory, Commission, Activation | NGN 594,652.08 |")
    assert len(table) == 12
    assert parts[2] == "Showing 10 of 61 matching dealers."
    assert parts[3] == ("Amount outstanding across all 61 matching dealers: NGN 2,737,023.81 "
                        "(counting only the 61 dealers with a payment record).")
    assert parts[4] == "Queue order: severity, then amount outstanding (largest first)."
    assert parts[-1] == "Source: Investigation queue."
    assert "Not checked" not in text
    assert_no_demo_words(text)


def test_module_answer_names_the_modules():
    text = answer(queue_modules=["payment", "inventory"], limit=3)
    assert text.startswith("Investigation queue for 202606: 31 dealers have findings in payment and "
                           "inventory (of 922 in the queue); showing the top 3.")
    assert "Showing 3 of 31 matching dealers." in text


def test_nothing_matched_answer_is_distinct_from_unavailable():
    text = answer(queue_severity="LOW", queue_modules=["inventory"])
    assert text.split("\n\n")[0] == ("No dealers in the 202606 investigation queue match LOW severity "
                                     "with findings in inventory (queue of 922 dealers).")
    assert "unavailable" not in text.lower() and "|" not in text


def test_unknown_month_answer_is_unavailable():
    req = request()
    req["periods"] = ["209901"]
    text = render_measure_response(req, execute_measure_request(req))
    assert text.startswith("Investigation queue unavailable for 209901:")
    assert "Missing evidence is not an empty queue." in text


# ── Renderer with fakes ─────────────────────────────────────────────────────

def fake_dealer(rank, code, severity="HIGH", modules=("payment",), outstanding=100.0):
    return {"rank": rank, "dealer_id": code, "dealer_name": f"Dealer {code}", "severity": severity,
            "lead_module": modules[0], "lead_type": "COMMISSION_DISPUTE", "modules": list(modules),
            "amount_outstanding": outstanding}


def fake_evidence(dealers, *, match_count=None, queue_size=None, severity=None, modules=(), limit=10,
                  unchecked=(), outstanding=None, payment_count=None):
    match_count = len(dealers) if match_count is None else match_count
    if queue_size is None:  # an unfiltered queue matches every dealer in it
        queue_size = 50 if severity or modules else match_count
    paid = [d for d in dealers if d["amount_outstanding"] is not None]
    body = {
        "severity": severity, "modules": list(modules), "limit": limit, "queue_size": queue_size,
        "match_count": match_count,
        "outstanding_ngn": (sum(d["amount_outstanding"] for d in paid) if outstanding is None else outstanding),
        "payment_dealer_count": len(paid) if payment_count is None else payment_count,
        "unchecked_modules": list(unchecked), "dealers": dealers,
    }
    if "payment" in unchecked:
        body["outstanding_ngn"] = body["payment_dealer_count"] = None
    rows = [{"dealer_id": d["dealer_id"], "dealer_name": d["dealer_name"],
             "dimension": f"Rank {d['rank']}", "value": d["severity"]} for d in dealers]
    period = {"period": "202606", "status": "available", "source": INVESTIGATION_QUEUE_SOURCE,
              "tool": INVESTIGATION_QUEUE_TOOL, "total": None, "note": "",
              "truncated": match_count > len(dealers), "total_rows": len(rows), "rows": rows,
              "queue": body}
    return envelope(period)


def envelope(period):
    return {"requested_periods": ["202606"], "dealer_id": None, "explanations": [],
            "measures": [{"measure": "investigation_queue", "label": "Investigation queue", "unit": "text",
                          "aggregation": "none", "note": "", "periods": [period]}]}


def render(evidence, **extra):
    return render_measure_response(request(**extra), evidence)


def test_truncation_line_and_aggregate_cover_every_match():
    dealers = [fake_dealer(i, str(i)) for i in range(1, 3)]
    text = render(fake_evidence(dealers, match_count=5, queue_size=5, limit=2, outstanding=500.0,
                                payment_count=5), limit=2)
    assert text.startswith("Investigation queue for 202606: 5 dealers; showing the top 2.")
    assert "Showing 2 of 5 matching dealers." in text
    assert "Amount outstanding across all 5 dealers in the queue: NGN 500.00" in text


def test_all_matches_shown_has_no_truncation_line():
    text = render(fake_evidence([fake_dealer(4, "44", outstanding=None)], severity="HIGH"),
                  queue_severity="HIGH")
    assert text.startswith("Investigation queue for 202606: 1 dealer matches HIGH severity "
                           "(of 50 in the queue); showing it.")
    assert "Showing" not in text.split("\n\n", 1)[1]
    assert "| No payment record |" in text
    assert ("Amount outstanding across the 1 matching dealer: NGN 0.00 "
            "(counting only the 0 dealers with a payment record).") in text


def test_unchecked_note_and_unavailable_amounts():
    dealers = [fake_dealer(1, "1", modules=("commission",), outstanding=None)]
    text = render(fake_evidence(dealers, unchecked=["payment"]))
    assert "Not checked: payment; the queue may be incomplete." in text
    assert "Amount outstanding unavailable: the payment module could not be checked." in text
    assert "| Unavailable |" in text


def test_nothing_matched_with_unchecked_module_says_so():
    text = render(fake_evidence([], severity="HIGH", unchecked=["inventory"]), queue_severity="HIGH")
    assert text.startswith("No dealers in the 202606 investigation queue match HIGH severity (queue of 50 dealers).")
    assert "Not checked: inventory; the queue may be incomplete." in text


def test_empty_unfiltered_queue_is_stated():
    text = render(fake_evidence([], queue_size=0))
    assert text.startswith("No dealers are in the 202606 investigation queue.")


def test_unavailable_renders_note_and_is_never_empty():
    period = overview._unavailable("202606", "The investigation queue is unavailable for 202606: "
                                   "no assurance module could be checked.", "queue")
    text = render(envelope(period))
    assert text.startswith("Investigation queue unavailable for 202606:")
    assert "Missing evidence is not an empty queue." in text
    assert "No dealers" not in text


@pytest.mark.parametrize("mutate", [
    lambda e: e["measures"][0]["periods"][0].__setitem__("queue", None),
    lambda e: e["measures"][0]["periods"][0]["queue"].__setitem__("match_count", 0),
    lambda e: e["measures"][0]["periods"][0]["queue"].__setitem__("queue_size", 1),
    lambda e: e["measures"][0]["periods"][0]["queue"].__setitem__("limit", 1),
    lambda e: e["measures"][0]["periods"][0]["queue"].__setitem__("severity", "LOW"),
    lambda e: e["measures"][0]["periods"][0]["queue"].__setitem__("outstanding_ngn", 999.0),
    lambda e: e["measures"][0]["periods"][0]["queue"].__setitem__("outstanding_ngn", None),
    lambda e: e["measures"][0]["periods"][0]["queue"]["dealers"][0].__setitem__("rank", 2),
    lambda e: e["measures"][0]["periods"][0]["queue"]["dealers"][0].__setitem__("severity", "BAD"),
    lambda e: e["measures"][0]["periods"][0]["queue"]["dealers"][0].__setitem__("modules", "payment"),
    lambda e: e["measures"][0]["periods"][0]["queue"]["dealers"][0].pop("lead_type"),
    lambda e: e["measures"][0]["periods"][0].__setitem__("truncated", True),
])
def test_malformed_payloads_are_rejected(mutate):
    evidence = fake_evidence([fake_dealer(1, "1"), fake_dealer(2, "2")])
    render(copy.deepcopy(evidence))  # well-formed baseline renders
    mutate(evidence)
    with pytest.raises(ValueError):
        render(evidence)


def test_filters_must_match_the_request():
    evidence = fake_evidence([fake_dealer(1, "1")], severity="HIGH")
    with pytest.raises(ValueError):
        render(evidence)  # request asked for no severity filter


def test_listed_dealers_must_satisfy_the_filter():
    evidence = fake_evidence([fake_dealer(1, "1", modules=("payment",))], modules=["inventory"])
    with pytest.raises(ValueError):
        render(evidence, queue_modules=["inventory"])


def test_queue_payload_belongs_only_to_its_measure():
    evidence = fake_evidence([fake_dealer(1, "1")])
    evidence["measures"][0]["measure"] = "data_coverage"
    with pytest.raises(ValueError):
        render_measure_response({**request(), "measures": ["data_coverage"]}, evidence)


def test_fake_answers_have_no_demo_words():
    text = render(fake_evidence([fake_dealer(1, "1")], unchecked=["inventory"]))
    assert_no_demo_words(text)


# ── Scope contract ──────────────────────────────────────────────────────────

def scope(**extra):
    return MeasureScope.model_validate({"kind": "measure", "measures": ["investigation_queue"],
                                        "periods": ["202606"], **extra})


def test_scope_accepts_the_queue_filters():
    parsed = scope(queue_severity="HIGH", queue_modules=["payment", "inventory"], limit=25)
    assert parsed.queue_severity == "HIGH" and parsed.queue_modules == ["payment", "inventory"]
    assert parsed.limit == 25
    assert scope().limit is None  # the reader applies the default of 10


@pytest.mark.parametrize("extra", [
    {"dealer_id": "296065"},
    {"dealer_name": "River Isle Ventures"},
    {"limit": 0}, {"limit": 101},
    {"queue_modules": ["payment", "payment"]},
    {"queue_modules": ["payment", "finance"]},
    {"queue_severity": "CRITICAL"},
    {"operation": "breakdown"},
    {"periods": ["202605", "202606"]},
    {"measures": ["investigation_queue", "payment_exceptions"]},
])
def test_scope_rejects_invalid_queue_requests(extra):
    with pytest.raises(ValidationError):
        scope(**extra)


@pytest.mark.parametrize("field", [{"queue_severity": "HIGH"}, {"queue_modules": ["payment"]}, {"limit": 10}])
@pytest.mark.parametrize("measure", ["investigation_priority", "payment_exceptions", "activation_count"])
def test_queue_fields_are_valid_only_with_the_queue(field, measure):
    with pytest.raises(ValidationError):
        MeasureScope.model_validate({"kind": "measure", "measures": [measure], "periods": ["202606"],
                                     "dealer_id": "296065", **field})


def test_scope_tool_routes_month_wide_and_single_dealer_questions_apart():
    from backend.agent.measure_scope import SCOPE_TOOL
    description = SCOPE_TOOL["description"]
    assert "investigation_queue" in description and "investigation_priority" in description
    assert "health" in description
