"""Phase 2 — Activation Assurance.

Translates the rows from :func:`backend.db.queries.get_activation_exceptions`
into the canonical :class:`AssuranceResult` shape.

Severity / action mapping (taken straight from the KB / spec):

    +-------------------------+----------+-----------------------------------------+
    | exception_type          | severity | recommended_action                      |
    +-------------------------+----------+-----------------------------------------+
    | ALL_UNQUALIFIED         | HIGH     | Verify product codes against USP        |
    |                         |          | dimension for this period               |
    | HIGH_UNQUALIFIED_RATE   | MEDIUM   | Review activation qualification rate    |
    |                         |          | and USP coverage                        |
    | UNUSUAL_VOLUME          | LOW      | Investigate activation volume for       |
    |                         |          | legitimacy. Not confirmed fraud.        |
    +-------------------------+----------+-----------------------------------------+
"""
from __future__ import annotations

from typing import Any

from backend.assurance.base import AssuranceResult, BaseAssuranceService
from backend.db.connection import execute_query


_SEVERITY_BY_EXCEPTION: dict[str, str] = {
    "ALL_UNQUALIFIED": "HIGH",
    "HIGH_UNQUALIFIED_RATE": "MEDIUM",
    "UNUSUAL_VOLUME": "LOW",
}

_ACTION_BY_EXCEPTION: dict[str, str] = {
    "ALL_UNQUALIFIED": (
        "Verify product codes against USP dimension for this period"
    ),
    "HIGH_UNQUALIFIED_RATE": (
        "Review activation qualification rate and USP coverage"
    ),
    "UNUSUAL_VOLUME": (
        "Investigate activation volume for legitimacy. Not confirmed fraud."
    ),
}


class ActivationAssuranceService(BaseAssuranceService):
    """Phase 2 — wraps ``get_activation_exceptions`` as assurance findings."""

    module_name = "Activation Assurance"
    phase = 2

    async def run(
        self,
        mon_period: str,
        dealer_id: str | None = None,
    ) -> AssuranceResult:
        df = execute_query(
            "get_activation_exceptions", {"mon_period": str(mon_period)}
        )

        if dealer_id is not None and dealer_id != "":
            df = df[df["dealer_id"].astype(str) == str(dealer_id)]

        findings: list[dict[str, Any]] = []
        for _, row in df.iterrows():
            exception_type = str(row["exception_type"])
            severity = _SEVERITY_BY_EXCEPTION.get(exception_type, "MEDIUM")
            action = _ACTION_BY_EXCEPTION.get(exception_type, "Investigate")
            findings.append(
                {
                    "type": exception_type,
                    "severity": severity,
                    "dealer_id": str(row["dealer_id"]),
                    "dealer_name": str(row["dealer_name"]),
                    "description": (
                        f"{exception_type}: {int(row['activation_count'])} activations, "
                        f"{int(row['qualified_activation_count'])} qualified, "
                        f"{float(row['qualification_rate_pct']):.2f}% rate"
                    ),
                    "recommended_action": action,
                }
            )

        high = sum(1 for f in findings if f["severity"] == "HIGH")
        medium = sum(1 for f in findings if f["severity"] == "MEDIUM")
        low = sum(1 for f in findings if f["severity"] == "LOW")
        unique_dealers = len({f["dealer_id"] for f in findings}) if findings else 0

        if not findings:
            status = "PASS"
            summary = f"No activation exceptions flagged in {mon_period}."
        else:
            status = "FLAG"
            summary = (
                f"{unique_dealers} dealers flagged in {mon_period}. "
                f"{high} HIGH severity, {medium} MEDIUM, {low} LOW."
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
                "unique_dealers": unique_dealers,
            },
        )
