"""Additive contracts for the bounded commission investigation workspace."""
from typing import Literal

from pydantic import BaseModel


class CommissionAccount(BaseModel):
    dealer_id: str
    dealer_name: str
    account_profile_class: str
    amount_ngn: float
    record_count: int
    zero_count: int
    prior_amount_ngn: float | None = None
    delta_ngn: float | None = None
    delta_pct: float | None = None


class CommissionTotals(BaseModel):
    account_count: int
    amount_ngn: float
    record_count: int
    zero_count: int
    accounts_with_zero: int
    all_zero_accounts: int
    prior_account_count: int | None = None
    prior_amount_ngn: float | None = None
    delta_ngn: float | None = None


class CommissionPage(BaseModel):
    mon_period: str
    prior_period: str | None
    stream: Literal['activation', 'orsc']
    source: str
    generated_at: str
    summary: CommissionTotals
    filtered_summary: CommissionTotals
    partner_classes: list[str]
    items: list[CommissionAccount]
    total: int
    limit: int
    offset: int


class DenominationAmount(BaseModel):
    denomination: str
    amount_ngn: float
    prior_amount_ngn: float | None
    delta_ngn: float | None


class CommissionDetail(BaseModel):
    mon_period: str
    prior_period: str | None
    stream: Literal['activation', 'orsc']
    source: str
    generated_at: str
    account: CommissionAccount
    denominations: list[DenominationAmount]
    unattributed_amount_ngn: float


class ZeroRecord(BaseModel):
    imei: str | None
    product_name: str | None
    product_code: str | None
    invoice_date: str | None
    first_activation_date: str | None
    unit_selling_price: float | None
    commission_rate: float | None


class ZeroRecordPage(BaseModel):
    mon_period: str
    dealer_id: str
    source: str
    generated_at: str
    items: list[ZeroRecord]
    total: int
    limit: int
    offset: int
