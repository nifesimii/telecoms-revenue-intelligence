"""FastAPI route handlers.

Three endpoints:

  * ``POST /chat``    — drives a turn of the agent loop and returns the
                        assembled answer plus the raw tool envelopes.
  * ``GET  /periods`` — distinct ``mon_period`` values available in the data.
  * ``GET  /dealers`` — per-dealer activation commission summary for one
                        period; data endpoint, not an LLM endpoint.

This module is the only place where HTTP concepts meet the agent / data
layers. It does not contain SQL, prompt text, or tool definitions.
"""
from __future__ import annotations

import json
import logging
from typing import Any

import pandas as pd
from fastapi import APIRouter, HTTPException, Query

from backend.agent.agent import run_agent
from backend.agent import tool_executor
from backend.api.schemas import (
    ActivationExceptionResponse,
    ActivationSummaryResponse,
    ActivationVarianceResponse,
    AssuranceModuleStatus,
    AssuranceStatusResponse,
    ChatRequest,
    ChatResponse,
    AuditRunResponse,
    DataCoverageTicketResponse,
    DealerStatementResponse,
    DealerSummary,
    DisputeDraftRequest,
    DisputeDraftResponse,
    InventoryComparisonRecord,
    PartnerHealthRecord,
    PaymentCoverageResponse,
    PaymentSummaryRecord,
    PaymentVarianceRecord,
    PeriodList,
)
from backend import config
from backend.assurance.registry import ASSURANCE_REGISTRY, is_implemented
from backend.db import queries
from backend.db.connection import execute_query

logger = logging.getLogger(__name__)

router = APIRouter()

CHAT_FAILURE_MESSAGE = "I was unable to process that request. Please try again."


# ---------------------------------------------------------------------------
# POST /chat
# ---------------------------------------------------------------------------


@router.post("/chat", response_model=ChatResponse)
async def chat(request: ChatRequest) -> ChatResponse:
    """Drive a single agent turn and return Claude's answer + raw tool data.

    If ``mon_period`` is on the request, prepend it to the question as
    explicit context for the agent. The original ``conversation_history`` is
    forwarded untouched.

    Any internal exception is swallowed into the response envelope — this
    endpoint must never 500 on a well-formed request.
    """
    if request.mon_period:
        message = (
            f"Context: reporting period is {request.mon_period}. "
            f"Question: {request.message}"
        )
    else:
        message = request.message

    try:
        result = await run_agent(message, list(request.conversation_history))
    except Exception as exc:  # noqa: BLE001 — never 500 on /chat
        logger.exception("POST /chat: run_agent raised")
        return ChatResponse(
            response=CHAT_FAILURE_MESSAGE,
            tools_called=[],
            raw_data={},
            error=f"{type(exc).__name__}: {exc}",
        )

    return ChatResponse(
        response=result.get("response", ""),
        tools_called=list(result.get("tools_called", [])),
        raw_data=dict(result.get("raw_data", {})),
        error=None,
    )


# ---------------------------------------------------------------------------
# GET /periods
# ---------------------------------------------------------------------------


@router.get("/periods", response_model=PeriodList)
def list_periods() -> PeriodList:
    """Return distinct ``mon_period`` values, most recent first."""
    return PeriodList(periods=queries.get_available_periods())


# ---------------------------------------------------------------------------
# GET /dealers
# ---------------------------------------------------------------------------


@router.get(
    "/dealers/{dealer_id}/statement",
    response_model=DealerStatementResponse,
)
def get_dealer_statement(
    dealer_id: str,
    mon_period: str = Query(pattern=r"^\d{6}$"),
) -> DealerStatementResponse:
    """Per-period dealer statement — Finance/RA internal view.

    Composes commission entitlement + payment settlement + ORSC + linked
    audit trails into a single call. The payment side reflects the current
    ``PAYMENT_SOURCE`` (simulated vs apdp) — the response's data_source
    field lets the UI badge it accordingly.
    """
    from backend.db.dealer_statement import compose_dealer_statement
    result = compose_dealer_statement(dealer_id, mon_period)
    if not result.get("found"):
        raise HTTPException(
            status_code=404,
            detail=(
                f"No activation record for dealer {dealer_id!r} in {mon_period}. "
                "Check the dealer ID and period."
            ),
        )
    # Drop the internal ``found`` flag before Pydantic validation.
    result.pop("found", None)
    return DealerStatementResponse(**result)


