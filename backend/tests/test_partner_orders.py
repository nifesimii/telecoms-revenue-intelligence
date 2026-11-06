"""A partner's own drafts and orders through the public HTTP API."""
from __future__ import annotations

import uuid

import pytest
from fastapi.testclient import TestClient

from backend.main import app
from backend.sales.simulation import simulation

ROUTER = "FBB-5G-ROUTER"
CARD = "RCC-0100"


@pytest.fixture(autouse=True)
def clean_simulation():
    simulation.reset()
    yield
    simulation.reset()


def partner(demo_logins, username="partner-296065") -> TestClient:
    client = TestClient(app)
    client.cookies.clear()
    login = demo_logins[username]
    assert client.post("/auth/login", json={"username": login["username"], "password": login["password"]}).status_code == 200
    return client


@pytest.fixture
def river_isle(demo_logins) -> TestClient:
    return partner(demo_logins)


def lines_of(*lines):
    return [{"product_code": code, "quantity": units} for code, units in lines]


def saved_draft(client, lines=((ROUTER, "2"), (CARD, "100"))):
    created = client.post("/partner-sales/my/draft")
    assert created.status_code == 200
    saved = client.put("/partner-sales/my/draft", json={"token": created.json()["token"], "lines": lines_of(*lines)})
    assert saved.status_code == 200
    return saved.json()


def submit(client, a_draft, action_id=None):
    return client.post("/partner-sales/my/draft/submit", json={"token": a_draft["token"], "action_id": action_id or uuid.uuid4().hex})


def order(client, **kwargs):
    submitted = submit(client, saved_draft(client, **kwargs))
    assert submitted.status_code == 200
    return submitted.json()


def test_a_partner_submits_a_draft_as_an_order(river_isle):
    submitted = order(river_isle)
    # SIM-ORD-0001 is the order seeded for Finance to review.
    assert submitted["reference"] == "SIM-ORD-0002"
    assert submitted["status"] == "Submitted"
    assert submitted["account"] == {"code": "296065", "name": "River Isle Ventures"}
    assert river_isle.get("/partner-sales/my/draft").json() == {"draft": None}


def test_line_and_order_totals_reconcile_exactly(river_isle):
    submitted = order(river_isle)
    assert [(line["product_code"], line["quantity"], line["line_total_minor"]) for line in submitted["lines"]] == [
        (ROUTER, 2, 10_000_000), (CARD, 100, 1_000_000),
    ]
    assert submitted["total_minor"] == 11_000_000
    assert order(river_isle, lines=(("FBB-MIFI", "3"),))["total_minor"] == 9_999_999


@pytest.mark.parametrize("lines,message", [
    ((), "Add at least one product before submitting."),
    (((ROUTER, "0"),), "Every quantity must be a whole number from 1 to 1,000,000."),
    (((ROUTER, "1.5"),), "Every quantity must be a whole number from 1 to 1,000,000."),
    (((ROUTER, "1000001"),), "Every quantity must be a whole number from 1 to 1,000,000."),
])
def test_empty_drafts_and_invalid_quantities_are_not_submitted(river_isle, lines, message):
    a_draft = saved_draft(river_isle, lines=lines)
    refused = submit(river_isle, a_draft)
    assert refused.status_code == 422
    assert refused.json()["detail"] == message
    assert river_isle.get("/partner-sales/my/draft").json() == {"draft": a_draft}
    assert river_isle.get("/partner-sales/my/orders").json()["pagination"]["total"] == 0


def test_repeated_submission_has_one_effect(river_isle):
    a_draft = saved_draft(river_isle)
    first = submit(river_isle, a_draft, action_id="double-click")
    second = submit(river_isle, a_draft, action_id="double-click")
    assert second.status_code == 200
    assert second.json() == first.json()
    assert river_isle.get("/partner-sales/my/orders").json()["pagination"]["total"] == 1


def test_an_action_id_never_reaches_another_partners_order(river_isle, demo_logins):
    submit(river_isle, saved_draft(river_isle), action_id="shared-id")
    same_name = partner(demo_logins, "partner-353072")
    attempt = submit(same_name, saved_draft(same_name, lines=((CARD, "1"),)), action_id="shared-id")
    assert attempt.status_code == 200
    assert attempt.json()["account"]["code"] == "353072"
    assert attempt.json()["reference"] == "SIM-ORD-0003"


def test_a_partner_sees_their_orders_newest_first_with_status(river_isle):
    first = order(river_isle)["reference"]
    second = order(river_isle, lines=((CARD, "5"),))["reference"]
    page = river_isle.get("/partner-sales/my/orders").json()
    assert [(entry["reference"], entry["status"]) for entry in page["items"]] == [(second, "Submitted"), (first, "Submitted")]
    detail = river_isle.get(f"/partner-sales/my/orders/{first}")
    assert detail.status_code == 200
    assert detail.json()["total_minor"] == 11_000_000


def test_another_partners_order_responds_as_if_it_did_not_exist(river_isle, demo_logins):
    reference = order(river_isle)["reference"]
    same_name = partner(demo_logins, "partner-353072")
    theirs = same_name.get(f"/partner-sales/my/orders/{reference}")
    missing = same_name.get("/partner-sales/my/orders/SIM-ORD-9999")
    assert theirs.status_code == missing.status_code == 404
    assert theirs.json() == missing.json()
    assert same_name.get("/partner-sales/my/orders").json()["items"] == []
    assert same_name.get("/partner-sales/my/draft").json() == {"draft": None}


