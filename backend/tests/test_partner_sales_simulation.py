"""The Partner Sales simulation through its public HTTP API."""
from __future__ import annotations

import uuid

import pytest
from fastapi.testclient import TestClient

from backend.main import app
from backend.sales.simulation import SalesSimulation, simulation

client = TestClient(app)
ROUTER = "FBB-5G-ROUTER"
CARD = "RCC-0100"
PERIOD = "202605"


@pytest.fixture(autouse=True)
def clean_simulation():
    simulation.reset()
    yield
    simulation.reset()


def lines_of(lines):
    return [{"product_code": code, "quantity": units} for code, units in lines]


def submitted_order(partner="296065", lines=((ROUTER, "2"), (CARD, "100"))):
    """A partner's submitted order, as Finance's queue holds it. Every invoice begins as one.
    The partner's side goes through the simulation directly: its routes need a partner login."""
    draft = simulation.create_order_draft(partner)
    draft = simulation.update_order_draft(partner, draft["token"], lines_of(lines))
    reference = simulation.submit_order(partner, uuid.uuid4().hex, draft["token"])["reference"]
    queue = client.get("/partner-sales/orders", params={"limit": 100}).json()["items"]
    return next(order for order in queue if order["reference"] == reference)


def issue(order, issue_date="2026-05-20", due_date="2026-06-19"):
    return client.post(f"/partner-sales/orders/{order['reference']}/issue", json={"token": order["token"], "issue_date": issue_date, "due_date": due_date})


def invoice(partner="296065", lines=((ROUTER, "2"), (CARD, "100")), **dates):
    issued = issue(submitted_order(partner, lines), **dates)
    assert issued.status_code == 200
    return issued.json()["reference"]


def detail(reference):
    return client.get(f"/partner-sales/invoices/{reference}").json()


def collect(reference, amount_minor, date="2026-05-25", action_id=None, token=None):
    return client.post(f"/partner-sales/invoices/{reference}/collections", json={
        "token": token or detail(reference)["invoice"]["token"],
        "action_id": action_id or f"action-{reference}-{amount_minor}-{date}", "date": date, "amount_minor": amount_minor,
    })


def records(**params):
    return client.get("/partner-sales/records", params={"mon_period": PERIOD, **params}).json()


def references(page):
    return [record["reference"] for record in page["items"]]


def test_starts_with_one_example_invoice_of_each_status():
    page = records()
    assert {record["reference"]: record["status"] for record in page["items"]} == {
        "SIM-INV-0001": "Paid", "SIM-INV-0002": "Partially paid", "SIM-INV-0003": "Unpaid",
    }
    assert client.get("/partner-sales/status").json() == {"invoices": 3, "collections": 2, "orders": 1, "next_invoice_reference": "SIM-INV-0004"}


def test_records_are_shared_between_sessions():
    reference = invoice()
    assert reference in references(TestClient(app).get("/partner-sales/records", params={"mon_period": PERIOD}).json())


def test_acceptance_example_reconciles_exactly():
    reference = invoice()
    assert detail(reference)["invoice"]["total_minor"] == 11_000_000
    assert detail(reference)["balance"]["status"] == "Unpaid"
    assert collect(reference, 4_000_000).status_code == 200
    assert detail(reference)["balance"] == {"status": "Partially paid", "outstanding_minor": 7_000_000, "collected_minor": 4_000_000, "as_of": "2026-05-25"}
    assert collect(reference, 7_000_000).status_code == 200
    assert detail(reference)["balance"]["status"] == "Paid"
    assert detail(reference)["balance"]["outstanding_minor"] == 0


def test_kobo_stays_exact():
    reference = invoice(lines=(("FBB-MIFI", "3"),))
    assert detail(reference)["invoice"]["total_minor"] == 9_999_999


def test_a_new_process_starts_from_the_seed():
    invoice()
    assert SalesSimulation().status() == {"invoices": 3, "collections": 2, "orders": 1, "next_invoice_reference": "SIM-INV-0004"}


def test_finance_has_no_way_to_draft_or_issue_an_invoice_directly():
    assert [path for path in app.openapi()["paths"] if path.startswith("/partner-sales/drafts")] == []
    assert client.post("/partner-sales/drafts", json={"account_code": "296065", "mon_period": PERIOD}).status_code in {404, 405}