@router.get("/dealers", response_model=list[DealerSummary])
def list_dealers(
    mon_period: str | None = Query(
        default=None,
        pattern=r"^\d{6}$",
        description=(
            "Optional reporting month (YYYYMM). If omitted, defaults to the "
            "most recent period available in the data."
        ),
    ),
) -> list[DealerSummary]:
    """Direct data endpoint — bypasses both the agent loop and the agent's
    triaged tool-result envelope.

    The frontend needs the full dealer list to render its sidebar table, so
    this endpoint calls :func:`execute_query` directly rather than going
    through :mod:`tool_executor`. The triaged envelope returned to the agent
    surfaces only the top must/worth-review rows, which is the wrong shape
    for a UI list.
    """
    period = mon_period or _most_recent_period()
    if period is None:
        return []

    try:
        df = execute_query("get_dealer_summary", {"mon_period": period})
    except Exception as exc:  # noqa: BLE001
        logger.exception("GET /dealers query failure")
        raise HTTPException(
            status_code=500,
            detail=f"Dealer summary failed: {type(exc).__name__}: {exc}",
        )

    return [
        DealerSummary(
            dealer_id=str(row.get("dealer_id", "")),
            dealer_name=str(row.get("dealer_name", "")),
            account_profile_class=str(row.get("account_profile_class", "")),
            total_activations=int(row.get("total_activations", 0) or 0),
            total_commission_ngn=float(row.get("total_commission_ngn", 0.0) or 0.0),
            zero_commission_count=int(row.get("zero_commission_count", 0) or 0),
        )
        for row in df.to_dict(orient="records")
    ]


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _most_recent_period() -> str | None:
    """Return the newest known ``mon_period`` or ``None`` if data is empty."""
    periods = queries.get_available_periods()
    return periods[0] if periods else None


def _parse_envelope(content: Any) -> dict[str, Any]:
    """Parse a tool_executor JSON envelope; return empty dict on failure."""
    if not isinstance(content, str) or not content:
        return {}
    try:
        return json.loads(content)
    except json.JSONDecodeError:
        return {}


# ---------------------------------------------------------------------------
# Phase 2 — Activation Intelligence endpoints
# ---------------------------------------------------------------------------


@router.get(
    "/activations/summary",
    response_model=list[ActivationSummaryResponse],
)
def list_activation_summary(
    mon_period: str | None = Query(
        default=None,
        pattern=r"^\d{6}$",
        description=(
            "Reporting month (YYYYMM). If omitted, defaults to the most "
            "recent period available in the data."
        ),
    ),
) -> list[ActivationSummaryResponse]:
    """Dealer-month activation totals — direct data endpoint, no agent."""
    period = mon_period or _most_recent_period()
    if period is None:
        return []

    df = execute_query("get_activation_summary", {"mon_period": period})
    return [ActivationSummaryResponse(**row) for row in df.to_dict(orient="records")]


@router.get(
    "/activations/variance",
    response_model=list[ActivationVarianceResponse],
)
def list_activation_variance(
    period_a: str = Query(
        default="202602",
        pattern=r"^\d{6}$",
        description="Earlier reporting month (YYYYMM). Defaults to 202602.",
    ),
    period_b: str = Query(
        default="202603",
        pattern=r"^\d{6}$",
        description="Later reporting month (YYYYMM). Defaults to 202603.",
    ),
) -> list[ActivationVarianceResponse]:
    """Per-dealer activation deltas between two periods."""
    df = execute_query(
        "get_activation_variance",
        {"period_a": period_a, "period_b": period_b},
    )
    return [ActivationVarianceResponse(**row) for row in df.to_dict(orient="records")]


@router.get(
    "/activations/exceptions",
    response_model=list[ActivationExceptionResponse],
)
def list_activation_exceptions(
    mon_period: str | None = Query(
        default=None,
        pattern=r"^\d{6}$",
        description=(
            "Reporting month (YYYYMM). If omitted, defaults to the most "
            "recent period available in the data."
        ),
    ),
) -> list[ActivationExceptionResponse]:
    """Dealers matching any of the three activation exception conditions."""
    period = mon_period or _most_recent_period()
    if period is None:
        return []

    df = execute_query("get_activation_exceptions", {"mon_period": period})
    return [
        ActivationExceptionResponse(**row) for row in df.to_dict(orient="records")
    ]


