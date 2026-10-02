"""Per-period dealer statement composer — Finance/RA internal view.

Answers the question: *"For dealer X in period Y, what did we owe them,
what did we pay, what's the variance, and which audit trails support
that verdict?"* All from a single call.

Sits on top of the existing query + audit layers — this is a formatter,
not a new data source. Reads:

  * ``get_dealer_summary`` — activation-side entitlement (commission owed)
  * ``get_orsc_summary`` — subscription revenue (informational, never owed)
  * ``subscription_evidence.summaries`` — subscription commission owed,
    settled and outstanding, a settlement separate from activation
  * ``payment_data.payment_lookup`` — activation settlement-side (respects
    ``PAYMENT_SOURCE=apdp|simulated``)

``combined`` is a plain sum of the two commission types; it includes
subscription commission only when that is recorded for the dealer-month.
  * ``audit_store`` — persisted verification trails for the same
    (dealer, period), so the statement links out to the audit evidence
    behind each number

Finance-internal tone: shows system-y detail (data source badges, trail
ids, run ids). If a dealer-facing variant is needed later, wrap this
composer with a stripped-down formatter — the underlying joins stay
the same.
"""
from __future__ import annotations

from typing import Any

import pandas as pd

from backend import config
from backend.audit.payment_data import extract_payment, payment_lookup
from backend.db.connection import execute_query


def _safe_float(v: Any) -> float:
    try:
        if v is None or (isinstance(v, float) and pd.isna(v)):
            return 0.0
        return float(v)
    except (TypeError, ValueError):
        return 0.0


def _safe_int(v: Any) -> int:
    try:
        if v is None or (isinstance(v, float) and pd.isna(v)):
            return 0
        return int(v)
    except (TypeError, ValueError):
        return 0


