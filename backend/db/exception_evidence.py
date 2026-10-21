"""Atlas evidence for one month's activation and payment exceptions.

Both readers project the computation behind the matching screen; nothing is
re-derived, re-classified or recalculated here. Read-only.

  * **activation_exceptions** — the Activation workspace Exceptions view:
    :func:`backend.db.activation_workspace.collection` with view
    ``exceptions``, ordered by highest finding severity, then dealer code
    (the screen's ``severity`` sort; its default sort is activation count). Finding types, labels and severities are the
    workspace's own.
  * **payment_exceptions** — the Payments Exceptions view: the source-aware
    :func:`backend.db.payment_snapshot.load_payment_snapshot` filtered and
    ordered by :func:`backend.db.payment_snapshot.payment_collection` with
    :data:`EXCEPTION_STATUSES`, outstanding amount largest first, then dealer
    code (the view's default order). This is the ``GET /payments`` read; the
    legacy ``/payments/exceptions`` endpoint is not used.

At most :data:`MAX_LISTED_DEALERS` dealers are listed; counts and aggregates
always cover every matching dealer. An unknown month or unreadable source is
*unavailable*, never "no exceptions"; a dealer with no record in a recorded
month is *not found*.
"""
from __future__ import annotations

import logging
from typing import Any

from backend.db import activation_workspace, payment_snapshot

logger = logging.getLogger(__name__)

ACTIVATION_EXCEPTIONS_SOURCE = "Activation exception checks"
ACTIVATION_EXCEPTIONS_TOOL = "activation_exceptions"
PAYMENT_EXCEPTIONS_SOURCE = "Payment settlement records"
PAYMENT_EXCEPTIONS_TOOL = "payment_exceptions"
MAX_LISTED_DEALERS = 100


def _unavailable(period: str, source: str, tool: str, payload: str, note: str) -> dict[str, Any]:
    return {"period": period, "status": "unavailable", "source": source, "tool": tool,
            "total": None, "truncated": False, "total_rows": 0, "note": note,
            "rows": [], payload: None}


def _known_month(period: str) -> str | None:
    """None when the month is recorded; otherwise the unavailable note."""
    from backend.db import queries

    try:
        known = period in queries.get_available_periods()
    except Exception:
        logger.exception("Exception evidence periods unavailable")
        return "the recorded months could not be read."
    return None if known else "no data is recorded for this month."


def _available(period: str, source: str, tool: str, payload: str, body: dict[str, Any],
               rows: list[dict[str, str]], matching: int | None) -> dict[str, Any]:
    return {"period": period, "status": "available", "source": source, "tool": tool,
            "total": None, "note": "", "truncated": bool(matching and matching > len(rows)),
            "total_rows": len(rows), "rows": rows, payload: body}


# ── Activation ──────────────────────────────────────────────────────────────

def _activation_dealer(row: dict[str, Any]) -> dict[str, Any]:
    return {"dealer_id": row["dealer_id"], "dealer_name": row["dealer_name"],
            "activation_count": int(row["activation_count"]),
            "zero_commission_count": int(row["non_qualified_activation_count"]),
            "findings": [{"type": f["type"], "label": f["label"], "severity": f["severity"]}
                         for f in row["findings"]]}


