"""Public assistant inputs share the bounded subscription read models."""
from pydantic import BaseModel, Field, ConfigDict
from backend.api.subscription_schemas import PaymentFilter, DealerSort, DeviceSort, Direction, ReasonFilter
from backend.db import subscription_workspace as workspace


class SummaryInput(BaseModel):
    model_config = ConfigDict(extra='forbid')
    mon_period: str = Field(pattern=r'^\d{6}$')
    distributor_code: str | None = None
    limit: int = Field(25, ge=1, le=100)
    offset: int = Field(0, ge=0)
    search: str = Field('', max_length=100)
    payment_status: PaymentFilter = 'all'
    sort_by: DealerSort = 'simulated_commission_ngn'
    direction: Direction = 'desc'


class DeviceInput(BaseModel):
    model_config = ConfigDict(extra='forbid')
    mon_period: str = Field(pattern=r'^\d{6}$')
    distributor_code: str
    limit: int = Field(25, ge=1, le=100)
    offset: int = Field(0, ge=0)
    search: str = Field('', max_length=100)
    reason: ReasonFilter = 'all'
    sort_by: DeviceSort = 'imei'
    direction: Direction = 'asc'


SUBSCRIPTION_TOOLS = [
    {'name': 'get_subscription_summary',
     'description': 'Subscription workspace recorded revenue, eligible revenue, illustrative commission, dealer expectation/variance and separate supplied subscription payment evidence. In sample mode these are synthetic, unconfirmed policy examples: preserve the exact policy_label and synthetic provenance in every answer. In live mode commission is unavailable, revenue only. Optional exact dealer selection returns account detail; otherwise bounded dealer page with whole-filter totals. Never combine these settlements with activation payments. Unknown remains null.',
     'input_schema': SummaryInput.model_json_schema()},
    {'name': 'get_subscription_devices',
     'description': 'On-demand bounded evidence for one selling dealer and reporting month: PAID activity, original activation and exclusive eligibility anniversary, recorded calculation, expectation variance, due/settlement evidence, and contextual churn with history completeness. Preserve exact policy_label and synthetic provenance. These illustrative exclusions differ from activation root causes; churn is never an exclusion. Live device commission evidence is unavailable.',
     'input_schema': DeviceInput.model_json_schema()},
]


def summary(tool_input):
    params = SummaryInput.model_validate(tool_input).model_dump()
    period = params.pop('mon_period')
    dealer = params.pop('distributor_code')
    if dealer:
        data = workspace.detail(period, dealer)
        if data is None:
            raise ValueError('No subscription records for this dealer and period')
        return data
    return workspace.page(period, **params)


def devices(tool_input):
    params = DeviceInput.model_validate(tool_input).model_dump()
    return workspace.devices(params.pop('mon_period'), params.pop('distributor_code'), **params)
