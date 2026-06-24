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
    _classify_zero_record,
    compose_dispute_response,
)
from backend.main import app  # noqa: E402


# ---------------------------------------------------------------------------
# Classifier
# ---------------------------------------------------------------------------

def test_classifier_null_profile_class_wins():
    row = {
        "account_profile_class": None,
        "product_denomination": "FBB_DEVICE",
        "invoice_date": "2025-01-01",
        "first_activation_date": "2025-01-15",
    }
    assert _classify_zero_record(row) == "NULL_PROFILE_CLASS"


def test_classifier_hynex_split():
    row = {
        "account_profile_class": "FIXED BROADBAND",
        "product_denomination": "Hynex_1",
        "invoice_date": "2025-01-01",
        "first_activation_date": "2025-01-15",
    }
    assert _classify_zero_record(row) == "HYNEX_DENOMINATION_SPLIT"


def test_classifier_outside_window():
    row = {
        "account_profile_class": "FIXED BROADBAND",
        "product_denomination": "FBB_DEVICE",
        "invoice_date": "2025-01-01",
        "first_activation_date": "20260201 10:00:00",   # > 180 days later
    }
    assert _classify_zero_record(row) == "OUTSIDE_6_MONTH_WINDOW"


def test_classifier_within_window_defaults_to_usp_miss():
    row = {
        "account_profile_class": "FIXED BROADBAND",
        "product_denomination": "FBB_DEVICE",
        "invoice_date": "2025-08-30",
        "first_activation_date": "20260210 10:00:00",   # < 180 days
    }
    assert _classify_zero_record(row) == "USP_SNAPSHOT_MISS"


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
        "NO_FURTHER_ACTION", "PARTIAL_PAYMENT_AGREED",
        "DISPUTE_DECLINED", "DECLINED_INSUFFICIENT_QUALIFICATION",
    }


def test_compose_markdown_includes_required_sections():
    payload = compose_dispute_response(distributor_code="74050", mon_period="202602")
    md = payload["markdown"]
    for header in [
        "# Commission dispute review",
        "## 1. Activation evidence",
        "## 2. Commission calculation",
        "## 4. Recommended settlement position",
        "## 5. Next steps",
        "MTN FBB Finance Team",
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


def test_compose_uses_amount_paid_override_for_position():
    # Force a clear over-payment scenario
    payload = compose_dispute_response(
        distributor_code="74050",
        mon_period="202602",
        amount_paid=999_999_999.99,
    )
    assert payload["summary"]["position_code"] == "DISPUTE_DECLINED"


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