# ---------------------------------------------------------------------------
# Assurance Layer — scaffolding endpoint
# ---------------------------------------------------------------------------


@router.get(
    "/assurance/status",
    response_model=AssuranceStatusResponse,
    response_model_exclude_none=True,
)
async def get_assurance_status(
    mon_period: str | None = Query(
        default=None,
        pattern=r"^\d{6}$",
        description=(
            "Reporting month (YYYYMM). If omitted, defaults to the most "
            "recent period available in the data."
        ),
    ),
) -> AssuranceStatusResponse:
    """Run every registered assurance module for the period and return their
    statuses in a single aggregated payload.

    Implemented modules (Activation, Commission) carry severity counts.
    Stub modules (Inventory, Payment) report ``NOT_IMPLEMENTED`` and omit
    the counts.
    """
    period = mon_period or _most_recent_period() or ""

    modules: list[AssuranceModuleStatus] = []
    for name, service in ASSURANCE_REGISTRY.items():
        result = await service.run(period)
        implemented = is_implemented(service)

        kwargs: dict[str, Any] = {
            "module": name,
            "phase": service.phase,
            "implemented": implemented,
            "status": result.status,
            "summary": result.summary,
        }
        if implemented:
            kwargs["high_count"] = int(result.metadata.get("high_count", 0))
            kwargs["medium_count"] = int(result.metadata.get("medium_count", 0))
            kwargs["low_count"] = int(result.metadata.get("low_count", 0))
            # Pass through up to 50 findings per module — enough to render
            # top-N inline and offer an expansion view without flooding the
            # response.
            kwargs["findings"] = [
                {
                    "type": str(f.get("type", "")),
                    "severity": str(f.get("severity", "LOW")),
                    "dealer_id": str(f.get("dealer_id", "")),
                    "dealer_name": str(f.get("dealer_name", "")),
                    "description": str(f.get("description", "")),
                    "recommended_action": f.get("recommended_action"),
                }
                for f in (result.findings or [])[:50]
            ]

        modules.append(AssuranceModuleStatus(**kwargs))

    # Stable display order by phase so cards always read 1 → 4 regardless
    # of registry insertion order.
    modules.sort(key=lambda m: m.phase)
    return AssuranceStatusResponse(period=period, modules=modules)


# ---------------------------------------------------------------------------
# Phase 3 — Inventory Assurance endpoint
# ---------------------------------------------------------------------------


@router.get(
    "/inventory/comparison",
    response_model=list[InventoryComparisonRecord],
)
def list_inventory_comparison(
    mon_period: str | None = Query(
        default=None,
        pattern=r"^\d{6}$",
        description=(
            "Reporting month (YYYYMM). If omitted, defaults to the most "
            "recent period available in the data."
        ),
    ),
    include_within_allocation: bool = Query(
        default=False,
        description=(
            "If true, include WITHIN_ALLOCATION rows. Default false — only "
            "CONFIRMED_MISMATCH and NO_INVOICE_RECORD rows are returned."
        ),
    ),
) -> list[InventoryComparisonRecord]:
    """Dealer-product activation vs. purchase comparison.

    Backed by :func:`backend.db.queries.get_inventory_comparison`. By
    default the WITHIN_ALLOCATION rows are excluded — they are not
    actionable for assurance review. Pass
    ``include_within_allocation=true`` to retrieve them.
    """
    period = mon_period or _most_recent_period()
    if period is None:
        return []

    df = execute_query("get_inventory_comparison", {"mon_period": period})

    if not include_within_allocation:
        df = df[df["finding_type"] != "WITHIN_ALLOCATION"]

    return [
        InventoryComparisonRecord(**row) for row in df.to_dict(orient="records")
    ]


# ---------------------------------------------------------------------------
# Data coverage ticket compiler (Stage 1 — no live ServiceNow submission)
# ---------------------------------------------------------------------------


