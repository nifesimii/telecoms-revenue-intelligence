"""Per-tool result triage.

The article we're working from calls this "compression vs. discovery": after
running a tool, surface the most-actionable rows FIRST, with explicit severity
labels, so the agent gets the answer up front instead of having to sift
through hundreds of rows. We do this only for the high-frequency tools —
small-result tools (variance, zero-records, ORSC summary) fall through to the
existing ``rows`` envelope unchanged.

Each triage handler takes the raw DataFrame returned by ``execute_query`` and
returns a dict with three keys:

  * ``headline``      — top-line stats the agent can quote directly
  * ``must_review``   — up to ~10 highest-priority rows
  * ``worth_review``  — up to ~10 next-tier rows
  * ``drill_down_hint`` — optional one-line suggestion for the next tool call

``tool_executor`` merges this into the success envelope.
"""
from __future__ import annotations

from typing import Any, Callable

import pandas as pd

# Hard caps so the must/worth review lists never bloat the tool result.
_MUST_REVIEW_CAP = 10
_WORTH_REVIEW_CAP = 10


def _ngn(value: float | int) -> str:
    return f"₦{float(value):,.2f}"


def _records(df: pd.DataFrame, cols: list[str] | None = None) -> list[dict[str, Any]]:
    """Convert a DataFrame slice to JSON-friendly records. Selects ``cols`` if given."""
    if df.empty:
        return []
    if cols:
        existing = [c for c in cols if c in df.columns]
        if existing:
            df = df[existing]
    # pandas → JSON → Python handles NaN/numpy types cleanly.
    import json

    return json.loads(
        df.to_json(orient="records", date_format="iso", default_handler=str)
    )


# ---------------------------------------------------------------------------
# Triage handlers
# ---------------------------------------------------------------------------


def _triage_get_dealer_summary(
    df: pd.DataFrame, params: dict
) -> dict[str, Any]:
    """Per-dealer activation commission summary.

    headline: total commission, dealer count, total activations, zero-comm dealers.
    must_review: dealers with zero_commission_count > 0 (revenue leakage).
    worth_review: top remaining dealers by commission (positioning).
    """
    if df.empty:
        return {
            "headline": {"dealer_count": 0, "total_commission_ngn": 0.0},
            "must_review": [],
            "worth_review": [],
            "drill_down_hint": (
                "No dealers matched the filter. Check mon_period (YYYYMM) or distributor_code."
            ),
        }

    total_commission = float(df["total_commission_ngn"].astype(float).sum())
    total_acts = int(df["total_activations"].astype(int).sum())
    zero_dealers = df[df["zero_commission_count"].astype(int) > 0]
    top_row = df.sort_values("total_commission_ngn", ascending=False).iloc[0]
    top_str = (
        f"{top_row['dealer_name']} · {_ngn(top_row['total_commission_ngn'])}"
    )

    headline = {
        "dealer_count": int(len(df)),
        "total_commission_ngn": round(total_commission, 2),
        "total_activations": total_acts,
        "dealers_with_zero_records": int(len(zero_dealers)),
        "top_dealer_by_commission": top_str,
    }

    # Leakage candidates ranked by zero count desc, then activation volume.
    must_cols = [
        "dealer_id",
        "dealer_name",
        "account_profile_class",
        "total_activations",
        "total_commission_ngn",
        "zero_commission_count",
    ]
    must = (
        zero_dealers.sort_values(
            ["zero_commission_count", "total_activations"], ascending=[False, False]
        )
        .head(_MUST_REVIEW_CAP)
    )
    worth = (
        df.sort_values("total_commission_ngn", ascending=False)
        .head(_WORTH_REVIEW_CAP)
    )

    return {
        "headline": headline,
        "must_review": _records(must, must_cols),
        "worth_review": _records(worth, must_cols),
        "drill_down_hint": (
            "For zero-record root causes call get_zero_commission_records with the "
            "dealer's distributor_code. For month-on-month context call "
            "get_month_on_month_variance."
        ),
    }


