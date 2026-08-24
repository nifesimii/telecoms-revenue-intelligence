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
    """One row of the dealer summary table — what ``GET /dealers`` returns.

    Uses the platform-wide API convention: ``dealer_id`` / ``dealer_name`` on
    the response side, even though the underlying SQL/CSV column is
    ``distributor_code``. See ARCHITECTURE.md "Naming conventions".
    """

    dealer_id: str
    dealer_name: str
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


class AssuranceFinding(BaseModel):
    """A single dealer-level finding produced by an assurance module.

    Mirrors :class:`backend.assurance.base.AssuranceResult.findings` dict
    entries. Surfaces the rich context (name, description, recommended
    action) that the dashboard needs to be actionable, not just countable.
    """

    type: str
    severity: str  # HIGH | MEDIUM | LOW
    dealer_id: str
    dealer_name: str
    description: str
    recommended_action: str | None = None


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
    findings: list[AssuranceFinding] = []


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
    """One row of the payment dataset for a dealer-month.

    The base fields are populated by every source. The reconciliation fields
    are only populated when ``data_source == "APDP"`` — they're derived from
    ``normalized.partner_settlements`` and let the UI show the richer
    reconciliation state (sales captured vs commissions earned vs paid).
    """

    dealer_id: str
    dealer_name: str
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

    # --- v1.3.0 APDP reconciliation enrichment (None when SIMULATED) ---
    reconciliation_status: str | None = None       # 6-state canonical
    sale_count: int | None = None                   # consumer sales captured
    total_sales_ngn: float | None = None
    statement_gross_revenue_ngn: float | None = None
    payment_variance_ngn: float | None = None       # signed: paid − owed
    paid_count: int | None = None
    partial_count: int | None = None
    disputed_count: int | None = None


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


# ---------------------------------------------------------------------------
# /dealers/{dealer_id}/statement — per-period Finance/RA internal statement
# ---------------------------------------------------------------------------


class DealerStatementCommission(BaseModel):
    expected_ngn: float
    total_activations: int
    qualified_activation_count: int
    zero_commission_count: int
    by_denomination: dict[str, float]


class DealerStatementOrsc(BaseModel):
    device_count: int
    total_subscription_amount_ngn: float
    zero_amount_count: int


class DealerStatementApdpDetail(BaseModel):
    sale_count: int
    total_sales_ngn: float
    statement_count: int
    statement_gross_revenue_ngn: float
    settlement_count: int
    paid_count: int
    partial_count: int
    disputed_count: int
    reconciliation_status: str


class DealerStatementPayment(BaseModel):
    data_source: str        # "simulated" | "apdp"
    amount_paid_ngn: float
    payment_found: bool
    payment_status: str | None = None
    apdp_detail: DealerStatementApdpDetail | None = None


class DealerStatementPosition(BaseModel):
    expected_ngn: float
    paid_ngn: float
    outstanding_ngn: float
    variance_pct: float | None = None
    headline: str           # "PAID_IN_FULL" | "UNDERPAID" | "OVERPAID"


class DealerStatementAuditRef(BaseModel):
    module: str
    label: str
    trail_id: int | None = None
    conclusion: str
    confidence: str
    caveat_count: int | None = None
    generated_at: str | None = None


class DealerStatementResponse(BaseModel):
    """Per-period Finance/RA internal statement for one dealer."""

    dealer_id: str
    dealer_name: str
    account_profile_class: str
    mon_period: str
    commission: DealerStatementCommission
    orsc: DealerStatementOrsc | None = None
    payment: DealerStatementPayment
    position: DealerStatementPosition
    audit_trails: list[DealerStatementAuditRef]


class IfsMissingItem(BaseModel):
    """One dealer with NO_INVOICE_RECORD inventory rows for the period."""

    dealer_id: str
    dealer_name: str
    affected_products: int
    activation_count: int


class UspMissingItem(BaseModel):
    """One dealer with NULL account_profile_class for the period."""

    dealer_id: str
    dealer_name: str
    total_activations: int
    zero_commission_count: int
    commission_ngn: float


class DataCoverageTicketResponse(BaseModel):
    """Payload for ``GET /inventory/data-coverage-issues``.

    ``ticket_body`` is markdown ready to paste into a ServiceNow incident
    or change-request. The structured ``ifs_missing`` / ``usp_missing``
    lists are included for the UI to render the same data natively.
    """

    mon_period: str
    source: str  # "ifs" | "usp" | "both"
    severity: str  # "LOW" | "MEDIUM" | "HIGH"
    severity_action: str
    affected_dealers: int
    ifs_missing: list[IfsMissingItem]
    usp_missing: list[UspMissingItem]
    ticket_body: str


class DisputeDraftRequest(BaseModel):
    """Body for ``POST /payments/disputes/draft``."""

    distributor_code: str
    mon_period: str
    # Optional verbatim quote of the dealer's claim — included in the
    # letter so the recipient sees exactly what we're responding to.
    dispute_text: str | None = None
    # If the caller already has the paid amount (e.g. from /payments/summary),
    # pass it through so the recommended position reflects real settlement state.
    amount_paid: float | None = None


class DisputeDraftSummary(BaseModel):
    reference: str
    dealer_id: str
    dealer_name: str
    mon_period: str
    total_activations: int
    qualified_activations: int
    unqualified_activations: int
    qualification_rate_pct: float
    qualified_commission_ngn: float
    statement_claim_ngn: float
    amount_paid_ngn: float
    outstanding_ngn: float
    root_cause_classifications: dict[str, int]
    position_code: str


class DisputeDraftResponse(BaseModel):
    """Payload for ``POST /payments/disputes/draft``."""

    markdown: str
    summary: DisputeDraftSummary


class AuditRunResponse(BaseModel):
    """Provenance returned by the audit run endpoints."""

    run_id: str
    mon_period: str
    payment_source: str
    trail_count: int
    started_at: str
    module: str = "zero_commission"


class PartnerHealthRecord(BaseModel):
    """One dealer's health scorecard row."""

    dealer_id: str
    dealer_name: str
    account_profile_class: str = ""
    health_score: float
    health_band: str
    settlement_rate_pct: float
    settlement_rate_delta: float | None = None
    commission_yield_pct: float
    zero_commission_rate_pct: float
    outstanding_ngn: float
    dispute_flag: bool
    data_source: str


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
