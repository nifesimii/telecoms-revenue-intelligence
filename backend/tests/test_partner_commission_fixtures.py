"""Partner Sales links a fictional statement to existing explanations only when it
reconciles to the same account's recorded sample statement. This holds the fixture
to the public statement API, so sample data cannot drift away from it unnoticed.
"""
import json
import os
from pathlib import Path

os.environ["USE_SAMPLE_DATA"] = "true"

import pytest
from fastapi.testclient import TestClient

from backend import config
from backend.main import app

FIXTURES = json.loads(
    (Path(__file__).parents[2] / "frontend/src/components/sales/linkedCommissionStatements.json").read_text()
)


def _sum(statement: dict, stream: str, kind: str) -> int:
    return sum(item["amountMinor"] for item in statement["activity"]
               if item["stream"] == stream and item["kind"] == kind)


def _minor(ngn: float) -> int:
    return round(ngn * 100)


@pytest.fixture
def client(monkeypatch):
    monkeypatch.setattr(config, "USE_SAMPLE_DATA", True)
    monkeypatch.setattr(config, "PAYMENT_SOURCE", "simulated")
    with TestClient(app) as test_client:
        yield test_client


@pytest.mark.parametrize("statement", FIXTURES, ids=lambda s: f"{s['accountCode']}-{s['period']}")
def test_linked_fixture_reconciles_to_the_recorded_statement(client, statement):
    response = client.get(f"/dealers/{statement['accountCode']}/statement",
                          params={"mon_period": statement["period"]})
    assert response.status_code == 200
    recorded = response.json()

    assert _sum(statement, "activation", "earning") == _minor(recorded["commission"]["expected_ngn"])
    assert _sum(statement, "activation", "settlement") == _minor(recorded["payment"]["amount_paid_ngn"])
    assert recorded["payment"]["payment_found"] is True

    detail = client.get(f"/commissions/{statement['accountCode']}/detail",
                        params={"mon_period": statement["period"], "stream": "orsc"})
    if statement["subscriptionRecorded"]:
        assert detail.status_code == 200
        account = detail.json()["account"]
        assert account["subscription_commission_complete"] is True
        assert _sum(statement, "subscription", "earning") == _minor(account["subscription_commission_ngn"])
        assert _sum(statement, "subscription", "settlement") == _minor(account["subscription_settled_ngn"])
    else:
        assert detail.status_code == 404
        assert _sum(statement, "subscription", "earning") == 0

    revenue = recorded["orsc"]["total_subscription_amount_ngn"] if recorded["orsc"] else None
    assert statement["subscriptionRevenueMinor"] == (None if revenue is None else _minor(revenue))


def test_linked_months_of_one_account_carry_the_closing_balance_forward():
    may, june = [s for s in FIXTURES if s["accountCode"] == "296065"]
    earned = _sum(may, "activation", "earning") + _sum(may, "subscription", "earning")
    settled = _sum(may, "activation", "settlement") + _sum(may, "subscription", "settlement")
    assert june["openingMinor"] == may["openingMinor"] + earned - settled