def compose_dealer_statement(dealer_id: str, mon_period: str) -> dict[str, Any]:
    """Build the per-period statement dict for one dealer.

    Returns ``{"found": False, ...}`` if the dealer isn't in the
    activation summary for the period. That shape lets the endpoint
    layer render a clean 404 without a separate DB round-trip.

    ``payment_source`` on the response reflects whichever source the
    platform is currently reading (config.PAYMENT_SOURCE) — the
    reconciliation numbers change accordingly, and the UI can badge the
    statement so a finance reviewer knows they're looking at live or
    simulated data.
    """
    dealer_id = str(dealer_id).strip()
    mon_period = str(mon_period).strip()

    # ── 1. Commission entitlement (activation side) ───────────────────────
    summary_df = execute_query(
        "get_dealer_summary",
        {"mon_period": mon_period, "distributor_code": dealer_id},
    )
    if summary_df.empty:
        return {"found": False, "dealer_id": dealer_id, "mon_period": mon_period}

    row = summary_df.iloc[0]
    dealer_name = str(row.get("dealer_name") or dealer_id)
    profile_class = str(row.get("account_profile_class") or "")
    total_activations = _safe_int(row.get("total_activations"))
    zero_commission_count = _safe_int(row.get("zero_commission_count"))
    qualified = max(0, total_activations - zero_commission_count)
    expected_commission = round(_safe_float(row.get("total_commission_ngn")), 2)
    commission_by_denom = dict(row.get("commission_by_denomination") or {})

    # ── 2. Subscription revenue (informational — not part of any amount owed) ─
    # ``orsc`` keeps its historical shape (None when absent); ``orsc_status``
    # says *why* it is absent so callers never read an unreadable source as "none".
    orsc_info, orsc_status = _subscription_revenue(dealer_id, mon_period)

    # ── 2b. Subscription commission (its own settlement, separate from activation) ─
    subscription = _subscription_commission(dealer_id, mon_period)

    # ── 3. Payment record (settlement side) ───────────────────────────────
    source = config.PAYMENT_SOURCE
    payment_df = payment_lookup(mon_period, source)
    paid, found, status = extract_payment(payment_df, dealer_id, source)
    paid = round(paid, 2)

    # APDP source carries richer per-dealer detail on the same frame —
    # cheap to surface here for the internal view.
    apdp_detail: dict[str, Any] | None = None
    if source == "apdp" and found:
        match = payment_df[payment_df["dealer_id"].astype(str) == dealer_id]
        if not match.empty:
            r = match.iloc[0]
            apdp_detail = {
                "sale_count":                  _safe_int(r.get("sale_count")),
                "total_sales_ngn":             round(_safe_float(r.get("total_sales_ngn")), 2),
                "statement_count":             _safe_int(r.get("statement_count")),
                "statement_gross_revenue_ngn": round(_safe_float(r.get("statement_gross_revenue_ngn")), 2),
                "settlement_count":            _safe_int(r.get("settlement_count")),
                "paid_count":                  _safe_int(r.get("paid_count")),
                "partial_count":               _safe_int(r.get("partial_count")),
                "disputed_count":              _safe_int(r.get("disputed_count")),
                "reconciliation_status":       str(r.get("reconciliation_status") or ""),
            }

    payment_info = {
        "data_source":       source,          # "simulated" | "apdp"
        "amount_paid_ngn":   paid,
        "payment_found":     bool(found),
        "payment_status":    status,
        "apdp_detail":       apdp_detail,
    }

    # ── 4. Position — the finance headline ────────────────────────────────
    outstanding = round(expected_commission - paid, 2)
    variance_pct: float | None = None
    if expected_commission > 0:
        variance_pct = round(outstanding / expected_commission * 100.0, 2)
    if abs(outstanding) < 1.0:
        headline = "PAID_IN_FULL"
    elif outstanding > 0:
        headline = "UNDERPAID"
    else:
        headline = "OVERPAID"

    position = {
        "expected_ngn":      expected_commission,
        "paid_ngn":          paid,
        "outstanding_ngn":   outstanding,
        "variance_pct":      variance_pct,
        "headline":          headline,
    }

    # ── 4b. Combined — plain sums of activation and subscription commission ──
    # Subscription is included only when recorded; paid/outstanding need the
    # activation payment record, otherwise they are unknown (never zero).
    includes_subscription = subscription["status"] == "recorded"

    def _plus(activation: float, subscription_key: str) -> float:
        extra = subscription[subscription_key] if includes_subscription else 0.0
        return round(activation + extra, 2)

    combined = {
        "includes_subscription": includes_subscription,
        "owed_ngn":        _plus(expected_commission, "owed_ngn"),
        "paid_ngn":        _plus(paid, "paid_ngn") if found else None,
        "outstanding_ngn": _plus(outstanding, "outstanding_ngn") if found else None,
    }

    # ── 5. Linked audit trails (evidence pointers) ────────────────────────
    audit_trails = _load_audit_trails_for(dealer_id, mon_period)

    return {
        "found":                 True,
        "dealer_id":             dealer_id,
        "dealer_name":           dealer_name,
        "account_profile_class": profile_class,
        "mon_period":            mon_period,

        "commission": {
            "expected_ngn":               expected_commission,
            "total_activations":          total_activations,
            "qualified_activation_count": qualified,
            "zero_commission_count":      zero_commission_count,
            "by_denomination":            {k: round(_safe_float(v), 2) for k, v in commission_by_denom.items()},
        },
        "orsc":     orsc_info,
        "orsc_status": orsc_status,
        "subscription_commission": subscription,
        "payment":  payment_info,
        "position": position,
        "combined": combined,

        # Per-dealer audit trails — thin refs, not full step chains.
        # UI can deep-link into /assurance/audit/trails/{partner_code} for details.
        "audit_trails": audit_trails,
    }


_SUBSCRIPTION_COMMISSION_SOURCE = "subscription_commission_demo"
_SUBSCRIPTION_REVENUE_SOURCE = "fbb_comm_orsc"


def _orsc_rows(dealer_id: str, mon_period: str) -> pd.DataFrame:
    return execute_query(
        "get_orsc_summary",
        {"mon_period": mon_period, "distributor_code": dealer_id},
    )


