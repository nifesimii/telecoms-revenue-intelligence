"""Public bounded subscription contracts; unknown financial evidence stays null."""
from typing import Literal
from pydantic import BaseModel

PaymentStatus = Literal['paid', 'overdue', 'not_yet_due', 'unknown', 'mixed', 'not_applicable']
PaymentFilter = Literal['all', 'paid', 'overdue', 'not_yet_due', 'unknown', 'mixed', 'not_applicable']
Reason = Literal['eligible', 'below_minimum', 'no_paid_subscription', 'expired_eligibility', 'unknown_evidence']
ReasonFilter = Literal['all', 'eligible', 'below_minimum', 'no_paid_subscription', 'expired_eligibility', 'unknown_evidence']
DealerSort = Literal['simulated_commission_ngn', 'recorded_subscription_revenue_ngn', 'eligible_revenue_ngn',
                     'dealer_expectation_ngn', 'variance_ngn', 'outstanding_ngn', 'dealer_name', 'device_count']
DeviceSort = Literal['imei', 'simulated_commission_ngn', 'recorded_subscription_revenue_ngn', 'variance_ngn', 'due_date']
Direction = Literal['asc', 'desc']


class Provenance(BaseModel):
    mon_period: str
    source: str
    synthetic: bool
    policy_label: str | None
    evidence_as_of: str | None
    commission_available: bool
    availability: Literal['demo', 'revenue_only', 'no_source_records']
    eligibility_boundary: str | None


class Amounts(BaseModel):
    recorded_subscription_revenue_ngn: float | None
    eligible_revenue_ngn: float | None
    simulated_commission_ngn: float | None
    dealer_expectation_ngn: float | None
    variance_ngn: float | None
    amount_paid_ngn: float | None
    outstanding_ngn: float | None


class Account(Amounts):
    dealer_id: str
    dealer_name: str
    account_profile_class: str | None
    device_count: int
    payment_status: PaymentStatus
    reason_counts: dict[str, int]
    unknown_commission_count: int


class Totals(Amounts):
    account_count: int
    device_count: int
    known_simulated_commission_ngn: float | None
    known_recorded_subscription_revenue_ngn: float | None
    unknown_commission_count: int
    payment_status_counts: dict[str, int]
    reason_counts: dict[str, int]


class SubscriptionPage(Provenance):
    summary: Totals
    filtered_summary: Totals
    items: list[Account]
    total: int
    limit: int
    offset: int


class SubscriptionDetail(Provenance):
    account: Account


class Purchase(BaseModel):
    date: str
    status: Literal['PAID', 'FAILED']
    amount_ngn: float | None


class HistoryMonth(BaseModel):
    mon_period: str
    has_paid_subscription: bool | None


class Device(Amounts):
    mon_period: str
    dealer_id: str
    dealer_name: str
    selling_dealer_id: str
    account_profile_class: str | None
    imei: str
    scenario: str
    product_name: str
    first_activation_date: str | None
    eligibility_end_exclusive: str | None
    eligibility_boundary: str
    eligibility_status: Literal['within_window', 'expired', 'unknown']
    reason: Reason
    purchases: list[Purchase]
    activity_evidence_complete: bool
    paid_subscription_count: int | None
    paid_subscription_dates: list[str] | None
    qualifying_revenue_ngn: float | None
    history: list[HistoryMonth]
    history_complete: bool
    churn_indicator: bool | None
    due_date: str | None
    payment_status: PaymentStatus
    payment_date: str | None
    payment_evidence_reference: str | None
    expectation_reference: str | None
    variance_explanation: str
    source: str
    synthetic: bool
    policy_label: str
    evidence_as_of: str


class DevicePage(Provenance):
    dealer_id: str
    evidence_available: bool
    unavailable_reason: str | None
    items: list[Device]
    total: int
    limit: int
    offset: int
