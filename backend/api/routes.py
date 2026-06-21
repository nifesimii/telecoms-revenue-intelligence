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
    DealerSummary,
    InventoryComparisonRecord,
    PaymentCoverageResponse,
    PaymentSummaryRecord,
    PaymentVarianceRecord,
    PeriodList,
)
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
            distributor_code=str(row.get("distributor_code", "")),
            distributor_name=str(row.get("distributor_name", "")),
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

    Returns aggregate coverage stats + the full per-dealer record list.
    Payment data is simulated — see KB Section 13.
    """
    period = mon_period or _most_recent_period() or ""
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
    df = execute_query(
        "get_payment_variance",
        {"period_a": period_a, "period_b": period_b},
    )
    return [PaymentVarianceRecord(**row) for row in df.to_dict(orient="records")]
