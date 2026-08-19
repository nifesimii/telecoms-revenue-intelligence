"""Tests for backend.agent.agent.run_agent.

Five mocked tests exercising the conversation loop in isolation, plus one
live Anthropic call (Test 6) that verifies the knowledge base is actually
reaching Claude in the system prompt.

Mocking strategy:
    * Fake content blocks duck-type the Anthropic SDK objects the agent
      consumes: ``block.type``, ``block.text`` / ``block.id`` /
      ``block.name`` / ``block.input``, plus ``block.model_dump()`` for
      the assistant-turn serialisation in :func:`agent._block_to_dict`.
    * :func:`_install_anthropic_mock` replaces
      ``backend.agent.agent.anthropic.AsyncAnthropic`` with a stub whose
      ``messages.create`` returns queued responses (or raises).
    * :func:`_install_tool_executor_mock` replaces
      ``backend.agent.agent.tool_executor.execute_tool`` so no real DB
      access happens during the mocked tests.

Async is handled with plain :func:`asyncio.run` inside sync test functions,
so no pytest-asyncio dependency is required.

Run from the project root:

    python -m pytest backend/tests/test_agent.py -v
"""
from __future__ import annotations

import os

# Force sample-data mode before any backend imports.
os.environ["USE_SAMPLE_DATA"] = "true"

import asyncio  # noqa: E402
import json  # noqa: E402
from unittest.mock import MagicMock  # noqa: E402

import pytest  # noqa: E402

from backend.agent import agent as agent_module  # noqa: E402
from backend.agent.agent import (  # noqa: E402
    FALLBACK_RESPONSE,
    MAX_TOOL_ITERATIONS,
    run_agent,
)


# ---------------------------------------------------------------------------
# Fake Anthropic content blocks and response
# ---------------------------------------------------------------------------


class _FakeTextBlock:
    type = "text"

    def __init__(self, text: str) -> None:
        self.text = text

    def model_dump(self) -> dict:
        return {"type": "text", "text": self.text}


class _FakeToolUseBlock:
    type = "tool_use"

    def __init__(self, id: str, name: str, input: dict) -> None:
        self.id = id
        self.name = name
        self.input = input

    def model_dump(self) -> dict:
        return {
            "type": "tool_use",
            "id": self.id,
            "name": self.name,
            "input": self.input,
        }


class _FakeResponse:
    def __init__(self, content: list, stop_reason: str = "end_turn") -> None:
        self.content = content
        self.stop_reason = stop_reason


# ---------------------------------------------------------------------------
# Mock installers
# ---------------------------------------------------------------------------


def _install_anthropic_mock(
    monkeypatch: pytest.MonkeyPatch,
    *,
    responses: list | None = None,
    on_create=None,
    raise_exc: BaseException | None = None,
) -> list[dict]:
    """Install a fake AsyncAnthropic into the agent module.

    Exactly one of ``responses``, ``on_create``, or ``raise_exc`` must be
    supplied. Returns a list that gets appended to with each call's kwargs
    so the test can inspect what was sent.
    """
    if sum(arg is not None for arg in (responses, on_create, raise_exc)) != 1:
        raise ValueError(
            "Supply exactly one of responses=, on_create=, or raise_exc=."
        )

    captured: list[dict] = []

    if responses is not None:
        seq_iter = iter(responses)
        last = responses[-1] if responses else None

        async def fake_create(**kwargs):
            captured.append(kwargs)
            try:
                return next(seq_iter)
            except StopIteration:
                return last

    elif on_create is not None:

        async def fake_create(**kwargs):
            captured.append(kwargs)
            return on_create(kwargs)

    else:  # raise_exc is not None

        async def fake_create(**kwargs):
            captured.append(kwargs)
            raise raise_exc  # type: ignore[misc]

    messages_attr = MagicMock()
    messages_attr.create = fake_create

    fake_client = MagicMock()
    fake_client.messages = messages_attr

    fake_class = MagicMock(return_value=fake_client)
    monkeypatch.setattr(agent_module.anthropic, "AsyncAnthropic", fake_class)

    return captured


def _install_tool_executor_mock(
    monkeypatch: pytest.MonkeyPatch,
    envelope_by_name: dict[str, dict],
) -> list[dict]:
    """Replace tool_executor.execute_tool with a canned-envelope stub.

    Returns a list of the tool_use blocks the executor was called with — so
    tests can confirm the agent dispatched the right tools with the right
    inputs.
    """
    received: list[dict] = []

    def fake_execute(tool_use: dict) -> dict:
        received.append(tool_use)
        name = tool_use.get("name", "")
        envelope = envelope_by_name.get(name) or {
            "tool": name,
            "parameters": tool_use.get("input"),
            "row_count": 0,
            "rows": [],
        }
        return {
            "type": "tool_result",
            "tool_use_id": tool_use.get("id", ""),
            "content": json.dumps(envelope),
        }

    monkeypatch.setattr(agent_module.tool_executor, "execute_tool", fake_execute)
    return received