def _subscription_revenue(dealer_id: str, mon_period: str) -> tuple[dict[str, Any] | None, str]:
    """Return ``(revenue, status)``; status is recorded | not_recorded | unavailable.

    ``not_recorded`` only when the source verifiably covers the month; an
    unreadable or uncovered source is ``unavailable``.
    """
    from backend.db import queries
    try:
        frame = _orsc_rows(dealer_id, mon_period)
    except Exception:
        return None, "unavailable"
    if frame is not None and not frame.empty:
        row = frame.iloc[0]
        return {
            "device_count": _safe_int(row.get("device_count")),
            "total_subscription_amount_ngn": round(_safe_float(row.get("total_subscription_amount_ngn")), 2),
            "zero_amount_count": _safe_int(row.get("zero_amount_count")),
        }, "recorded"
    covered = queries.has_source_period(_SUBSCRIPTION_REVENUE_SOURCE, mon_period)
    return None, "not_recorded" if covered else "unavailable"


def _subscription_commission(dealer_id: str, mon_period: str) -> dict[str, Any]:
    """The dealer's subscription commission owed, settled and outstanding, as the source reports it.

    ``unavailable`` when the source does not cover the month, cannot be read,
    or the dealer's records are incomplete; ``not_recorded`` when the source
    covers the month but holds nothing for this dealer. Never zero-filled.
    """
    from backend.db import queries, subscription_evidence
    unknown = {"owed_ngn": None, "paid_ngn": None, "outstanding_ngn": None, "record_count": 0}
    if not queries.has_source_period(_SUBSCRIPTION_COMMISSION_SOURCE, mon_period):
        return {"status": "unavailable", **unknown}
    try:
        summary = subscription_evidence.summaries(mon_period).get(dealer_id)
    except Exception:
        return {"status": "unavailable", **unknown}
    if summary is None:
        return {"status": "not_recorded", **unknown}
    amounts = {"owed_ngn": summary.get("subscription_commission_ngn"),
               "paid_ngn": summary.get("subscription_settled_ngn"),
               "outstanding_ngn": summary.get("subscription_outstanding_ngn")}
    if not summary.get("subscription_commission_complete") or any(v is None for v in amounts.values()):
        return {"status": "unavailable", **unknown}
    return {"status": "recorded", **{k: round(float(v), 2) for k, v in amounts.items()},
            "record_count": int(summary.get("subscription_commission_record_count") or 0)}


def _load_audit_trails_for(dealer_id: str, mon_period: str) -> list[dict[str, Any]]:
    """Latest persisted audit-trail summaries for this (dealer, period)
    across every registered module.

    Returns an empty list when the audit Postgres is unreachable — this
    endpoint is a formatter, not an audit endpoint, so a missing DB
    should degrade gracefully rather than 500.
    """
    try:
        from backend.db import audit_store
    except Exception:
        return []
    trails: list[dict[str, Any]] = []
    try:
        from backend.audit.base import list_modules
        for module in list_modules():
            # zero_commission / payment_reconciliation / eligibility_window use
            # partner_code = dealer_id; inventory_mismatch composes it. We show
            # only the modules whose subject IS the dealer, not per-product.
            if module.name == "inventory_mismatch":
                continue
            try:
                trail = audit_store.get_partner_trail(dealer_id, mon_period, module.name)
            except Exception:
                continue
            if not trail:
                continue
            generated_at = trail.get("generated_at")
            if hasattr(generated_at, "isoformat"):
                generated_at = generated_at.isoformat()
            trails.append({
                "module":       module.name,
                "label":        module.label,
                "trail_id":     trail.get("trail_id"),
                "conclusion":   trail.get("conclusion"),
                "confidence":   trail.get("confidence"),
                "caveat_count": trail.get("caveat_count"),
                "generated_at": generated_at,
            })
    except Exception:
        return trails
    return trails
