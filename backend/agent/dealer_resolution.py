"""Resolve a dealer named in a measure question to one recorded dealer code.

The model copies the name as written; it never supplies a code. Resolution
uses the recorded name/code lookup for the request's months: an exact
(case-insensitive, whitespace-normalised) name first, otherwise names that
contain it. Exactly one code proceeds. None, several, or an unreadable source
yields an application-written answer and no evidence read.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable, Literal

from backend.agent import tool_executor
from backend.agent.measure_response import _text

MAX_CANDIDATES = 5

Status = Literal['matched', 'none', 'ambiguous', 'unavailable']


@dataclass(frozen=True)
class DealerResolution:
    status: Status
    text: str
    dealer_id: str | None = None
    lookup: dict[str, Any] | None = None


def _span(periods: list[str]) -> list[str]:
    """Every month between the earliest and latest requested month (the lookup needs a contiguous range)."""
    if not periods:
        return []
    indices = [int(p[:4]) * 12 + int(p[4:]) - 1 for p in periods]
    return [f'{i // 12:04d}{i % 12 + 1:02d}' for i in range(min(indices), max(indices) + 1)]


def _months(periods: list[str]) -> str:
    return ', '.join(sorted(periods)) if periods else 'the available months'


def _candidate(row: dict) -> tuple[str, str]:
    return ' / '.join(row['recorded_names']), str(row['dealer_id'])


def resolve_dealer_name(request: dict, lookup: Callable[[dict], dict] | None = None) -> DealerResolution:
    """Resolve request['dealer_name'] for request['periods']; never picks among several dealers."""
    lookup = lookup or tool_executor.execute_dealer_lookup
    name = ' '.join(request['dealer_name'].split())
    periods = list(request.get('periods') or [])
    quoted = f'“{_text(name)}”'
    try:
        evidence = None
        for match in ('exact', 'contains'):
            evidence = lookup({'dealer_name': name, 'periods': _span(periods), 'match': match})
            if evidence['rows']:
                break
    except Exception:
        return DealerResolution('unavailable', (
            f'The dealer name {quoted} could not be resolved because the dealer records for '
            f'{_months(periods)} could not be read; give the dealer code to continue.'))
    rows = evidence['rows']
    total = evidence.get('total_codes', len(rows))
    if not rows:
        return DealerResolution('none', (
            f'No dealer named {quoted} is recorded for {_months(periods)}; '
            'give the dealer code or the full recorded name.'), lookup=evidence)
    if total == 1 and len(rows) == 1:
        recorded, code = _candidate(rows[0])
        return DealerResolution('matched', f'Matched {quoted} to {_text(recorded)} \\({_text(code)}\\).',
                                dealer_id=code, lookup=evidence)
    shown = [_candidate(row) for row in rows[:MAX_CANDIDATES]]
    header = f'Several recorded dealers match {quoted} for {_months(periods)}'
    header += f' ({total:,} in total; showing {len(shown)}).' if total > MAX_CANDIDATES else '.'
    listing = '\n'.join(f'- {_text(recorded)} \\({_text(code)}\\)' for recorded, code in shown)
    return DealerResolution('ambiguous', '\n\n'.join([
        header, listing, 'Which dealer do you mean? Give the dealer code.']), lookup=evidence)
