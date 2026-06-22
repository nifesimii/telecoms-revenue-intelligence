"""Data coverage ticket compiler.

Two distinct gap classes affect FBB commission accuracy and need to be
escalated to the data / task team via ServiceNow:

  * **IFS missing**  — dealer has activations this period but no IFS invoice
    record (``NO_INVOICE_RECORD`` rows in the inventory comparison view).
    Affects inventory mismatch determination and may flag false positives.

  * **USP missing** — dealer's ``account_profile_class`` is NULL in the
    dealer summary. One of the four KB-documented root causes for
    zero-commission records. Affects qualification and commission payout.

This module reads the existing query results, groups them by dealer, and
returns a structured payload + a markdown-formatted ServiceNow ticket body
suitable for paste-into-the-portal (Stage 1 — no live ServiceNow API call).

Severity rules (configurable later):
    1-3 dealers   → LOW    ("data-window verify")
    4-10 dealers  → MEDIUM ("investigate snapshot")
    10+ dealers   → HIGH   ("USP refresh / IFS reload likely needed")
"""
from __future__ import annotations

from typing import Any, Literal

import pandas as pd

from backend.db.connection import execute_query

Source = Literal["ifs", "usp", "both"]

_SEVERITY_LOW = 3
_SEVERITY_MEDIUM = 10


def _severity_for(total_dealers: int) -> tuple[str, str]:
    """Return (label, recommended_action)."""
    if total_dealers <= _SEVERITY_LOW:
        return "LOW", "Verify whether the affected dealers' data falls outside the IFS / USP snapshot window."
    if total_dealers <= _SEVERITY_MEDIUM:
        return "MEDIUM", "Investigate the source snapshot — partial refresh may be needed for the affected dealers."
    return "HIGH", "Full USP dimension refresh and/or IFS reload likely required for this period."


def _collect_ifs_missing(mon_period: str) -> list[dict[str, Any]]:
    """Group NO_INVOICE_RECORD rows from the inventory comparison by dealer."""
    df = execute_query(
        "get_inventory_comparison",
        {"mon_period": mon_period, "include_within_allocation": False},
    )
    if df.empty:
        return []
    df = df[df["finding_type"] == "NO_INVOICE_RECORD"]
    if df.empty:
        return []

    rows: list[dict[str, Any]] = []
    for dealer_id, grp in df.groupby("dealer_id", sort=False):
        rows.append({
            "dealer_id":         str(dealer_id),
            "dealer_name":       str(grp.iloc[0].get("dealer_name") or dealer_id),
            "affected_products": int(len(grp)),
            "activation_count":  int(pd.to_numeric(grp["activation_count"], errors="coerce").fillna(0).sum()),
        })
    rows.sort(key=lambda r: -r["activation_count"])
    return rows


def _collect_usp_missing(mon_period: str) -> list[dict[str, Any]]:
    """Dealers whose ``account_profile_class`` is NULL or empty.

    Per KB: a missing account_profile_class is one of the four documented
    root causes for zero-commission records. We surface ALL such dealers
    (not only those with zero-comm records this period) so the data team
    can fix the upstream USP snapshot before next month's commission run.
    """
    df = execute_query("get_dealer_summary", {"mon_period": mon_period})
    if df.empty:
        return []

    pc = df.get("account_profile_class")
    if pc is None:
        return []
    is_null = pc.isna() | (pc.astype(str).str.strip() == "")
    df = df[is_null]
    if df.empty:
        return []

    rows: list[dict[str, Any]] = []
    for _, r in df.iterrows():
        rows.append({
            "dealer_id":             str(r.get("distributor_code") or ""),
            "dealer_name":           str(r.get("distributor_name") or r.get("distributor_code") or ""),
            "total_activations":     int(pd.to_numeric(r.get("total_activations"), errors="coerce") or 0),
            "zero_commission_count": int(pd.to_numeric(r.get("zero_commission_count"), errors="coerce") or 0),
            "commission_ngn":        float(pd.to_numeric(r.get("total_commission_ngn"), errors="coerce") or 0),
        })
    rows.sort(key=lambda r: (-r["zero_commission_count"], -r["total_activations"]))
    return rows


