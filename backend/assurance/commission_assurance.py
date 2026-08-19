"""Phase 2 — Commission Assurance.

Emits one finding per dealer that has ``zero_commission_count > 0`` in the
period. We read those counts straight from
:func:`backend.db.queries.get_dealer_summary` (which already exposes the
per-dealer zero-commission count). Pulling raw rows via
``get_zero_commission_records`` for every dealer would be inefficient and
``get_zero_commission_records`` requires a ``distributor_code`` parameter
anyway, so the dealer-summary aggregate is the right data source for this
specific finding shape.

All findings are MEDIUM severity per the spec — Commission Assurance flags
qualified vs unqualified activations; it does not adjudicate fraud or
inventory issues.
"""
from __future__ import annotations

from typing import Any

from backend.assurance.base import AssuranceResult, BaseAssuranceService
from backend.db.connection import execute_query


class CommissionAssuranceService(BaseAssuranceService):
    """Phase 1 — wraps dealer-level zero-commission counts as findings.

    The original scaffolding spec set ``phase = 2`` because the service
    *code* landed during the Phase 2 assurance scaffolding work. We later
    aligned the attribute with the *roadmap* phase the underlying
    intelligence module belongs to (Commission Intelligence = Phase 1) so
    the UI cards read 1 / 2 / 3 / 4 in roadmap order.
    """

    module_name = "Commission Assurance"
    phase = 1

    async def run(
        self,
        mon_period: str,
        dealer_id: str | None = None,
    ) -> AssuranceResult:
        params: dict[str, str] = {"mon_period": str(mon_period)}
        if dealer_id is not None and dealer_id != "":
            params["distributor_code"] = str(dealer_id)

        df = execute_query("get_dealer_summary", params)

        # Only dealers with at least one zero-commission record.
        flagged = df[df["zero_commission_count"].astype(int) > 0]

        findings: list[dict[str, Any]] = []
        for _, row in flagged.iterrows():
            findings.append(
                {
                    "type": "ZERO_COMMISSION_ACTIVATION",
                    "severity": "MEDIUM",
                    "dealer_id": str(row["dealer_id"]),
                    "dealer_name": str(row["dealer_name"]),
                    "description": (
                        f"{int(row['zero_commission_count'])} zero-commission "
                        f"activations of {int(row['total_activations'])} total"
                    ),
                    "recommended_action": (
                        "Review USP dimension coverage for affected product codes"
                    ),
                }
            )

        total_zero_records = (
            int(flagged["zero_commission_count"].astype(int).sum())
            if not flagged.empty
            else 0
        )

        if not findings:
            status = "PASS"
            summary = f"No zero-commission activations in {mon_period}."
        else:
            status = "FLAG"
            summary = (
                f"{len(findings)} dealers have zero-commission activations "
                f"totalling {total_zero_records} unqualified activations."
            )

        return AssuranceResult(
            module=self.module_name,
            status=status,
            findings=findings,
            summary=summary,
            metadata={
                "period": str(mon_period),
                "high_count": 0,
                "medium_count": len(findings),
                "low_count": 0,
                "total_zero_records": total_zero_records,
            },
        )