def test_issuing_an_order_twice_creates_one_invoice():
    order = submitted_order()
    assert issue(order).status_code == 200
    assert issue(order).status_code == 409
    assert client.get("/partner-sales/status").json()["invoices"] == 4


def test_repeated_collection_action_has_one_effect():
    reference = invoice()
    first = collect(reference, 100, action_id="same").json()
    second = collect(reference, 100, action_id="same").json()
    assert first == second
    assert detail(reference)["balance"]["collected_minor"] == 100


@pytest.mark.parametrize("amount,date", [
    (0, "2026-05-25"), (-1, "2026-05-25"), (11_000_001, "2026-05-25"), (100, "2026-05-19"), (100, "12026-05-25"), (100, "not-a-date"),
])
def test_invalid_collections_leave_the_balance_unchanged(amount, date):
    reference = invoice()
    assert collect(reference, amount, date=date).status_code == 422
    assert detail(reference)["balance"]["outstanding_minor"] == 11_000_000


def test_paid_invoices_and_orders_cannot_be_collected_against():
    paid = invoice()
    assert collect(paid, 11_000_000).status_code == 200
    assert collect(paid, 1).status_code == 422
    assert collect(submitted_order(partner="353072")["reference"], 1, token="any").status_code == 404


def test_collections_stay_on_their_exact_account():
    first = invoice(partner="296065")
    second = invoice(partner="353072")
    collect(first, 500)
    assert client.get("/partner-sales/partners/353072/obligations").json()["outstanding_minor"] == 11_000_000
    assert client.get("/partner-sales/partners/296065/obligations").json()["outstanding_minor"] == 10_999_500
    assert detail(second)["balance"]["collected_minor"] == 0


def test_backdated_collection_keeps_a_chronological_history():
    reference = invoice()
    collect(reference, 100, date="2026-05-28")
    collect(reference, 200, date="2026-05-22")
    history = detail(reference)["collections"]["items"]
    assert [entry["outstanding_after_minor"] for entry in history] == [10_999_800, 10_999_700]


def test_pages_are_bounded_and_totals_describe_the_whole_set():
    for partner in ("296065", "353072", "295083"):
        invoice(partner=partner)
    first = records(limit=2)
    second = records(limit=2, offset=2)
    assert first["pagination"] == {"total": 6, "returned": 2, "offset": 0, "limit": 2, "has_more": True}
    assert first["summary"] == second["summary"]
    assert set(references(first)).isdisjoint(references(second))
    assert client.get("/partner-sales/records", params={"mon_period": PERIOD, "limit": 101}).status_code == 422


def test_records_have_a_fixed_order():
    assert references(records()) == ["SIM-INV-0003", "SIM-INV-0002", "SIM-INV-0001"]
    assert references(records()) == references(records())


def test_a_page_beyond_the_set_falls_back_to_its_last_page():
    page = records(limit=2, offset=50)
    assert page["pagination"]["offset"] == 2
    assert references(page) == ["SIM-INV-0001"]


def test_filters_apply_to_rows_and_summary():
    page = records(status="Unpaid")
    assert references(page) == ["SIM-INV-0003"]
    assert page["summary"]["count"] == 1
    assert references(records(search="ember hill")) == ["SIM-INV-0002"]
    assert client.get("/partner-sales/records", params={"mon_period": "202606"}).json()["items"] == []


def test_invoices_keep_their_issue_month():
    reference = invoice(issue_date="2026-06-10", due_date="2026-07-10")
    assert reference not in references(records())
    assert reference in references(records(mon_period="202606"))


def test_unknown_records_are_not_found():
    assert client.get("/partner-sales/invoices/SIM-INV-9999").status_code == 404
    assert client.get("/partner-sales/partners/000000/obligations").status_code == 404
    assert client.post("/partner-sales/invoices/SIM-INV-9999/collections", json={"token": "any", "action_id": "any", "date": "2026-05-25", "amount_minor": 1}).status_code == 404


def test_reset_restores_the_seed_and_restarts_references():
    invoice()
    collect("SIM-INV-0003", 100)
    assert client.post("/partner-sales/reset").json()["next_invoice_reference"] == "SIM-INV-0004"
    assert references(records()) == ["SIM-INV-0003", "SIM-INV-0002", "SIM-INV-0001"]
    assert detail("SIM-INV-0003")["balance"]["status"] == "Unpaid"


