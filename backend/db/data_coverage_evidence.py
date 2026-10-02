"""Atlas evidence for one month's data coverage gaps.

Projects the two collectors behind the data coverage ticket
(:mod:`backend.db.data_coverage`) into the period evidence contract. Every
figure is the collector's own: nothing is re-added, re-derived or recalculated
here. Read-only.

Two gaps are checked:

  * **profile_class** — dealers whose ``account_profile_class`` is not
    recorded. Per the KB this comes from a missing customer-master entry; it
    is not a snapshot miss.
  * **invoice** — dealers with activations but no IFS invoice record.

What this layer adds is the distinction the collectors cannot express on their
own: an unknown month or an unreadable source is *unavailable*; a gap whose
collector failed is reported as unavailable, never as zero dealers; a dealer
with no activation records in a recorded month is *not found*.
"""
from __future__ import annotations

import logging
from typing import Any, Callable

from backend import config
from backend.db import connection, data_coverage

logger = logging.getLogger(__name__)

DATA_COVERAGE_SOURCE = "Data coverage checks"
DATA_COVERAGE_TOOL = "data_coverage"
MAX_LISTED_DEALERS = 20


def _unavailable(period: str, note: str) -> dict[str, Any]:
    return {"period": period, "status": "unavailable",
            "source": DATA_COVERAGE_SOURCE, "tool": DATA_COVERAGE_TOOL,
            "total": None, "truncated": False, "total_rows": 0, "note": note,
            "rows": [], "coverage": None}


def _profile_class_row(dealer: dict[str, Any]) -> dict[str, str]:
    return {"dealer_id": dealer["dealer_id"], "dealer_name": dealer["dealer_name"],
            "dimension": "Account profile class not recorded",
            "value": f"{dealer['total_activations']:,} activations, "
                     f"{dealer['zero_commission_count']:,} zero-commission"}


def _invoice_row(dealer: dict[str, Any]) -> dict[str, str]:
    return {"dealer_id": dealer["dealer_id"], "dealer_name": dealer["dealer_name"],
            "dimension": "No IFS invoice record",
            "value": f"{dealer['activation_count']:,} activations across "
                     f"{dealer['affected_products']:,} products"}


# Order matters: profile_class is listed before invoice in "gaps" and rows.
_GAPS: tuple[tuple[str, Callable[[str], list[dict[str, Any]]],
                   Callable[[dict[str, Any]], dict[str, str]]], ...] = (
    ("profile_class", lambda p: data_coverage.collect_profile_class_missing(p), _profile_class_row),
    ("invoice", lambda p: data_coverage.collect_ifs_missing(p), _invoice_row),
)


def data_coverage_evidence(period: str, dealer_id: str | None) -> dict[str, Any]:
    """Coverage gaps for ``period``, optionally scoped to one dealer."""
    from backend.db import queries

    try:
        known = period in queries.get_available_periods()
    except Exception:
        logger.exception("Data coverage periods unavailable")
        return _unavailable(period, "the recorded months could not be read.")
    if not known:
        return _unavailable(period, "no data is recorded for this month.")

    base = {"period": period, "status": "available",
            "source": DATA_COVERAGE_SOURCE, "tool": DATA_COVERAGE_TOOL,
            "total": None, "note": ""}
    sample_data = bool(config.USE_SAMPLE_DATA)
    code = None if dealer_id is None else str(dealer_id).strip()
    if code is not None:
        try:
            activity = connection.execute_query(
                "get_dealer_summary", {"mon_period": period, "distributor_code": code})
        except Exception:
            logger.exception("Data coverage dealer activity unavailable: %s %s", code, period)
            return _unavailable(period, "the dealer's activation records could not be read.")
        if activity.empty:
            return {**base, "truncated": False, "total_rows": 0, "rows": [],
                    "coverage": {"dealer_scoped": True, "found": False,
                                 "sample_data": sample_data, "gaps": None}}

    gaps: dict[str, dict[str, Any]] = {}
    rows: list[dict[str, str]] = []
    for name, collect, to_row in _GAPS:
        try:
            dealers = collect(period)
        except Exception:
            logger.exception("Data coverage %s collector failed: %s", name, period)
            gaps[name] = {"status": "unavailable", "dealer_count": None, "dealers": []}
            continue
        if code is not None:
            dealers = [d for d in dealers if str(d["dealer_id"]) == code]
        listed = dealers[:MAX_LISTED_DEALERS]
        gaps[name] = {"status": "checked", "dealer_count": len(dealers), "dealers": listed}
        rows.extend(to_row(dealer) for dealer in listed)

    if all(gap["status"] == "unavailable" for gap in gaps.values()):
        return _unavailable(period, "the coverage sources could not be read.")

    truncated = any(gap["status"] == "checked" and gap["dealer_count"] > len(gap["dealers"])
                    for gap in gaps.values())
    return {**base, "truncated": truncated, "total_rows": len(rows), "rows": rows,
            "coverage": {"dealer_scoped": code is not None, "found": True,
                         "sample_data": sample_data, "gaps": gaps}}
