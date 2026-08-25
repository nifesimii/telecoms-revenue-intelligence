"""Phase 3 — agent tests for Inventory Assurance.

Test 9 is a mocked routing check. Test 10 is a live API call to confirm the
KB Section 12 language rules reach the model.
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


# ---------------------------------------------------------------------------
# Fake content blocks (same shape as test_agent.py / test_activation_agent.py)
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
# Test 9 — agent routes inventory questions to get_inventory_comparison
# ---------------------------------------------------------------------------


def test_agent_inventory_question(monkeypatch: pytest.MonkeyPatch) -> None:
    responses = [
        _FakeResponse(
            content=[
                _FakeToolUseBlock(
                    id="t_inv_1",
                    name="get_inventory_comparison",
                    input={"mon_period": "202603"},
                )
            ],
            stop_reason="tool_use",
        ),
        _FakeResponse(
            content=[
                _FakeTextBlock(
                    "Found 24 CONFIRMED_MISMATCH records; top dealer is "
                    "Tivos Technology Ltd at 118 activations vs 60 purchased."
                )
            ],
            stop_reason="end_turn",
        ),
    ]
    _install_anthropic_mock(monkeypatch, responses=responses)
    _install_tool_executor_mock(
        monkeypatch,
        {
            "get_inventory_comparison": {
                "tool": "get_inventory_comparison",
                "parameters": {"mon_period": "202603"},
                "row_count": 1,
                "rows": [],
            }
        },
    )

    result = _run(run_agent("Show inventory comparison for 202603"))

    assert "get_inventory_comparison" in result["tools_called"]
    assert result["response"]
    assert "get_inventory_comparison" in result["raw_data"]


# ---------------------------------------------------------------------------
# Test 10 — LIVE: KB Section 12 language rules and CONFIRMED_MISMATCH framing
# ---------------------------------------------------------------------------


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
