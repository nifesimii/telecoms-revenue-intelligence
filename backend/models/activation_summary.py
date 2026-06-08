"""Dealer-month activation summary — Phase 2 (Activation Intelligence).

Aggregate-only model: no IMEI-level fields, no MoMo, no inventory. This is
the canonical shape returned by the activation summary query and any
dealer-month aggregate consumed by the UI or the agent.
"""
from __future__ import annotations

from pydantic import BaseModel, Field


class ActivationSummary(BaseModel):
    """One dealer's activation totals for a single reporting month."""

    dealer_id: str = Field(
        ..., description="Distributor code as a numeric string."
    )
    dealer_name: str
    account_profile_class: str = Field(
        default="",
        description="Partner type (FIXED BROADBAND, DATA PARTNERS, etc.). Empty if unclassified in TAS.",
    )
    report_month: str = Field(..., description="Reporting month in YYYYMM format.")

    activation_count: int = Field(
        ..., ge=0, description="Total activation rows for this dealer / month."
    )
    qualified_activation_count: int = Field(
        ...,
        ge=0,
        description="Activations where commission_rate > 0 (USP matched and within the 6-month eligibility window).",
    )
    non_qualified_activation_count: int = Field(
        ...,
        ge=0,
        description="Activations where commission_rate = 0. Root causes in KB Section 6.",
    )
    activation_commission_amount: float = Field(
        ...,
        ge=0.0,
        description="Sum of commission_rate over the qualified activations, in Naira.",
    )
    qualification_rate_pct: float = Field(
        ...,
        ge=0.0,
        le=100.0,
        description="qualified_activation_count / activation_count expressed as a percentage, rounded to 2dp.",
    )