def _triage_get_activation_summary(
    df: pd.DataFrame, params: dict
) -> dict[str, Any]:
    """Per-dealer-month activation summary.

    headline: total acts, qualified, qualification rate, qualifying-rate band.
    must_review: dealers with qualification_rate_pct < 50 (high non-qualified).
    worth_review: top dealers by activation volume (operational interest).
    """
    if df.empty:
        return {
            "headline": {"dealer_count": 0, "total_activations": 0},
            "must_review": [],
            "worth_review": [],
            "drill_down_hint": "No dealers matched the filter.",
        }

    total_acts = int(df["activation_count"].astype(int).sum())
    total_qual = int(df["qualified_activation_count"].astype(int).sum())
    total_non_qual = int(df["non_qualified_activation_count"].astype(int).sum())
    overall_rate = (
        round(total_qual / total_acts * 100.0, 2) if total_acts > 0 else 0.0
    )
    top_row = df.sort_values("activation_count", ascending=False).iloc[0]
    top_str = (
        f"{top_row['dealer_name']} · {int(top_row['activation_count'])} acts "
        f"@ {float(top_row['qualification_rate_pct']):.1f}%"
    )

    low_qual = df[df["qualification_rate_pct"].astype(float) < 50.0]

    headline = {
        "dealer_count": int(len(df)),
        "total_activations": total_acts,
        "total_qualified": total_qual,
        "total_non_qualified": total_non_qual,
        "overall_qualification_rate_pct": overall_rate,
        "dealers_below_50pct_qual": int(len(low_qual)),
        "top_dealer_by_volume": top_str,
    }

    cols = [
        "dealer_id",
        "dealer_name",
        "account_profile_class",
        "activation_count",
        "qualified_activation_count",
        "non_qualified_activation_count",
        "qualification_rate_pct",
        "activation_commission_amount",
    ]
    must = (
        low_qual.sort_values("activation_count", ascending=False)
        .head(_MUST_REVIEW_CAP)
    )
    worth = df.head(_WORTH_REVIEW_CAP)  # already sorted by activation_count desc

    return {
        "headline": headline,
        "must_review": _records(must, cols),
        "worth_review": _records(worth, cols),
        "drill_down_hint": (
            "Qualification rate < 50% should prompt get_zero_commission_records for "
            "that dealer to classify the failure mode (KB Issue 1 / Section 1 window / "
            "Issue 4 / Issue 6)."
        ),
    }


def _triage_get_activation_exceptions(
    df: pd.DataFrame, params: dict
) -> dict[str, Any]:
    """Activation exception rows (ALL_UNQUALIFIED / HIGH_UNQUALIFIED_RATE / UNUSUAL_VOLUME)."""
    if df.empty:
        return {
            "headline": {"total_records": 0},
            "must_review": [],
            "worth_review": [],
            "drill_down_hint": "No activation exceptions for this period.",
        }

    counts = df["exception_type"].value_counts().to_dict()
    headline = {
        "total_records": int(len(df)),
        "all_unqualified": int(counts.get("ALL_UNQUALIFIED", 0)),
        "high_unqualified_rate": int(counts.get("HIGH_UNQUALIFIED_RATE", 0)),
        "unusual_volume": int(counts.get("UNUSUAL_VOLUME", 0)),
    }

    cols = [
        "dealer_id",
        "dealer_name",
        "account_profile_class",
        "exception_type",
        "activation_count",
        "qualified_activation_count",
        "qualification_rate_pct",
        "activation_commission_amount",
    ]

    # Must: HIGH severity → ALL_UNQUALIFIED first, then UNUSUAL_VOLUME with
    # high volume. Sort within each by activation_count desc.
    must_pool = df[
        df["exception_type"].isin(["ALL_UNQUALIFIED", "UNUSUAL_VOLUME"])
    ]
    must = (
        must_pool.sort_values(
            ["exception_type", "activation_count"], ascending=[True, False]
        )
        .head(_MUST_REVIEW_CAP)
    )

    # Worth: HIGH_UNQUALIFIED_RATE, sorted by activation_count desc.
    worth = (
        df[df["exception_type"] == "HIGH_UNQUALIFIED_RATE"]
        .sort_values("activation_count", ascending=False)
        .head(_WORTH_REVIEW_CAP)
    )

    return {
        "headline": headline,
        "must_review": _records(must, cols),
        "worth_review": _records(worth, cols),
        "drill_down_hint": (
            "ALL_UNQUALIFIED → most likely USP snapshot miss (KB Issue 1). "
            "HIGH_UNQUALIFIED_RATE → run get_zero_commission_records to classify. "
            "UNUSUAL_VOLUME → present as 'requires investigation', never 'fraud'."
        ),
    }


