"""Validated interpretation of a chat turn; never a source of financial facts.

Natural-language interpretation is probabilistic. After interpretation the
application, not the model, chooses queries, fields, labels and output values.
"""
from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator


Measure = Literal[
    'activation_count', 'activation_commission', 'zero_commission_count',
    'activation_qualified_count', 'activation_unqualified_count',
    'subscription_revenue', 'subscription_commission', 'subscription_settled',
    'subscription_outstanding', 'payment_paid', 'payment_owed',
    'payment_outstanding', 'payment_status', 'retail_sales_units',
    'retail_sales_value', 'dealer_purchases', 'inventory_gap',
    'inventory_recorded_purchases', 'financial_revenue', 'financial_net_profit',
    'financial_statements', 'financial_kpis', 'investigation_priority',
    'dealer_statement', 'verification_outcome', 'commission_variance', 'data_coverage',
]
# Each answers from one dealer-month evidence read: alone, one dealer, one month.
DEALER_MONTH_MEASURES = frozenset({'investigation_priority', 'dealer_statement', 'verification_outcome'})
# Each compares one dealer across two months: alone, one dealer, two months.
DEALER_COMPARISON_MEASURES = frozenset({'commission_variance'})
# Each answers for one month, across all dealers or one: alone, one month.
MONTH_MEASURES = frozenset({'data_coverage'})
# Answered from their own evidence read and renderer, never combined with other measures.
STANDALONE_MEASURES = DEALER_MONTH_MEASURES | DEALER_COMPARISON_MEASURES | MONTH_MEASURES