def _format_ticket_body(
    mon_period: str,
    severity: str,
    severity_action: str,
    ifs_missing: list[dict[str, Any]],
    usp_missing: list[dict[str, Any]],
) -> str:
    """Markdown ticket body ready for paste into ServiceNow."""
    total_dealers = len({r["dealer_id"] for r in ifs_missing} | {r["dealer_id"] for r in usp_missing})

    lines = [
        "# FBB Commission Data Coverage Issue",
        "",
        f"**Period:** {mon_period}",
        "**Source:** FBB Revenue Intelligence Platform",
        f"**Severity:** {severity}",
        f"**Affected dealers:** {total_dealers}",
        "",
        "## Issue",
        "",
        "The following dealers have data coverage gaps that affect FBB ",
        "commission accuracy. Please verify whether these are genuine ",
        "coverage issues (e.g. snapshot window mismatch) or whether the ",
        "underlying tables need updating.",
        "",
    ]

    if ifs_missing:
        lines.append("## IFS missing — activations without invoice records")
        lines.append("")
        lines.append("Dealers activated FBB devices this period but no matching ")
        lines.append("IFS purchase record was found in the 6-month window. May ")
        lines.append("indicate stale IFS extract or out-of-window purchases.")
        lines.append("")
        lines.append("| Dealer | Code | Affected products | Activations |")
        lines.append("|---|---|---:|---:|")
        for r in ifs_missing:
            lines.append(
                f"| {r['dealer_name']} | {r['dealer_id']} | "
                f"{r['affected_products']} | {r['activation_count']:,} |"
            )
        lines.append("")

    if usp_missing:
        lines.append("## USP missing — NULL account_profile_class")
        lines.append("")
        lines.append("Per the FBB Commission KB, a missing account_profile_class is ")
        lines.append("one of four documented root causes for zero-commission records. ")
        lines.append("Fix at source (USP dimension snapshot) before the next commission run.")
        lines.append("")
        lines.append("| Dealer | Code | Activations | Zero-comm records | Commission earned |")
        lines.append("|---|---|---:|---:|---:|")
        for r in usp_missing:
            lines.append(
                f"| {r['dealer_name']} | {r['dealer_id']} | "
                f"{r['total_activations']:,} | {r['zero_commission_count']:,} | "
                f"NGN {r['commission_ngn']:,.2f} |"
            )
        lines.append("")

    lines.extend([
        "## Suggested actions",
        "",
        f"1. {severity_action}",
        "2. Confirm whether the affected dealers should appear in the next ",
        "   USP / IFS snapshot. If yes, refresh the source table.",
        "3. Re-run the FBB commission job (`fbb_commission.py`) once the ",
        "   underlying tables are updated.",
        "4. Notify Finance / Revenue Assurance once the data is corrected so ",
        "   any affected dealer disputes can be resolved.",
        "",
        "## Downstream impact",
        "",
        f"* Inventory: {len(ifs_missing)} dealers flagged as NO_INVOICE_RECORD",
        f"* Commission: {len(usp_missing)} dealers with NULL account_profile_class",
    ])
    if usp_missing:
        total_zero = sum(r["zero_commission_count"] for r in usp_missing)
        if total_zero > 0:
            lines.append(
                f"* {total_zero:,} zero-commission activation records across "
                f"the USP-missing dealers may be re-classifiable as qualified "
                f"once the snapshot is fixed."
            )
    lines.extend([
        "",
        "---",
        f"_Compiled by FBB Revenue Intelligence Platform for period {mon_period}._",
    ])
    return "\n".join(lines)


def compile_data_coverage_ticket(
    mon_period: str,
    source: Source = "both",
) -> dict[str, Any]:
    """Build the structured payload + ticket body for a data coverage issue.

    Args:
        mon_period: YYYYMM. Required.
        source:     ``"ifs"`` | ``"usp"`` | ``"both"`` (default ``"both"``).

    Returns:
        ``{
            "mon_period": str,
            "source": str,
            "severity": "LOW" | "MEDIUM" | "HIGH",
            "severity_action": str,
            "affected_dealers": int,
            "ifs_missing": [...],   # empty list if source excludes IFS
            "usp_missing": [...],   # empty list if source excludes USP
            "ticket_body":  str,    # markdown
        }``
    """
    ifs_missing: list[dict[str, Any]] = []
    usp_missing: list[dict[str, Any]] = []

    if source in ("ifs", "both"):
        ifs_missing = _collect_ifs_missing(mon_period)
    if source in ("usp", "both"):
        usp_missing = _collect_usp_missing(mon_period)

    affected = len({r["dealer_id"] for r in ifs_missing} | {r["dealer_id"] for r in usp_missing})
    severity, severity_action = _severity_for(affected)
    body = _format_ticket_body(mon_period, severity, severity_action, ifs_missing, usp_missing)

    return {
        "mon_period":       mon_period,
        "source":           source,
        "severity":         severity,
        "severity_action":  severity_action,
        "affected_dealers": affected,
        "ifs_missing":      ifs_missing,
        "usp_missing":      usp_missing,
        "ticket_body":      body,
    }
