"""Composite query helpers — join multiple underlying queries into a single
agent-facing dossier.

The pattern: many "tell me about Dealer X" questions require Commission +
Activation + Inventory + Payment data for the same dealer-month. Without
this module the agent makes 4 separate tool round-trips, each one adding
~10 KB of message history. ``assemble_dealer_full_context`` collapses them
to a single call.

This is the L1 bread-and-butter case from our memory hierarchy: when the
distribution shows the same shape of question repeatedly, build one
hand-engineered, token-compact wrapper instead of making the agent compose
the answer call-by-call.
"""
from __future__ import annotations

from typing import Any

import pandas as pd

from backend.db.connection import execute_query
from backend.db.queries import get_available_periods


# Hard caps for the embedded detail rows. Keeps the dossier compact even
# for dealers with hundreds of products / zero-records.
_MAX_INVENTORY_FINDINGS = 15
_MAX_ZERO_RECORDS_SAMPLE = 5


def _safe_num(value: Any) -> float | None:
    """Convert NaN/None to None, otherwise float."""
    if value is None:
        return None
    try:
        if pd.isna(value):
            return None
    except (TypeError, ValueError):
        pass
    return float(value)


def _safe_str(value: Any) -> str | None:
    """Convert NaN/None to None, otherwise str."""
    if value is None:
        return None
    try:
        if pd.isna(value):
            return None
    except (TypeError, ValueError):
        pass
    return str(value)


