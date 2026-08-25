"""Phase 4 — agent tests for Payment Intelligence.

Two mocked routing tests + one live KB-grounding test.
"""
from __future__ import annotations

import asyncio
import json
import os

os.environ["USE_SAMPLE_DATA"] = "true"

from unittest.mock import MagicMock  # noqa: E402

import pytest  # noqa: E402

from backend.agent import agent as agent_module  # noqa: E402
from backend.agent.agent import run_agent  # noqa: E402


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
# Test 9 — agent routes payment summary questions
# ---------------------------------------------------------------------------


def test_agent_payment_summary_question(monkeypatch: pytest.MonkeyPatch) -> None:
    responses = [
        _FakeResponse(
            content=[
                _FakeToolUseBlock(
                    id="t_pay_1",
                    name="get_payment_summary",
                    input={"mon_period": "202603"},
                )
            ],
            stop_reason="tool_use",
        ),
        _FakeResponse(
            content=[
                _FakeTextBlock(
                    "Based on simulated payment data — coverage for 202603 is "
                    "85.1% of ₦47,642,607.64 owed."
                )
            ],
            stop_reason="end_turn",
        ),
    ]
    _install_anthropic_mock(monkeypatch, responses=responses)
    _install_tool_executor_mock(
        monkeypatch,
        {
            "get_payment_summary": {
                "tool": "get_payment_summary",
                "parameters": {"mon_period": "202603"},
                "row_count": 0,
                "rows": [],
            }
        },
    )

    result = _run(run_agent("Show payment status for 202603"))

    assert "get_payment_summary" in result["tools_called"]
    assert result["response"]


# ---------------------------------------------------------------------------
# Test 10 — agent routes payment-exceptions questions
# ---------------------------------------------------------------------------


def test_agent_payment_exceptions_question(monkeypatch: pytest.MonkeyPatch) -> None:
    responses = [
        _FakeResponse(
            content=[
                _FakeToolUseBlock(
                    id="t_exc_1",
                    name="get_payment_exceptions",
                    input={"mon_period": "202603"},
                )
            ],
            stop_reason="tool_use",
        ),
        _FakeResponse(
            content=[
                _FakeTextBlock(
                    "22 DISPUTED dealers identified for 202603 — each linked "
                    "to a Phase 3 inventory mismatch. (Simulated payment data.)"
                )
            ],
            stop_reason="end_turn",
        ),
    ]
    _install_anthropic_mock(monkeypatch, responses=responses)
    _install_tool_executor_mock(
        monkeypatch,
        {
            "get_payment_exceptions": {
                "tool": "get_payment_exceptions",
                "parameters": {"mon_period": "202603"},
                "row_count": 0,
                "rows": [],
            }
        },
    )

    result = _run(
        run_agent("Which dealers have disputed commissions in 202603?")
    )

    assert "get_payment_exceptions" in result["tools_called"]
    assert result["response"]


# ---------------------------------------------------------------------------
# Test 11 — LIVE: KB Section 13 transparency rules
# ---------------------------------------------------------------------------


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
    assert "₦" in text, f"Response did not include a ₦ amount:\n\n{text}"

    # Must mention disputed dealers / commissions.
    assert "disputed" in lower or "dispute" in lower, (
        "Response did not mention disputed:\n\n" + text
    )