class MeasureScope(BaseModel):
    """One active request, resolved using the latest question and scoped history."""

    model_config = ConfigDict(extra='forbid', strict=True)

    kind: Literal['measure', 'clarification', 'knowledge', 'identity']
    measures: list[Measure] = Field(default_factory=list, max_length=12)
    periods: list[str] = Field(default_factory=list, max_length=24)
    dealer_id: str | None = Field(default=None, min_length=1, max_length=100, pattern=r'^\S+$')
    dealer_name: str | None = Field(default=None, min_length=1, max_length=300)
    operation: Literal['total', 'breakdown', 'compare', 'explain'] = 'total'
    breakdown: Literal['dealer', 'product', 'month'] = 'dealer'
    filter: Literal['all', 'zero_commission', 'disputed', 'unpaid', 'low_qualification'] = 'all'
    kpi_ids: list[Literal['gross_margin', 'net_margin', 'operating_cash_flow', 'current_ratio', 'debt_to_equity', 'dscr']] = Field(default_factory=list, max_length=6)
    statement_ids: list[Literal['income', 'balance', 'cashflow']] = Field(default_factory=list, max_length=3)
    line_ids: list[Literal[
        'sales_revenue', 'commission_income', 'revenue', 'cost_of_sales', 'gross_profit',
        'operating_expenses', 'depreciation', 'operating_profit', 'interest', 'profit_before_tax',
        'tax', 'net_profit', 'cash', 'receivables', 'inventory', 'current_assets', 'fixed_assets',
        'total_assets', 'payables', 'current_debt', 'current_liabilities', 'long_term_debt',
        'total_liabilities', 'capital', 'retained_earnings', 'total_equity', 'liabilities_and_equity',
        'receivables_cash_adjustment', 'inventory_cash_adjustment', 'payables_cash_adjustment',
        'operating_cash_flow', 'capital_expenditure', 'investing_cash_flow', 'new_borrowing',
        'principal_paid', 'financing_cash_flow', 'opening_cash', 'net_cash_change', 'closing_cash',
    ]] = Field(default_factory=list, max_length=40)
    clarification: Literal['sales_meaning', 'measure', 'period', 'dealer', 'request'] | None = None
    knowledge_quote: str | None = Field(default=None, min_length=1, max_length=1600)

    @model_validator(mode='after')
    def validate_scope(self):
        import re

        if any(not re.fullmatch(r'\d{4}(0[1-9]|1[0-2])', period) for period in self.periods):
            raise ValueError('Periods must be valid YYYYMM months')
        if len(set(self.periods)) != len(self.periods) or len(set(self.measures)) != len(self.measures):
            raise ValueError('Duplicate periods or measures')
        if self.kind not in {'identity', 'measure'} and self.dealer_name:
            raise ValueError('Name association lookups require the identity contract')
        # A measure names its dealer by code or by name (resolved by the application), never both.
        if self.kind == 'measure' and self.dealer_name is not None and (
                self.dealer_id is not None or not self.dealer_name.strip()):
            raise ValueError('A measure dealer is a code or a recorded name, not both')
        dealer = self.dealer_id or self.dealer_name
        if self.kpi_ids and 'financial_kpis' not in self.measures:
            raise ValueError('KPI selectors require a financial KPI request')
        if (self.statement_ids or self.line_ids) and 'financial_statements' not in self.measures:
            raise ValueError('Statement selectors require a financial statement request')
        if self.kind == 'measure':
            unsupported = {'retail_sales_units', 'retail_sales_value', 'dealer_purchases'}
            if (not self.measures or (not self.periods and not set(self.measures) <= unsupported)
                    or self.clarification or self.knowledge_quote):
                raise ValueError('A measure request requires measures and periods only')
            if self.operation in {'compare', 'explain'} and len(self.periods) > 2:
                raise ValueError('Comparisons support at most two explicit months')
            if DEALER_MONTH_MEASURES.intersection(self.measures) and (
                    len(self.measures) != 1 or len(self.periods) != 1
                    or not dealer or self.operation != 'total' or self.filter != 'all'):
                raise ValueError('Dealer-month measures stand alone for one dealer and one month')
            if DEALER_COMPARISON_MEASURES.intersection(self.measures) and (
                    len(self.measures) != 1 or len(self.periods) != 2 or not dealer
                    or self.operation not in {'compare', 'explain'} or self.filter != 'all'):
                raise ValueError('Dealer comparison measures stand alone for one dealer and two months')
            if MONTH_MEASURES.intersection(self.measures) and (
                    len(self.measures) != 1 or len(self.periods) != 1
                    or self.operation != 'total' or self.filter != 'all'):
                raise ValueError('Month measures stand alone for one month')
        elif self.kind == 'clarification':
            if not self.clarification or self.measures or self.knowledge_quote:
                raise ValueError('A clarification cannot authorize evidence or quote policy')
        elif self.kind == 'identity':
            if not self.dealer_name or not self.dealer_name.strip() or self.measures or self.clarification or self.knowledge_quote:
                raise ValueError('Identity lookup requires only an exact recorded dealer name and optional periods')
        elif self.measures or self.clarification or not self.knowledge_quote:
            raise ValueError('Knowledge answers must cite an exact core KB excerpt')
        return self


