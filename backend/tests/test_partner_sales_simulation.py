"""The Partner Sales simulation through its public HTTP API."""
from __future__ import annotations

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


def draft(partner="296065", period=PERIOD, lines=((ROUTER, "2"), (CARD, "100")), issue_date="2026-05-20", due_date=""):
    created = client.post("/partner-sales/drafts", json={"partner_code": partner, "period": period})
    assert created.status_code == 200
    reference = created.json()["reference"]
    change = {"issue_date": issue_date, "due_date": due_date, "lines": [{"product_code": code, "quantity": units} for code, units in lines]}
    assert client.put(f"/partner-sales/drafts/{reference}", json=change).status_code == 200
    return reference


def invoice(**kwargs):
    reference = draft(**kwargs)
    assert client.post(f"/partner-sales/drafts/{reference}/issue").status_code == 200
    return reference


def collect(reference, amount_minor, date="2026-05-25", action_id=None):
    return client.post(f"/partner-sales/invoices/{reference}/collections", json={
        "action_id": action_id or f"action-{reference}-{amount_minor}-{date}", "date": date, "amount_minor": amount_minor,
    })


def detail(reference):
    return client.get(f"/partner-sales/invoices/{reference}").json()


def records(**params):
    return client.get("/partner-sales/records", params={"mon_period": PERIOD, **params}).json()


def references(page):
    return [record["reference"] for record in page["items"]]


def test_starts_with_one_example_invoice_of_each_status():
    page = records()
    assert {record["reference"]: record["status"] for record in page["items"]} == {
        "SIM-INV-0001": "Paid", "SIM-INV-0002": "Partially paid", "SIM-INV-0003": "Unpaid",
    }
    assert client.get("/partner-sales/status").json() == {
        "drafts": 0, "invoices": 3, "collections": 2, "next_draft_reference": "SIM-INV-0004",
    }


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


@pytest.mark.parametrize("change", [
    {"lines": ()},
    {"lines": ((ROUTER, "0"),)},
    {"lines": ((ROUTER, "1.5"),)},
    {"lines": ((ROUTER, "1000001"),)},
    {"issue_date": "2026-06-01"},
    {"issue_date": "12026-05-01"},
    {"issue_date": ""},
    {"due_date": "2026-05-01"},
])
def test_invalid_drafts_stay_drafts(change):
    reference = draft(**change)
    assert client.post(f"/partner-sales/drafts/{reference}/issue").status_code == 422
    assert client.get("/partner-sales/status").json()["invoices"] == 3
    assert reference in references(records())


def test_invalid_quantities_remain_as_typed_on_the_draft():
    draft(lines=((ROUTER, "abc"),))
    saved = client.get("/partner-sales/drafts", params={"partner_code": "296065", "mon_period": PERIOD}).json()["draft"]
    assert saved["lines"][0]["quantity"] == "abc"


@pytest.mark.parametrize("lines", [((ROUTER, "1"), (ROUTER, "2")), (("NOT-A-PRODUCT", "1"),)])
def test_draft_lines_must_name_different_catalogue_products(lines):
    created = client.post("/partner-sales/drafts", json={"partner_code": "296065", "period": PERIOD}).json()
    change = {"issue_date": "", "due_date": "", "lines": [{"product_code": code, "quantity": units} for code, units in lines]}
    assert client.put(f"/partner-sales/drafts/{created['reference']}", json=change).status_code == 422


@pytest.mark.parametrize("period", ["202613", "202600", "20260", "٢٠٢٦٠٥"])
def test_drafts_require_a_real_month(period):
    assert client.post("/partner-sales/drafts", json={"partner_code": "296065", "period": period}).status_code == 422


def test_a_new_process_starts_from_the_seed():
    invoice()
    assert SalesSimulation().status() == {"drafts": 0, "invoices": 3, "collections": 2, "next_draft_reference": "SIM-INV-0004"}


def test_drafts_require_a_known_partner():
    assert client.post("/partner-sales/drafts", json={"partner_code": "000000", "period": PERIOD}).status_code == 404


def test_repeated_draft_creation_returns_the_same_draft():
    first = client.post("/partner-sales/drafts", json={"partner_code": "296065", "period": PERIOD}).json()
    second = client.post("/partner-sales/drafts", json={"partner_code": "296065", "period": PERIOD}).json()
    assert first["reference"] == second["reference"]


def test_drafts_do_not_count_as_obligations():
    draft()
    page = records(search="296065")
    assert page["summary"] == {"count": 1, "issued": 0, "drafts": 1, "outstanding_minor": 0, "as_of": ""}


def test_issuing_twice_creates_one_invoice():
    reference = draft()
    first = client.post(f"/partner-sales/drafts/{reference}/issue").json()
    second = client.post(f"/partner-sales/drafts/{reference}/issue").json()
    assert first == second
    assert client.get("/partner-sales/status").json()["invoices"] == 4


def test_issued_invoice_is_frozen():
    reference = invoice()
    before = detail(reference)["invoice"]
    change = {"issue_date": "2026-05-01", "due_date": "", "lines": []}
    assert client.put(f"/partner-sales/drafts/{reference}", json=change).status_code == 404
    assert detail(reference)["invoice"] == before


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


def test_paid_invoices_and_drafts_cannot_be_collected_against():
    paid = invoice()
    assert collect(paid, 11_000_000).status_code == 200
    assert collect(paid, 1).status_code == 422
    assert collect(draft(partner="353072"), 1).status_code == 404


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
    reference = invoice(period="202606", issue_date="2026-06-10")
    assert reference not in references(records())
    assert reference in references(records(mon_period="202606"))


def test_unknown_records_are_not_found():
    assert client.get("/partner-sales/invoices/SIM-INV-9999").status_code == 404
    assert client.get("/partner-sales/partners/000000/obligations").status_code == 404
    assert client.post("/partner-sales/drafts/SIM-INV-9999/issue").status_code == 404


def test_reset_restores_the_seed_and_restarts_references():
    invoice()
    collect("SIM-INV-0003", 100)
    assert client.post("/partner-sales/reset").json()["next_draft_reference"] == "SIM-INV-0004"
    assert references(records()) == ["SIM-INV-0003", "SIM-INV-0002", "SIM-INV-0001"]
    assert detail("SIM-INV-0003")["balance"]["status"] == "Unpaid"


def test_sales_actions_leave_existing_evidence_unchanged():
    evidence = ["/payments?mon_period=202605", "/commissions?mon_period=202605", "/inventory/comparison-page?mon_period=202605", "/financial-health?mon_period=202605", "/dealers/296065/statement?mon_period=202605"]
    def read_evidence():
        return [{key: value for key, value in client.get(path).json().items() if key != "generated_at"} for path in evidence]

    before = read_evidence()
    reference = invoice()
    collect(reference, 100)
    assert read_evidence() == before


def test_simulation_routes_are_internal_only(demo_logins):
    partner = TestClient(app)
    partner.cookies.clear()
    login = demo_logins["partner-296065"]
    assert partner.post("/auth/login", json={"username": login["username"], "password": login["password"]}).status_code == 200
    assert partner.get("/partner-sales/records", params={"mon_period": PERIOD}).status_code == 403
    assert partner.post("/partner-sales/reset").status_code == 403
