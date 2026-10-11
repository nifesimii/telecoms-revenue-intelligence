"""Requested measures exercised through real sample evidence and the public agent."""
import os
import pytest

os.environ["USE_SAMPLE_DATA"] = "true"

from backend.agent.agent import run_agent
from backend.tests.test_agent import _run, measure_scope, install_scope_provider, evidence_period


def test_agent_payment_summary_question(monkeypatch):
    install_scope_provider(monkeypatch, measure_scope("payment_paid", "payment_outstanding", "payment_status", dealer_id="296065"))
    result = _run(run_agent("Show 296065 payments paid, outstanding and status for March 2026"))
    assert evidence_period(result, 0)["total"] == 368324.63
    assert evidence_period(result, 1)["total"] == 552486.95
    assert evidence_period(result, 2)["rows"][0]["value"] == "DISPUTED"
    assert "NGN 368,324.63" in result["response"] and "Source: Payment records" in result["response"]
    assert "simulated" in result["response"].lower()
    assert "disputed" in result["response"].lower()
    assert result["tools_called"] == ["get_payment_summary"]


def test_agent_payment_exceptions_question(monkeypatch):
    install_scope_provider(monkeypatch, measure_scope("payment_status", "payment_outstanding", dealer_id=None,
                                                     operation="breakdown", filter="disputed"))
    result = _run(run_agent("List disputed dealer payment statuses and outstanding amounts for March 2026"))
    statuses = evidence_period(result, 0)["rows"]
    assert statuses and all(row["value"] == "DISPUTED" for row in statuses)
    assert next(row for row in evidence_period(result, 1)["rows"] if row["dealer_id"] == "296065")["value"] == 552486.95
    assert "simulated" in result["response"].lower() and "DISPUTED" in result["response"]
    assert "CONFIRMED" not in result["response"]  # Payment status does not establish a causal finding.


@pytest.mark.live_agent
@pytest.mark.skipif(
    os.getenv("RUN_LIVE_AGENT_TESTS") != "1",
    reason="live agent tests are opt-in (set RUN_LIVE_AGENT_TESTS=1)",
)
def test_kb_payment_transparency() -> None:
    """Real API call. Response must disclose simulated status, cite a ₦
    coverage amount, and mention disputed dealers."""
    from backend import config

    if not config.ANTHROPIC_API_KEY:
        pytest.skip(
            "ANTHROPIC_API_KEY not configured — skipping live Phase 4 KB test"
        )

    result = _run(
        run_agent(
            "What is the payment coverage for March 2026 and which dealers "
            "have disputed commissions?"
        )
    )

    text = result["response"] or ""
    assert text, "Live API returned empty response"

    lower = text.lower()

    # Must disclose simulated data.
    assert "simulated" in lower, (
        "Response did not disclose simulated payment data:\n\n" + text
    )

    # Must contain a ₦ amount.
    assert "NGN " in text, f"Response did not include an NGN amount:\n\n{text}"

    # Must mention disputed dealers / commissions.
    assert "disputed" in lower or "dispute" in lower, (
        "Response did not mention disputed:\n\n" + text
    )
