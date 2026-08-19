"""End-to-end tests for the FastAPI layer using FastAPI's TestClient.

Sample-data mode is enforced for every test — none of them touch a live
Presto cluster.

The success ``/chat`` test (test 4) makes a real call to the Anthropic API
and so consumes a small amount of credit on each run. The error-path test
(test 6) monkeypatches ``run_agent`` to avoid network/billing dependencies.

Run from the project root:

    python -m pytest backend/tests/test_api.py -v
"""
from __future__ import annotations

import os

# Force sample-data mode before any backend module imports.
os.environ["USE_SAMPLE_DATA"] = "true"

import pytest  # noqa: E402  — must be imported after env var is set
from fastapi.testclient import TestClient  # noqa: E402

from backend.main import app  # noqa: E402


@pytest.fixture(scope="module")
def client():
    """One TestClient per test module with the lifespan triggered exactly once."""
    with TestClient(app) as c:
        yield c


# ---------------------------------------------------------------------------
# 1. GET /health
# ---------------------------------------------------------------------------


def test_health_returns_ok_and_sample_mode(client: TestClient) -> None:
    response = client.get("/health")
    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "ok"
    assert body["sample_data_mode"] is True


# ---------------------------------------------------------------------------
# 2. GET /periods
# ---------------------------------------------------------------------------


def test_periods_returns_list_with_at_least_one(client: TestClient) -> None:
    response = client.get("/periods")
    assert response.status_code == 200
    body = response.json()
    assert "periods" in body
    assert isinstance(body["periods"], list)
    assert len(body["periods"]) >= 1
    # All periods should be YYYYMM strings.
    for p in body["periods"]:
        assert isinstance(p, str)
        assert len(p) == 6 and p.isdigit()


# ---------------------------------------------------------------------------
# 3. GET /dealers
# ---------------------------------------------------------------------------


def test_dealers_returns_list_of_dealer_summary(client: TestClient) -> None:
    response = client.get("/dealers")
    assert response.status_code == 200
    body = response.json()
    assert isinstance(body, list)
    assert len(body) > 0

    required_fields = {
        "dealer_id",
        "dealer_name",
        "account_profile_class",
        "total_activations",
        "total_commission_ngn",
        "zero_commission_count",
    }
    first = body[0]
    assert required_fields.issubset(set(first.keys()))
    assert isinstance(first["dealer_id"], str)
    assert isinstance(first["total_activations"], int)
    assert isinstance(first["total_commission_ngn"], float)


# ---------------------------------------------------------------------------
# 4. POST /chat (happy path — real Anthropic call)
# ---------------------------------------------------------------------------


def test_chat_summary_question_returns_response_and_tool(
    client: TestClient,
) -> None:
    response = client.post(
        "/chat",
        json={"message": "Summarise dealer commissions for 202603"},
    )
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["error"] is None
    assert isinstance(body["response"], str)
    assert body["response"].strip(), "Empty response from /chat"
    assert "get_dealer_summary" in body["tools_called"]
    # The raw envelope should carry the tool's row data through to the client.
    assert "get_dealer_summary" in body["raw_data"]


# ---------------------------------------------------------------------------
# 5. POST /chat with empty message → 422
# ---------------------------------------------------------------------------


def test_chat_empty_message_returns_422(client: TestClient) -> None:
    response = client.post("/chat", json={"message": ""})
    assert response.status_code == 422


# ---------------------------------------------------------------------------
# 6. POST /chat with internal failure → 200 + populated error field
# ---------------------------------------------------------------------------


def test_chat_internal_failure_returns_200_with_error(
    client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """If run_agent raises, /chat must swallow it and surface .error — never 500."""
    import backend.api.routes as routes_module

    async def _exploding_run_agent(*_args, **_kwargs):
        raise RuntimeError("simulated agent failure for test 6")

    monkeypatch.setattr(routes_module, "run_agent", _exploding_run_agent)

    response = client.post("/chat", json={"message": "anything"})
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["response"] == (
        "I was unable to process that request. Please try again."
    )
    assert body["tools_called"] == []
    assert body["raw_data"] == {}
    assert body["error"] is not None
    assert "simulated agent failure" in body["error"]
