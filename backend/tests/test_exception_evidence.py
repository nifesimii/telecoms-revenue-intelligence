"""Atlas activation and payment exception evidence is the screens' own computation.

Oracles use sample data with no mocks: activation exceptions match the
Activation workspace Exceptions view (``activation_workspace.collection``) and
payment exceptions match the Payments Exceptions view (``GET /payments`` with
the DISPUTED, PARTIALLY_PAID and PENDING status filter) for 202606.
Failure cases monkeypatch the underlying reads.
"""
import os

os.environ["USE_SAMPLE_DATA"] = "true"

import pytest
from fastapi.testclient import TestClient

from backend import config
from backend.db import activation_workspace, payment_snapshot, queries
from backend.db.exception_evidence import (
    ACTIVATION_EXCEPTIONS_SOURCE,
    ACTIVATION_EXCEPTIONS_TOOL,
    MAX_LISTED_DEALERS,
    PAYMENT_EXCEPTIONS_SOURCE,
    PAYMENT_EXCEPTIONS_TOOL,
    activation_exceptions_evidence,
    payment_exceptions_evidence,
)
from backend.main import app

PERIOD_KEYS = {"period", "status", "source", "tool", "total", "truncated",
               "total_rows", "note", "rows"}


@pytest.fixture(autouse=True)
def sample_mode(monkeypatch):
    monkeypatch.setattr(config, "USE_SAMPLE_DATA", True)
    monkeypatch.setattr(config, "PAYMENT_SOURCE", "simulated")


def fail(*_args, **_kwargs):
    raise RuntimeError("source down")


def unavailable(period, source, tool, payload, note):
    return {"period": period, "status": "unavailable", "source": source, "tool": tool,
            "total": None, "truncated": False, "total_rows": 0, "note": note,
            "rows": [], payload: None}


# ── Activation oracle ───────────────────────────────────────────────────────

def test_activation_month_evidence_matches_the_exceptions_view():
    evidence = activation_exceptions_evidence("202606", None)

    assert set(evidence) == PERIOD_KEYS | {"activation_exceptions"}
    assert evidence["status"] == "available"
    assert evidence["source"] == ACTIVATION_EXCEPTIONS_SOURCE
    assert evidence["tool"] == ACTIVATION_EXCEPTIONS_TOOL
    exceptions = evidence["activation_exceptions"]
    assert exceptions["dealer_scoped"] is False and exceptions["found"] is True
    assert exceptions["dealer_count"] == 155 and exceptions["finding_count"] == 190
    assert exceptions["by_finding"] == [
        {"type": "ALL_UNQUALIFIED", "label": "All activations have zero commission",
         "severity": "HIGH", "dealer_count": 35},
        {"type": "HIGH_UNQUALIFIED_RATE", "label": "More than half have zero commission",
         "severity": "MEDIUM", "dealer_count": 123},
        {"type": "UNUSUAL_VOLUME", "label": "Unusual activation volume",
         "severity": "LOW", "dealer_count": 32},
    ]
    assert len(exceptions["dealers"]) == MAX_LISTED_DEALERS == 100
    assert evidence["truncated"] is True and evidence["total_rows"] == 100
    assert [d["dealer_id"] for d in exceptions["dealers"][:3]] == ["19398", "19519", "19630"]
    assert exceptions["dealers"][0] == {
        "dealer_id": "19398", "dealer_name": "Harbor Moon Communications",
        "activation_count": 9, "zero_commission_count": 9,
        "findings": [
            {"type": "ALL_UNQUALIFIED", "label": "All activations have zero commission", "severity": "HIGH"},
            {"type": "HIGH_UNQUALIFIED_RATE", "label": "More than half have zero commission", "severity": "MEDIUM"},
        ],
    }
    assert evidence["rows"][0] == {
        "dealer_id": "19398", "dealer_name": "Harbor Moon Communications", "dimension": "HIGH",
        "value": "All activations have zero commission; More than half have zero commission",
    }


def test_activation_listing_is_the_screen_order():
    screen = activation_workspace.collection("202606", None, "exceptions", "", "", "all", "severity", "desc")
    evidence = activation_exceptions_evidence("202606", None)
    listed = [d["dealer_id"] for d in evidence["activation_exceptions"]["dealers"]]
    assert listed == [row["dealer_id"] for row in screen["items"][:MAX_LISTED_DEALERS]]
    assert evidence["activation_exceptions"]["dealer_count"] == screen["total"]
    assert evidence["activation_exceptions"]["finding_count"] == screen["filtered_summary"]["finding_count"]


