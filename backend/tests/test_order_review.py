"""Finance reviewing partner orders through the public HTTP API: the queue, and
issuing or rejecting each order once."""
from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from backend.main import app
from backend.sales.simulation import simulation
from backend.tests.test_partner_orders import CARD, ROUTER, order, partner

# The order waiting at first login, for the same-named Sunset Crest account 295083.
SEEDED = "SIM-ORD-0001"


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


def queue(finance, **params):
    response = finance.get("/partner-sales/orders", params=params)
    assert response.status_code == 200
    return response.json()


def test_finance_sees_the_seeded_order_waiting_with_its_exact_account(finance):
    waiting = queue(finance)
    assert waiting["pagination"]["total"] == 1
    [seeded] = waiting["items"]
    assert (seeded["reference"], seeded["status"], seeded["account"]) == (SEEDED, "Submitted", {"code": "295083", "name": "Sunset Crest Communications"})
    assert seeded["total_minor"] == 10_999_999


def waiting(finance, reference):
    return next(entry for entry in queue(finance)["items"] if entry["reference"] == reference)


def issue(finance, reviewed, issue_date="2026-06-02", due_date="2026-07-02"):
    return finance.post(f"/partner-sales/orders/{reviewed['reference']}/issue", json={"token": reviewed["token"], "issue_date": issue_date, "due_date": due_date})


def test_issuing_an_order_makes_the_invoice_the_partner_sees(finance, river_isle):
    submitted = order(river_isle)
    issued = issue(finance, waiting(finance, submitted["reference"]))
    assert issued.status_code == 200
    invoice = issued.json()
    assert invoice["reference"].startswith("SIM-INV-")
    assert (invoice["buyer"], invoice["issue_date"], invoice["due_date"], invoice["total_minor"]) == ({"code": "296065", "name": "River Isle Ventures"}, "2026-06-02", "2026-07-02", 11_000_000)
    assert [(line["product_code"], line["quantity"], line["line_total_minor"]) for line in invoice["lines"]] == [(ROUTER, 2, 10_000_000), (CARD, 100, 1_000_000)]
    assert invoice["order_reference"] == submitted["reference"]

    seen = river_isle.get(f"/partner-sales/my/orders/{submitted['reference']}").json()
    assert seen["status"] == "Issued"
    assert seen["invoice"] == {"reference": invoice["reference"], "issue_date": "2026-06-02", "due_date": "2026-07-02"}
    assert [entry["reference"] for entry in queue(finance)["items"]] == [SEEDED]
    detail = finance.get(f"/partner-sales/invoices/{invoice['reference']}").json()
    assert (detail["balance"]["status"], detail["balance"]["outstanding_minor"]) == ("Unpaid", 11_000_000)


def reject(finance, reviewed, reason="Recharge cards are out of stock this month."):
    return finance.post(f"/partner-sales/orders/{reviewed['reference']}/reject", json={"token": reviewed["token"], "reason": reason})


def test_rejecting_an_order_gives_the_partner_the_reason(finance, river_isle):
    submitted = order(river_isle)
    rejected = reject(finance, waiting(finance, submitted["reference"]), reason="  Recharge cards are out of stock this month.  ")
    assert rejected.status_code == 200
    seen = river_isle.get(f"/partner-sales/my/orders/{submitted['reference']}").json()
    assert (seen["status"], seen["rejection_reason"], seen["invoice"]) == ("Rejected", "Recharge cards are out of stock this month.", None)
    assert rejected.json() == {**seen, "token": rejected.json()["token"]}
    assert [entry["reference"] for entry in queue(finance)["items"]] == [SEEDED]


@pytest.mark.parametrize("reason", ["", "   "])
def test_a_rejection_needs_a_reason(finance, reason):
    refused = reject(finance, waiting(finance, SEEDED), reason=reason)
    assert refused.status_code == 422
    assert refused.json()["detail"] == "Enter a reason for the partner."
    assert waiting(finance, SEEDED)["status"] == "Submitted"


@pytest.mark.parametrize("issue_date,due_date,message", [
    ("", "2026-07-02", "Enter a valid issue date."),
    ("2026-02-30", "2026-07-02", "Enter a valid issue date."),
    ("02/06/2026", "2026-07-02", "Enter a valid issue date."),
    ("2026-06-02", "", "Enter a due date on or after the issue date."),
    ("2026-06-02", "2026-06-01", "Enter a due date on or after the issue date."),
    ("2026-06-02", "2026-13-01", "Enter a due date on or after the issue date."),
])
def test_invalid_issue_and_due_dates_are_rejected(finance, issue_date, due_date, message):
    before = finance.get("/partner-sales/status").json()
    refused = issue(finance, waiting(finance, SEEDED), issue_date=issue_date, due_date=due_date)
    assert refused.status_code == 422
    assert refused.json()["detail"] == message
    assert finance.get("/partner-sales/status").json() == before
    assert waiting(finance, SEEDED)["status"] == "Submitted"


@pytest.mark.parametrize("first,second", [("issue", "issue"), ("issue", "reject"), ("reject", "issue"), ("reject", "reject")])
def test_an_order_is_decided_only_once(finance, river_isle, first, second):
    decide = {"issue": issue, "reject": reject}
    reviewed = waiting(finance, order(river_isle)["reference"])
    assert decide[first](finance, reviewed).status_code == 200
    seen = river_isle.get(f"/partner-sales/my/orders/{reviewed['reference']}").json()
    status = finance.get("/partner-sales/status").json()
    again = decide[second](finance, reviewed)
    assert again.status_code == 409
    assert again.json()["detail"] == "This changed elsewhere or the simulation was reset."
    assert river_isle.get(f"/partner-sales/my/orders/{reviewed['reference']}").json() == seen
    assert finance.get("/partner-sales/status").json() == status


def test_an_order_from_before_a_reset_cannot_decide_its_namesake(finance):
    before_reset = waiting(finance, SEEDED)
    finance.post("/partner-sales/reset")
    assert issue(finance, before_reset).status_code == 409
    assert reject(finance, before_reset).status_code == 409
    assert waiting(finance, SEEDED)["status"] == "Submitted"


def test_deciding_a_missing_order_is_not_found(finance):
    assert issue(finance, {"reference": "SIM-ORD-9999", "token": "x"}).status_code == 404


def test_the_queue_keeps_same_named_partners_separate(finance, river_isle, demo_logins):
    order(river_isle)
    same_name = partner(demo_logins, "partner-353072")
    order(same_name, lines=((CARD, "1"),))
    assert [(entry["reference"], entry["account"]["code"], entry["total_minor"]) for entry in queue(finance)["items"]] == [
        (SEEDED, "295083", 10_999_999), ("SIM-ORD-0002", "296065", 11_000_000), ("SIM-ORD-0003", "353072", 10_000),
    ]
    page = queue(finance, limit=1, offset=1)
    assert ([entry["reference"] for entry in page["items"]], page["pagination"]["total"]) == (["SIM-ORD-0002"], 3)


def test_partners_cannot_issue_or_reject_orders(finance, river_isle):
    reviewed = waiting(finance, SEEDED)
    assert issue(river_isle, reviewed).status_code == 403
    assert reject(river_isle, reviewed).status_code == 403
    assert river_isle.get("/partner-sales/orders").status_code == 403
    assert waiting(finance, SEEDED)["status"] == "Submitted"
