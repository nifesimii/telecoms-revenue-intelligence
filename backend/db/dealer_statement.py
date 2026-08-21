"""Per-period dealer statement composer — Finance/RA internal view.

Answers the question: *"For dealer X in period Y, what did we owe them,
what did we pay, what's the variance, and which audit trails support
that verdict?"* All from a single call.

Sits on top of the existing query + audit layers — this is a formatter,
not a new data source. Reads:

  * ``get_dealer_summary`` — activation-side entitlement (commission owed)
  * ``get_orsc_summary`` — ORSC-side revenue base
  * ``payment_data.payment_lookup`` — settlement-side (respects
    ``PAYMENT_SOURCE=apdp|simulated``)
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

    # ── 2. ORSC side (informational — not part of the payment reconciliation) ─
    try:
        orsc_df = execute_query(
            "get_orsc_summary",
            {"mon_period": mon_period, "distributor_code": dealer_id},
        )
        if not orsc_df.empty:
            orsc_row = orsc_df.iloc[0]
            orsc_info: dict[str, Any] | None = {
                "device_count": _safe_int(orsc_row.get("device_count")),
                "total_subscription_amount_ngn": round(
                    _safe_float(orsc_row.get("total_subscription_amount_ngn")), 2
                ),
                "zero_amount_count": _safe_int(orsc_row.get("zero_amount_count")),
            }
        else:
            orsc_info = None
    except Exception:
        orsc_info = None

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
        "payment":  payment_info,
        "position": position,

        # Per-dealer audit trails — thin refs, not full step chains.
        # UI can deep-link into /assurance/audit/trails/{partner_code} for details.
        "audit_trails": audit_trails,
    }


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
            trails.append({
                "module":     module.name,
                "label":      module.label,
                "trail_id":   trail.get("trail_id"),
                "conclusion": trail.get("conclusion"),
                "confidence": trail.get("confidence"),
                "caveat_count": trail.get("caveat_count"),
                "generated_at": trail.get("generated_at"),
            })
    except Exception:
        return trails
    return trails
