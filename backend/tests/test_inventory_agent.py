"""Requested measures exercised through real sample evidence and the public agent."""
import os
import pytest

os.environ["USE_SAMPLE_DATA"] = "true"

from backend.agent.agent import run_agent
from backend.tests.test_agent import _run, measure_scope, install_scope_provider, evidence_period


def test_agent_inventory_question(monkeypatch):
    install_scope_provider(monkeypatch, measure_scope("inventory_gap", "inventory_recorded_purchases", dealer_id="332070",
                                                     operation="breakdown", breakdown="product"))
    result = _run(run_agent("Show dealer 332070 inventory gap and recorded purchases by product in March 2026"))
    assert evidence_period(result, 0)["total"] == -5
    assert evidence_period(result, 1)["total"] == 6
    assert "Stone Wind Communications" in result["response"] and "1283280" in result["response"]
    assert "cumulative" in result["response"].lower()
    assert "fraud" not in result["response"].lower() and "NGN" not in result["response"]
    assert result["tools_called"] == ["get_inventory_comparison"]


def test_complete_dealer_purchases_are_not_substituted_with_inventory_snapshot(monkeypatch):
    install_scope_provider(monkeypatch, measure_scope("dealer_purchases", dealer_id="332070"))
    result = _run(run_agent("What are dealer 332070 total purchases in March 2026?"))
    assert evidence_period(result)["status"] == "unavailable"
    assert evidence_period(result)["total"] is None and result["tools_called"] == []
    assert "dated complete purchase records" in result["response"]


@pytest.mark.live_agent
@pytest.mark.skipif(
    os.getenv("RUN_LIVE_AGENT_TESTS") != "1",
    reason="live agent tests are opt-in (set RUN_LIVE_AGENT_TESTS=1)",
)
def test_kb_inventory_rules_grounded() -> None:
    """Real API call. Confirms the KB Section 12 rules are reaching the model:
    answer cites CONFIRMED_MISMATCH or 'confirmed mismatch', recommends
    investigation, and never uses 'fraud'.
    """
    from backend import config

    if not config.ANTHROPIC_API_KEY:
        pytest.skip(
            "ANTHROPIC_API_KEY not configured — skipping live Phase 3 KB test"
        )

    result = _run(
        run_agent(
            "A dealer activated 300 units but only has 60 units in their "
            "purchase record. What does this mean and what should Finance do?"
        )
    )

    text = (result["response"] or "").lower()
    assert text, "Live API returned empty response"

    # Must cite the CONFIRMED_MISMATCH concept.
    assert "confirmed_mismatch" in text or "confirmed mismatch" in text, (
        "Response did not reference CONFIRMED_MISMATCH:\n\n"
        + result["response"]
    )

    # Must recommend investigation.
    assert "investigation" in text or "investigate" in text, (
        "Response did not mention investigation:\n\n" + result["response"]
    )

    # Must NOT use 'fraud'.
    assert "fraud" not in text, (
        "Response used the forbidden word 'fraud':\n\n" + result["response"]
    )
