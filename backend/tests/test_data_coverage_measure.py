"""Atlas data-coverage answers render the coverage evidence; gaps are named, never guessed."""
import copy
import os

os.environ["USE_SAMPLE_DATA"] = "true"

import pytest
from pydantic import ValidationError

from backend import config
from backend.agent.measure_response import render_measure_response
from backend.agent.measure_scope import MeasureScope
from backend.agent.tool_executor import execute_measure_request
from backend.db import data_coverage
from backend.db.data_coverage_evidence import data_coverage_evidence

DEALER_ANSWER = "\n\n".join([
    "Data coverage for dealer 296065, 202606: gaps found — no IFS invoice record.",
    "\n".join([
        "No IFS invoice record:",
        "| Dealer | Activations on those products | Products without an invoice |",
        "| --- | --- | --- |",
        "| River Isle Ventures (296065) | 294 | 11 products |",
    ]),
    "A missing invoice record limits the inventory comparison for those products; "
    "it does not by itself establish a mismatch or an amount owed.",
    "Sample data: invoice gaps may include synthetic demonstration scenarios, not authentic IFS evidence.",
    "Source: Data coverage checks (activation records and IFS invoice comparison).",
])


@pytest.fixture(autouse=True)
def sample_mode(monkeypatch):
    monkeypatch.setattr(config, "USE_SAMPLE_DATA", True)


def request(dealer_id=None, period="202606"):
    return {"measures": ["data_coverage"], "periods": [period], "dealer_id": dealer_id, "operation": "total"}


def envelope(period_evidence, dealer_id=None):
    return {"requested_periods": [period_evidence["period"]], "dealer_id": dealer_id, "explanations": [],
            "measures": [{"measure": "data_coverage", "label": "Data coverage", "unit": "text",
                          "aggregation": "none", "note": "", "periods": [period_evidence]}]}


def test_dealer_answer_names_the_gap():
    req = request("296065")
    assert render_measure_response(req, execute_measure_request(req)) == DEALER_ANSWER


def test_month_answer_counts_each_gap_and_bounds_the_list():
    req = request()
    answer = render_measure_response(req, execute_measure_request(req))
    assert answer.startswith("Data coverage for 202606: account profile class not recorded: 0 dealers; "
                             "no IFS invoice record: 919 dealers.")
    assert "| Stone Light Networks (74050) | 429 | 16 products |" in answer
    assert "Showing 20 of 919 dealers, most activations first." in answer
    assert "USP" not in answer and "snapshot" not in answer


def test_profile_class_gap_cites_the_documented_cause(monkeypatch):
    monkeypatch.setattr(data_coverage, "collect_profile_class_missing", lambda period: [
        {"dealer_id": "296065", "dealer_name": "River Isle Ventures", "total_activations": 495,
         "zero_commission_count": 50, "commission_ngn": 0.0}])
    req = request("296065")
    answer = render_measure_response(req, execute_measure_request(req))
    assert "gaps found — account profile class not recorded, no IFS invoice record." in answer
    assert "| River Isle Ventures (296065) | 495 | 50 zero-commission |" in answer
    assert "no customer-master entry; it is one of the four documented zero-commission causes." in answer


def test_failed_check_is_not_a_clean_result(monkeypatch):
    def fail(period):
        raise RuntimeError("inventory source down")
    monkeypatch.setattr(data_coverage, "collect_ifs_missing", fail)
    req = request("296065")
    answer = render_measure_response(req, execute_measure_request(req))
    assert "no gap found in the checks that ran." in answer
    assert "No IFS invoice record: check unavailable" in answer and "not a clean result" in answer


def test_unknown_month_and_dealer_are_stated():
    unknown = render_measure_response(request(period="209901"), envelope(data_coverage_evidence("209901", None)))
    assert "Data coverage unavailable for 209901: no data is recorded for this month" in unknown
    missing = render_measure_response(request("NO_SUCH_DEALER"),
                                      envelope(data_coverage_evidence("202606", "NO_SUCH_DEALER"), "NO_SUCH_DEALER"))
    assert "Dealer NO\\_SUCH\\_DEALER has no recorded activity in 202606" in missing


@pytest.mark.parametrize("change", [
    lambda c: c["gaps"]["invoice"].update(dealer_count=0),
    lambda c: c["gaps"]["invoice"].update(status="unavailable"),
    lambda c: c.update(found=False),
    lambda c: c["gaps"].pop("profile_class"),
])
def test_malformed_coverage_evidence_is_rejected(change):
    evidence = copy.deepcopy(data_coverage_evidence("202606", "296065"))
    change(evidence["coverage"])
    with pytest.raises(ValueError):
        render_measure_response(request("296065"), envelope(evidence, "296065"))


def test_scope_is_one_month_with_an_optional_dealer():
    base = {"kind": "measure", "measures": ["data_coverage"], "periods": ["202606"], "operation": "total"}
    assert MeasureScope.model_validate(base).dealer_id is None
    assert MeasureScope.model_validate({**base, "dealer_id": "296065"}).dealer_id == "296065"
    for change in ({"periods": ["202605", "202606"]}, {"operation": "breakdown"},
                   {"measures": ["data_coverage", "activation_count"]}):
        with pytest.raises(ValidationError):
            MeasureScope.model_validate({**base, **change})