def assemble_dealer_full_context(
    distributor_code: str, mon_period: str
) -> dict[str, Any]:
    """Return a single-call dossier for one dealer for one reporting month.

    On success the dict has ``found=True`` and the full dossier. On a
    not-found lookup it returns ``found=False`` with the available periods so
    the agent can suggest a correction.
    """
    distributor_code = str(distributor_code).strip()
    mon_period = str(mon_period).strip()

    # --- Phase 1: dealer summary (single dealer filter) -------------------
    summary_df = execute_query(
        "get_dealer_summary",
        {"mon_period": mon_period, "distributor_code": distributor_code},
    )
    if summary_df.empty:
        periods = get_available_periods()
        return {
            "found": False,
            "parameters": {
                "distributor_code": distributor_code,
                "mon_period": mon_period,
            },
            "message": (
                f"No record of distributor_code {distributor_code!r} in period "
                f"{mon_period!r}. Available periods: {periods}. Suggest "
                "verifying the distributor_code with the user or trying an "
                "adjacent period."
            ),
        }

    row = summary_df.iloc[0]

    # --- Phase 2: activation summary -------------------------------------
    act_df = execute_query("get_activation_summary", {"mon_period": mon_period})
    act_match = act_df[act_df["dealer_id"].astype(str) == distributor_code]
    activation_info: dict[str, Any] = {}
    if not act_match.empty:
        a = act_match.iloc[0]
        activation_info = {
            "activation_count": int(a["activation_count"]),
            "qualified_activation_count": int(a["qualified_activation_count"]),
            "non_qualified_activation_count": int(
                a["non_qualified_activation_count"]
            ),
            "qualification_rate_pct": float(a["qualification_rate_pct"]),
            "activation_commission_amount": float(a["activation_commission_amount"]),
        }

    # --- Phase 2: activation exceptions for this dealer ------------------
    exc_df = execute_query(
        "get_activation_exceptions", {"mon_period": mon_period}
    )
    exc_match = exc_df[exc_df["dealer_id"].astype(str) == distributor_code]
    activation_exceptions = [
        {
            "exception_type": str(e["exception_type"]),
            "activation_count": int(e["activation_count"]),
            "qualified_activation_count": int(e["qualified_activation_count"]),
            "qualification_rate_pct": float(e["qualification_rate_pct"]),
        }
        for _, e in exc_match.iterrows()
    ]

    # --- Phase 3: inventory findings for this dealer ---------------------
    inv_df = execute_query(
        "get_inventory_comparison", {"mon_period": mon_period}
    )
    inv_match = inv_df[inv_df["dealer_id"].astype(str) == distributor_code]
    confirmed_count = int((inv_match["finding_type"] == "CONFIRMED_MISMATCH").sum())
    no_invoice_count = int((inv_match["finding_type"] == "NO_INVOICE_RECORD").sum())
    within_count = int((inv_match["finding_type"] == "WITHIN_ALLOCATION").sum())

    # Findings sorted: CONFIRMED_MISMATCH first (by gap_pct desc), then the
    # rest. Capped at _MAX_INVENTORY_FINDINGS to keep the dossier compact.
    inv_match = inv_match.copy()
    inv_match["_severity_order"] = inv_match["finding_type"].map(
        {"CONFIRMED_MISMATCH": 0, "NO_INVOICE_RECORD": 1, "WITHIN_ALLOCATION": 2}
    ).fillna(99)
    inv_match = inv_match.sort_values(
        ["_severity_order", "gap_pct"], ascending=[True, False], na_position="last"
    ).head(_MAX_INVENTORY_FINDINGS)

    inventory_findings = [
        {
            "product_code": str(i["product_code"]),
            "product_name": str(i["product_name"])[:80],
            "activation_count": int(i["activation_count"]),
            "total_units_purchased": _safe_num(i["total_units_purchased"]),
            "inventory_gap": _safe_num(i["inventory_gap"]),
            "gap_pct": _safe_num(i["gap_pct"]),
            "finding_type": str(i["finding_type"]),
        }
        for _, i in inv_match.iterrows()
    ]

    # --- Phase 4: payment status for this dealer -------------------------
    pay_df = execute_query("get_payment_summary", {"mon_period": mon_period})
    pay_match = pay_df[
        pay_df["dealer_id"].astype(str) == distributor_code
    ]
    payment_info: dict[str, Any] = {}
    if not pay_match.empty:
        p = pay_match.iloc[0]
        payment_info = {
            "commission_owed_ngn": float(p["commission_owed"]),
            "amount_paid_ngn": float(p["amount_paid"]),
            "amount_unpaid_ngn": float(p["amount_unpaid"]),
            "payment_status": str(p["payment_status"]),
            "exception_flag": _safe_str(p["exception_flag"]),
            "payment_channel": str(p["payment_channel"]),
            "payment_date": _safe_str(p["payment_date"]),
            "data_source": "SIMULATED",
        }

    # --- Zero-commission records sample (only if there are any) ----------
    zero_records_sample: list[dict[str, Any]] = []
    if int(row["zero_commission_count"]) > 0:
        zero_df = execute_query(
            "get_zero_commission_records",
            {"mon_period": mon_period, "distributor_code": distributor_code},
        )
        for _, z in zero_df.head(_MAX_ZERO_RECORDS_SAMPLE).iterrows():
            zero_records_sample.append(
                {
                    "imei": str(z["imei"]),
                    "product_code": str(z["product_code"]),
                    "product_name": str(z["product_name"])[:60],
                    "first_activation_date": _safe_str(z["first_activation_date"]),
                }
            )

    return {
        "found": True,
        "dealer": {
            "dealer_id": str(row["dealer_id"]),
            "dealer_name": str(row["dealer_name"]),
            "account_profile_class": str(row["account_profile_class"]),
            "period": mon_period,
        },
        "commission": {
            "total_commission_ngn": round(float(row["total_commission_ngn"]), 2),
            "total_activations": int(row["total_activations"]),
            "zero_commission_count": int(row["zero_commission_count"]),
            "commission_by_denomination": dict(row["commission_by_denomination"]),
        },
        "activation": activation_info,
        "activation_exceptions": activation_exceptions,
        "inventory": {
            "products_in_period": int(len(inv_df[inv_df["dealer_id"].astype(str) == distributor_code])),
            "confirmed_mismatches": confirmed_count,
            "no_invoice_records": no_invoice_count,
            "within_allocation": within_count,
            "findings": inventory_findings,
            "findings_capped_at": _MAX_INVENTORY_FINDINGS,
        },
        "payment": payment_info,
        "zero_records_sample": zero_records_sample,
        "zero_records_sample_capped_at": _MAX_ZERO_RECORDS_SAMPLE,
    }