def test_activation_listing_equals_the_workspace_endpoint():
    client = TestClient(app)
    response = client.get("/activations/accounts", params={
        "mon_period": "202606", "view": "exceptions", "sort_by": "severity",
        "direction": "desc", "limit": 100})
    assert response.status_code == 200
    page = response.json()
    evidence = activation_exceptions_evidence("202606", None)["activation_exceptions"]
    assert evidence["dealer_count"] == page["total"]
    assert [(d["dealer_id"], [f["type"] for f in d["findings"]]) for d in evidence["dealers"]] == [
        (row["dealer_id"], [f["type"] for f in row["findings"]]) for row in page["items"]]


def test_activation_dealer_evidence_lists_only_that_dealer():
    evidence = activation_exceptions_evidence("202606", "296065")

    exceptions = evidence["activation_exceptions"]
    assert exceptions["dealer_scoped"] is True and exceptions["found"] is True
    assert exceptions["dealer_count"] == 1 and exceptions["finding_count"] == 1
    assert exceptions["dealers"] == [{
        "dealer_id": "296065", "dealer_name": "River Isle Ventures",
        "activation_count": 495, "zero_commission_count": 50,
        "findings": [{"type": "UNUSUAL_VOLUME", "label": "Unusual activation volume", "severity": "LOW"}],
    }]
    assert exceptions["by_finding"] == [{"type": "UNUSUAL_VOLUME", "label": "Unusual activation volume",
                                         "severity": "LOW", "dealer_count": 1}]
    assert evidence["truncated"] is False and evidence["total_rows"] == 1


def test_activation_dealer_without_findings_has_none(monkeypatch):
    real = activation_workspace.enrich_accounts

    def no_findings(period, prior):
        rows = real(period, prior)
        for row in rows:
            if row["dealer_id"] == "296065":
                row["findings"] = []
        return rows
    monkeypatch.setattr(activation_workspace, "enrich_accounts", no_findings)

    exceptions = activation_exceptions_evidence("202606", "296065")["activation_exceptions"]
    assert exceptions["found"] is True and exceptions["dealer_count"] == 0
    assert exceptions["dealers"] == [] and exceptions["by_finding"] == []


def test_activation_unknown_dealer_is_not_found():
    evidence = activation_exceptions_evidence("202606", "NO_SUCH_DEALER")
    assert evidence["status"] == "available" and evidence["rows"] == []
    assert evidence["activation_exceptions"] == {
        "dealer_scoped": True, "found": False, "dealer_count": None, "finding_count": None,
        "by_finding": [], "dealers": []}


def test_activation_unknown_month_and_unreadable_source_are_unavailable(monkeypatch):
    args = (ACTIVATION_EXCEPTIONS_SOURCE, ACTIVATION_EXCEPTIONS_TOOL, "activation_exceptions")
    assert activation_exceptions_evidence("209901", None) == unavailable(
        "209901", *args, "no data is recorded for this month.")
    monkeypatch.setattr(activation_workspace, "execute_query", fail)
    assert activation_exceptions_evidence("202606", None) == unavailable(
        "202606", *args, "the activation exception checks could not be read.")
    monkeypatch.setattr(queries, "get_available_periods", fail)
    assert activation_exceptions_evidence("202606", None) == unavailable(
        "202606", *args, "the recorded months could not be read.")


# ── Payment oracle ──────────────────────────────────────────────────────────

def test_payment_month_evidence_pins_count_rows_and_outstanding():
    evidence = payment_exceptions_evidence("202606", None)

    assert set(evidence) == PERIOD_KEYS | {"payment_exceptions"}
    assert evidence["status"] == "available"
    assert evidence["source"] == PAYMENT_EXCEPTIONS_SOURCE
    assert evidence["tool"] == PAYMENT_EXCEPTIONS_TOOL
    exceptions = evidence["payment_exceptions"]
    assert exceptions["dealer_scoped"] is False and exceptions["found"] is True
    assert exceptions["dealer_count"] == 887
    assert exceptions["outstanding_ngn"] == 8049638.78
    assert exceptions["status_counts"] == [
        {"status": "DISPUTED", "dealer_count": 26},
        {"status": "PARTIALLY_PAID", "dealer_count": 83},
        {"status": "PENDING", "dealer_count": 778},
    ]
    assert exceptions["dealer_status"] is None
    assert len(exceptions["dealers"]) == 100 and evidence["truncated"] is True
    assert exceptions["dealers"][0] == {
        "dealer_id": "296065", "dealer_name": "River Isle Ventures", "payment_status": "DISPUTED",
        "commission_owed": 991086.8, "amount_paid": 396434.72, "amount_unpaid": 594652.08,
        "exception_flag": "CONFIRMED_MISMATCH",
    }
    assert [d["dealer_id"] for d in exceptions["dealers"][:3]] == ["296065", "19562", "369075"]
    assert evidence["rows"][0] == {"dealer_id": "296065", "dealer_name": "River Isle Ventures",
                                   "dimension": "DISPUTED", "value": "NGN 594,652.08 outstanding"}