@router.get(
    "/inventory/data-coverage-issues",
    response_model=DataCoverageTicketResponse,
)
def get_data_coverage_issues(
    mon_period: str | None = Query(
        default=None,
        pattern=r"^\d{6}$",
        description=(
            "Reporting month (YYYYMM). If omitted, defaults to the most "
            "recent period available in the data."
        ),
    ),
    source: str = Query(
        default="both",
        pattern=r"^(ifs|usp|both)$",
        description=(
            "Which coverage gap class to include. ``ifs`` = dealers with "
            "NO_INVOICE_RECORD inventory rows. ``usp`` = dealers with NULL "
            "account_profile_class. ``both`` (default) = both."
        ),
    ),
) -> DataCoverageTicketResponse:
    """Compile a ServiceNow-ready ticket draft for data coverage gaps.

    Stage 1 — returns the structured dealer list + a markdown ticket body
    for the finance officer to paste into ServiceNow manually. No external
    write happens here. Stage 2 (live ServiceNow API call) is deferred
    pending credentials + an explicit CLAUDE.md whitelist update.
    """
    from backend.db.data_coverage import compile_data_coverage_ticket

    period = mon_period or _most_recent_period() or ""
    payload = compile_data_coverage_ticket(period, source=source)  # type: ignore[arg-type]
    return DataCoverageTicketResponse(**payload)


# ---------------------------------------------------------------------------
# Phase 4 — Payment Intelligence endpoints
# ---------------------------------------------------------------------------


def _row_to_payment_record(row: dict[str, Any]) -> PaymentSummaryRecord:
    """Normalise NaN → None for the nullable string columns before pydantic."""
    cleaned = {}
    for k, v in row.items():
        if isinstance(v, float) and pd.isna(v):
            cleaned[k] = None
        else:
            cleaned[k] = v
    return PaymentSummaryRecord(**cleaned)


# ---------------------------------------------------------------------------
# APDP Postgres → PaymentSummaryRecord adapter
# ---------------------------------------------------------------------------
# When PAYMENT_SOURCE=apdp the /payments/* endpoints read from APDP's
# normalized.partner_settlements view instead of the simulated CSV. The
# view's reconciliation_status drives payment_status mapping; the rest of
# the record carries the v1.3.0 enrichment fields so the UI can show
# sales-vs-statement-vs-settlement context.

_RECON_TO_STATUS = {
    "RECONCILED":               "FULLY_PAID",
    "PARTIALLY_PAID":           "PARTIALLY_PAID",
    "AMOUNT_MISMATCH":          "PARTIALLY_PAID",
    "DISPUTED":                 "DISPUTED",
    "STATEMENT_WITHOUT_PAYMENT": "PENDING",
    "SALES_WITHOUT_STATEMENT":  "PENDING",
}


def _apdp_row_to_payment_record(row: dict[str, Any]) -> PaymentSummaryRecord:
    owed   = float(row.get("expected_commission_ngn") or 0)
    paid   = float(row.get("total_settled_ngn") or 0)
    unpaid = max(0.0, round(owed - paid, 2))
    recon  = row.get("reconciliation_status") or "RECONCILED"
    dealer = row.get("dealer_id") or ""
    return PaymentSummaryRecord(
        dealer_id             = dealer,
        dealer_name           = dealer,  # APDP view doesn't carry the name
        account_profile_class = "",
        report_month          = row.get("settlement_period") or "",
        commission_owed       = round(owed, 2),
        amount_paid           = round(paid, 2),
        amount_unpaid         = unpaid,
        payment_status        = _RECON_TO_STATUS.get(recon, "PENDING"),
        payment_channel       = "",
        payment_date          = None,
        exception_flag        = recon if recon != "RECONCILED" else None,
        data_source           = "APDP",
        reconciliation_status = recon,
        sale_count            = int(row.get("sale_count") or 0),
        total_sales_ngn       = float(row.get("total_sales_ngn") or 0),
        statement_gross_revenue_ngn = float(row.get("statement_gross_revenue_ngn") or 0),
        payment_variance_ngn  = float(row.get("payment_variance_ngn") or 0),
        paid_count            = int(row.get("paid_count") or 0),
        partial_count         = int(row.get("partial_count") or 0),
        disputed_count        = int(row.get("disputed_count") or 0),
    )


# Status sort ranking used by the APDP exceptions endpoint and as a tie-breaker
# elsewhere — matches the simulated path's DISPUTED → PARTIAL → PENDING order.
_STATUS_RANK = {"DISPUTED": 0, "PARTIALLY_PAID": 1, "PENDING": 2, "FULLY_PAID": 3}