SCOPE_TOOL = {
    'name': 'resolve_measure_request',
    'description': (
        'Interpret the latest question, using active dealer/period context and the conversation. '
        'Return only the requested measures, never suggested proxies or unrelated workspace metrics. '
        'This is an interpretation contract, not a query: do not supply numbers, answers, or tool names. '
        'Use clarification for unresolved meanings, time ranges, dealers, or unsupported operations. '
        'Sales has no global default meaning: reuse only a meaning explicitly established by the user '
        'in this conversation; otherwise clarify sales_meaning. "Sales revenue" is the dealer income '
        'statement line: select financial_statements with line_ids [\'sales_revenue\']. Explicit '
        'customer sales or sales value are retail_sales_units/value and may be unavailable. '
        'Dealer purchases are not activations. '
        'For explicit retail sales or complete dealer purchases, a missing period does not '
        'need clarification: periods may be empty because evidence is unavailable regardless. '
        'An offered alternative is authorized only after user acceptance. '
        'A current explicit measure overrides old questions and workspace labels. '
        'Do not clarify sales for an explicit activation question. '
        'Include every month of the requested year/range, including months without evidence; '
        'never shorten a calendar year to available months. If this year or YTD has no clear '
        'anchor, clarify period. Preserve exact active dealer codes including leading zeros. '
        'Use breakdown for requested lists/rankings, product only for product breakdowns; '
        'explain for why, compare for two-month comparisons. Only select filters explicitly asked for. '
        'Qualification counts describe recorded commission-bearing records, not verified eligibility. '
        'Inventory comparison can request inventory_gap and inventory_recorded_purchases; '
        'these are not total dealer purchases. financial_* metrics are whole-business Financial '
        'Health statements, including non-MTN activity; use them only for statement terms. '
        'Questions such as whether a dealer is a (high) priority, whether to investigate a dealer, '
        'or where it sits in the investigation queue, including priority "on commission", select '
        "measures ['investigation_priority'] alone for the reporting month and the active dealer, "
        'one period, operation total. If no dealer is active or named, clarify dealer. '
        "A dealer's statement, or what MTN owes a dealer together with what has been paid and "
        "what is outstanding in one answer, selects measures ['dealer_statement'] alone for the "
        'reporting month and the active dealer, one period, operation total; a single payment '
        'figure asked on its own keeps its payment_* measure. If no dealer is active or named, clarify dealer. '
        'Questions whether a dealer was paid correctly, whether it can be proven, what the audit '
        'found, or whether zero-commission records are really outside the eligibility window select '
        "measures ['verification_outcome'] alone, the same way (one dealer, one month, total). "
        "Why a dealer's commission changed between two months, or how the change splits by "
        "product or denomination, selects measures ['commission_variance'] alone for the active "
        'dealer and exactly two months (the reporting month and the month before it unless both '
        'are named), operation explain for why or compare otherwise. If no dealer is active or '
        'named, clarify dealer. '
        'Whether the data for a month can be trusted, which dealers have missing source data, '
        'missing invoice (IFS) records or a missing account profile class, select measures '
        "['data_coverage'] alone for one month, operation total, with dealer_id only when one "
        'dealer is asked about. '
        'For a particular ratio, select financial_kpis and its exact kpi_ids. '
        'For a particular statement or line, select financial_statements and exact statement_ids '
        'and/or line_ids. Empty financial selectors mean ALL KPIs or statements, and are '
        'authorized only when the user explicitly requests all of them. '
        'For listing codes associated with an exact complete dealer name, use kind identity '
        'with dealer_name, no measures. Omit periods to search all available months unless '
        'the user explicitly requests a date range; workspace month must not narrow this lookup. '
        'For a general policy question, use knowledge with an exact, relevant contiguous quote '
        'from the core KB. Do not use knowledge to answer a request for dealer figures. '
        'Unknown intents must clarify request, not guess an available measure. '
        'When a measure question names a dealer instead of giving its code, set dealer_name '
        'to the name exactly as the user wrote it and omit dealer_id; never guess a code, and '
        'never send both. A named dealer counts as named wherever a dealer is required.'
    ),
    'input_schema': MeasureScope.model_json_schema(),
}


def clarification_response(scope: MeasureScope) -> str:
    """Application-owned questions cannot leak model-authored alternative figures."""
    questions = {
        'sales_meaning': 'By sales, do you mean customer units sold, customer sales value, or purchases by the dealer from MTN? Recorded activations are a separate measure.',
        'measure': 'Which business measure would you like: activations, commission, subscription revenue, payments, or another explicitly named measure?',
        'period': 'Which reporting month or date range should I use? Please distinguish a full calendar year from activity through a selected month.',
        'dealer': 'Which exact dealer account should I use, or should I include all dealers?',
        'request': 'Please specify the measure and the figure, breakdown or comparison you need. I cannot resolve this request safely from the available scope.',
    }
    context = []
    if scope.dealer_id:
        # Dealer codes are context, never model-authored amounts or labels.
        context.append(f'Dealer account {scope.dealer_id}')
    if scope.periods:
        context.append('reporting months ' + ', '.join(scope.periods))
    return (('; '.join(context) + '.\n\n') if context else '') + questions[scope.clarification]


def knowledge_response(scope: MeasureScope, kb: str) -> str:
    """Only a verifiable policy excerpt can cross this non-data answer boundary."""
    quote = scope.knowledge_quote
    if not quote or quote not in kb:
        raise ValueError('Knowledge excerpt is not present in the core KB')
    return 'Documented policy:\n\n' + quote
