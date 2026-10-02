"""Requested measures exercised through real sample evidence and the public agent."""
import os
import pytest

os.environ["USE_SAMPLE_DATA"] = "true"

from backend.agent.agent import run_agent
from backend.tests.test_agent import _run, measure_scope, install_scope_provider, evidence_period


def test_agent_activation_summary_question(monkeypatch):
    install_scope_provider(monkeypatch, measure_scope("activation_count", "activation_qualified_count", "activation_unqualified_count"))
    result = _run(run_agent("Show 74050 March 2026 activations and qualified/unqualified counts"))
    assert [evidence_period(result, i)["total"] for i in range(3)] == [806, 713, 93]
    assert "806" in result["response"] and "713" in result["response"]
    assert "NGN" not in result["response"]
    assert set(result["tools_called"]) == {"get_dealer_summary", "get_activation_summary"}


def test_agent_activation_exceptions_question(monkeypatch):
    install_scope_provider(monkeypatch, measure_scope("activation_qualified_count", "activation_unqualified_count",
                                                     dealer_id=None, operation="breakdown", filter="low_qualification"))
    result = _run(run_agent("List low-qualification dealers and qualified/unqualified counts in March 2026"))
    qualified = evidence_period(result, 0)
    unqualified = evidence_period(result, 1)
    assert next(row for row in qualified["rows"] if row["dealer_id"] == "19335")["value"] == 55
    assert next(row for row in unqualified["rows"] if row["dealer_id"] == "19335")["value"] == 82
    assert all(row["dealer_id"] != "74050" for row in qualified["rows"])
    assert "Raven View Networks" in result["response"]
    assert "fraud" not in result["response"].lower() and "NGN" not in result["response"]


@pytest.mark.live_agent
@pytest.mark.skipif(
    os.getenv("RUN_LIVE_AGENT_TESTS") != "1",
    reason="live agent tests are opt-in (set RUN_LIVE_AGENT_TESTS=1)",
)
def test_kb_activation_rules_grounded() -> None:
    """Asks a question that requires Rule 4 + 6-month eligibility window
    knowledge. Confirms the answer cites both and avoids the word 'fraud'."""
    from backend import config

    if not config.ANTHROPIC_API_KEY:
        pytest.skip(
            "ANTHROPIC_API_KEY not configured — skipping live Phase 2 KB test"
        )

    result = _run(
        run_agent(
            "A dealer had 200 activations but earned zero commission. "
            "What are the possible reasons?"
        )
    )

    text = (result["response"] or "").lower()
    assert text, "Live API returned empty response"

    # Must reference USP snapshot miss — the documented Rule-4 root cause.
    assert "usp" in text and "snapshot" in text, (
        "Response did not reference USP snapshot miss:\n\n" + result["response"]
    )

    # Must reference the 6-month eligibility window.
    assert "6-month" in text or "six-month" in text or "6 month" in text, (
        "Response did not reference the 6-month eligibility window:\n\n"
        + result["response"]
    )

    # Must NOT use the word 'fraud'.
    assert "fraud" not in text, (
        "Response used the forbidden word 'fraud':\n\n" + result["response"]
    )
