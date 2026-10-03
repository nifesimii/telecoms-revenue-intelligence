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
    'activation_exceptions', 'payment_exceptions', 'investigation_queue',
]
# Each answers from one dealer-month evidence read: alone, one dealer, one month.
DEALER_MONTH_MEASURES = frozenset({'investigation_priority', 'dealer_statement', 'verification_outcome'})
# Each compares one dealer across two months: alone, one dealer, two months.
DEALER_COMPARISON_MEASURES = frozenset({'commission_variance'})
# Each answers for one month, across all dealers or one: alone, one month.
MONTH_MEASURES = frozenset({'data_coverage', 'activation_exceptions', 'payment_exceptions',
                            'investigation_queue'})
# Month measures over every dealer at once; a dealer is never part of their scope.
ALL_DEALER_MEASURES = frozenset({'investigation_queue'})
# Answered from their own evidence read and renderer, never combined with other measures.
STANDALONE_MEASURES = DEALER_MONTH_MEASURES | DEALER_COMPARISON_MEASURES | MONTH_MEASURES


class MeasureScope(BaseModel):
    """One active request, resolved using the latest question and scoped history."""

    model_config = ConfigDict(extra='forbid', strict=True)

    kind: Literal['measure', 'clarification', 'knowledge', 'identity', 'unsupported', 'affiliation'] = Field(
        description='Use measure for explicit measures even when evidence is unavailable. Clarification must have no measures.')
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
    # Queue filters, plus a bounded limit for single-month commission rankings.
    queue_severity: Literal['HIGH', 'MEDIUM', 'LOW'] | None = None
    queue_modules: list[Literal['commission', 'activation', 'inventory', 'payment']] = Field(
        default_factory=list, max_length=4)
    limit: int | None = Field(default=None, ge=1, le=100)
    clarification: Literal['sales_meaning', 'measure', 'period', 'dealer', 'request'] | None = None
    knowledge_quote: str | None = Field(default=None, min_length=1, max_length=1600)
    knowledge_topic: Literal['zero_commission_causes', 'activation_eligibility'] | None = None
    unsupported_reason: Literal[
        'read_only_action', 'lending_decision', 'subscription_policy',
        'payment_reference', 'momo', 'personal_data', 'capability',
    ] | None = None
    verification_focus: Literal['eligibility_window'] | None = None

    @model_validator(mode='after')
    def validate_scope(self):
        import re

        if any(not re.fullmatch(r'\d{4}(0[1-9]|1[0-2])', period) for period in self.periods):
            raise ValueError('Periods must be valid YYYYMM months')
        if len(set(self.periods)) != len(self.periods) or len(set(self.measures)) != len(self.measures):
            raise ValueError('Duplicate periods or measures')
        if self.kind not in {'identity', 'measure', 'affiliation'} and self.dealer_name:
            raise ValueError('Name association lookups require the identity contract')
        # A measure names its dealer by code or by name (resolved by the application), never both.
        if self.kind == 'measure' and self.dealer_name is not None and (
                self.dealer_id is not None or not self.dealer_name.strip()):
            raise ValueError('A measure dealer is a code or a recorded name, not both')
        dealer = self.dealer_id or self.dealer_name
        if self.unsupported_reason and self.kind != 'unsupported':
            raise ValueError('Unsupported reasons cannot authorize other response kinds')
        if self.knowledge_topic and self.kind != 'knowledge':
            raise ValueError('Policy topics require a knowledge response')
        if self.verification_focus and self.measures != ['verification_outcome']:
            raise ValueError('Verification focus requires a verification outcome request')
        if (self.queue_severity or self.queue_modules) and (
                self.measures != ['investigation_queue']):
            raise ValueError('Queue filters require an investigation_queue request')
        commission_ranking = (self.kind == 'measure' and self.measures == ['activation_commission']
            and len(self.periods) == 1 and not dealer and self.operation == 'breakdown'
            and self.breakdown == 'dealer' and self.filter == 'all')
        if self.limit is not None and self.measures != ['investigation_queue'] and not commission_ranking:
            raise ValueError('Limit requires an investigation queue or single-month activation commission ranking')
        if len(set(self.queue_modules)) != len(self.queue_modules):
            raise ValueError('Duplicate queue modules')
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
            if ALL_DEALER_MEASURES.intersection(self.measures) and dealer:
                raise ValueError('The investigation queue covers all dealers; one dealer is investigation_priority')
        elif self.kind == 'unsupported':
            if not self.unsupported_reason or self.measures or self.clarification or self.knowledge_quote:
                raise ValueError('Unsupported requests require only a documented capability boundary')
        elif self.kind == 'clarification':
            if not self.clarification or self.measures or self.knowledge_quote:
                raise ValueError('A clarification cannot authorize evidence or quote policy')
        elif self.kind == 'identity':
            if not self.dealer_name or not self.dealer_name.strip() or self.measures or self.clarification or self.knowledge_quote:
                raise ValueError('Identity lookup requires only an exact recorded dealer name and optional periods')
        elif self.kind == 'affiliation':
            # Affiliation groups the sibling account codes recorded under one dealer for a single
            # reporting month, anchored on exactly one dealer (active code or an exact typed name).
            one_anchor = bool(self.dealer_id) != bool(self.dealer_name)
            blank_name = self.dealer_name is not None and not self.dealer_name.strip()
            if (not one_anchor or blank_name or len(self.periods) != 1
                    or self.measures or self.clarification or self.knowledge_quote
                    or self.operation != 'total' or self.filter != 'all'):
                raise ValueError('Affiliation requires one dealer (code or name) and one reporting month')
        elif self.measures or self.clarification or bool(self.knowledge_quote) == bool(self.knowledge_topic):
            raise ValueError('Knowledge answers require either a named topic or an exact core KB excerpt')
        return self