def test_sales_actions_leave_existing_evidence_unchanged():
    evidence = ["/payments?mon_period=202605", "/commissions?mon_period=202605", "/inventory/comparison-page?mon_period=202605", "/financial-health?mon_period=202605", "/dealers/296065/statement?mon_period=202605"]
    def read_evidence():
        return [{key: value for key, value in client.get(path).json().items() if key != "generated_at"} for path in evidence]

    before = read_evidence()
    reference = invoice()
    collect(reference, 100)
    [seeded] = client.get("/partner-sales/orders").json()["items"]
    assert client.post(f"/partner-sales/orders/{seeded['reference']}/issue", json={"token": seeded["token"], "issue_date": "2026-05-20", "due_date": "2026-06-19"}).status_code == 200
    assert read_evidence() == before
    assert client.post("/partner-sales/reset").status_code == 200
    assert read_evidence() == before


def status():
    return client.get("/partner-sales/status").json()


def test_a_collection_from_before_a_reset_cannot_reach_a_new_invoice_with_the_same_reference():
    reference = invoice()
    stale_token = detail(reference)["invoice"]["token"]
    assert client.post("/partner-sales/reset").status_code == 200
    assert invoice(partner="74050") == reference
    assert collect(reference, 100, token=stale_token).status_code == 409
    assert detail(reference)["balance"]["collected_minor"] == 0


def test_tokens_are_never_reused_across_a_reset_or_a_restart():
    before = detail("SIM-INV-0001")["invoice"]["token"]
    assert client.post("/partner-sales/reset").status_code == 200
    assert detail("SIM-INV-0001")["invoice"]["token"] != before
    restarted = SalesSimulation().invoice_detail("SIM-INV-0001", 25, 0)["invoice"]["token"]
    assert restarted not in {before, detail("SIM-INV-0001")["invoice"]["token"]}


def test_retrying_a_collection_still_returns_the_earlier_result():
    issued = issue(submitted_order()).json()
    token = issued["token"]
    first = collect(issued["reference"], 100, action_id="retry", token=token).json()
    assert collect(issued["reference"], 100, action_id="retry", token=token).json() == first
    assert detail(issued["reference"])["balance"]["collected_minor"] == 100


def test_changing_an_invoice_requires_its_token():
    collection = {"action_id": "no-token", "date": "2026-05-25", "amount_minor": 100}
    assert client.post("/partner-sales/invoices/SIM-INV-0003/collections", json=collection).status_code == 422


@pytest.mark.parametrize("amount", [True, "100", 100.0, 100.5])
def test_a_collection_amount_must_be_whole_kobo(amount):
    reference = invoice()
    assert collect(reference, amount).status_code == 422
    assert detail(reference)["balance"]["collected_minor"] == 0


@pytest.mark.parametrize("path", ["/partner-sales/invoices/SIM-INV-0001", "/partner-sales/partners/296065/obligations"])
def test_every_page_is_limited_to_100_rows(path):
    assert client.get(path, params={"limit": 100}).status_code == 200
    assert client.get(path, params={"limit": 101}).status_code == 422


def test_the_reference_data_publishes_the_quantity_limit_and_status_names():
    published = client.get("/partner-sales/reference").json()
    assert published["max_quantity"] == 1_000_000
    assert published["statuses"] == ["Unpaid", "Partially paid", "Paid"]


def test_lists_and_obligations_hold_invoices_only():
    simulation.create_order_draft("296065")
    reference = invoice(partner="74050")
    page = records()
    assert page["summary"] == {"count": 4, "outstanding_minor": 29_000_000, "as_of": "2026-05-20"}
    assert all("is_draft" not in record for record in page["items"])
    obligations = client.get("/partner-sales/partners/296065/obligations").json()
    assert "drafts" not in obligations
    assert (obligations["outstanding_minor"], obligations["as_of"]) == (0, "")
    assert reference in references(client.get("/partner-sales/partners/74050/obligations").json()["invoices"])


def test_simulation_routes_are_internal_only(demo_logins):
    partner = TestClient(app)
    partner.cookies.clear()
    login = demo_logins["partner-296065"]
    assert partner.post("/auth/login", json={"username": login["username"], "password": login["password"]}).status_code == 200
    assert partner.get("/partner-sales/records", params={"mon_period": PERIOD}).status_code == 403
    assert partner.post("/partner-sales/reset").status_code == 403
