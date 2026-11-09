"""Fictional Partner Commission Account statements, served by the server through the
public HTTP API: Finance reads any account's, and a partner only their own."""
from __future__ import annotations

import uuid
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from backend.main import app
from backend.sales.simulation import simulation
from backend.tests.test_partner_orders import order, partner

FRONTEND_SOURCE = Path(__file__).parents[2] / "frontend/src"


@pytest.fixture(autouse=True)
def clean_simulation():
    simulation.reset()
    yield
    simulation.reset()


@pytest.fixture
def finance() -> TestClient:
    return TestClient(app)


@pytest.fixture
def river_isle(demo_logins) -> TestClient:
    return partner(demo_logins)


def statement_of(client, path, period="202605"):
    response = client.get(path, params={"mon_period": period})
    assert response.status_code == 200
    return response.json()["statement"]


def finance_statement(finance, account_code, period="202605"):
    return statement_of(finance, f"/partner-sales/partners/{account_code}/statement", period)


def own_statement(client, period="202605"):
    return statement_of(client, "/partner-sales/my/statement", period)


def test_finance_reads_a_fictional_statement_for_an_exact_account_and_month(finance):
    statement = finance_statement(finance, "74050")
    assert (statement["account_code"], statement["period"], statement["linked"]) == ("74050", "202605", False)
    assert (statement["opening_minor"], statement["opening_reference"]) == (2_000_000, "SIM-OPEN-74050-202605")
    assert (statement["subscription_recorded"], statement["subscription_revenue_minor"]) == (True, 24_000_000)
    assert statement["activity"][0] == {"date": "2026-05-12", "reference": "SIM-COM-74050-0501", "stream": "activation", "kind": "earning", "amount_minor": 900_000}
    assert {item["stream"] for item in statement["activity"]} == {"activation", "subscription"}


def test_a_statement_that_reconciles_to_recorded_evidence_is_marked_linked(finance):
    assert finance_statement(finance, "296065")["linked"] is True
    assert finance_statement(finance, "296065", "202606")["linked"] is True


def test_a_month_without_a_statement_is_missing_not_zero(finance):
    assert finance_statement(finance, "353072", "202606") is None


def test_missing_evidence_stays_distinct_from_a_recorded_zero(finance):
    zero_settlement = finance_statement(finance, "98052")
    assert [item["amount_minor"] for item in zero_settlement["activity"] if item["kind"] == "settlement"] == [0]
    assert (zero_settlement["subscription_recorded"], zero_settlement["subscription_revenue_minor"]) == (False, None)
    no_settlement = finance_statement(finance, "205044")
    assert [item for item in no_settlement["activity"] if item["kind"] == "settlement"] == []


def test_a_long_statement_spans_more_than_the_largest_page(finance):
    activity = finance_statement(finance, "295083")["activity"]
    assert len(activity) == 120
    assert sum(item["amount_minor"] for item in activity if item["kind"] == "earning") == 11_000_000
    assert sum(item["amount_minor"] for item in activity if item["kind"] == "settlement") == 500_000


def test_an_unknown_account_is_not_found_and_a_malformed_month_is_refused(finance):
    assert finance.get("/partner-sales/partners/99999/statement", params={"mon_period": "202605"}).status_code == 404
    assert finance.get("/partner-sales/partners/74050/statement", params={"mon_period": "2026-05"}).status_code == 422
    assert finance.get("/partner-sales/partners/74050/statement").status_code == 422


def test_a_partner_reads_their_own_statement_without_the_link_to_recorded_evidence(finance, river_isle):
    own = own_statement(river_isle)
    assert "linked" not in own
    assert own == {key: value for key, value in finance_statement(finance, "296065").items() if key != "linked"}


def test_a_partner_learns_which_months_have_a_statement(river_isle, demo_logins):
    assert river_isle.get("/partner-sales/my/reference").json()["statement_periods"] == ["202606", "202605"]
    namesake = partner(demo_logins, "partner-353072")
    assert namesake.get("/partner-sales/my/reference").json()["statement_periods"] == ["202605"]
    assert own_statement(namesake, "202606") is None


def test_a_partner_cannot_fetch_another_accounts_statement(river_isle, demo_logins):
    assert river_isle.get("/partner-sales/partners/353072/statement", params={"mon_period": "202605"}).status_code == 403
    own = river_isle.get("/partner-sales/my/statement", params={"mon_period": "202605", "account_code": "353072"}).json()["statement"]
    assert own["account_code"] == "296065"
    namesake = partner(demo_logins, "partner-353072")
    assert own_statement(namesake)["account_code"] == "353072"
    assert own_statement(namesake) != own


def test_internal_users_have_no_partner_statement_view(finance):
    assert finance.get("/partner-sales/my/statement", params={"mon_period": "202605"}).status_code == 403


def test_orders_invoices_collections_and_reset_leave_statements_unchanged(finance, river_isle):
    def read():
        return [finance_statement(finance, "296065"), finance_statement(finance, "74050"), own_statement(river_isle)]

    before = read()
    reference = order(river_isle)["reference"]
    waiting = next(entry for entry in finance.get("/partner-sales/orders").json()["items"] if entry["reference"] == reference)
    invoice = finance.post(f"/partner-sales/orders/{reference}/issue", json={"token": waiting["token"], "issue_date": "2026-05-30", "due_date": "2026-06-29"}).json()
    collected = finance.post(f"/partner-sales/invoices/{invoice['reference']}/collections", json={
        "token": invoice["token"], "action_id": uuid.uuid4().hex, "date": "2026-06-01", "amount_minor": 11_000_000,
    })
    assert collected.status_code == 200
    assert read() == before
    assert finance.post("/partner-sales/reset").status_code == 200
    assert read() == before


def test_the_delivered_frontend_carries_no_statements():
    sources = [path for path in FRONTEND_SOURCE.rglob("*") if path.suffix in {".js", ".jsx", ".json"}]
    assert sources
    markers = ("SIM-OPEN-", "SIM-COM-", "SIM-SET-")
    assert [str(path) for path in sources if any(marker in path.read_text() for marker in markers)] == []
