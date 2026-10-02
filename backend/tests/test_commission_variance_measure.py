"""Atlas commission-variance evidence is the month-on-month query, projected.

The oracle uses sample data with no mocks: the 202606 total matches the
dealer statement's activation commission for 296065 (NGN 991,086.80).
"""
import copy
import os

os.environ["USE_SAMPLE_DATA"] = "true"

import pandas as pd
import pytest
from pydantic import ValidationError

from backend import config
from backend.agent.measure_response import render_measure_response
from backend.agent.measure_scope import MeasureScope
from backend.agent.tool_executor import execute_measure_request
from backend.db import variance_evidence
from backend.db.variance_evidence import VARIANCE_SOURCE, VARIANCE_TOOL, commission_variance_evidence

ORACLE_ANSWER = "\n\n".join([
    "Activation commission for dealer 296065, 202605 to 202606: up NGN 39,873.42 "
    "(from NGN 951,213.38 to NGN 991,086.80, 4.2%).",
    "\n".join([
        "| Product | Activations 202605 | Commission 202605 | Activations 202606 | Commission 202606 | Change | Change % |",
        "| --- | --- | --- | --- | --- | --- | --- |",
        "| 5G ROUTER | 58 | NGN 476,516.98 | 60 | NGN 492,948.60 | up NGN 16,431.62 | 3.4% |",
        "| HYNETFLEX | 33 | NGN 55,255.86 | 35 | NGN 58,604.70 | up NGN 3,348.84 | 6.1% |",
        "| MIFI | 104 | NGN 130,604.24 | 109 | NGN 136,883.29 | up NGN 6,279.05 | 4.8% |",
        "| MIFI\\_1 | 230 | NGN 288,836.30 | 241 | NGN 302,650.21 | up NGN 13,813.91 | 4.8% |",
        "| UNCLASSIFIED | 47 | NGN 0.00 | 50 | NGN 0.00 | no change | — |",
        "| Total | 472 | NGN 951,213.38 | 495 | NGN 991,086.80 | up NGN 39,873.42 | 4.2% |",
    ]),
    "Largest change: 5G ROUTER, up NGN 16,431.62.",
    "This splits the change by product; it does not establish why it changed. "
    "Ask for the verification outcome to check zero-commission records against the documented causes.",
    "Source: Activation commission records.",
])


@pytest.fixture(autouse=True)
def sample_mode(monkeypatch):
    monkeypatch.setattr(config, "USE_SAMPLE_DATA", True)


def request(dealer_id="296065", periods=("202605", "202606"), operation="explain"):
    return {"measures": ["commission_variance"], "periods": list(periods), "dealer_id": dealer_id,
            "operation": operation}


def envelope(period_evidence, periods=("202605", "202606"), dealer_id="296065"):
    return {"requested_periods": list(periods), "dealer_id": dealer_id, "explanations": [],
            "measures": [{"measure": "commission_variance", "label": "Commission variance by product",
                          "unit": "text", "aggregation": "none", "note": "", "periods": [period_evidence]}]}


def frame(rows):
    return pd.DataFrame(rows, columns=["period", "product_denomination", "activation_count",
                                       "total_commission_ngn", "delta_ngn", "delta_pct"])


# ── Oracle: real sample data ────────────────────────────────────────────────

def test_variance_evidence_splits_the_change_by_product():
    evidence = commission_variance_evidence("202605", "202606", "296065")
    assert evidence["status"] == "available" and evidence["period"] == "202606"
    assert evidence["source"] == VARIANCE_SOURCE and evidence["tool"] == VARIANCE_TOOL
    variance = evidence["variance"]
    assert variance["totals"] == {"earlier_activations": 472, "earlier_ngn": 951213.38,
                                  "later_activations": 495, "later_ngn": 991086.8, "change_ngn": 39873.42}
    assert [p["product"] for p in variance["products"]] == ["5G ROUTER", "HYNETFLEX", "MIFI", "MIFI_1", "UNCLASSIFIED"]
    assert variance["earlier_recorded"] and variance["later_recorded"]
    assert all(row["dealer_id"] == "296065" for row in evidence["rows"])
    assert evidence["total_rows"] == len(evidence["rows"]) == 6


@pytest.mark.parametrize("periods", [("202605", "202606"), ("202606", "202605")])
def test_oracle_answer_is_rendered_in_either_month_order(periods):
    req = request(periods=periods)
    assert render_measure_response(req, execute_measure_request(req)) == ORACLE_ANSWER