def _run(coro):
    """Run an async coroutine to completion in a fresh event loop."""
    return asyncio.run(coro)


# ---------------------------------------------------------------------------
# Test 1 — tool routing
# ---------------------------------------------------------------------------


def test_tool_routing_calls_dealer_summary(monkeypatch: pytest.MonkeyPatch) -> None:
    """Single tool round-trip: tool_use response → tool result → final text."""
    responses = [
        _FakeResponse(
            content=[
                _FakeToolUseBlock(
                    id="tu_1",
                    name="get_dealer_summary",
                    input={"mon_period": "202603"},
                )
            ],
            stop_reason="tool_use",
        ),
        _FakeResponse(
            content=[
                _FakeTextBlock(
                    "Total commission for 202603 is ₦310,095.87 across 77 dealers."
                )
            ],
            stop_reason="end_turn",
        ),
    ]
    captured = _install_anthropic_mock(monkeypatch, responses=responses)
    received_tools = _install_tool_executor_mock(
        monkeypatch,
        {
            "get_dealer_summary": {
                "tool": "get_dealer_summary",
                "parameters": {"mon_period": "202603"},
                "row_count": 1,
                "rows": [
                    {
                        "dealer_id": "100",
                        "dealer_name": "Test Dealer Ltd",
                        "total_commission_ngn": 12345.67,
                    }
                ],
            }
        },
    )

    result = _run(run_agent("Summarise dealer commissions for 202603"))

    assert "get_dealer_summary" in result["tools_called"]
    assert isinstance(result["response"], str) and result["response"].strip()
    assert "get_dealer_summary" in result["raw_data"]
    assert result["raw_data"]["get_dealer_summary"]["row_count"] == 1

    # Two API rounds: one to receive the tool_use, one to receive the final text.
    assert len(captured) == 2
    # The tool was dispatched exactly once with the right input.
    assert len(received_tools) == 1
    assert received_tools[0]["name"] == "get_dealer_summary"
    assert received_tools[0]["input"] == {"mon_period": "202603"}


# ---------------------------------------------------------------------------
# Test 2 — multi-tool chain
# ---------------------------------------------------------------------------


def test_multi_tool_chain(monkeypatch: pytest.MonkeyPatch) -> None:
    """Three rounds: summary → zero-records → final text."""
    responses = [
        _FakeResponse(
            content=[
                _FakeTextBlock("Let me check the dealer summary first."),
                _FakeToolUseBlock(
                    "tu_1", "get_dealer_summary", {"mon_period": "202603"}
                ),
            ],
            stop_reason="tool_use",
        ),
        _FakeResponse(
            content=[
                _FakeTextBlock("Now pulling the zero-commission detail."),
                _FakeToolUseBlock(
                    "tu_2",
                    "get_zero_commission_records",
                    {"mon_period": "202603", "distributor_code": "121038"},
                ),
            ],
            stop_reason="tool_use",
        ),
        _FakeResponse(
            content=[
                _FakeTextBlock(
                    "CCA Links Ltd has 3 zero-commission records, all classified "
                    "as USP snapshot miss (KB Issue 1)."
                )
            ],
            stop_reason="end_turn",
        ),
    ]
    _install_anthropic_mock(monkeypatch, responses=responses)
    received = _install_tool_executor_mock(
        monkeypatch,
        {
            "get_dealer_summary": {
                "tool": "get_dealer_summary",
                "row_count": 1,
                "rows": [],
            },
            "get_zero_commission_records": {
                "tool": "get_zero_commission_records",
                "row_count": 3,
                "rows": [],
            },
        },
    )

    result = _run(
        run_agent("Which dealers have zero commission records for 202603 and why?")
    )

    assert "get_dealer_summary" in result["tools_called"]
    assert "get_zero_commission_records" in result["tools_called"]
    # Order is preserved.
    assert result["tools_called"].index("get_dealer_summary") < result[
        "tools_called"
    ].index("get_zero_commission_records")
    assert result["response"]
    # Both tools were dispatched exactly once each.
    names_dispatched = [t["name"] for t in received]
    assert names_dispatched == [
        "get_dealer_summary",
        "get_zero_commission_records",
    ]


