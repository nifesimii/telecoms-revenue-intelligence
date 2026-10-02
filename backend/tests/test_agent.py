"""Public Atlas scope boundary: mock intent provider, retain real sample evidence.

These checks prove enforcement after scope resolution, not model intent accuracy.
The opt-in provider regression separately checks natural-language grounding.
"""
import asyncio
from copy import deepcopy
import json
import os
from types import SimpleNamespace

os.environ["USE_SAMPLE_DATA"] = "true"

import pytest

from backend.agent import agent as agent_module, prompts
from backend.agent.agent import FALLBACK_RESPONSE, run_agent


def _run(coroutine):
    return asyncio.run(coroutine)


def measure_scope(*measures, **options):
    return {"kind": "measure", "measures": list(measures), "periods": ["202603"],
            "dealer_id": "74050", "operation": "total", **options}


def install_scope_provider(monkeypatch, scope=None, *, error=None, blocks=None):
    """Only provider I/O is mocked; query, projection and rendering remain real."""
    captured = []
    closed = []

    async def create(**kwargs):
        captured.append(deepcopy(kwargs))
        if error:
            raise error
        content = blocks if blocks is not None else [SimpleNamespace(
            type="tool_use", id="scope-1", name="resolve_measure_request", input=scope)]
        return SimpleNamespace(content=content, stop_reason="tool_use")

    async def close():
        closed.append(True)

    client = SimpleNamespace(messages=SimpleNamespace(create=create), close=close)
    monkeypatch.setattr(agent_module, "new_client", lambda key: client)
    return captured, closed


def evidence_period(result, index=0):
    return result["raw_data"]["measure_evidence"]["measures"][index]["periods"][0]


def test_requested_commission_uses_sample_aggregate_not_provider_prose(monkeypatch):
    scope = measure_scope("activation_commission")
    calls, closed = install_scope_provider(monkeypatch, blocks=[
        SimpleNamespace(type="text", text="Sales are NGN 999,999,999.00; disputed."),
        SimpleNamespace(type="tool_use", id="scope", name="resolve_measure_request", input=scope),
    ])
    result = _run(run_agent("What activation commission is recorded for dealer 74050 in 202603?"))
    assert "NGN 1,140,192.85" in result["response"]
    assert "999,999,999" not in result["response"] and "disputed" not in result["response"]
    assert evidence_period(result)["total"] == 1140192.85
    assert result["tools_called"] == ["get_dealer_summary"]
    assert len(calls) == 1 and closed == [True]
    assert [tool["name"] for tool in calls[0]["tools"]] == ["resolve_measure_request"]


def test_multiple_measures_and_zero_commission_why_preserve_uncertainty(monkeypatch):
    install_scope_provider(monkeypatch, measure_scope("activation_commission", "zero_commission_count", operation="explain"))
    result = _run(run_agent("What commission and zero-commission count does 74050 have in March 2026, and why?"))
    assert evidence_period(result, 0)["total"] == 1140192.85
    assert evidence_period(result, 1)["total"] == 93
    assert "93" in result["response"] and "unverified" in result["response"]
    assert "checked 93 of 93" in result["response"]
    assert "Historical USP" in result["response"]
    assert "USP snapshot miss" not in result["response"]
    assert result["tools_called"] == ["get_dealer_summary", "get_zero_commission_records"]


@pytest.mark.parametrize("scope", [
    measure_scope("activation_count", invented_answer="NGN 999.00"),
    measure_scope("imaginary_retail_margin"),
    measure_scope("activation_count", periods=["202613"]),
    measure_scope("activation_count", periods=["202603", "202603"]),
])
def test_invalid_scope_fails_in_one_provider_call_without_evidence(monkeypatch, scope):
    calls, closed = install_scope_provider(monkeypatch, scope)
    result = _run(run_agent("Resolve this requested figure"))
    assert result == {"response": FALLBACK_RESPONSE, "tools_called": [], "raw_data": {}}
    assert len(calls) == 1 and closed == [True]


