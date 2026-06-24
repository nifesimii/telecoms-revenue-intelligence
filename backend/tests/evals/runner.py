"""Agent eval runner.

Loads ``golden.jsonl``, dispatches every case through ``run_agent()``,
and asserts per-case invariants. Returns a structured report so the
pytest wrapper and the standalone CLI share the same logic.

This is INTENTIONALLY opt-in — every case is a real Anthropic API call.
Run via:

    RUN_EVALS=1 python -m pytest backend/tests/test_evals.py -v

…or as a standalone CLI:

    python -m backend.tests.evals.runner [--filter <category>]

Invariant grammar per case (all optional):
    must_call_tools      — list[str]; every name must appear in tools_called
    must_not_call_tools  — list[str]; none may appear
    must_mention_any     — list[str]; response (case-insensitive) must contain ≥1
    must_mention_all     — list[str]; response (case-insensitive) must contain all
    must_not_mention     — list[str]; response must contain none
    min_response_chars   — int; response must be at least this long
"""
from __future__ import annotations

import argparse
import asyncio
import json
import os
import sys
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

# Ensure backend modules import correctly regardless of cwd.
ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT))

# Force sample-data mode so tools work without Presto.
os.environ.setdefault("USE_SAMPLE_DATA", "true")

from backend.agent.agent import run_agent  # noqa: E402


GOLDEN_PATH = Path(__file__).parent / "golden.jsonl"


@dataclass
class CaseResult:
    case_id: str
    category: str
    passed: bool
    errors: list[str] = field(default_factory=list)
    duration_s: float = 0.0
    tools_called: list[str] = field(default_factory=list)
    response_preview: str = ""


def _load_cases(filter_category: str | None = None) -> list[dict[str, Any]]:
    cases: list[dict[str, Any]] = []
    with GOLDEN_PATH.open() as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith("//"):
                continue
            case = json.loads(line)
            if filter_category and case.get("category") != filter_category:
                continue
            cases.append(case)
    return cases


def _check_invariants(case: dict[str, Any], response_text: str,
                      tools_called: list[str]) -> list[str]:
    errors: list[str] = []
    lower = (response_text or "").lower()

    for required in case.get("must_call_tools", []):
        if required not in tools_called:
            errors.append(f"missing tool call: {required} (got {tools_called})")

    for forbidden in case.get("must_not_call_tools", []):
        if forbidden in tools_called:
            errors.append(f"unexpected tool call: {forbidden}")

    must_any = case.get("must_mention_any")
    if must_any:
        if not any(m.lower() in lower for m in must_any):
            errors.append(f"must mention any of {must_any}")

    must_all = case.get("must_mention_all")
    if must_all:
        missing = [m for m in must_all if m.lower() not in lower]
        if missing:
            errors.append(f"must mention all but missing: {missing}")

    for forbidden in case.get("must_not_mention", []):
        if forbidden.lower() in lower:
            errors.append(f"forbidden mention present: '{forbidden}'")

    min_chars = case.get("min_response_chars", 0)
    if len(response_text or "") < min_chars:
        errors.append(
            f"response too short: {len(response_text or '')} < {min_chars} chars"
        )

    return errors


async def _run_one(case: dict[str, Any]) -> CaseResult:
    start = time.monotonic()
    try:
        result = await run_agent(
            user_message=case["question"],
            conversation_history=[],
            mon_period=case.get("mon_period"),
        )
        elapsed = time.monotonic() - start
        response_text = getattr(result, "response", None) or ""
        tools_called = list(getattr(result, "tools_called", []) or [])
        errors = _check_invariants(case, response_text, tools_called)
        return CaseResult(
            case_id=case["id"],
            category=case.get("category", "uncategorized"),
            passed=not errors,
            errors=errors,
            duration_s=elapsed,
            tools_called=tools_called,
            response_preview=(response_text or "")[:160].replace("\n", " "),
        )
    except Exception as e:
        return CaseResult(
            case_id=case["id"],
            category=case.get("category", "uncategorized"),
            passed=False,
            errors=[f"exception during run_agent: {type(e).__name__}: {e}"],
            duration_s=time.monotonic() - start,
        )


async def run_all(filter_category: str | None = None,
                  parallel: int = 3) -> list[CaseResult]:
    """Run every case with bounded parallelism. Default 3 concurrent runs
    keeps Anthropic rate limits comfortable."""
    cases = _load_cases(filter_category)
    if not cases:
        return []

    sem = asyncio.Semaphore(parallel)

    async def _bounded(case):
        async with sem:
            return await _run_one(case)

    return await asyncio.gather(*[_bounded(c) for c in cases])


def _format_report(results: list[CaseResult]) -> str:
    passed = sum(1 for r in results if r.passed)
    failed = len(results) - passed
    total_time = sum(r.duration_s for r in results)
    lines = [
        f"\n{'=' * 70}",
        f"  Agent eval suite — {passed}/{len(results)} passed · {total_time:.1f}s",
        f"{'=' * 70}",
    ]
    by_cat: dict[str, list[CaseResult]] = {}
    for r in results:
        by_cat.setdefault(r.category, []).append(r)
    for cat, items in sorted(by_cat.items()):
        ok = sum(1 for r in items if r.passed)
        lines.append(f"\n  {cat}: {ok}/{len(items)}")
        for r in items:
            mark = "✓" if r.passed else "✗"
            lines.append(f"    {mark} {r.case_id} ({r.duration_s:.1f}s)")
            if not r.passed:
                for e in r.errors:
                    lines.append(f"        · {e}")
                if r.response_preview:
                    lines.append(f"        preview: {r.response_preview}")
    lines.append("")
    lines.append(f"  {'PASS' if failed == 0 else 'FAIL'}: {passed}/{len(results)}")
    lines.append("=" * 70)
    return "\n".join(lines)


def main() -> int:
    parser = argparse.ArgumentParser(description="Run the agent eval suite.")
    parser.add_argument("--filter", help="Only run cases in this category")
    parser.add_argument("--parallel", type=int, default=3,
                        help="Bounded parallelism (default 3)")
    args = parser.parse_args()

    results = asyncio.run(run_all(args.filter, args.parallel))
    print(_format_report(results))
    return 0 if all(r.passed for r in results) else 1


if __name__ == "__main__":
    sys.exit(main())