def _triage_get_inventory_comparison(
    df: pd.DataFrame, params: dict
) -> dict[str, Any]:
    """Activations vs IFS purchases. The biggest payoff for triage — raw result is 4k+ rows."""
    if df.empty:
        return {
            "headline": {"total_records": 0},
            "must_review": [],
            "worth_review": [],
            "drill_down_hint": "No inventory comparison records.",
        }

    confirmed = df[df["finding_type"] == "CONFIRMED_MISMATCH"]
    no_invoice = df[df["finding_type"] == "NO_INVOICE_RECORD"]
    within = df[df["finding_type"] == "WITHIN_ALLOCATION"]

    total_excess = 0.0
    top_str = "—"
    if not confirmed.empty:
        total_excess = float(confirmed["inventory_gap"].astype(float).sum())
        top = confirmed.sort_values("gap_pct", ascending=False).iloc[0]
        top_str = (
            f"{top['dealer_name']} · product {top['product_code']} · "
            f"{int(top['activation_count'])} acts vs "
            f"{int(top['total_units_purchased'])} purchased "
            f"({float(top['gap_pct']):.1f}% excess)"
        )

    headline = {
        "confirmed_mismatches": int(len(confirmed)),
        "no_invoice_records": int(len(no_invoice)),
        "within_allocation": int(len(within)),
        "total_excess_units_confirmed": round(total_excess, 0),
        "worst_confirmed_mismatch": top_str,
    }

    cols = [
        "dealer_id",
        "dealer_name",
        "product_code",
        "product_name",
        "activation_count",
        "qualified_count",
        "total_units_purchased",
        "inventory_gap",
        "gap_pct",
        "finding_type",
    ]

    # Must: CONFIRMED_MISMATCH sorted by gap_pct desc (highest severity first).
    must = (
        confirmed.sort_values("gap_pct", ascending=False).head(_MUST_REVIEW_CAP)
    )

    # Worth: NO_INVOICE_RECORD sorted by activation_count desc — these are
    # the largest volume "may or may not be a mismatch" cases.
    worth = (
        no_invoice.sort_values("activation_count", ascending=False)
        .head(_WORTH_REVIEW_CAP)
    )

    return {
        "headline": headline,
        "must_review": _records(must, cols),
        "worth_review": _records(worth, cols),
        "drill_down_hint": (
            "Lead with CONFIRMED_MISMATCH. NO_INVOICE_RECORD is NOT a confirmed "
            "finding — always note the data-window caveat. Severity per KB "
            "Rule 3: gap_pct ≥ 200 HIGH, 100-199 MEDIUM, < 100 LOW. Apply "
            "KB Section 12 Rule 4 language constraints when describing findings."
        ),
    }


def _triage_get_payment_summary(
    df: pd.DataFrame, params: dict
) -> dict[str, Any]:
    """Per-dealer payment status. Lead with coverage; surface DISPUTED & PARTIAL."""
    if df.empty:
        return {
            "headline": {"dealer_count": 0},
            "must_review": [],
            "worth_review": [],
            "drill_down_hint": "No payment records for this period.",
        }

    total_owed = float(df["commission_owed"].astype(float).sum())
    total_paid = float(df["amount_paid"].astype(float).sum())
    total_unpaid = float(df["amount_unpaid"].astype(float).sum())
    coverage_pct = (
        round(total_paid / total_owed * 100.0, 1) if total_owed > 0 else 0.0
    )
    status_counts = df["payment_status"].value_counts().to_dict()

    disputed = df[df["payment_status"] == "DISPUTED"]
    partial = df[df["payment_status"] == "PARTIALLY_PAID"]

    top_str = "—"
    if not disputed.empty:
        top = disputed.sort_values("amount_unpaid", ascending=False).iloc[0]
        flag = top.get("exception_flag") or "?"
        top_str = (
            f"{top['dealer_name']} · {_ngn(top['amount_unpaid'])} unpaid "
            f"({flag})"
        )

    headline = {
        "dealer_count": int(len(df)),
        "total_commission_owed_ngn": round(total_owed, 2),
        "total_amount_paid_ngn": round(total_paid, 2),
        "total_amount_unpaid_ngn": round(total_unpaid, 2),
        "payment_coverage_pct": coverage_pct,
        "status_breakdown": {k: int(v) for k, v in status_counts.items()},
        "biggest_dispute": top_str,
        "data_source": "SIMULATED",
    }

    cols = [
        "dealer_id",
        "dealer_name",
        "account_profile_class",
        "commission_owed",
        "amount_paid",
        "amount_unpaid",
        "payment_status",
        "exception_flag",
    ]

    must = disputed.sort_values("amount_unpaid", ascending=False).head(_MUST_REVIEW_CAP)
    worth = partial.sort_values("amount_unpaid", ascending=False).head(_WORTH_REVIEW_CAP)

    return {
        "headline": headline,
        "must_review": _records(must, cols),
        "worth_review": _records(worth, cols),
        "drill_down_hint": (
            "DISPUTED → name the linked Phase 2/3 exception_flag and recommend "
            "verifying that root cause before settlement. PARTIALLY_PAID → linked "
            "to HIGH_UNQUALIFIED_RATE. Always disclose SIMULATED data."
        ),
    }


