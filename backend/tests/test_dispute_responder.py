"""Tests for the dispute response generator.

Hits the pure-Python template + the POST /payments/disputes/draft endpoint.
Sample-data mode, no API key required.
"""
from __future__ import annotations

import os

import pytest
from fastapi.testclient import TestClient

os.environ["USE_SAMPLE_DATA"] = "true"

from backend.agent.dispute_responder import (  # noqa: E402
    compose_dispute_response,
)
from backend.main import app  # noqa: E402


# ---------------------------------------------------------------------------
# Classifier
# ---------------------------------------------------------------------------

def test_dispute_uses_the_same_verified_causes_as_chat():
    from backend.db.investigation_evidence import investigate
    result = investigate('296065', ['202606'])
    letter = compose_dispute_response(distributor_code='296065', mon_period='202606')
    assert letter['summary']['root_cause_classifications'] == {c['cause']: c['count'] for c in result['causes']}
    assert 'fallback candidate' not in letter['markdown']


def test_dispute_keeps_missing_support_unresolved(monkeypatch):
    from backend.db import queries
    original = queries.investigation_support
    monkeypatch.setattr(queries, 'investigation_support', lambda *a, **kw: original(*a, **kw).iloc[:0])
    letter = compose_dispute_response(distributor_code='296065', mon_period='202606')
    assert letter['summary']['root_cause_classifications'] == {'OUTSIDE_6_MONTH_WINDOW': 2, 'UNRESOLVED': 48}


# ---------------------------------------------------------------------------
# compose_dispute_response — happy path against real sample data
# ---------------------------------------------------------------------------

def test_compose_dispute_response_for_real_dealer_in_sample():
    # Dealer 74050 has 86 zero-comm records in 202602 sample data.
    payload = compose_dispute_response(
        distributor_code="74050",
        mon_period="202602",
    )
    assert "markdown" in payload and "summary" in payload
    s = payload["summary"]
    assert s["dealer_id"] == "74050"
    assert s["mon_period"] == "202602"
    assert s["unqualified_activations"] >= 80  # ~86 in sample
    # Classifications should sum to the unqualified count
    assert sum(s["root_cause_classifications"].values()) == s["unqualified_activations"]
    # Position should be derived
    assert s["position_code"] in {
        "RECORDED_BALANCE_ALIGNED", "RECORDED_SHORTFALL",
        "RECORDED_EXCESS",
    }


def test_compose_markdown_includes_required_sections():
    payload = compose_dispute_response(distributor_code="74050", mon_period="202602")
    md = payload["markdown"]
    for header in [
        "# Commission dispute review",
        "## 1. Activation evidence",
        "## 2. Recorded payment position",
        "## 4. Conditional Finance observation",
        "## 5. Next steps",
        "Draft for Finance review",
    ]:
        assert header in md, f"missing section: {header}"


def test_compose_includes_dispute_text_when_provided():
    payload = compose_dispute_response(
        distributor_code="74050",
        mon_period="202602",
        dispute_text="We activated 1,800 devices but only received commission on 1,200.",
    )
    assert "Your stated position" in payload["markdown"]
    assert "1,800 devices" in payload["markdown"]


def test_compose_raises_for_unknown_dealer():
    with pytest.raises(ValueError):
        compose_dispute_response(distributor_code="999999", mon_period="202602")


def test_compose_ignores_amount_paid_override_for_position():
    # Client-supplied settlement must not override the recorded account.
    from backend.db.connection import execute_query
    payments = execute_query("get_payment_summary", {"mon_period": "202602"})
    account = payments[payments["dealer_id"].astype(str) == "74050"].iloc[0]
    payload = compose_dispute_response(
        distributor_code="74050",
        mon_period="202602",
        amount_paid=999_999_999.99,
    )
    assert payload["summary"]["amount_paid_ngn"] == account["amount_paid"]
    assert payload["summary"]["statement_claim_ngn"] == round(account["commission_owed"], 2)
    assert payload["summary"]["outstanding_ngn"] == round(account["amount_unpaid"], 2)
    assert "Simulated" in payload["markdown"]
    assert "3 business days" not in payload["markdown"]
    assert "dispute is declined" not in payload["markdown"]


# ---------------------------------------------------------------------------
# Endpoint
# ---------------------------------------------------------------------------

@pytest.fixture(scope="module")
def client():
    with TestClient(app) as c:
        yield c


def test_endpoint_happy_path(client: TestClient):
    r = client.post(
        "/payments/disputes/draft",
        json={"distributor_code": "74050", "mon_period": "202602"},
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["summary"]["dealer_id"] == "74050"
    assert body["markdown"].startswith("# Commission dispute review")


def test_endpoint_unknown_dealer_returns_404(client: TestClient):
    r = client.post(
        "/payments/disputes/draft",
        json={"distributor_code": "999999", "mon_period": "202602"},
    )
    assert r.status_code == 404
    assert "No commission data" in r.json()["detail"]


def test_endpoint_includes_dispute_text(client: TestClient):
    r = client.post(
        "/payments/disputes/draft",
        json={
            "distributor_code": "74050",
            "mon_period": "202602",
            "dispute_text": "We dispute the commission shortfall of NGN 500,000.",
        },
    )
    assert r.status_code == 200
    assert "NGN 500,000" in r.json()["markdown"]
