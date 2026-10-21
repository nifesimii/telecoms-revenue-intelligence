"""Atlas evidence for one dealer-month statement.

Projects :func:`backend.db.dealer_statement.compose_dealer_statement` (the
composer behind ``GET /dealers/{id}/statement``) into the dealer-month
evidence contract. Every figure is the composer's own: nothing is re-added,
re-derived or recalculated here. Read-only.

What this layer adds is the distinction the composer cannot express on its
own: an unknown month or an unreadable source is *unavailable*; a dealer with
no activation records in a recorded month is *no recorded activity*; a
missing payment record or an unreadable audit store is reported per component,
never as zero.
"""
from __future__ import annotations

import logging
from typing import Any

from backend import config
from backend.db.dealer_statement import compose_dealer_statement

logger = logging.getLogger(__name__)

DEALER_STATEMENT_SOURCE = "Dealer statement"
DEALER_STATEMENT_TOOL = "dealer_statement"


def payment_source_label() -> str:
    """Neutral display name for the configured payment source."""
    return "APDP settlement records" if config.PAYMENT_SOURCE == "apdp" else "Payment records"


def _unavailable(period: str, note: str) -> dict[str, Any]:
    return {"period": period, "status": "unavailable",
            "source": DEALER_STATEMENT_SOURCE, "tool": DEALER_STATEMENT_TOOL,
            "total": None, "truncated": False, "total_rows": 0, "note": note,
            "rows": [], "statement": None}


def _audit_store_readable() -> bool:
    try:
        from backend.db import audit_store
        return bool(audit_store.healthcheck())
    except Exception:
        return False


def _payment_source_readable() -> bool:
    if config.PAYMENT_SOURCE != "apdp":
        return True
    try:
        from backend.db import apdp
        return bool(apdp.healthcheck())
    except Exception:
        return False


def _ngn(value: float) -> str:
    return f"NGN {value:,.2f}"


def dealer_statement_evidence(period: str, dealer_id: str | None) -> dict[str, Any]:
    """One dealer's statement for ``period``: owed, paid, outstanding, evidence."""
    if dealer_id is None:
        return _unavailable(period, "a dealer account is needed; select or name one.")
    from backend.db import queries

    try:
        known = period in queries.get_available_periods()
    except Exception:
        logger.exception("Dealer statement periods unavailable")
        return _unavailable(period, "the recorded months could not be read.")
    if not known:
        return _unavailable(period, "no data is recorded for this month.")
    code = str(dealer_id).strip()
    try:
        composed = compose_dealer_statement(code, period)
    except Exception:
        logger.exception("Dealer statement unavailable: %s %s", code, period)
        if not _payment_source_readable():
            reason = f"the payment source ({payment_source_label()}) could not be read"
        else:
            reason = "a statement source could not be read"
        return _unavailable(period, f"{reason}; amounts owed, paid and outstanding are unavailable.")

    base = {"period": period, "status": "available",
            "source": DEALER_STATEMENT_SOURCE, "tool": DEALER_STATEMENT_TOOL,
            "total": None, "truncated": False, "note": ""}
    if not composed.get("found"):
        return {**base, "total_rows": 0, "rows": [], "statement": {"found": False}}

    name = composed["dealer_name"]
    commission, payment, position = composed["commission"], composed["payment"], composed["position"]
    orsc = composed["orsc"]
    subscription, combined = composed["subscription_commission"], composed["combined"]
    trails = composed["audit_trails"]
    statement = {
        "found": True,
        "dealer_name": name,
        "account_profile_class": composed["account_profile_class"],
        "commission": {key: commission[key] for key in (
            "expected_ngn", "total_activations", "qualified_activation_count",
            "zero_commission_count", "by_denomination")},
        "orsc": None if orsc is None else {key: orsc[key] for key in (
            "device_count", "total_subscription_amount_ngn", "zero_amount_count")},
        "orsc_status": composed["orsc_status"],
        # Amounts and record count only: statement/settlement references stay internal.
        "subscription_commission": {key: subscription[key] for key in (
            "status", "owed_ngn", "paid_ngn", "outstanding_ngn", "record_count")},
        "combined": {key: combined[key] for key in (
            "includes_subscription", "owed_ngn", "paid_ngn", "outstanding_ngn")},
        "payment": {"source": payment_source_label(),
                    "payment_found": payment["payment_found"],
                    "amount_paid_ngn": payment["amount_paid_ngn"],
                    "payment_status": payment["payment_status"]},
        "position": {key: position[key] for key in (
            "expected_ngn", "paid_ngn", "outstanding_ngn", "variance_pct", "headline")},
        # Conclusions only: step-level evidence belongs to the verification measure.
        "audit": {"readable": bool(trails) or _audit_store_readable(),
                  "trails": [{"module": t["module"], "label": t["label"],
                              "conclusion": t["conclusion"]} for t in trails]},
    }

    def row(dimension: str, value: str) -> dict[str, str]:
        return {"dealer_id": code, "dealer_name": name, "dimension": dimension, "value": value}

    rows = [row(f"Activation commission · {denomination}", _ngn(amount))
            for denomination, amount in commission["by_denomination"].items()]
    rows.append(row("Activation commission (amount owed)", _ngn(commission["expected_ngn"])))
    if payment["payment_found"]:
        rows.append(row("Activation commission paid", _ngn(position["paid_ngn"])))
        rows.append(row("Activation commission outstanding", _ngn(position["outstanding_ngn"])))
    if subscription["status"] == "recorded":
        rows.append(row("Subscription commission (amount owed)", _ngn(subscription["owed_ngn"])))
        rows.append(row("Subscription commission paid", _ngn(subscription["paid_ngn"])))
        rows.append(row("Subscription commission outstanding", _ngn(subscription["outstanding_ngn"])))
    scope = "" if combined["includes_subscription"] else " (activation only)"
    rows.append(row(f"Total amount owed{scope}", _ngn(combined["owed_ngn"])))
    if combined["paid_ngn"] is not None:
        rows.append(row(f"Total amount paid{scope}", _ngn(combined["paid_ngn"])))
        rows.append(row(f"Total amount outstanding{scope}", _ngn(combined["outstanding_ngn"])))
    if orsc is not None:
        rows.append(row("Subscription revenue (not part of amount owed)",
                        _ngn(orsc["total_subscription_amount_ngn"])))
    return {**base, "total_rows": len(rows), "rows": rows, "statement": statement}