def _apdp_summary_response(period: str) -> PaymentCoverageResponse:
    """Build /payments/summary from APDP partner_settlements rows."""
    from backend.db import apdp as apdp_db  # imported lazily to avoid psycopg2 cost in sample mode
    try:
        raw_rows = apdp_db.get_partner_settlements(period)
    except Exception as e:
        logger.exception("APDP partner_settlements read failed")
        raise HTTPException(status_code=503, detail=f"APDP unreachable: {e}")

    records = [_apdp_row_to_payment_record(r) for r in raw_rows]

    total_owed   = round(sum(r.commission_owed for r in records), 2)
    total_paid   = round(sum(r.amount_paid     for r in records), 2)
    total_unpaid = round(sum(r.amount_unpaid   for r in records), 2)
    coverage_pct = round(total_paid / total_owed * 100.0, 1) if total_owed > 0 else 0.0

    status_counts: dict[str, int] = {}
    for r in records:
        status_counts[r.payment_status] = status_counts.get(r.payment_status, 0) + 1

    return PaymentCoverageResponse(
        period                 = period,
        total_commission_owed  = total_owed,
        total_amount_paid      = total_paid,
        total_amount_unpaid    = total_unpaid,
        payment_coverage_pct   = coverage_pct,
        disputed_count         = status_counts.get("DISPUTED", 0),
        partially_paid_count   = status_counts.get("PARTIALLY_PAID", 0),
        pending_count          = status_counts.get("PENDING", 0),
        fully_paid_count       = status_counts.get("FULLY_PAID", 0),
        data_source            = "APDP",
        records                = records,
    )


@router.get(
    "/payments/summary",
    response_model=PaymentCoverageResponse,
)
def get_payment_summary(
    mon_period: str | None = Query(
        default=None,
        pattern=r"^\d{6}$",
        description=(
            "Reporting month (YYYYMM). If omitted, defaults to the most "
            "recent period available in the data."
        ),
    ),
) -> PaymentCoverageResponse:
    """Payment status across all dealers for the period.

    Source switches on ``config.PAYMENT_SOURCE``:
      * ``simulated`` → reads from payment_simulation.csv (KB Section 13)
      * ``apdp``     → reads from APDP ``normalized.partner_settlements`` view
    """
    period = mon_period or _most_recent_period() or ""

    if config.PAYMENT_SOURCE == "apdp":
        return _apdp_summary_response(period)

    df = execute_query("get_payment_summary", {"mon_period": period})

    records = [
        _row_to_payment_record(row) for row in df.to_dict(orient="records")
    ]

    total_owed = float(df["commission_owed"].astype(float).sum()) if not df.empty else 0.0
    total_paid = float(df["amount_paid"].astype(float).sum()) if not df.empty else 0.0
    total_unpaid = (
        float(df["amount_unpaid"].astype(float).sum()) if not df.empty else 0.0
    )
    coverage_pct = (
        round(total_paid / total_owed * 100.0, 1) if total_owed > 0 else 0.0
    )

    status_counts = (
        df["payment_status"].value_counts().to_dict() if not df.empty else {}
    )

    return PaymentCoverageResponse(
        period=period,
        total_commission_owed=round(total_owed, 2),
        total_amount_paid=round(total_paid, 2),
        total_amount_unpaid=round(total_unpaid, 2),
        payment_coverage_pct=coverage_pct,
        disputed_count=int(status_counts.get("DISPUTED", 0)),
        partially_paid_count=int(status_counts.get("PARTIALLY_PAID", 0)),
        pending_count=int(status_counts.get("PENDING", 0)),
        fully_paid_count=int(status_counts.get("FULLY_PAID", 0)),
        data_source="SIMULATED",
        records=records,
    )


@router.get(
    "/payments/exceptions",
    response_model=list[PaymentSummaryRecord],
)
def list_payment_exceptions(
    mon_period: str | None = Query(
        default=None,
        pattern=r"^\d{6}$",
        description=(
            "Reporting month (YYYYMM). If omitted, defaults to the most "
            "recent period available in the data."
        ),
    ),
) -> list[PaymentSummaryRecord]:
    """Non-FULLY_PAID payment records, sorted DISPUTED → PARTIAL → PENDING."""
    period = mon_period or _most_recent_period() or ""

    if config.PAYMENT_SOURCE == "apdp":
        summary = _apdp_summary_response(period)
        exceptions = [r for r in summary.records if r.payment_status != "FULLY_PAID"]
        exceptions.sort(key=lambda r: _STATUS_RANK.get(r.payment_status, 9))
        return exceptions

    df = execute_query("get_payment_exceptions", {"mon_period": period})
    return [_row_to_payment_record(row) for row in df.to_dict(orient="records")]