def _by_finding(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Dealers per finding type, in the workspace's finding order."""
    counts: dict[str, dict[str, Any]] = {}
    for row in rows:
        for finding in row["findings"]:
            entry = counts.setdefault(finding["type"], {
                "type": finding["type"], "label": finding["label"],
                "severity": finding["severity"], "dealer_count": 0})
            entry["dealer_count"] += 1
    rank = activation_workspace._SEVERITY_RANK
    return sorted(counts.values(), key=lambda e: (-rank[e["severity"]], e["type"]))


def activation_exceptions_evidence(period: str, dealer_id: str | None) -> dict[str, Any]:
    """Activation exceptions for ``period``, optionally scoped to one dealer."""
    args = (ACTIVATION_EXCEPTIONS_SOURCE, ACTIVATION_EXCEPTIONS_TOOL, "activation_exceptions")
    note = _known_month(period)
    if note:
        return _unavailable(period, *args, note)
    code = None if dealer_id is None else str(dealer_id).strip()
    try:
        if code is None:
            matching = activation_workspace.collection(
                period, None, "exceptions", "", "", "all", "severity", "desc")["items"]
        else:
            account = activation_workspace.detail(period, None, code)
    except Exception:
        logger.exception("Activation exception evidence unavailable: %s %s", code, period)
        return _unavailable(period, *args, "the activation exception checks could not be read.")

    if code is not None:
        if account is None:
            return _available(period, *args, {
                "dealer_scoped": True, "found": False, "dealer_count": None,
                "finding_count": None, "by_finding": [], "dealers": []}, [], None)
        matching = [account["account"]] if account["account"]["findings"] else []

    dealers = [_activation_dealer(row) for row in matching[:MAX_LISTED_DEALERS]]
    rows = [{"dealer_id": d["dealer_id"], "dealer_name": d["dealer_name"],
             "dimension": d["findings"][0]["severity"],
             "value": "; ".join(f["label"] for f in d["findings"])} for d in dealers]
    body = {"dealer_scoped": code is not None, "found": True,
            "dealer_count": len(matching),
            "finding_count": sum(len(row["findings"]) for row in matching),
            "by_finding": _by_finding(matching), "dealers": dealers}
    return _available(period, *args, body, rows, len(matching))


# ── Payment ─────────────────────────────────────────────────────────────────

def _payment_dealer(record: payment_snapshot.PaymentSummaryRecord) -> dict[str, Any]:
    return {"dealer_id": record.dealer_id, "dealer_name": record.dealer_name,
            "payment_status": record.payment_status,
            "commission_owed": record.commission_owed, "amount_paid": record.amount_paid,
            "amount_unpaid": record.amount_unpaid, "exception_flag": record.exception_flag}


def payment_exceptions_evidence(period: str, dealer_id: str | None) -> dict[str, Any]:
    """Payment exceptions for ``period``, optionally scoped to one dealer."""
    args = (PAYMENT_EXCEPTIONS_SOURCE, PAYMENT_EXCEPTIONS_TOOL, "payment_exceptions")
    note = _known_month(period)
    if note:
        return _unavailable(period, *args, note)
    try:
        summary = payment_snapshot.load_payment_snapshot(period)
        frame = payment_snapshot.payment_collection(
            summary, statuses=set(payment_snapshot.EXCEPTION_STATUSES),
            sort_column="amount_unpaid", direction="desc")
    except Exception:
        logger.exception("Payment exception evidence unavailable: %s", period)
        return _unavailable(period, *args, "the payment records could not be read.")
    if not summary.records:
        return _unavailable(period, *args, "no payment records are recorded for this month.")

    code = None if dealer_id is None else str(dealer_id).strip()
    dealer_status = None
    if code is not None:
        recorded = [r for r in summary.records if str(r.dealer_id) == code]
        if not recorded:
            return _available(period, *args, {
                "dealer_scoped": True, "found": False, "dealer_count": None,
                "outstanding_ngn": None, "status_counts": [], "dealer_status": None,
                "dealers": []}, [], None)
        dealer_status = recorded[0].payment_status
        frame = frame[frame["dealer_id"].astype(str) == code]

    records = [payment_snapshot.row_to_payment_record(row) for row in frame.to_dict(orient="records")]
    counts: dict[str, int] = {}
    for record in records:
        counts[record.payment_status] = counts.get(record.payment_status, 0) + 1
    dealers = [_payment_dealer(record) for record in records[:MAX_LISTED_DEALERS]]
    rows = [{"dealer_id": d["dealer_id"], "dealer_name": d["dealer_name"],
             "dimension": d["payment_status"],
             "value": f"NGN {d['amount_unpaid']:,.2f} outstanding"} for d in dealers]
    body = {"dealer_scoped": code is not None, "found": True, "dealer_count": len(records),
            "outstanding_ngn": round(sum(r.amount_unpaid for r in records), 2),
            "status_counts": [{"status": s, "dealer_count": counts[s]} for s in sorted(counts)],
            "dealer_status": dealer_status, "dealers": dealers}
    return _available(period, *args, body, rows, len(records))
