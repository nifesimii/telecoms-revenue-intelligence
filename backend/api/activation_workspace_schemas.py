"""Additive contracts for the bounded activation investigation workspace."""
from typing import Literal

from pydantic import BaseModel, Field

from backend.api.schemas import ActivationSummaryResponse


ActivationView = Literal['accounts', 'comparison', 'exceptions']
ActivationFindingFilter = Literal[
    'all', 'with_zero', 'all_zero', 'ALL_UNQUALIFIED',
    'HIGH_UNQUALIFIED_RATE', 'UNUSUAL_VOLUME',
]
ActivationSort = Literal[
    'activation_count', 'dealer_name', 'non_qualified_activation_count',
    'qualification_rate_pct', 'activation_commission_amount',
    'delta_activations', 'severity',
]


class ActivationFinding(BaseModel):
    type: str
    label: str
    severity: Literal['HIGH', 'MEDIUM', 'LOW']
    recommended_action: str


class ActivationAccount(ActivationSummaryResponse):
    findings: list[ActivationFinding] = Field(default_factory=list)
    prior_activation_count: int | None = None
    prior_qualification_rate_pct: float | None = None
    prior_commission_amount: float | None = None
    delta_activations: int | None = None
    delta_qualification_rate: float | None = None
    delta_commission_ngn: float | None = None


class ActivationTotals(BaseModel):
    account_count: int
    activation_count: int
    qualified_activation_count: int
    non_qualified_activation_count: int
    qualification_rate_pct: float | None
    activation_commission_amount: float
    accounts_with_zero: int
    all_zero_accounts: int
    finding_count: int
    flagged_accounts: int


class ActivationPage(BaseModel):
    mon_period: str
    prior_period: str | None
    view: ActivationView
    source: str
    generated_at: str
    summary: ActivationTotals
    filtered_summary: ActivationTotals
    comparison_account_count: int
    partner_classes: list[str]
    items: list[ActivationAccount]
    total: int
    limit: int
    offset: int


class ActivationDetail(BaseModel):
    mon_period: str
    prior_period: str | None
    source: str
    generated_at: str
    account: ActivationAccount