def test_payment_exceptions_equal_the_payments_exceptions_endpoint():
    client = TestClient(app)
    items, offset, total = [], 0, None
    while total is None or offset < total:
        page = client.get("/payments", params={
            "mon_period": "202606", "payment_status": "DISPUTED,PARTIALLY_PAID,PENDING",
            "sort_by": "amount_unpaid", "sort_direction": "desc", "limit": 100, "offset": offset})
        assert page.status_code == 200
        body = page.json()
        total = body["pagination"]["total"]
        items.extend(body["items"])
        offset += 100

    exceptions = payment_exceptions_evidence("202606", None)["payment_exceptions"]
    assert exceptions["dealer_count"] == total == len(items)
    assert exceptions["outstanding_ngn"] == round(sum(item["amount_unpaid"] for item in items), 2)
    assert [(d["dealer_id"], d["payment_status"], d["commission_owed"], d["amount_paid"], d["amount_unpaid"])
            for d in exceptions["dealers"]] == [
        (i["dealer_id"], i["payment_status"], i["commission_owed"], i["amount_paid"], i["amount_unpaid"])
        for i in items[:MAX_LISTED_DEALERS]]


def test_payment_dealer_evidence_lists_only_that_dealer():
    evidence = payment_exceptions_evidence("202606", "296065")
    exceptions = evidence["payment_exceptions"]
    assert exceptions["dealer_scoped"] is True and exceptions["found"] is True
    assert exceptions["dealer_count"] == 1 and exceptions["outstanding_ngn"] == 594652.08
    assert exceptions["dealer_status"] == "DISPUTED"
    assert [d["dealer_id"] for d in exceptions["dealers"]] == ["296065"]
    assert exceptions["status_counts"] == [{"status": "DISPUTED", "dealer_count": 1}]
    assert evidence["truncated"] is False and evidence["total_rows"] == 1


def test_fully_paid_dealer_has_no_payment_exception():
    exceptions = payment_exceptions_evidence("202606", "19630")["payment_exceptions"]
    assert exceptions["found"] is True and exceptions["dealer_status"] == "FULLY_PAID"
    assert exceptions["dealer_count"] == 0 and exceptions["dealers"] == []
    assert exceptions["outstanding_ngn"] == 0 and exceptions["status_counts"] == []


def test_payment_unknown_dealer_is_not_found():
    exceptions = payment_exceptions_evidence("202606", "NO_SUCH_DEALER")["payment_exceptions"]
    assert exceptions == {"dealer_scoped": True, "found": False, "dealer_count": None,
                          "outstanding_ngn": None, "status_counts": [], "dealer_status": None,
                          "dealers": []}


def test_payment_unknown_month_empty_snapshot_and_unreadable_source_are_unavailable(monkeypatch):
    args = (PAYMENT_EXCEPTIONS_SOURCE, PAYMENT_EXCEPTIONS_TOOL, "payment_exceptions")
    assert payment_exceptions_evidence("209901", None) == unavailable(
        "209901", *args, "no data is recorded for this month.")
    real = payment_snapshot.load_payment_snapshot
    monkeypatch.setattr(payment_snapshot, "load_payment_snapshot",
                        lambda period: real(period).model_copy(update={"records": []}))
    assert payment_exceptions_evidence("202606", None) == unavailable(
        "202606", *args, "no payment records are recorded for this month.")
    monkeypatch.setattr(payment_snapshot, "load_payment_snapshot", fail)
    assert payment_exceptions_evidence("202606", None) == unavailable(
        "202606", *args, "the payment records could not be read.")