def test_a_submitted_order_cannot_be_edited_or_withdrawn(river_isle):
    a_draft = saved_draft(river_isle)
    submitted = submit(river_isle, a_draft).json()
    path = f"/partner-sales/my/orders/{submitted['reference']}"
    assert river_isle.put("/partner-sales/my/draft", json={"token": a_draft["token"], "lines": lines_of((CARD, "1"))}).status_code == 404
    assert river_isle.put(path, json={"lines": lines_of((CARD, "1"))}).status_code == 405
    assert river_isle.delete(path).status_code == 405
    assert river_isle.get(path).json() == submitted


def test_a_partner_deletes_their_draft(river_isle):
    a_draft = saved_draft(river_isle)
    assert river_isle.request("DELETE", "/partner-sales/my/draft", params={"token": a_draft["token"]}).status_code == 204
    assert river_isle.get("/partner-sales/my/draft").json() == {"draft": None}
    # A retry after a lost response finds it already gone.
    assert river_isle.request("DELETE", "/partner-sales/my/draft", params={"token": a_draft["token"]}).status_code == 204


def test_deleting_an_older_copy_of_a_draft_is_refused(river_isle):
    first_copy = saved_draft(river_isle)
    newer = river_isle.put("/partner-sales/my/draft", json={"token": first_copy["token"], "lines": lines_of((CARD, "5"))}).json()
    assert river_isle.request("DELETE", "/partner-sales/my/draft", params={"token": first_copy["token"]}).status_code == 409
    assert river_isle.get("/partner-sales/my/draft").json() == {"draft": newer}


def test_submitting_an_older_copy_of_a_draft_is_refused(river_isle):
    first_copy = saved_draft(river_isle)
    newer = river_isle.put("/partner-sales/my/draft", json={"token": first_copy["token"], "lines": lines_of((CARD, "5"))}).json()
    assert submit(river_isle, first_copy).status_code == 409
    assert [line["quantity"] for line in submit(river_isle, newer).json()["lines"]] == [5]


def test_supplying_an_account_reaches_only_the_session_account(river_isle, demo_logins):
    created = river_isle.post("/partner-sales/my/draft", params={"account_code": "353072"}, json={"account_code": "353072"})
    assert created.status_code == 200
    reference = submit(river_isle, saved_draft(river_isle)).json()["reference"]
    assert river_isle.get("/partner-sales/my/orders", params={"account_code": "353072"}).json()["items"][0]["account"]["code"] == "296065"
    same_name = partner(demo_logins, "partner-353072")
    assert same_name.get("/partner-sales/my/orders").json()["items"] == []
    assert same_name.get(f"/partner-sales/my/orders/{reference}", params={"account_code": "296065"}).status_code == 404


def internal_view():
    finance = TestClient(app)
    return [finance.get(path, params=params).json() for path, params in (
        ("/partner-sales/status", {}), ("/partner-sales/records", {"mon_period": "202605"}), ("/partner-sales/orders", {}),
    )]


def test_saving_a_draft_sends_nothing_to_finance(river_isle):
    before = internal_view()
    saved_draft(river_isle)
    assert internal_view() == before


def test_retrying_a_save_whose_response_was_lost_is_not_a_conflict(river_isle):
    a_draft = saved_draft(river_isle)
    change = {"token": a_draft["token"], "lines": lines_of((CARD, "5"))}
    first = river_isle.put("/partner-sales/my/draft", json=change)
    retried = river_isle.put("/partner-sales/my/draft", json=change)
    assert retried.status_code == 200
    assert retried.json() == first.json()
    assert river_isle.put("/partner-sales/my/draft", json={**change, "lines": lines_of((CARD, "6"))}).status_code == 409


def test_the_partner_reads_their_own_account_and_the_catalogue(river_isle):
    published = river_isle.get("/partner-sales/my/reference").json()
    assert published["account"] == {"code": "296065", "name": "River Isle Ventures"}
    assert published["max_quantity"] == 1_000_000
    assert [product["code"] for product in published["catalogue"]][:2] == [ROUTER, "FBB-4G-ROUTER"]
    assert "partners" not in published


def test_reset_discards_drafts_and_orders_and_restarts_order_references(river_isle):
    order(river_isle)
    saved_draft(river_isle)
    assert TestClient(app).post("/partner-sales/reset").json()["orders"] == 1
    assert river_isle.get("/partner-sales/my/draft").json() == {"draft": None}
    assert river_isle.get("/partner-sales/my/orders").json()["items"] == []
    assert order(river_isle)["reference"] == "SIM-ORD-0002"


def test_deleting_a_draft_that_was_submitted_elsewhere_is_refused(river_isle):
    a_draft = saved_draft(river_isle)
    assert submit(river_isle, a_draft).status_code == 200
    assert river_isle.request("DELETE", "/partner-sales/my/draft", params={"token": a_draft["token"]}).status_code == 404
    assert river_isle.get("/partner-sales/my/orders").json()["pagination"]["total"] == 1
