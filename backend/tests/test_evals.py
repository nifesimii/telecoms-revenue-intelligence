"""Opt-in pytest wrapper around the agent eval suite.

Skipped unless ``RUN_EVALS=1`` (or ``ANTHROPIC_RUN_EVALS=1``) is set,
since each case is a real Anthropic API call and burns credits.

    RUN_EVALS=1 python -m pytest backend/tests/test_evals.py -v

Each golden case becomes its own pytest test via parametrize, so the
output reports per-case pass/fail clearly. Cases run sequentially in
the pytest path (parallel only available via the standalone runner).
"""
from __future__ import annotations

import asyncio
import os

import pytest

from backend.tests.evals.runner import _check_invariants, _load_cases, _run_one


_ENABLED = os.getenv("RUN_EVALS") == "1" or os.getenv("ANTHROPIC_RUN_EVALS") == "1"
_EVAL_SKIP_REASON = "agent evals are opt-in (set RUN_EVALS=1 to run; each case is a real API call)"

# Always load cases so the parametrize id list is stable. The skip happens
# per-test below so the cheap loader / invariant tests still run by default.
CASES = _load_cases()


@pytest.mark.skipif(not _ENABLED, reason=_EVAL_SKIP_REASON)
@pytest.mark.parametrize(
    "case",
    CASES,
    ids=[c["id"] for c in CASES] if CASES else [],
)
def test_agent_eval_case(case):
    """One pytest test per golden case."""
    result = asyncio.run(_run_one(case))
    assert result.passed, (
        f"{case['id']} failed:\n  "
        + "\n  ".join(result.errors)
        + (f"\nResponse: {result.response}" if result.response else "")
    )


def test_runner_loads_at_least_15_cases():
    """Sanity guard: catch accidental deletion of the golden file."""
    cases = _load_cases()
    assert len(cases) >= 15, f"expected ≥15 eval cases, got {len(cases)}"
    # Every case has an id + question
    for c in cases:
        assert "id" in c and "question" in c, f"malformed case: {c}"


def test_invariant_checker_logic():
    """Sanity test for the invariant checker without hitting the API."""
    case = {
        "must_call_tools": ["get_dealer_summary"],
        "must_mention_any": ["NGN"],
        "must_not_mention": ["$"],
        "min_response_chars": 10,
    }
    # Passing case
    assert _check_invariants(case, "Dealer earned NGN 100.00", ["get_dealer_summary"]) == []
    # Missing tool
    errs = _check_invariants(case, "Dealer earned NGN 100.00", [])
    assert any("missing tool" in e for e in errs)
    # Missing mention
    errs = _check_invariants(case, "Dealer earned 100", ["get_dealer_summary"])
    assert any("must mention any" in e for e in errs)
    # Forbidden mention
    errs = _check_invariants(case, "Dealer earned NGN 100.00 ($50)", ["get_dealer_summary"])
    assert any("forbidden" in e for e in errs)
    # Too short
    errs = _check_invariants(case, "NGN 1", ["get_dealer_summary"])
    assert any("too short" in e for e in errs)


@pytest.mark.parametrize("with_context", [False, True])
def test_runner_uses_public_agent_contract_and_preserves_answer(monkeypatch, with_context):
    from backend.tests.evals import runner

    history = [{"role": "user", "content": "By sales I mean activations."}]
    case = {
        "id": "follow-up", "question": "How many this month?", "mon_period": "202603",
        "must_call_tools": ["get_dealer_summary"], "must_mention_all": ["806"],
    }
    if with_context:
        case.update(conversation_history=history, investigation_context="Dealer account 74050")
    answer = "806 activations.\n" + "Source evidence remains available. " * 8

    async def fake_agent(user_message, conversation_history=None, *,
                         reporting_period=None, investigation_context=None):
        assert user_message == case["question"]
        assert reporting_period == "202603"
        assert conversation_history == (history if with_context else [])
        assert investigation_context == ("Dealer account 74050" if with_context else None)
        return {"response": answer, "tools_called": ["get_dealer_summary"], "raw_data": {}}

    monkeypatch.setattr(runner, "run_agent", fake_agent)
    result = asyncio.run(runner._run_one(case))
    assert result.passed, result.errors
    assert result.tools_called == ["get_dealer_summary"]
    assert result.response == answer
    assert result.response_preview == answer[:160].replace("\n", " ")


def test_runner_reports_failed_invariants_from_dictionary_response(monkeypatch):
    from backend.tests.evals import runner

    async def fake_agent(*args, **kwargs):
        return {"response": "Unsupported claim", "tools_called": [], "raw_data": {}}

    monkeypatch.setattr(runner, "run_agent", fake_agent)
    result = asyncio.run(runner._run_one({
        "id": "failed-answer", "question": "Explain", "must_not_mention": ["Unsupported"],
    }))
    assert not result.passed
    assert result.errors == ["forbidden mention present: 'Unsupported'"]
    assert result.response == "Unsupported claim"


def test_runner_never_passes_agent_error_fallback(monkeypatch):
    from backend.agent.agent import FALLBACK_RESPONSE
    from backend.tests.evals import runner

    async def fake_agent(*args, **kwargs):
        return {"response": FALLBACK_RESPONSE, "tools_called": [], "raw_data": {}}

    monkeypatch.setattr(runner, "run_agent", fake_agent)
    result = asyncio.run(runner._run_one({"id": "fallback", "question": "Explain"}))
    assert not result.passed
    assert "agent returned retrieval error fallback" in result.errors


@pytest.mark.parametrize('sample,payment_source', [(False, 'simulated'), (True, 'apdp')])
def test_runner_rejects_live_data_configuration_before_model_call(monkeypatch, sample, payment_source):
    from backend import config
    from backend.tests.evals import runner

    monkeypatch.setattr(config, 'USE_SAMPLE_DATA', sample)
    monkeypatch.setattr(config, 'PAYMENT_SOURCE', payment_source)

    async def unexpected_agent(*args, **kwargs):
        pytest.fail('Unsafe evaluation reached the model')

    monkeypatch.setattr(runner, 'run_agent', unexpected_agent)
    result = asyncio.run(runner._run_one({'id': 'unsafe-config', 'question': 'Explain'}))
    assert not result.passed
    assert any('USE_SAMPLE_DATA=true and PAYMENT_SOURCE=simulated' in error for error in result.errors)
