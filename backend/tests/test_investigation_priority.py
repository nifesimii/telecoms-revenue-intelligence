"""Atlas investigation-priority evidence comes from the Overview computation.

Sample data, no mocks for the oracle: the values below must match the
Investigation Queue the Overview tab shows for the same month.
"""
import os

os.environ["USE_SAMPLE_DATA"] = "true"

import pytest
from fastapi.testclient import TestClient

from backend import config
from backend.assurance import overview
from backend.assurance.overview import (
    INVESTIGATION_QUEUE_SOURCE,
    INVESTIGATION_QUEUE_TOOL,
    investigation_priority_evidence,
)


@pytest.fixture(autouse=True)
def sample_mode(monkeypatch):
    monkeypatch.setattr(config, "USE_SAMPLE_DATA", True)
    monkeypatch.setattr(config, "PAYMENT_SOURCE", "simulated")


def test_high_payment_dealer_ranks_first_with_every_module_finding():
    evidence = investigation_priority_evidence("202606", "296065")

    assert evidence["period"] == "202606"
    assert evidence["status"] == "available"
    assert evidence["source"] == INVESTIGATION_QUEUE_SOURCE == "Investigation queue"
    assert evidence["tool"] == INVESTIGATION_QUEUE_TOOL == "investigation_queue"
    assert evidence["total"] is None and evidence["truncated"] is False
    priority = evidence["priority"]
    assert priority["in_queue"] is True
    assert priority["rank"] == 1
    assert priority["queue_size"] == 922
    assert priority["severity"] == "HIGH"
    assert priority["payment_status"] == "DISPUTED"
    assert priority["amount_outstanding"] == 594652.08
    assert priority["lead_module"] == "payment"
    assert priority["lead_type"] == "COMMISSION_DISPUTE"

    findings = priority["findings"]
    assert [(f["module"], f["severity"], f["type"]) for f in findings] == [
        # Lead first, then rank_dealers' order: severity, then finding type.
        ("payment", "HIGH", "COMMISSION_DISPUTE"),
        ("inventory", "MEDIUM", "INVENTORY_MISMATCH"),
        ("commission", "MEDIUM", "ZERO_COMMISSION_ACTIVATION"),
        ("activation", "LOW", "UNUSUAL_VOLUME"),
    ]
    assert findings[0]["description"] == "NGN 594,652.08 outstanding · disputed"
    assert "1299801" in findings[1]["description"]
    assert "110.0%" in findings[1]["description"]
    assert "50 zero-commission activations of 495" in findings[2]["description"]
    assert priority["finding_count"] >= len(findings)

    assert priority["commission"]["severity"] == "MEDIUM"
    assert priority["commission"]["type"] == "ZERO_COMMISSION_ACTIVATION"
    assert "50 zero-commission activations of 495" in priority["commission"]["description"]
    assert priority["commission_module_status"] == "FLAG"
    assert priority["unchecked_modules"] == []

    rows = evidence["rows"]
    assert evidence["total_rows"] == len(rows) == 4
    assert rows[0] == {
        "dealer_id": "296065",
        "dealer_name": rows[0]["dealer_name"],
        "dimension": "Payment · COMMISSION_DISPUTE",
        "value": "HIGH: NGN 594,652.08 outstanding · disputed",
    }
    assert [r["dimension"].split(" · ")[0] for r in rows] == [
        "Payment", "Inventory", "Commission", "Activation"]


def test_dealer_outside_the_queue_is_available_but_not_in_queue():
    evidence = investigation_priority_evidence("202606", "NO_SUCH_DEALER")
    assert evidence["status"] == "available"
    assert evidence["rows"] == [] and evidence["total_rows"] == 0
    priority = evidence["priority"]
    assert priority["in_queue"] is False
    assert priority["severity"] is None and priority["rank"] is None
    assert priority["queue_size"] == 922
    assert priority["findings"] == []
    assert priority["unchecked_modules"] == []


def test_unknown_period_is_unavailable_not_low():
    evidence = investigation_priority_evidence("209901", "296065")
    assert evidence["status"] == "unavailable"
    assert evidence["priority"] is None
    assert evidence["rows"] == []
    assert evidence["note"] == "no data is recorded for this month."
    assert "low" not in evidence["note"].lower()


def test_missing_dealer_asks_for_an_account():
    evidence = investigation_priority_evidence("202606", None)
    assert evidence["status"] == "unavailable"
    assert evidence["priority"] is None
    assert evidence["note"] == (
        "Investigation priority needs a dealer account; select or name one.")


def test_overview_failure_is_unavailable(monkeypatch):
    async def broken(*_args, **_kwargs):
        raise RuntimeError("boom")
    monkeypatch.setattr(overview, "collect_overview", broken)
    evidence = investigation_priority_evidence("202606", "296065")
    assert evidence["status"] == "unavailable"
    assert evidence["priority"] is None
    assert evidence["note"] == "the overview could not be computed."


def test_no_checked_module_is_unavailable_not_outside_queue(monkeypatch):
    async def nothing_checked(period, *_args, **_kwargs):
        modules = [{"module": name, "status": "UNAVAILABLE"} for name in ("payment", "commission")]
        return {"period": period, "modules": modules}, [], []
    monkeypatch.setattr(overview, "collect_overview", nothing_checked)
    evidence = investigation_priority_evidence("202606", "296065")
    assert evidence["status"] == "unavailable"
    assert evidence["priority"] is None
    assert evidence["note"] == "no assurance module could be checked."


def test_payment_outage_reports_unchecked_module(monkeypatch):
    from backend.db import apdp
    monkeypatch.setattr(config, "PAYMENT_SOURCE", "apdp")

    def offline(_period):
        raise ConnectionError("offline")
    monkeypatch.setattr(apdp, "get_partner_settlements", offline)
    priority = investigation_priority_evidence("202606", "296065")["priority"]
    assert "payment" in priority["unchecked_modules"]
    assert priority["lead_module"] != "payment"
    assert priority["payment_status"] is None


def test_overview_endpoint_shares_the_same_computation():
    from backend.main import app
    data = TestClient(app).get("/assurance/overview?mon_period=202606&limit=1").json()
    first = data["items"][0]
    assert first["dealer_id"] == "296065"
    assert data["affected_dealers"] == 922
    evidence = investigation_priority_evidence("202606", "296065")
    assert first["severity"] == evidence["priority"]["severity"]
    assert first["amount_outstanding"] == evidence["priority"]["amount_outstanding"]


def test_lower_layers_do_not_import_the_api_layer():
    import pathlib
    root = pathlib.Path(__file__).resolve().parents[1]
    for layer in ("db", "assurance"):
        for path in (root / layer).glob("*.py"):
            assert "backend.api" not in path.read_text(), path
    assert "backend.assurance" not in (root / "db" / "payment_snapshot.py").read_text()
