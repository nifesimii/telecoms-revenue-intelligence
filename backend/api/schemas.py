"""Pydantic request and response models for the FastAPI layer.

Single source of truth for the wire format between the React frontend and the
FastAPI backend. All schema validation, OpenAPI doc generation, and JSON
(de)serialisation flows through these models.
"""
from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field


# ---------------------------------------------------------------------------
# /chat
# ---------------------------------------------------------------------------


class ChatRequest(BaseModel):
    """Inbound payload for ``POST /chat``."""

    message: str = Field(
        ...,
        min_length=1,
        description="The Finance / Revenue Assurance user's question.",
    )
    conversation_history: list[dict[str, Any]] = Field(
        default_factory=list,
        description=(
            "Prior turns in the conversation, in the Anthropic Messages API "
            "shape: ``[{'role': 'user' | 'assistant', 'content': ...}]``. "
            "Defaults to an empty list (single-turn)."
        ),
    )
    mon_period: str | None = Field(
        default=None,
        pattern=r"^\d{6}$",
        description=(
            "Optional reporting month (YYYYMM). When provided, the route "
            "layer prepends it to the question as explicit context for the "
            "agent."
        ),
    )


class ChatResponse(BaseModel):
    """Outbound payload for ``POST /chat``."""

    response: str = Field(
        ...,
        description="Claude's final text response, ready to render in the UI.",
    )
    tools_called: list[str] = Field(
        default_factory=list,
        description="Ordered list of tool names invoked during this turn.",
    )
    raw_data: dict[str, Any] = Field(
        default_factory=dict,
        description=(
            "Parsed envelope returned by each tool, keyed by tool name. "
            "The frontend uses these to render tables / variance cards "
            "without re-parsing the assistant text."
        ),
    )
    error: str | None = Field(
        default=None,
        description=(
            "Populated only if the route caught an unexpected exception. "
            "``None`` on a successful turn."
        ),
    )


# ---------------------------------------------------------------------------
# /dealers
# ---------------------------------------------------------------------------


class DealerSummary(BaseModel):
    """One row of the dealer summary table — what ``GET /dealers`` returns."""

    distributor_code: str
    distributor_name: str
    account_profile_class: str
    total_activations: int
    total_commission_ngn: float
    zero_commission_count: int


# ---------------------------------------------------------------------------
# /periods
# ---------------------------------------------------------------------------


class PeriodList(BaseModel):
    """Wrapper for the list of available ``mon_period`` values."""

    periods: list[str] = Field(
        default_factory=list,
        description=(
            "Distinct mon_period values (YYYYMM) present in the activation "
            "data, sorted descending."
        ),
    )


# ---------------------------------------------------------------------------
# Phase 2 — Activation Intelligence
# ---------------------------------------------------------------------------


class ActivationSummaryResponse(BaseModel):
    """One dealer-month activation summary row, as returned by
    ``GET /activations/summary``."""

    dealer_id: str
    dealer_name: str
    account_profile_class: str = ""
    report_month: str
    activation_count: int
    qualified_activation_count: int
    non_qualified_activation_count: int
    activation_commission_amount: float
    qualification_rate_pct: float


class ActivationVarianceResponse(BaseModel):
    """One dealer's activation delta between two periods, returned by
    ``GET /activations/variance``."""

    dealer_id: str
    dealer_name: str
    period_a: str
    period_b: str
    activation_count_a: int
    activation_count_b: int
    delta_activations: int
    delta_commission_ngn: float
    delta_qualification_rate: float


class ActivationExceptionResponse(BaseModel):
    """One row of an activation exception flag, returned by
    ``GET /activations/exceptions``."""

    dealer_id: str
    dealer_name: str
    account_profile_class: str = ""
    exception_type: str
    activation_count: int
    qualified_activation_count: int
    qualification_rate_pct: float
    activation_commission_amount: float


# ---------------------------------------------------------------------------
# Assurance Layer scaffolding
# ---------------------------------------------------------------------------


class AssuranceModuleStatus(BaseModel):
    """Per-module summary inside ``AssuranceStatusResponse``.

    ``high_count``, ``medium_count`` and ``low_count`` are optional — they
    are present only for implemented modules. NOT_IMPLEMENTED stubs omit
    them entirely (see ``response_model_exclude_none=True`` on the route).
    """

    module: str
    phase: int
    implemented: bool
    status: str
    summary: str
    high_count: int | None = None
    medium_count: int | None = None
    low_count: int | None = None


class AssuranceStatusResponse(BaseModel):
    """Response payload for ``GET /assurance/status``."""

    period: str
    modules: list[AssuranceModuleStatus]


# ---------------------------------------------------------------------------
# Phase 3 — Inventory Assurance
# ---------------------------------------------------------------------------


class InventoryComparisonRecord(BaseModel):
    """One row of the dealer-product inventory comparison, returned by
    ``GET /inventory/comparison``."""

    dealer_id: str
    dealer_name: str
    product_code: str
    product_name: str
    activation_count: int
    qualified_count: int
    total_units_purchased: float | None = None
    inventory_gap: float | None = None
    gap_pct: float | None = None
    finding_type: str
    data_coverage_note: str


# ---------------------------------------------------------------------------
# Phase 4 — Payment Intelligence
# ---------------------------------------------------------------------------


class PaymentSummaryRecord(BaseModel):
    """One row of the simulated payment dataset for a dealer-month."""

    distributor_code: str
    distributor_name: str
    account_profile_class: str = ""
    report_month: str
    commission_owed: float
    amount_paid: float
    amount_unpaid: float
    payment_status: str
    payment_channel: str
    payment_date: str | None = None
    exception_flag: str | None = None
    data_source: str = "SIMULATED"


class PaymentCoverageResponse(BaseModel):
    """Aggregated coverage payload for ``GET /payments/summary``."""

    period: str
    total_commission_owed: float
    total_amount_paid: float
    total_amount_unpaid: float
    payment_coverage_pct: float
    disputed_count: int
    partially_paid_count: int
    pending_count: int
    fully_paid_count: int
    data_source: str = "SIMULATED"
    records: list[PaymentSummaryRecord]


class PaymentVarianceRecord(BaseModel):
    """One dealer's payment delta between two periods, returned by
    ``GET /payments/variance``."""

    dealer_id: str
    dealer_name: str
    period_a: str
    period_b: str
    commission_owed_a: float
    amount_paid_a: float
    payment_status_a: str
    commission_owed_b: float
    amount_paid_b: float
    payment_status_b: str
    delta_paid: float
    status_changed: bool
