"""A partner reading their own invoices and collections through the public HTTP API,
while recording collections stays with Finance."""
from __future__ import annotations

import uuid

import pytest
from fastapi.testclient import TestClient

from backend.main import app
from backend.sales.simulation import simulation
from backend.tests.test_partner_orders import CARD, ROUTER, order, partner


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


def issued(finance, client, issue_date="2026-05-30", due_date="2026-06-29", **lines):
    """A partner's order as Finance issues it: the invoice, with its token."""
    reference = order(client, **lines)["reference"]
    waiting = next(entry for entry in finance.get("/partner-sales/orders").json()["items"] if entry["reference"] == reference)
    response = finance.post(f"/partner-sales/orders/{reference}/issue", json={"token": waiting["token"], "issue_date": issue_date, "due_date": due_date})
    assert response.status_code == 200
    return response.json()


def collect(client, invoice, amount_minor, date="2026-06-05", action_id=None):
    return client.post(f"/partner-sales/invoices/{invoice['reference']}/collections", json={
        "token": invoice["token"], "action_id": action_id or uuid.uuid4().hex, "date": date, "amount_minor": amount_minor,
    })


def own_invoices(client, **params):
    response = client.get("/partner-sales/my/invoices", params=params)
    assert response.status_code == 200
    return response.json()


def own_invoice(client, reference, **params):
    response = client.get(f"/partner-sales/my/invoices/{reference}", params=params)
    assert response.status_code == 200
    return response.json()


def test_a_partner_with_no_invoices_sees_none_of_the_examples(river_isle):
    assert own_invoices(river_isle) == {
        "items": [], "pagination": {"total": 0, "returned": 0, "offset": 0, "limit": 25, "has_more": False},
        "summary": {"count": 0, "outstanding_minor": 0, "as_of": ""},
    }


def test_an_issued_invoice_appears_in_the_partners_list(finance, river_isle):
    invoice = issued(finance, river_isle)
    listed = own_invoices(river_isle)
    [record] = listed["items"]
    assert (record["reference"], record["status"], record["date"]) == (invoice["reference"], "Unpaid", "2026-05-30")
    assert (record["amount_minor"], record["outstanding_minor"]) == (11_000_000, 11_000_000)
    assert record["partner"] == {"code": "296065", "name": "River Isle Ventures"}
    assert listed["summary"] == {"count": 1, "outstanding_minor": 11_000_000, "as_of": "2026-05-30"}


def test_the_partner_reads_the_invoice_lines_dates_and_order(finance, river_isle):
    invoice = issued(finance, river_isle)
    detail = own_invoice(river_isle, invoice["reference"])
    assert detail["invoice"]["order_reference"] == "SIM-ORD-0002"
    assert (detail["invoice"]["issue_date"], detail["invoice"]["due_date"]) == ("2026-05-30", "2026-06-29")
    assert [(line["product_code"], line["quantity"], line["line_total_minor"]) for line in detail["invoice"]["lines"]] == [
        (ROUTER, 2, 10_000_000), (CARD, 100, 1_000_000),
    ]
    assert detail["balance"] == {"status": "Unpaid", "outstanding_minor": 11_000_000, "collected_minor": 0, "as_of": "2026-05-30"}
    assert detail["collections"]["items"] == []


def test_the_partner_view_carries_nothing_that_could_change_the_invoice(finance, river_isle):
    invoice = issued(finance, river_isle)
    assert collect(finance, invoice, 1_000_000).status_code == 200
    detail = own_invoice(river_isle, invoice["reference"])
    assert "token" not in detail["invoice"]
    [collection] = detail["collections"]["items"]
    assert "action_id" not in collection