def test_compare_renders_the_same_answer_as_explain():
    req = request(operation="compare")
    assert render_measure_response(req, execute_measure_request(req)) == ORACLE_ANSWER


# ── Missing evidence is never zero ──────────────────────────────────────────

def test_unknown_dealer_is_no_recorded_activity():
    evidence = commission_variance_evidence("202605", "202606", "NO_SUCH_DEALER")
    assert evidence["status"] == "available" and evidence["variance"]["found"] is False
    answer = render_measure_response(request("NO_SUCH_DEALER"), envelope(evidence, dealer_id="NO_SUCH_DEALER"))
    assert "no recorded activations in 202605 or 202606" in answer


def test_unknown_month_is_unavailable_and_named():
    evidence = commission_variance_evidence("202606", "209901", "296065")
    assert evidence["status"] == "unavailable" and evidence["variance"] is None
    answer = render_measure_response(request(periods=("202606", "209901")),
                                     envelope(evidence, periods=("202606", "209901")))
    assert "no data is recorded for 209901" in answer and "not zero" in answer
    assert "NGN" not in answer


def test_unreadable_source_is_unavailable(monkeypatch):
    def fail(*args):
        raise RuntimeError("presto down")
    monkeypatch.setattr(variance_evidence, "execute_query", fail)
    evidence = commission_variance_evidence("202605", "202606", "296065")
    assert evidence["status"] == "unavailable"
    assert "could not be read" in render_measure_response(request(), envelope(evidence))


def test_product_sold_only_in_the_earlier_month_counts_as_a_fall(monkeypatch):
    # The query puts delta_ngn on later-month rows only; this product must not drop out.
    monkeypatch.setattr(variance_evidence, "execute_query", lambda *args: frame([
        ("202605", "MIFI", 10, 1000.0, 0.0, 0.0),
        ("202605", "HYNETFLEX", 4, 400.0, 0.0, 0.0),
        ("202606", "MIFI", 12, 1200.0, 200.0, 20.0),
    ]))
    evidence = commission_variance_evidence("202605", "202606", "296065")
    products = {p["product"]: p for p in evidence["variance"]["products"]}
    assert products["HYNETFLEX"]["change_ngn"] == -400.0 and products["HYNETFLEX"]["later_activations"] == 0
    assert evidence["variance"]["totals"]["change_ngn"] == -200.0
    answer = render_measure_response(request(), envelope(evidence))
    assert "down NGN 200.00" in answer and "Largest change: HYNETFLEX, down NGN 400.00." in answer
    assert "NGN -" not in answer and "-%" not in answer


def test_month_without_records_is_stated(monkeypatch):
    monkeypatch.setattr(variance_evidence, "execute_query", lambda *args: frame([
        ("202606", "MIFI", 12, 1200.0, 1200.0, 100.0)]))
    evidence = commission_variance_evidence("202605", "202606", "296065")
    answer = render_measure_response(request(), envelope(evidence))
    assert "no recorded activations in 202605" in answer
    assert "| MIFI | 0 | NGN 0.00 | 12 | NGN 1,200.00 | up NGN 1,200.00 | new |" in answer


# ── Contract ────────────────────────────────────────────────────────────────

@pytest.mark.parametrize("change", [
    lambda v: v["products"][0].update(change_ngn=1.0),
    lambda v: v["totals"].update(later_ngn=1.0),
    lambda v: v.update(earlier="202607"),
    lambda v: v["products"].append(dict(v["products"][0])),
])
def test_malformed_variance_evidence_is_rejected(change):
    evidence = copy.deepcopy(commission_variance_evidence("202605", "202606", "296065"))
    change(evidence["variance"])
    with pytest.raises(ValueError):
        render_measure_response(request(), envelope(evidence))


def test_scope_requires_one_dealer_and_two_months():
    base = {"kind": "measure", "measures": ["commission_variance"], "periods": ["202605", "202606"],
            "dealer_id": "296065", "operation": "explain"}
    assert MeasureScope.model_validate(base).operation == "explain"
    for change in ({"periods": ["202606"]}, {"dealer_id": None}, {"operation": "total"},
                   {"measures": ["commission_variance", "activation_count"]}, {"filter": "zero_commission"}):
        with pytest.raises(ValidationError):
            MeasureScope.model_validate({**base, **change})
