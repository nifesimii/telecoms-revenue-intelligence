"""Shared payment-data helpers for the audit modules.

Extracted from ``zero_commission_audit`` so ``payment_reconciliation`` (and
any future payment-aware module) can call the same lookup / extraction /
adjacency / coverage helpers without a leaky underscore-import chain.

Public API — anything a caller relies on carries no leading underscore:

  * :data:`PAY_TOLERANCE` — the small-NGN equality tolerance used by every
    "paid in full" / "correctly zero" comparison.
  * :func:`payment_lookup` — per-dealer payment rows for a period, from
    either the simulated CSV path or APDP's ``partner_settlements`` view.
  * :func:`extract_payment` — per-partner (paid, found, status) tuple
    against a payment frame, tolerating the schema difference between
    the two sources.
  * :func:`adjacent_period_payments` — payments to a partner in the
    immediately adjacent periods, for the "near-match" step chain.
  * :func:`payment_source_covers_period` — dataset-coverage check for
    upstream-completeness step chains.
  * :func:`known_periods` — sorted list of periods the data layer knows
    about, used to bound adjacency lookups.

Design note. This module has no notion of a trail or a specific audit
module — it just knows about the payment data. Every audit module reads
these helpers; none of them writes them. If a helper would need
audit-module-specific behaviour, it belongs in that module, not here.
"""
from __future__ import annotations

from typing import Any

import pandas as pd

from backend.db.connection import execute_query

# Small NGN tolerance used across the audit layer for "paid in full" and
# "correctly zero" comparisons. Kept in one place so tolerance changes
# cascade to every module consistently.
PAY_TOLERANCE = 1.0


def payment_lookup(period: str, source: str) -> pd.DataFrame:
    """Per-dealer payment rows for the period, from the active payment source.

    ``source='apdp'`` reads ``normalized.partner_settlements`` (via
    :mod:`backend.db.apdp`) and returns a frame with ``dealer_id`` +
    ``total_settled_ngn``. Any other value falls through to the simulated
    ``get_payment_summary`` query which returns ``distributor_code`` +
    ``amount_paid``. ``extract_payment`` handles the schema difference.
    """
    if source == "apdp":
        from backend.db import apdp as apdp_db
        rows = apdp_db.get_partner_settlements(period)
        return pd.DataFrame(rows)
    return execute_query("get_payment_summary", {"mon_period": period})


def extract_payment(
    payment_df: pd.DataFrame, partner_code: str, source: str
) -> tuple[float, bool, str | None]:
    """Return ``(amount_paid, found, status)`` for one partner in the frame.

    Empty frame → ``(0.0, False, None)``; not found → same. Column names
    differ per source: ``dealer_id`` / ``total_settled_ngn`` /
    ``reconciliation_status`` on APDP, ``distributor_code`` / ``amount_paid``
    / ``payment_status`` on the simulated path.
    """
    if payment_df is None or payment_df.empty:
        return 0.0, False, None
    code_col = "dealer_id" if source == "apdp" else "distributor_code"
    paid_col = "total_settled_ngn" if source == "apdp" else "amount_paid"
    status_col = "reconciliation_status" if source == "apdp" else "payment_status"
    if code_col not in payment_df.columns:
        return 0.0, False, None
    match = payment_df[payment_df[code_col].astype(str) == str(partner_code)]
    if match.empty:
        return 0.0, False, None
    row = match.iloc[0]
    paid = float(row.get(paid_col) or 0.0)
    status = str(row.get(status_col)) if status_col in match.columns else None
    return paid, True, status


def adjacent_periods_for(period: str, all_periods: list[str] | None) -> list[str]:
    """Return the periods immediately before and after ``period`` in the
    sorted ``all_periods`` list. Empty when the period is unknown or the
    list is empty.

    Split out so an orchestrator can pre-fetch adjacent payment frames
    once per run instead of every helper re-computing the neighbour set.
    """
    if not all_periods:
        return []
    ordered = sorted(str(p) for p in all_periods)
    try:
        idx = ordered.index(str(period))
    except ValueError:
        return []
    return [ordered[j] for j in (idx - 1, idx + 1) if 0 <= j < len(ordered)]


def adjacent_period_payments(
    partner_code: str,
    period: str,
    source: str,
    all_periods: list[str] | None,
    *,
    adjacent_frames: dict[str, pd.DataFrame] | None = None,
) -> list[dict[str, Any]]:
    """Payments to this partner in the immediately adjacent periods.

    ``all_periods`` is the sorted set of periods the data layer knows
    about — see :func:`known_periods`. Missing / empty ``all_periods``
    returns ``[]`` (adjacency is undefined without context).

    ``adjacent_frames`` is an optional pre-fetched ``{period: payment_df}``
    cache. When supplied, the helper avoids per-partner ``payment_lookup``
    round-trips — an orchestrator processing N partners can pre-fetch two
    adjacent periods once and pay 2 lookups total instead of 2·N. When
    absent, the helper falls back to fetching on demand (kept so
    single-partner callers and tests don't need to wire the cache).

    Only payments strictly above :data:`PAY_TOLERANCE` are returned —
    below that they're indistinguishable from noise.
    """
    neighbours = adjacent_periods_for(period, all_periods)
    if not neighbours:
        return []

    out: list[dict[str, Any]] = []
    for p in neighbours:
        if adjacent_frames is not None and p in adjacent_frames:
            df = adjacent_frames[p]
        else:
            df = payment_lookup(p, source)
        paid, found, status = extract_payment(df, partner_code, source)
        if found and paid > PAY_TOLERANCE:
            out.append({"period": p, "amount_paid_ngn": paid, "status": status})
    return out


def prefetch_adjacent_frames(
    period: str, source: str, all_periods: list[str] | None,
) -> dict[str, pd.DataFrame]:
    """Pre-fetch payment frames for every period adjacent to ``period``.

    Convenience for run_period orchestrators: one call, one dict, then
    thread it into every :func:`adjacent_period_payments` call.
    """
    return {p: payment_lookup(p, source) for p in adjacent_periods_for(period, all_periods)}


def payment_source_covers_period(
    payment_df: pd.DataFrame, period: str, source: str
) -> bool:
    """True if the payment dataset has any rows for this period.

    The simulated path carries ``report_month``; APDP carries
    ``settlement_period``. If neither column exists (the frame is already
    period-scoped from an upstream filter), non-empty means covered.
    """
    _ = source  # signature parity — column names cover both sources below
    if payment_df is None or payment_df.empty:
        return False
    for col in ("report_month", "settlement_period"):
        if col in payment_df.columns:
            return (payment_df[col].astype(str) == str(period)).any()
    return not payment_df.empty


def known_periods() -> list[str]:
    """Sorted list of periods the data layer knows about.

    Best-effort — a missing data layer returns ``[]`` (adjacency lookups
    will then early-return empty, not crash).
    """
    try:
        from backend.db import queries
        return [str(p) for p in queries.get_available_periods()]
    except Exception:
        return []