def test_direct_query_tool_call_is_rejected_without_executing_it(monkeypatch):
    calls, _ = install_scope_provider(monkeypatch, blocks=[SimpleNamespace(
        type="tool_use", id="old-tool", name="get_dealer_summary", input={"mon_period": "202603"})])
    result = _run(run_agent("Summarise commission"))
    assert result["response"] == FALLBACK_RESPONSE
    assert result["raw_data"] == {} and result["tools_called"] == []
    assert len(calls) == 1


def test_api_failure_returns_fallback_and_closes_client(monkeypatch):
    calls, closed = install_scope_provider(monkeypatch, error=RuntimeError("provider unavailable"))
    result = _run(run_agent("Summarise commissions for March 2026"))
    assert result == {"response": FALLBACK_RESPONSE, "tools_called": [], "raw_data": {}}
    assert len(calls) == 1 and closed == [True]


def test_history_and_current_selection_are_separate_and_never_mutated(monkeypatch):
    history = [{"role": "user", "content": "By sales I mean recorded activations."},
               {"role": "assistant", "content": "I will use recorded activations in this conversation."}]
    original = deepcopy(history)
    calls, _ = install_scope_provider(monkeypatch, measure_scope("activation_count"))
    result = _run(run_agent("How many this month?", history, reporting_period="202603",
                           investigation_context="Selected dealer 74050; payment workspace"))
    assert history == original
    assert calls[0]["messages"][:-1] == original
    assert json.loads(calls[0]["messages"][-1]["content"]) == {
        "question": "How many this month?", "reporting_period": "202603",
        "investigation_context": "Selected dealer 74050; payment workspace"}
    assert evidence_period(result)["total"] == 806
    assert "payment" not in result["response"].lower()


def test_policy_quote_is_verified_against_complete_core_kb(monkeypatch):
    quote = "| 5G ROUTER            | 68,465.12                | 8,215.81              | TOZED ROUMOD4393, ZTE MC888D 5G CPE, HUAWEI ROUWIR4332      |"
    calls, _ = install_scope_provider(monkeypatch, {"kind": "knowledge", "knowledge_quote": quote})
    result = _run(run_agent("What is the commission rate for a 5G Router activation?"))
    assert "8,215.81" in result["response"]
    assert result["tools_called"] == [] and result["raw_data"] == {}
    assert prompts.KB_CONTENT in calls[0]["system"][0]["text"]


def test_invented_policy_quote_does_not_cross_answer_boundary(monkeypatch):
    install_scope_provider(monkeypatch, {"kind": "knowledge", "knowledge_quote": "All partners earn 99% commission."})
    result = _run(run_agent("What is the rate?"))
    assert result["response"] == FALLBACK_RESPONSE


def test_financial_statements_render_source_lines_without_summing_them(monkeypatch):
    install_scope_provider(monkeypatch, measure_scope("financial_statements", operation="breakdown"))
    result = _run(run_agent("Show dealer 74050 financial statements for March 2026"))
    period = evidence_period(result)
    assert period["total"] is None
    sales = next(row for row in period["rows"] if row["dimension"].endswith(": Sales revenue"))
    assert sales["value"] == 12600000
    assert "NGN 12,600,000.00" in result["response"]
    assert "Synthetic" in result["response"] and "Sales revenue" in result["response"]
    assert "get_financial_health_report" in result["tools_called"]


@pytest.mark.live_agent
@pytest.mark.skipif(
    os.getenv("RUN_LIVE_AGENT_TESTS") != "1",
    reason="live agent tests are opt-in (set RUN_LIVE_AGENT_TESTS=1)",
)
def test_kb_grounding_returns_5g_router_commission_rate() -> None:
    """Real API call. Confirms the KB is reaching Claude via the system prompt.

    Skipped if no ANTHROPIC_API_KEY is configured. Costs a small amount of
    credit on each run.
    """
    from backend import config

    if not config.ANTHROPIC_API_KEY:
        pytest.skip("ANTHROPIC_API_KEY not configured — skipping live KB grounding test")

    result = _run(
        run_agent("What is the commission rate for a 5G Router activation?")
    )

    assert isinstance(result["response"], str)
    assert result["response"], "Live API returned empty response"
    assert "8,215.81" in result["response"], (
        "Expected '8,215.81' (the KB-documented 5G ROUTER commission rate) "
        f"in the response, but got:\n\n{result['response']}"
    )