# ---------------------------------------------------------------------------
# Test 3 — max iteration safety
# ---------------------------------------------------------------------------


def test_loop_breaks_at_max_iterations(monkeypatch: pytest.MonkeyPatch) -> None:
    """When Claude keeps requesting tools, the loop must cap at MAX_TOOL_ITERATIONS."""
    counter = {"n": 0}

    def relentless_tool_use(_kwargs):
        counter["n"] += 1
        return _FakeResponse(
            content=[
                _FakeTextBlock(f"Iteration {counter['n']} — still working."),
                _FakeToolUseBlock(
                    f"tu_{counter['n']}",
                    "get_dealer_summary",
                    {"mon_period": "202603"},
                ),
            ],
            stop_reason="tool_use",
        )

    captured = _install_anthropic_mock(monkeypatch, on_create=relentless_tool_use)
    _install_tool_executor_mock(
        monkeypatch,
        {
            "get_dealer_summary": {
                "tool": "get_dealer_summary",
                "row_count": 0,
                "rows": [],
            }
        },
    )

    # Should return normally — never raise, never hang.
    result = _run(run_agent("Loop forever"))

    # Exactly MAX_TOOL_ITERATIONS API calls, then loop breaks.
    assert len(captured) == MAX_TOOL_ITERATIONS == 5
    assert len(result["tools_called"]) == MAX_TOOL_ITERATIONS
    # All calls were to the same tool.
    assert set(result["tools_called"]) == {"get_dealer_summary"}
    assert isinstance(result, dict) and "response" in result
    assert isinstance(result["response"], str) and result["response"].strip()


# ---------------------------------------------------------------------------
# Test 4 — API failure handling
# ---------------------------------------------------------------------------


def test_api_failure_returns_fallback_dict(monkeypatch: pytest.MonkeyPatch) -> None:
    """If messages.create raises, run_agent must return the documented fallback."""
    _install_anthropic_mock(
        monkeypatch, raise_exc=RuntimeError("simulated api outage")
    )

    result = _run(run_agent("anything"))

    assert isinstance(result, dict)
    assert result["response"] == FALLBACK_RESPONSE
    assert result["response"]  # non-empty
    assert result["tools_called"] == []
    assert result["raw_data"] == {}


# ---------------------------------------------------------------------------
# Test 5 — conversation history threading
# ---------------------------------------------------------------------------


def test_conversation_history_is_threaded(monkeypatch: pytest.MonkeyPatch) -> None:
    """Turn 2 must receive turn 1's user/assistant messages in the API payload."""
    turn1 = _FakeResponse(
        content=[
            _FakeTextBlock(
                "Kashmir Global earned ₦31,082.75 in 202603 — the top dealer "
                "that month."
            )
        ],
        stop_reason="end_turn",
    )
    turn2 = _FakeResponse(
        content=[
            _FakeTextBlock(
                "Yes — Kashmir Global was the top earner for 202603 as I noted."
            )
        ],
        stop_reason="end_turn",
    )

    state = {"calls": 0, "last_messages": None}

    def on_create(kwargs):
        state["calls"] += 1
        state["last_messages"] = kwargs.get("messages")
        return turn1 if state["calls"] == 1 else turn2

    _install_anthropic_mock(monkeypatch, on_create=on_create)
    _install_tool_executor_mock(monkeypatch, {})

    # Turn 1 — no prior history.
    q1 = "Who is the top dealer in 202603?"
    r1 = _run(run_agent(q1))
    assert "Kashmir" in r1["response"]

    # Build the conversation history exactly the way the frontend does in
    # useChat.js — strings, not block lists.
    history = [
        {"role": "user", "content": q1},
        {"role": "assistant", "content": r1["response"]},
    ]

    # Turn 2 — second question that depends on the first.
    q2 = "Was that one Kashmir Global Ltd?"
    r2 = _run(run_agent(q2, conversation_history=history))

    # Confirm what was sent to the API on turn 2: the two history entries
    # AND the new user message — in that order.
    sent = state["last_messages"]
    assert sent is not None and len(sent) == 3
    assert sent[0] == {"role": "user", "content": q1}
    assert sent[1]["role"] == "assistant"
    assert sent[1]["content"] == r1["response"]
    assert sent[2] == {"role": "user", "content": q2}

    # And the second response is non-empty and is coherent (mocked to echo
    # the prior context — verifying the agent surfaced it correctly).
    assert r2["response"]
    assert "Kashmir" in r2["response"]


# ---------------------------------------------------------------------------
# Test 6 — KB grounding (LIVE Anthropic API call)
# ---------------------------------------------------------------------------


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