SCOPE_TOOL = {
    'name': 'resolve_measure_request',
    'description': (
        'Interpret the latest question, using active dealer/period context and the conversation. '
        'Return only the requested measures, never suggested proxies or unrelated workspace metrics. '
        'This is an interpretation contract, not a query: do not supply numbers, answers, or tool names. '
        'Use clarification only for genuinely unresolved meanings, time ranges or dealers. '
        'For a clear unsupported request use kind unsupported with unsupported_reason: '
        'read_only_action for database changes, releasing or initiating payments; '
        'lending_decision for loan offers/limits/approval; subscription_policy for approved '
        'subscription commission rates or eligibility rules; payment_reference for Oracle AP '
        'references or actual payment dates; momo for wallet balances/history; personal_data '
        'for personal phone numbers/contact data; capability for other unavailable operations '
        'such as semantic similarity search. Do not ask the user to rephrase a clear unsupported '
        'request. Do not use unsupported for a supported measure whose evidence may be missing. '
        'Sales has no global default meaning: reuse only a meaning explicitly established by the user '
        'in this conversation; otherwise clarify sales_meaning. "Sales revenue" is the dealer income '
        'statement line: select financial_statements with line_ids [\'sales_revenue\']. Explicit '
        'customer sales or sales value are retail_sales_units/value and may be unavailable. '
        'Explicit actual retail sales to customers has an established meaning even without '
        'specifying units versus value: select both retail_sales_units and retail_sales_value '
        'if neither is specified, since both lack customer transaction evidence. Do not ask '
        'for a different measure or clarify sales_meaning again. '
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
        'For top dealers by activation commission use activation_commission, one month, '
        'operation breakdown, breakdown dealer, no dealer, and limit equal to the requested '
        'number (1 for the top dealer, max 100). '
        'Qualification counts describe recorded commission-bearing records, not verified eligibility. '
        'Inventory comparison can request inventory_gap and inventory_recorded_purchases; '
        'these are not total dealer purchases. financial_* metrics are whole-business Financial '
        'Health statements, including non-MTN activity; use them only for statement terms. '
        'Questions about ONE dealer, such as whether it is a (high) priority, whether to investigate '
        'it, or where it sits in the investigation queue, including priority "on commission", select '
        "measures ['investigation_priority'] alone for the reporting month and the active dealer, "
        'one period, operation total. If no dealer is active or named, clarify dealer. '
        'Month-wide queue questions across all dealers, such as the top or HIGH-priority dealers '
        'this month, which dealers have both payment and inventory findings, who to investigate '
        "first, or which dealers' assurance health is worst (not Financial Health statements), "
        "select measures ['investigation_queue'] alone for one month, operation total, with no "
        'dealer_id or dealer_name, even when a dealer is active; it never answers for one dealer. Set queue_severity only when '
        'a severity is asked for, queue_modules only for modules the dealer must have findings in '
        '(all listed), and limit only when a number of dealers is asked for (default 10, max 100). '
        "A dealer's statement, or what MTN owes a dealer together with what has been paid and "
        "what is outstanding in one answer, selects measures ['dealer_statement'] alone for the "
        'reporting month and the active dealer, one period, operation total; a single payment '
        'figure asked on its own keeps its payment_* measure. If no dealer is active or named, clarify dealer. '
        'Questions whether a dealer was paid correctly, whether it can be proven, what the audit '
        'found, or whether zero-commission records are really outside the eligibility window select '
        "measures ['verification_outcome'] alone, the same way (one dealer, one month, total). "
        'For a question specifically about the eligibility window, set verification_focus '
        'to eligibility_window so unrelated payment or inventory audits are not included. '
        'For why a dealer has zero commission or whether its cause is verified, use '
        'zero_commission_count with operation explain, NOT verification_outcome. '
        'This supplies the count plus bounded record observations and unverified-cause limits. '
        'verification_outcome ALWAYS requires operation total, even when the question says why. '
        "Why a dealer's commission changed between two months, or how the change splits by "
        "product or denomination, selects measures ['commission_variance'] alone for the active "
        'dealer and exactly two months (the reporting month and the month before it unless both '
        'are named), operation explain for why or compare otherwise. If no dealer is active or '
        'named, clarify dealer. '
        'Comparing activation commission BY PRODUCT across two months also selects '
        'commission_variance alone, operation compare; it supplies per-product changes. '
        'Whether the data for a month can be trusted, which dealers have missing source data, '
        'missing invoice (IFS) records or a missing account profile class, select measures '
        "['data_coverage'] alone for one month, operation total, with dealer_id only when one "
        'dealer is asked about. '
        'Which dealers have activation exceptions, or how many, select measures '
        "['activation_exceptions'] alone; which dealers have payment exceptions (disputed, "
        "partially paid or pending settlements), or how many, select ['payment_exceptions'] "
        'alone. Each is for one month, operation total, with dealer_id only when one dealer '
        'is asked about. '
        'For a particular ratio, select financial_kpis and its exact kpi_ids. '
        'For a particular statement or line, select financial_statements and exact statement_ids '
        'and/or line_ids. Empty financial selectors mean ALL KPIs or statements, and are '
        'authorized only when the user explicitly requests all of them. '
        'For listing codes associated with an exact complete dealer name, use kind identity '
        'with dealer_name, no measures. Omit periods to search all available months unless '
        'the user explicitly requests a date range; workspace month must not narrow this lookup. '
        'How many OTHER dealer codes are addressed to, or recorded under, the same dealer (the '
        'same recorded dealer name) as the current dealer, and/or those sibling codes\' combined '
        'or total commission, use kind affiliation for one month (the reporting month), anchored '
        'on the active dealer code (dealer_id) when a dealer is active, otherwise on an exact '
        'typed dealer_name; set no measures, operation total, filter all. This groups account '
        'codes by recorded name, an unverified association, not a measure. A single dealer\'s own '
        'commission stays a normal measure, never affiliation. '
        'For general zero-commission causes (including questions about a fifth cause), use '
        'kind knowledge, knowledge_topic zero_commission_causes, and omit knowledge_quote. '
        'For general activation eligibility-window policy, use kind knowledge, '
        'knowledge_topic activation_eligibility, and omit knowledge_quote. The application '
        'reads the documented KB section for these topics; do not transcribe it. '
        'For other general policy questions, use knowledge with an exact, relevant contiguous '
        'knowledge_quote from the core KB and omit knowledge_topic. Do not use knowledge '
        'to answer a request for dealer figures. '
        'Ambiguous intents must clarify request, not guess an available measure. '
        'When a measure question names a dealer instead of giving its code, set dealer_name '
        'to the name exactly as the user wrote it and omit dealer_id; never guess a code, and '
        'never send both. A named dealer counts as named wherever a dealer is required. '
        'Contract examples (substitute the actual active dealer and months): '
        '"I need customer sales value, not activations" => kind measure, measures '
        '[retail_sales_value], no clarification. Evidence unavailable does NOT mean unclear intent. '
        '"Why zero commission?" => kind measure, measures [zero_commission_count], '
        'operation explain, dealer_id and one period. '
        '"Compare May and June commission by product" => kind measure, measures '
        '[commission_variance], operation compare, dealer_id and periods [202605,202606]. '
        'For kind clarification, measures MUST be empty. Do not set contradictory kind, '
        'measures, clarification or unsupported_reason fields.'
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
    from backend.agent.knowledge_response import knowledge_response as render_knowledge

    return render_knowledge(scope, kb)


def unsupported_response(scope: MeasureScope, kb: str) -> str:
    """Select a KB-owned limitation; model-authored explanations cannot cross here."""
    import re

    marker = '**' + scope.unsupported_reason + '**'
    for paragraph in re.split(r'\n\s*\n', kb):
        if paragraph.startswith(marker + ' — '):
            return paragraph[len(marker + ' — '):].strip()
    raise ValueError('Unsupported capability boundary is missing from the core KB')