@router.get(
    "/payments/variance",
    response_model=list[PaymentVarianceRecord],
)
def list_payment_variance(
    period_a: str = Query(
        default="202602",
        pattern=r"^\d{6}$",
        description="Earlier reporting month (YYYYMM). Defaults to 202602.",
    ),
    period_b: str = Query(
        default="202603",
        pattern=r"^\d{6}$",
        description="Later reporting month (YYYYMM). Defaults to 202603.",
    ),
) -> list[PaymentVarianceRecord]:
    """Per-dealer payment delta between two periods (dealers in both only)."""
    if config.PAYMENT_SOURCE == "apdp":
        from backend.db import apdp as apdp_db
        try:
            rows_a, rows_b = apdp_db.get_partner_settlements_two_periods(period_a, period_b)
        except Exception as e:
            logger.exception("APDP partner_settlements variance read failed")
            raise HTTPException(status_code=503, detail=f"APDP unreachable: {e}")

        by_a = {r["dealer_id"]: r for r in rows_a}
        by_b = {r["dealer_id"]: r for r in rows_b}
        records: list[PaymentVarianceRecord] = []
        for dealer_id in sorted(by_a.keys() & by_b.keys()):
            a, b = by_a[dealer_id], by_b[dealer_id]
            owed_a = round(float(a.get("expected_commission_ngn") or 0), 2)
            owed_b = round(float(b.get("expected_commission_ngn") or 0), 2)
            paid_a = round(float(a.get("total_settled_ngn") or 0), 2)
            paid_b = round(float(b.get("total_settled_ngn") or 0), 2)
            status_a = _RECON_TO_STATUS.get(a.get("reconciliation_status") or "", "PENDING")
            status_b = _RECON_TO_STATUS.get(b.get("reconciliation_status") or "", "PENDING")
            records.append(PaymentVarianceRecord(
                dealer_id         = dealer_id,
                dealer_name       = dealer_id,
                period_a          = period_a,
                period_b          = period_b,
                commission_owed_a = owed_a,
                amount_paid_a     = paid_a,
                payment_status_a  = status_a,
                commission_owed_b = owed_b,
                amount_paid_b     = paid_b,
                payment_status_b  = status_b,
                delta_paid        = round(paid_b - paid_a, 2),
                status_changed    = status_a != status_b,
            ))
        return records

    df = execute_query(
        "get_payment_variance",
        {"period_a": period_a, "period_b": period_b},
    )
    return [PaymentVarianceRecord(**row) for row in df.to_dict(orient="records")]


# ---------------------------------------------------------------------------
# Partner Health Scorecard
# ---------------------------------------------------------------------------


@router.get(
    "/partner/health",
    response_model=list[PartnerHealthRecord],
)
def get_partner_health(
    period: str = Query(
        default="202603",
        pattern=r"^\d{6}$",
        description="Current reporting month (YYYYMM).",
    ),
    prior_period: str = Query(
        default="202602",
        pattern=r"^\d{6}$",
        description="Prior month for MoM delta (YYYYMM).",
    ),
) -> list[PartnerHealthRecord]:
    """Composite financial health scorecard per dealer.

    Returns all dealers sorted worst-first (lowest health_score first) so the
    most at-risk partners surface immediately. Each row carries four ratios:
    settlement_rate, commission_yield, zero_commission_rate, outstanding_ngn;
    plus a weighted health_score (0–100) and health_band (HEALTHY/WATCH/AT RISK).
    """
    df = execute_query(
        "get_health_scorecard",
        {"current_period": period, "prior_period": prior_period},
    )
    records = []
    for row in df.to_dict(orient="records"):
        records.append(
            PartnerHealthRecord(
                dealer_id=str(row["dealer_id"]),
                dealer_name=str(row["dealer_name"]),
                account_profile_class=str(row.get("account_profile_class", "")),
                health_score=float(row["health_score"]),
                health_band=str(row["health_band"]),
                settlement_rate_pct=float(row["settlement_rate_pct"]),
                settlement_rate_delta=(
                    float(row["settlement_rate_delta"])
                    if row.get("settlement_rate_delta") is not None
                    and row["settlement_rate_delta"] == row["settlement_rate_delta"]
                    else None
                ),
                commission_yield_pct=float(row["commission_yield_pct"]),
                zero_commission_rate_pct=float(row["zero_commission_rate_pct"]),
                outstanding_ngn=float(row["outstanding_ngn"]),
                dispute_flag=bool(row["dispute_flag"]),
                data_source=str(row["data_source"]),
            )
        )
    return records