def test_finance_collections_move_the_partners_invoice_to_paid(finance, river_isle):
    invoice = issued(finance, river_isle)
    assert collect(finance, invoice, 4_000_000, date="2026-06-05").status_code == 200
    partly = own_invoice(river_isle, invoice["reference"])
    assert partly["balance"] == {"status": "Partially paid", "outstanding_minor": 7_000_000, "collected_minor": 4_000_000, "as_of": "2026-06-05"}
    assert own_invoices(river_isle)["summary"] == {"count": 1, "outstanding_minor": 7_000_000, "as_of": "2026-06-05"}

    assert collect(finance, invoice, 7_000_000, date="2026-06-20").status_code == 200
    paid = own_invoice(river_isle, invoice["reference"])
    assert paid["balance"]["status"] == "Paid"
    assert [(entry["date"], entry["amount_minor"], entry["outstanding_after_minor"]) for entry in paid["collections"]["items"]] == [
        ("2026-06-05", 4_000_000, 7_000_000), ("2026-06-20", 7_000_000, 0),
    ]
    assert own_invoices(river_isle)["items"][0]["status"] == "Paid"


def test_a_partner_cannot_record_a_collection(finance, river_isle):
    invoice = issued(finance, river_isle)
    assert collect(river_isle, invoice, 1_000_000).status_code == 403
    assert own_invoice(river_isle, invoice["reference"])["balance"]["outstanding_minor"] == 11_000_000
    assert simulation.status()["collections"] == 2


def test_another_partners_invoice_responds_as_if_it_did_not_exist(finance, river_isle, demo_logins):
    invoice = issued(finance, river_isle)
    namesake = partner(demo_logins, "partner-353072")
    assert own_invoices(namesake)["items"] == []
    theirs = namesake.get(f"/partner-sales/my/invoices/{invoice['reference']}")
    missing = namesake.get("/partner-sales/my/invoices/SIM-INV-9999")
    assert theirs.status_code == missing.status_code == 404
    assert theirs.json() == missing.json()
    # The examples belong to other accounts, so they are missing too.
    assert namesake.get("/partner-sales/my/invoices/SIM-INV-0001").status_code == 404


def test_supplying_an_account_reaches_only_the_session_account(finance, river_isle, demo_logins):
    issued(finance, partner(demo_logins, "partner-353072"))
    assert own_invoices(river_isle, account_code="353072")["items"] == []


def test_partner_lists_are_bounded_newest_first_and_total_the_whole_filter_set(finance, river_isle):
    first = issued(finance, river_isle, issue_date="2026-05-10", due_date="2026-06-09")
    second = issued(finance, river_isle, issue_date="2026-06-15", due_date="2026-07-15", lines=(("FBB-MIFI", "3"),))
    third = issued(finance, river_isle, issue_date="2026-05-10", due_date="2026-06-09", lines=((CARD, "10"),))
    assert collect(finance, first, 11_000_000, date="2026-05-20").status_code == 200

    page = own_invoices(river_isle, limit=1, offset=1)
    assert [record["reference"] for record in page["items"]] == [third["reference"]]
    assert page["pagination"] == {"total": 3, "returned": 1, "offset": 1, "limit": 1, "has_more": True}
    assert page["summary"] == {"count": 3, "outstanding_minor": 9_999_999 + 100_000, "as_of": "2026-06-15"}
    assert [record["reference"] for record in own_invoices(river_isle)["items"]] == [second["reference"], third["reference"], first["reference"]]

    unpaid = own_invoices(river_isle, status="Unpaid")
    assert [record["reference"] for record in unpaid["items"]] == [second["reference"], third["reference"]]
    assert unpaid["summary"] == {"count": 2, "outstanding_minor": 9_999_999 + 100_000, "as_of": "2026-06-15"}
    assert own_invoices(river_isle, status="Paid")["summary"] == {"count": 1, "outstanding_minor": 0, "as_of": "2026-05-20"}


@pytest.mark.parametrize("params", [{"limit": 0}, {"limit": 101}, {"offset": -1}])
def test_partner_pages_stay_within_the_bounds(river_isle, params):
    assert river_isle.get("/partner-sales/my/invoices", params=params).status_code == 422


def test_internal_users_have_no_partner_invoice_view(finance):
    assert finance.get("/partner-sales/my/invoices").status_code == 403
    assert finance.get("/partner-sales/my/invoices/SIM-INV-0001").status_code == 403


def test_a_reset_returns_the_partner_to_no_invoices(finance, river_isle):
    issued(finance, river_isle)
    assert finance.post("/partner-sales/reset").status_code == 200
    assert own_invoices(river_isle)["summary"]["count"] == 0
