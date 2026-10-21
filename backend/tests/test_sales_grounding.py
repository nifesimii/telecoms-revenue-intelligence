"""Opt-in response-quality check; uses the configured model and sample tools."""
import asyncio
import os

import pytest

from backend.agent.agent import run_agent


@pytest.mark.live_agent
@pytest.mark.skipif(
    os.getenv("RUN_LIVE_AGENT_TESTS") != "1",
    reason="Opt-in: makes a billed model call",
)
def test_ambiguous_sales_followup_clarifies_measure_before_querying():
    result = asyncio.run(run_agent(
        "Active investigation context: Reporting period 202606. Exact dealer "
        "account code 296065 (River Isle Ventures). Payment settlement investigation.\n\n"
        "User question: what sales did this dealer make this year",
        conversation_history=[
            {"role": "user", "content": "Explain this dealer's payment position."},
            {"role": "assistant", "content": "River Isle Ventures (296065) has "
             "recorded activation commission and payment evidence for June 2026. "
             "Payment figures are simulated; the underlying cause remains unverified."},
        ],
    ))
    answer = result["response"]
    # A focused clarification must precede an unrelated commission investigation.
    assert not result["tools_called"], result
    assert "?" in answer, answer
    assert "sales" in answer.lower() and "activation" in answer.lower(), answer
    assert "296065" in answer, answer
    assert len(answer.split()) <= 180, answer
    assert "sourcing issues" not in answer.lower(), answer