def _triage_get_payment_exceptions(
    df: pd.DataFrame, params: dict
) -> dict[str, Any]:
    """Non-FULLY_PAID payment rows. Same triage shape as get_payment_summary but
    pre-filtered to actionable items."""
    if df.empty:
        return {
            "headline": {"total_records": 0},
            "must_review": [],
            "worth_review": [],
            "drill_down_hint": "No payment exceptions for this period.",
        }

    counts = df["payment_status"].value_counts().to_dict()
    total_unpaid = float(df["amount_unpaid"].astype(float).sum())
    disputed_unpaid = float(
        df[df["payment_status"] == "DISPUTED"]["amount_unpaid"].astype(float).sum()
    )

    disputed = df[df["payment_status"] == "DISPUTED"]
    partial = df[df["payment_status"] == "PARTIALLY_PAID"]
    pending = df[df["payment_status"] == "PENDING"]

    top_str = "—"
    if not disputed.empty:
        top = disputed.sort_values("amount_unpaid", ascending=False).iloc[0]
        flag = top.get("exception_flag") or "?"
        top_str = (
            f"{top['dealer_name']} · {_ngn(top['amount_unpaid'])} unpaid "
            f"({flag})"
        )

    headline = {
        "total_records": int(len(df)),
        "disputed_count": int(counts.get("DISPUTED", 0)),
        "partially_paid_count": int(counts.get("PARTIALLY_PAID", 0)),
        "pending_count": int(counts.get("PENDING", 0)),
        "total_unpaid_ngn": round(total_unpaid, 2),
        "disputed_unpaid_ngn": round(disputed_unpaid, 2),
        "biggest_dispute": top_str,
        "data_source": "SIMULATED",
    }

    cols = [
        "dealer_id",
        "dealer_name",
        "account_profile_class",
        "commission_owed",
        "amount_paid",
        "amount_unpaid",
        "payment_status",
        "exception_flag",
    ]

    # Must: DISPUTED first, sorted by unpaid desc.
    must = disputed.sort_values("amount_unpaid", ascending=False).head(_MUST_REVIEW_CAP)

    # Worth: PARTIALLY_PAID (linked to HIGH_UNQUALIFIED_RATE) + top PENDING by
    # unpaid as backfill if we have slots left.
    worth_pool: list[pd.DataFrame] = []
    if not partial.empty:
        worth_pool.append(
            partial.sort_values("amount_unpaid", ascending=False).head(
                _WORTH_REVIEW_CAP
            )
        )
    remaining = _WORTH_REVIEW_CAP - sum(len(w) for w in worth_pool)
    if remaining > 0 and not pending.empty:
        worth_pool.append(
            pending.sort_values("amount_unpaid", ascending=False).head(remaining)
        )
    worth = (
        pd.concat(worth_pool, ignore_index=True)
        if worth_pool
        else pd.DataFrame(columns=cols)
    )

    return {
        "headline": headline,
        "must_review": _records(must, cols),
        "worth_review": _records(worth, cols),
        "drill_down_hint": (
            "Lead with DISPUTED — each maps to a Phase 2 ALL_UNQUALIFIED or "
            "Phase 3 CONFIRMED_MISMATCH exception_flag. Recommend Finance "
            "verify that flag before settling/contesting. PARTIALLY_PAID → "
            "HIGH_UNQUALIFIED_RATE. PENDING → normal settlement window. "
            "Always disclose SIMULATED data."
        ),
    }


# ---------------------------------------------------------------------------
# Registry
# ---------------------------------------------------------------------------

# tool name -> callable(df, params) -> {headline, must_review, worth_review, drill_down_hint?}
TRIAGE_HANDLERS: dict[
    str, Callable[[pd.DataFrame, dict[str, Any]], dict[str, Any]]
] = {
    "get_dealer_summary": _triage_get_dealer_summary,
    "get_activation_summary": _triage_get_activation_summary,
    "get_activation_exceptions": _triage_get_activation_exceptions,
    "get_inventory_comparison": _triage_get_inventory_comparison,
    "get_payment_summary": _triage_get_payment_summary,
    "get_payment_exceptions": _triage_get_payment_exceptions,
}
