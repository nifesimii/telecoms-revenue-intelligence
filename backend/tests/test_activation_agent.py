"""Phase 2 — agent-level tests for Activation Intelligence tools.

Two mocked tests (8 & 9) confirm Claude routes the right new tool. Test 10
is a live API call that verifies the Phase 2 KB section (Rule 4 + 6-month
eligibility window) actually reaches the model.

Mock infrastructure mirrors test_agent.py exactly — duck-typed content
blocks, a flexible AsyncAnthropic stub, and tool_executor monkeypatching.
"""
from __future__ import annotations

import os

os.environ["USE_SAMPLE_DATA"] = "true"

import asyncio  # noqa: E402
import json  # noqa: E402
from unittest.mock import MagicMock  # noqa: E402

import pytest  # noqa: E402

from backend.agent import agent as agent_module  # noqa: E402
from backend.agent.agent import run_agent  # noqa: E402


# ---------------------------------------------------------------------------
# Fake content blocks (same shape as test_agent.py helpers)
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


def _install_anthropic_mock(monkeypatch, *, responses: list) -> list[dict]:
    captured: list[dict] = []
    seq_iter = iter(responses)
    last = responses[-1] if responses else None

    async def fake_create(**kwargs):
        captured.append(kwargs)
        try:
            return next(seq_iter)
        except StopIteration:
            return last

    messages_attr = MagicMock()
    messages_attr.create = fake_create
    fake_client = MagicMock()
    fake_client.messages = messages_attr
    fake_class = MagicMock(return_value=fake_client)
    monkeypatch.setattr(agent_module.anthropic, "AsyncAnthropic", fake_class)
    return captured


def _install_tool_executor_mock(monkeypatch, envelope_by_name: dict[str, dict]):
    def fake_execute(tool_use: dict) -> dict:
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


def _run(coro):
    return asyncio.run(coro)


# ---------------------------------------------------------------------------
# Test 8 — agent routes "Show activation summary for 202603" to the new tool
# ---------------------------------------------------------------------------


def test_agent_activation_summary_question(monkeypatch: pytest.MonkeyPatch) -> None:
    responses = [
        _FakeResponse(
            content=[
                _FakeToolUseBlock(
                    id="t_act_1",
                    name="get_activation_summary",
                    input={"mon_period": "202603"},
                )
            ],
            stop_reason="tool_use",
        ),
        _FakeResponse(
            content=[
                _FakeTextBlock(
                    "Total activations in 202603: 30,892 across 922 dealers. "
                    "Top dealer is Nestobar Nigeria Ltd at 806 activations."
                )
            ],
            stop_reason="end_turn",
        ),
    ]
    _install_anthropic_mock(monkeypatch, responses=responses)
    _install_tool_executor_mock(
        monkeypatch,
        {
            "get_activation_summary": {
                "tool": "get_activation_summary",
                "parameters": {"mon_period": "202603"},
                "row_count": 1,
                "rows": [
                    {
                        "dealer_id": "74050",
                        "dealer_name": "Nestobar Nigeria Ltd",
                        "activation_count": 806,
                        "qualified_activation_count": 713,
                        "qualification_rate_pct": 88.46,
                    }
                ],
            }
        },
    )

    result = _run(run_agent("Show activation summary for 202603"))

    assert "get_activation_summary" in result["tools_called"]
    assert result["response"]
    assert "get_activation_summary" in result["raw_data"]


# ---------------------------------------------------------------------------
# Test 9 — agent routes "unusual activation behaviour" to exceptions tool
# ---------------------------------------------------------------------------


def test_agent_activation_exceptions_question(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    responses = [
        _FakeResponse(
            content=[
                _FakeToolUseBlock(
                    id="t_exc_1",
                    name="get_activation_exceptions",
                    input={"mon_period": "202603"},
                )
            ],
            stop_reason="tool_use",
        ),
        _FakeResponse(
            content=[
                _FakeTextBlock(
                    "Flagged 190 records across three exception types. "
                    "ALL_UNQUALIFIED accounts for 35 dealers."
                )
            ],
            stop_reason="end_turn",
        ),
    ]
    _install_anthropic_mock(monkeypatch, responses=responses)
    _install_tool_executor_mock(
        monkeypatch,
        {
            "get_activation_exceptions": {
                "tool": "get_activation_exceptions",
                "parameters": {"mon_period": "202603"},
                "row_count": 0,
                "rows": [],
            }
        },
    )

    result = _run(
        run_agent("Which dealers have unusual activation behaviour in 202603?")
    )

    assert "get_activation_exceptions" in result["tools_called"]
    assert result["response"]


# ---------------------------------------------------------------------------
# Test 10 — live API; verifies the Phase 2 KB section is reaching the model.
# ---------------------------------------------------------------------------


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
