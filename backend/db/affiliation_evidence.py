"""Affiliated dealer codes for one month: codes sharing a recorded dealer name.

A trade partner may hold several account codes. This collector groups codes by
their *recorded* dealer name — an unverified association, not a confirmed
legal entity — and attaches each code's recorded activation commission for one
month. It reuses existing queries only (``get_dealer_summary`` for names and
commission, ``get_dealer_codes`` for set discovery); nothing is recalculated.

A code without an activation record in the month has *unavailable*
commission, never zero. Read-only.
"""
from __future__ import annotations

import re
from math import isfinite
from typing import Any

from backend.db.connection import execute_query
from backend.db import measure_evidence
from backend.db.queries import has_source_period

AFFILIATION_SOURCE = 'Recorded dealer records'
AFFILIATION_TOOLS = ['get_dealer_codes', 'get_dealer_summary']
# The dealer summary read always runs first; code discovery only when an anchor resolves.
SUMMARY_TOOL = ['get_dealer_summary']
# A month is assessable only if at least one affiliation source actually has rows for it.
AFFILIATION_SOURCES = ('fbb_comm_dev_act', 'fbb_comm_orsc')
MAX_ROWS = 100
_PERIOD = re.compile(r'[0-9]{4}(0[1-9]|1[0-2])')
_READ_ERRORS = (ValueError, KeyError, OSError, NotImplementedError)
_ASSOCIATION_NOTE = ('Codes are grouped by recorded dealer name only; this is not a verified '
                     'branch or legal-entity link.')


def _clean(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def _validate(request: dict) -> tuple[str | None, str | None, str]:
    dealer_id = _clean(request.get('dealer_id'))
    dealer_name = _clean(request.get('dealer_name'))
    if (dealer_id is None) == (dealer_name is None):
        raise ValueError('exactly one of dealer_id or dealer_name is required')
    periods = request.get('periods')
    if (not isinstance(periods, list) or len(periods) != 1
            or not isinstance(periods[0], str) or not _PERIOD.fullmatch(periods[0])):
        raise ValueError('periods must contain exactly one YYYYMM value')
    return dealer_id, dealer_name, periods[0]


def _envelope(dealer_id: str | None, dealer_name: str | None, period: str, **values: Any) -> dict:
    envelope = {
        'anchor_type': 'code' if dealer_id is not None else 'name',
        'anchor_id': dealer_id,
        'anchor_query': dealer_name,
        'anchor_name': dealer_name,
        'period': period,
        'status': 'available',
        'found': False,
        'resolved_names': [],
        'rows': [],
        'total_codes': 0,
        'other_count': 0,
        'indicative_total_ngn': 0.0,
        'others_with_commission': 0,
        'others_unavailable': 0,
        'truncated': False,
        'source': AFFILIATION_SOURCE,
        'tools': SUMMARY_TOOL.copy(),
        'note': '',
    }
    envelope.update(values)
    return envelope


def _commission(record: dict | None) -> float | None:
    if record is None:
        return None
    try:
        value = float(record.get('total_commission_ngn'))
    except (TypeError, ValueError):
        return None
    return value if isfinite(value) else None


def _discover(names: list[str], period: str) -> tuple[dict[str, list[str]], int]:
    """Union of codes recorded under any of ``names`` in ``period``, plus the
    lookup-reported set size (the lookup page itself is bounded)."""
    codes: dict[str, list[str]] = {}
    reported = 0
    for name in names:
        lookup = measure_evidence.collect_dealer_codes(
            {'dealer_name': name, 'periods': [period], 'match': 'exact'})
        reported += int(lookup.get('total_codes') or 0)
        for row in lookup.get('rows', []):
            recorded = codes.setdefault(str(row['dealer_id']), [])
            for recorded_name in row.get('recorded_names') or []:
                if recorded_name not in recorded:
                    recorded.append(recorded_name)
    return codes, reported


def _sort_key(row: dict) -> tuple:
    commission = row['commission_ngn']
    return (not row['is_anchor'], commission is None, -(commission or 0.0), row['dealer_id'])


def _month_covered(period: str) -> bool:
    """True when at least one affiliation source actually records the month; missing != zero."""
    return any(has_source_period(source, period) for source in AFFILIATION_SOURCES)


def collect_affiliation(request: dict) -> dict:
    """Codes sharing the anchor's recorded dealer name, with month commission."""
    dealer_id, dealer_name, period = _validate(request)
    tools = SUMMARY_TOOL.copy()  # the summary read is always attempted first
    try:
        frame = execute_query('get_dealer_summary', {'mon_period': period, 'distributor_code': None})
        by_code = {str(record['dealer_id']): record for record in frame.to_dict(orient='records')}
        if not _month_covered(period):
            # No source records cover the month; absence here is uncertainty, not a verified zero.
            return _envelope(dealer_id, dealer_name, period, status='unavailable', anchor_name=None, tools=tools, note=(
                f'No source records cover {period}, so related dealer codes and their commission '
                'cannot be assessed for this month. Missing coverage is not zero.'))
        if dealer_id is not None:
            anchor = by_code.get(dealer_id)
            anchor_name = _clean(anchor.get('dealer_name')) if anchor else None
            if anchor_name is None:
                return _envelope(dealer_id, None, period, anchor_name=None, tools=tools, note=(
                    f'Account {dealer_id} has no recorded activation in {period}, so related codes '
                    'cannot be identified for this month. Missing records are not zero.'))
            resolved_names = [anchor_name]
        else:
            anchor_name = dealer_name
            resolved_names = [dealer_name]
        tools = AFFILIATION_TOOLS.copy()  # code discovery is about to be attempted
        codes, reported = _discover(resolved_names, period)
    except _READ_ERRORS:
        return _envelope(dealer_id, dealer_name, period, status='unavailable', anchor_name=None, tools=tools, note=(
            f'Dealer records for {period} could not be read; related codes and commission are unavailable.'))

    if dealer_id is not None and dealer_id not in codes:
        # The anchor may fall beyond the lookup's first page; include it for display without
        # double-counting, since the lookup's reported total already covers it.
        codes[dealer_id] = [anchor_name]
    rows = []
    for code, recorded_names in codes.items():
        commission = _commission(by_code.get(code))
        rows.append({'dealer_id': code, 'recorded_names': recorded_names,
                     'is_anchor': code == dealer_id,
                     'commission_ngn': commission,
                     'commission_status': 'available' if commission is not None else 'unavailable'})
    rows.sort(key=_sort_key)
    others = [row for row in rows if not row['is_anchor']]
    available = [row['commission_ngn'] for row in others if row['commission_status'] == 'available']
    total_codes = max(len(rows), reported)
    other_count = total_codes - 1 if dealer_id is not None else total_codes
    if not rows:
        note = (f'No account codes are recorded under the name "{dealer_name}" in {period}. '
                'Searches are exact and month-scoped.')
    else:
        note = (f'{_ASSOCIATION_NOTE} Commission is recorded activation commission for {period}; '
                'a code without an activation record that month has unavailable commission, not zero.')
    return _envelope(
        dealer_id, dealer_name, period,
        anchor_name=anchor_name,
        found=total_codes > 0,
        resolved_names=resolved_names,
        rows=rows[:MAX_ROWS],
        total_codes=total_codes,
        other_count=other_count,
        indicative_total_ngn=float(sum(available)),
        others_with_commission=len(available),
        others_unavailable=len(others) - len(available),
        truncated=total_codes > MAX_ROWS,
        tools=tools,  # both the summary read and code discovery ran
        note=note,
    )