# ---------------------------------------------------------------------------
# Dispute response generator
# ---------------------------------------------------------------------------


@router.post(
    "/payments/disputes/draft",
    response_model=DisputeDraftResponse,
)
def draft_dispute_response(req: DisputeDraftRequest) -> DisputeDraftResponse:
    """Compose a finance-ready commission dispute response for one
    (dealer, period). Pure-Python template — deterministic, no LLM call,
    output fully grounded in the same query layer the rest of the platform
    uses. See ``backend/agent/dispute_responder.py`` for the template logic.
    """
    from backend.agent.dispute_responder import compose_dispute_response
    try:
        payload = compose_dispute_response(
            distributor_code = req.distributor_code,
            mon_period       = req.mon_period,
            dispute_text     = req.dispute_text,
            amount_paid      = req.amount_paid,
        )
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    return DisputeDraftResponse(**payload)


# ---------------------------------------------------------------------------
# Zero-commission audit trail (Phase 1)
# ---------------------------------------------------------------------------
# The "run assurance for period X" job generates + persists a verification
# trail per flagged partner. Writes are deliberate (this endpoint), never
# triggered by a page view. GET endpoints expose the persisted trails for
# audit inspection and evaluation aggregation.


@router.post(
    "/assurance/zero-commission/run",
    response_model=AuditRunResponse,
)
def run_zero_commission_audit(
    mon_period: str = Query(
        pattern=r"^\d{6}$",
        description="Reporting month (YYYYMM) to generate trails for.",
    ),
) -> AuditRunResponse:
    """Generate + persist a verification trail for every partner flagged
    with zero-commission activity in the period. Idempotent: re-running a
    period atomically replaces that period's trails. Writes to the
    dedicated FBB audit Postgres.
    """
    from backend.audit.zero_commission_audit import run_period
    from backend.db import audit_store

    trails = run_period(mon_period, config.PAYMENT_SOURCE)
    try:
        result = audit_store.replace_period_trails(
            mon_period, config.PAYMENT_SOURCE, trails, triggered_by="api",
        )
    except Exception as e:
        logger.exception("audit trail persistence failed")
        raise HTTPException(
            status_code=503,
            detail=f"FBB audit Postgres unreachable: {e}",
        )
    return AuditRunResponse(**result)


@router.get("/assurance/zero-commission/trails")
def list_zero_commission_trails(
    mon_period: str = Query(pattern=r"^\d{6}$"),
    caveat_step: str | None = Query(
        default=None,
        description=(
            "If set, return only trails where this step raised a caveat, "
            "e.g. 'upstream_completeness'. Powers evaluation queries."
        ),
    ),
) -> list[dict[str, Any]]:
    """Fetch persisted trails for a period. With ``caveat_step`` set, returns
    only trails where that step raised a caveat (evaluation surface)."""
    from backend.db import audit_store
    try:
        if caveat_step:
            return audit_store.get_trails_with_caveat_step(caveat_step, mon_period)
        return audit_store.get_period_trails(mon_period)
    except Exception as e:
        logger.exception("audit trail read failed")
        raise HTTPException(status_code=503, detail=f"FBB audit Postgres unreachable: {e}")


@router.get("/assurance/zero-commission/trails/{partner_code}")
def get_zero_commission_trail(
    partner_code: str,
    mon_period: str = Query(pattern=r"^\d{6}$"),
) -> dict[str, Any]:
    """The full verification chain for one partner/period — the auditor view."""
    from backend.db import audit_store
    try:
        trail = audit_store.get_partner_trail(partner_code, mon_period)
    except Exception as e:
        logger.exception("audit trail read failed")
        raise HTTPException(status_code=503, detail=f"FBB audit Postgres unreachable: {e}")
    if trail is None:
        raise HTTPException(
            status_code=404,
            detail=f"No trail for partner {partner_code} in {mon_period}. "
                   "Has the run job been executed for this period?",
        )
    return trail


