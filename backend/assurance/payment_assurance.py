"""Phase 4 — Payment Assurance.

Wraps :func:`backend.db.queries.get_payment_exceptions` and emits one
finding per non-FULLY_PAID record. Each finding carries severity from the
payment status and references the underlying Phase 2 / Phase 3 exception
flag in the recommended action so the agent can chain reasoning across
phases.

Severity mapping:
    DISPUTED         → HIGH    (linked to ALL_UNQUALIFIED / CONFIRMED_MISMATCH)
    PARTIALLY_PAID   → MEDIUM  (linked to HIGH_UNQUALIFIED_RATE)
    PENDING          → LOW     (no exception — within settlement window)

Metadata always includes ``data_source = "SIMULATED"`` and a verbose note
explaining the simulation origin — the agent must surface this.
"""
from __future__ import annotations

from typing import Any

from backend.assurance.base import AssuranceResult, BaseAssuranceService
from backend.db.connection import execute_query


_SEVERITY_BY_STATUS: dict[str, str] = {
    "DISPUTED": "HIGH",
    "PARTIALLY_PAID": "MEDIUM",
    "PENDING": "LOW",
}

_FINDING_TYPE_BY_STATUS: dict[str, str] = {
    "DISPUTED": "COMMISSION_DISPUTE",
    "PARTIALLY_PAID": "PARTIAL_PAYMENT",
    "PENDING": "PENDING_SETTLEMENT",
}


def _ngn(value: float) -> str:
    return f"₦{value:,.2f}"


class PaymentAssuranceService(BaseAssuranceService):
    """Phase 4 — to be implemented when UDDM payment data is wired up."""

    module_name = "Payment Assurance"
    phase = 4

    async def run(
        self,
        mon_period: str,
        dealer_id: str | None = None,
    ) -> AssuranceResult:
        # Exception records (non-FULLY_PAID) → findings.
        exc_df = execute_query(
            "get_payment_exceptions", {"mon_period": str(mon_period)}
        )
        if dealer_id is not None and dealer_id != "":
            exc_df = exc_df[
                exc_df["distributor_code"].astype(str) == str(dealer_id)
            ]

        # Full summary → totals + coverage metadata.
        sum_df = execute_query(
            "get_payment_summary", {"mon_period": str(mon_period)}
        )
        if dealer_id is not None and dealer_id != "":
            sum_df = sum_df[
                sum_df["distributor_code"].astype(str) == str(dealer_id)
            ]

        total_owed = float(sum_df["commission_owed"].astype(float).sum())
        total_paid = float(sum_df["amount_paid"].astype(float).sum())
        total_unpaid = float(sum_df["amount_unpaid"].astype(float).sum())
        coverage_pct = (
            round(total_paid / total_owed * 100.0, 1) if total_owed > 0 else 0.0
        )

        findings: list[dict[str, Any]] = []
        for _, row in exc_df.iterrows():
            status = str(row["payment_status"])
            severity = _SEVERITY_BY_STATUS.get(status, "MEDIUM")
            finding_type = _FINDING_TYPE_BY_STATUS.get(status, "PAYMENT_EXCEPTION")
            dealer_name = str(row["distributor_name"])
            amount_unpaid = float(row["amount_unpaid"])
            exception_flag = (
                None
                if row["exception_flag"] is None
                or (isinstance(row["exception_flag"], float))
                else str(row["exception_flag"])
            )

            if status == "DISPUTED":
                action = (
                    f"Commission of {_ngn(amount_unpaid)} disputed for "
                    f"{dealer_name}. Linked to {exception_flag} exception. "
                    "Verify activation records before settlement."
                )
                description = (
                    f"{_ngn(amount_unpaid)} disputed; linked to "
                    f"{exception_flag} exception"
                )
            elif status == "PARTIALLY_PAID":
                action = (
                    f"{_ngn(amount_unpaid)} outstanding for {dealer_name}. "
                    "Partial payment processed. Review qualification rate."
                )
                description = (
                    f"{_ngn(amount_unpaid)} outstanding; partial settlement"
                )
            else:  # PENDING
                action = (
                    f"{_ngn(amount_unpaid)} pending settlement for "
                    f"{dealer_name}. Within normal payment window."
                )
                description = (
                    f"{_ngn(amount_unpaid)} pending; within settlement window"
                )

            findings.append(
                {
                    "type": finding_type,
                    "severity": severity,
                    "dealer_id": str(row["distributor_code"]),
                    "dealer_name": dealer_name,
                    "description": description,
                    "recommended_action": action,
                }
            )

        disputed = sum(1 for f in findings if f["severity"] == "HIGH")
        partial = sum(1 for f in findings if f["severity"] == "MEDIUM")
        pending = sum(1 for f in findings if f["severity"] == "LOW")

        # Coverage rule of thumb from KB Rule 3.
        if not findings:
            status = "PASS"
            summary = (
                f"Payment coverage: {coverage_pct}% of {_ngn(total_owed)} owed "
                f"in {mon_period}. All commissions FULLY_PAID. [SIMULATED DATA]"
            )
        else:
            status = "FLAG"
            summary = (
                f"Payment coverage: {coverage_pct}% of {_ngn(total_owed)} owed "
                f"in {mon_period}. {disputed} DISPUTED, {partial} "
                f"PARTIALLY_PAID, {pending} PENDING. [SIMULATED DATA]"
            )

        simulation_note = (
            "Payment data is synthetically generated from real commission "
            "and exception data. Results will improve when live Oracle AP "
            "data is integrated."
        )

        return AssuranceResult(
            module=self.module_name,
            status=status,
            findings=findings,
            summary=summary,
            metadata={
                "period": str(mon_period),
                "high_count": disputed,
                "medium_count": partial,
                "low_count": pending,
                "total_commission_owed": float(round(total_owed, 2)),
                "total_amount_paid": float(round(total_paid, 2)),
                "total_amount_unpaid": float(round(total_unpaid, 2)),
                "payment_coverage_pct": coverage_pct,
                "data_source": "SIMULATED",
                "simulation_note": simulation_note,
            },
        )
