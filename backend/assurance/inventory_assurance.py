"""Phase 3 — Inventory Assurance.

Wraps :func:`backend.db.queries.get_inventory_comparison` and emits one
finding per CONFIRMED_MISMATCH dealer-product combination. NO_INVOICE_RECORD
rows are counted into ``metadata`` so the data-window caveat surfaces in the
agent's response, but they are NOT emitted as findings — the spec is
explicit that absence of an IFS record is not a confirmed finding.

Severity bands (gap_pct):
    >= 200%  → HIGH   (3x or more units activated vs purchased)
    >= 100%  → MEDIUM (~2x)
    <  100%  → LOW    (minor excess)
"""
from __future__ import annotations

from typing import Any

from backend.assurance.base import AssuranceResult, BaseAssuranceService
from backend.db.connection import execute_query


def _severity_for(gap_pct: float | None) -> str:
    if gap_pct is None:
        # CONFIRMED_MISMATCH with zero purchases — treat as HIGH.
        return "HIGH"
    if gap_pct >= 200:
        return "HIGH"
    if gap_pct >= 100:
        return "MEDIUM"
    return "LOW"


def _format_units(value: float | None) -> str:
    if value is None:
        return "?"
    return f"{value:.0f}" if float(value).is_integer() else f"{value:.2f}"


class InventoryAssuranceService(BaseAssuranceService):
    """Phase 3 — to be implemented when inventory data lands."""

    module_name = "Inventory Assurance"
    phase = 3

    async def run(
        self,
        mon_period: str,
        dealer_id: str | None = None,
    ) -> AssuranceResult:
        df = execute_query(
            "get_inventory_comparison", {"mon_period": str(mon_period)}
        )

        if dealer_id is not None and dealer_id != "":
            df = df[df["dealer_id"].astype(str) == str(dealer_id)]

        # Count NO_INVOICE_RECORD rows for the metadata caveat — these are not
        # findings per spec.
        no_invoice_count = int(
            (df["finding_type"] == "NO_INVOICE_RECORD").sum()
        )

        # Findings are CONFIRMED_MISMATCH only.
        mismatches = df[df["finding_type"] == "CONFIRMED_MISMATCH"]

        findings: list[dict[str, Any]] = []
        for _, row in mismatches.iterrows():
            gap_pct = row["gap_pct"] if row["gap_pct"] is not None else None
            try:
                gap_pct_f = float(gap_pct) if gap_pct is not None else None
            except (TypeError, ValueError):
                gap_pct_f = None
            severity = _severity_for(gap_pct_f)
            activation_count = int(row["activation_count"])
            purchased = (
                None
                if row["total_units_purchased"] is None
                else float(row["total_units_purchased"])
            )
            gap_pct_label = "?" if gap_pct_f is None else f"{gap_pct_f:.1f}"

            findings.append(
                {
                    "type": "INVENTORY_MISMATCH",
                    "severity": severity,
                    "dealer_id": str(row["dealer_id"]),
                    "dealer_name": str(row["dealer_name"]),
                    "description": (
                        f"Product {row['product_code']}: "
                        f"{activation_count} activations, "
                        f"{_format_units(purchased)} purchased, "
                        f"{gap_pct_label}% excess"
                    ),
                    "recommended_action": (
                        f"Verify dealer purchase records against activation "
                        f"count for product {row['product_code']}. Activated "
                        f"{activation_count} units, purchased "
                        f"{_format_units(purchased)} units "
                        f"({gap_pct_label}% excess)."
                    ),
                }
            )

        high = sum(1 for f in findings if f["severity"] == "HIGH")
        medium = sum(1 for f in findings if f["severity"] == "MEDIUM")
        low = sum(1 for f in findings if f["severity"] == "LOW")

        coverage_note = (
            f"{no_invoice_count} dealer-product combos have activations "
            "with no matched IFS invoice record. This may reflect purchases "
            "outside the available data window, not confirmed mismatches."
        )

        if not findings:
            status = "PASS"
            summary = (
                f"No confirmed inventory mismatches found in {mon_period}. "
                f"{no_invoice_count} dealer-product combos have no invoice "
                "record in the available data window."
            )
        else:
            status = "FLAG"
            summary = (
                f"{len(findings)} confirmed mismatches found in {mon_period}. "
                f"{high} HIGH severity, {medium} MEDIUM, {low} LOW. "
                f"{no_invoice_count} additional dealer-product combos have no "
                "invoice record in the available data window."
            )

        return AssuranceResult(
            module=self.module_name,
            status=status,
            findings=findings,
            summary=summary,
            metadata={
                "period": str(mon_period),
                "high_count": high,
                "medium_count": medium,
                "low_count": low,
                "no_invoice_record_count": no_invoice_count,
                "coverage_note": coverage_note,
            },
        )