@router.get("/assurance/zero-commission/breakdown")
def zero_commission_breakdown(
    mon_period: str = Query(pattern=r"^\d{6}$"),
) -> list[dict[str, Any]]:
    """Aggregate trail counts by (conclusion, confidence) for a period."""
    from backend.db import audit_store
    try:
        return audit_store.get_conclusion_breakdown(mon_period)
    except Exception as e:
        logger.exception("audit trail read failed")
        raise HTTPException(status_code=503, detail=f"FBB audit Postgres unreachable: {e}")


# ---------------------------------------------------------------------------
# Generic audit layer (module-aware)
# ---------------------------------------------------------------------------
# The same verification-trail machinery across every audit domain. Modules
# self-register (backend/audit/base.py); the frontend Audit Trails panel is
# driven entirely off these endpoints. Zero-commission is the only module
# today — inventory/payment drop in later with no changes here.


def _resolve_module(module: str):
    from backend.audit.base import get_module
    m = get_module(module)
    if m is None:
        from backend.audit.base import list_modules
        names = [x.name for x in list_modules()]
        raise HTTPException(
            status_code=404,
            detail=f"Unknown audit module '{module}'. Registered: {names}",
        )
    return m


@router.get("/assurance/audit/modules")
def list_audit_modules() -> list[dict[str, Any]]:
    """Registered audit modules — populates the UI module dropdown."""
    from backend.audit.base import list_modules
    return [m.to_dict() for m in list_modules()]


@router.post("/assurance/audit/run", response_model=AuditRunResponse)
def run_audit_module(
    module: str = Query(default="zero_commission", description="Audit module name."),
    mon_period: str = Query(pattern=r"^\d{6}$", description="Reporting month (YYYYMM)."),
) -> AuditRunResponse:
    """Generate + persist trails for a module/period. Idempotent per
    (module, period): re-running replaces that module's trails."""
    from backend.db import audit_store

    mod = _resolve_module(module)
    trails = mod.build_trails(mon_period, config.PAYMENT_SOURCE)
    try:
        result = audit_store.replace_period_trails(
            mon_period, config.PAYMENT_SOURCE, trails,
            module=module, triggered_by="api",
        )
    except Exception as e:
        logger.exception("audit trail persistence failed")
        raise HTTPException(status_code=503, detail=f"FBB audit Postgres unreachable: {e}")
    return AuditRunResponse(**result)


@router.get("/assurance/audit/trails")
def list_audit_trails(
    module: str = Query(default="zero_commission"),
    mon_period: str = Query(pattern=r"^\d{6}$"),
    caveat_step: str | None = Query(
        default=None,
        description="Only trails where this step raised a caveat (evaluation filter).",
    ),
) -> list[dict[str, Any]]:
    """Trails for a module/period; optional caveat-step evaluation filter."""
    from backend.db import audit_store
    _resolve_module(module)
    try:
        if caveat_step:
            return audit_store.get_trails_with_caveat_step(caveat_step, mon_period, module)
        return audit_store.get_period_trails(mon_period, module)
    except Exception as e:
        logger.exception("audit trail read failed")
        raise HTTPException(status_code=503, detail=f"FBB audit Postgres unreachable: {e}")


@router.get("/assurance/audit/breakdown")
def audit_breakdown(
    module: str = Query(default="zero_commission"),
    mon_period: str = Query(pattern=r"^\d{6}$"),
) -> list[dict[str, Any]]:
    """Counts by (conclusion, confidence) for a module/period."""
    from backend.db import audit_store
    _resolve_module(module)
    try:
        return audit_store.get_conclusion_breakdown(mon_period, module)
    except Exception as e:
        logger.exception("audit trail read failed")
        raise HTTPException(status_code=503, detail=f"FBB audit Postgres unreachable: {e}")


@router.get("/assurance/audit/trails/{partner_code}")
def get_audit_trail(
    partner_code: str,
    module: str = Query(default="zero_commission"),
    mon_period: str = Query(pattern=r"^\d{6}$"),
) -> dict[str, Any]:
    """Full verification chain for one subject/period — the auditor view."""
    from backend.db import audit_store
    _resolve_module(module)
    try:
        trail = audit_store.get_partner_trail(partner_code, mon_period, module)
    except Exception as e:
        logger.exception("audit trail read failed")
        raise HTTPException(status_code=503, detail=f"FBB audit Postgres unreachable: {e}")
    if trail is None:
        raise HTTPException(
            status_code=404,
            detail=f"No {module} trail for {partner_code} in {mon_period}. "
                   "Has the run job been executed?",
        )
    return trail
