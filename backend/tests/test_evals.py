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
        + (f"\nResponse: {result.response_preview}" if result.response_preview else "")
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
