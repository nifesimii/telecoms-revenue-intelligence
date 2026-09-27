"""Deterministic, isolated synthetic whole-business statements. No external reads.

All amounts are integer NGN. This is a demonstration accounting model, never a
commission calculator or a claim about a real dealer. Interest and taxes are
paid in the reporting month; capital/owner drawings are unchanged.
"""
from calendar import monthrange
from copy import deepcopy
from functools import lru_cache

PERIODS = ('202601', '202602', '202603', '202604', '202605', '202606')
DEALERS = (
    dict(dealer_id='DEMO-001', dealer_name='Cedar Connect', scenario='Cash-generating operations',
         revenue=12_000_000, growth=1_000_000, cost_pct=60, expenses=2_100_000,
         interest=100_000, receivables_change=200_000, inventory_change=100_000,
         payables_change=50_000, capex=300_000, borrowing=0, principal=100_000),
    dict(dealer_id='DEMO-002', dealer_name='Harbour Digital', scenario='Cash tied up in working capital',
         revenue=10_000_000, growth=500_000, cost_pct=65, expenses=2_000_000,
         interest=120_000, receivables_change=2_000_000, inventory_change=800_000,
         payables_change=200_000, capex=100_000, borrowing=200_000, principal=100_000),
    dict(dealer_id='DEMO-003', dealer_name='Northstar Devices', scenario='Operating losses and debt pressure',
         revenue=8_000_000, growth=-200_000, cost_pct=85, expenses=2_000_000,
         interest=180_000, receivables_change=0, inventory_change=-100_000,
         payables_change=100_000, capex=50_000, borrowing=600_000, principal=200_000),
    dict(dealer_id='DEMO-004', dealer_name='Orchard Telecom', scenario='Repayment schedule unavailable',
         revenue=9_000_000, growth=500_000, cost_pct=60, expenses=1_700_000,
         interest=90_000, receivables_change=100_000, inventory_change=50_000,
         payables_change=30_000, capex=150_000, borrowing=0, principal=100_000),
)


def calculate_kpis(v):
    """Keep missing evidence and undefined denominators distinct from zero."""
    definitions = [
        ('gross_margin', 'Gross profit margin', 'percent', 'Gross profit / revenue × 100',
         ['gross_profit', 'revenue']),
        ('net_margin', 'Net profit margin', 'percent', 'Net profit after tax / revenue × 100',
         ['net_profit', 'revenue']),
        ('operating_cash_flow', 'Operating cash flow', 'ngn', 'Net cash from operating activities',
         ['operating_cash_flow']),
        ('current_ratio', 'Current ratio', 'multiple', 'Current assets / current liabilities',
         ['current_assets', 'current_liabilities']),
        ('debt_to_equity', 'Total liabilities-to-equity', 'multiple', 'Total liabilities / total equity',
         ['total_liabilities', 'total_equity']),
        ('dscr', 'Debt-service coverage', 'multiple', 'EBITDA / (scheduled principal + interest)',
         ['ebitda', 'scheduled_principal', 'interest']),
    ]
    result = []
    for key, label, unit, formula, fields in definitions:
        inputs = {field: v.get(field) for field in fields}
        status, reason, value = 'available', '', None
        if any(x is None for x in inputs.values()):
            status, reason = 'unavailable', 'Repayment schedule unavailable.' if key == 'dscr' else 'Required source records unavailable.'
        elif key == 'operating_cash_flow':
            value = v[key]
        elif key == 'debt_to_equity' and v['total_equity'] <= 0:
            status, reason = 'not_meaningful', 'Equity is zero or negative; a leverage multiple would be misleading.'
        else:
            denominator = v[fields[1]] + v['interest'] if key == 'dscr' else v[fields[1]]
            if denominator == 0:
                status = 'not_applicable'
                reason = 'No scheduled debt service for this month.' if key == 'dscr' else 'The denominator is zero.'
            else:
                value = round(v[fields[0]] / denominator * (100 if unit == 'percent' else 1), 2)
        result.append(dict(id=key, label=label, unit=unit, formula=formula, inputs=inputs,
                           value=value, status=status, reason=reason))
    return result


def _month(dealer, opening, index):
    v = opening.copy()
    v['revenue'] = dealer['revenue'] + index * dealer['growth']
    v['commission_income'] = v['revenue'] // 10
    v['sales_revenue'] = v['revenue'] - v['commission_income']
    v['cost_of_sales'] = v['revenue'] * dealer['cost_pct'] // 100
    v['gross_profit'] = v['revenue'] - v['cost_of_sales']
    v['operating_expenses'] = dealer['expenses']
    v['ebitda'] = v['gross_profit'] - v['operating_expenses']
    v['depreciation'] = 200_000
    v['operating_profit'] = v['ebitda'] - v['depreciation']
    v['interest'] = dealer['interest']
    v['profit_before_tax'] = v['operating_profit'] - v['interest']
    # Fictional scenario assumption, not a Nigerian tax calculation.
    v['tax'] = max(0, v['profit_before_tax'] * 30 // 100)
    v['net_profit'] = v['profit_before_tax'] - v['tax']
    for field in ('receivables', 'inventory', 'payables'):
        v[field] += dealer[f'{field}_change']
        v[f'{field}_cash_adjustment'] = dealer[f'{field}_change'] * (1 if field == 'payables' else -1)
    v['operating_cash_flow'] = v['net_profit'] + v['depreciation'] + sum(v[f'{f}_cash_adjustment'] for f in ('receivables', 'inventory', 'payables'))
    v['capital_expenditure'] = -dealer['capex']
    v['investing_cash_flow'] = v['capital_expenditure']
    v['new_borrowing'] = dealer['borrowing']
    v['principal_paid'] = -dealer['principal']
    v['financing_cash_flow'] = v['new_borrowing'] + v['principal_paid']
    v['net_cash_change'] = v['operating_cash_flow'] + v['investing_cash_flow'] + v['financing_cash_flow']
    v['opening_cash'] = opening['cash']
    v['cash'] += v['net_cash_change']
    v['closing_cash'] = v['cash']
    v['fixed_assets'] += dealer['capex'] - v['depreciation']
    v['current_debt'] -= dealer['principal']
    v['long_term_debt'] += dealer['borrowing']
    v['retained_earnings'] += v['net_profit']
    v['current_assets'] = v['cash'] + v['receivables'] + v['inventory']
    v['total_assets'] = v['current_assets'] + v['fixed_assets']
    v['current_liabilities'] = v['payables'] + v['current_debt']
    v['total_liabilities'] = v['current_liabilities'] + v['long_term_debt']
    v['total_equity'] = v['capital'] + v['retained_earnings']
    v['liabilities_and_equity'] = v['total_liabilities'] + v['total_equity']
    # Actual principal payment remains observable; a missing contractual schedule
    # does not prove whether that payment met the obligation.
    v['scheduled_principal'] = None if dealer['dealer_id'] == 'DEMO-004' else dealer['principal']
    return v


STATEMENTS = [
    ('income', 'Income statement', [
        ('Revenue', [('sales_revenue', 'Sales revenue'), ('commission_income', 'Commission income'), ('revenue', 'Total revenue')]),
        ('Profitability', [('cost_of_sales', 'Cost of sales'), ('gross_profit', 'Gross profit'), ('operating_expenses', 'Operating expenses'), ('depreciation', 'Depreciation'), ('operating_profit', 'Operating profit'), ('interest', 'Interest expense'), ('profit_before_tax', 'Profit before tax'), ('tax', 'Tax expense'), ('net_profit', 'Net profit after tax')]),
    ]),
    ('balance', 'Balance sheet', [
        ('Assets', [('cash', 'Cash and bank balances'), ('receivables', 'Trade receivables'), ('inventory', 'Inventory'), ('current_assets', 'Total current assets'), ('fixed_assets', 'Property and equipment, net'), ('total_assets', 'Total assets')]),
        ('Liabilities', [('payables', 'Trade payables'), ('current_debt', 'Current portion of borrowings'), ('current_liabilities', 'Total current liabilities'), ('long_term_debt', 'Long-term borrowings'), ('total_liabilities', 'Total liabilities')]),
        ('Equity', [('capital', 'Contributed capital'), ('retained_earnings', 'Retained earnings'), ('total_equity', 'Total equity'), ('liabilities_and_equity', 'Total liabilities and equity')]),
    ]),
    ('cashflow', 'Cash flow statement', [
        ('Operating activities', [('net_profit', 'Net profit after tax'), ('depreciation', 'Add back depreciation'), ('receivables_cash_adjustment', 'Change in receivables'), ('inventory_cash_adjustment', 'Change in inventory'), ('payables_cash_adjustment', 'Change in payables'), ('operating_cash_flow', 'Net cash from operating activities')]),
        ('Investing activities', [('capital_expenditure', 'Purchase of property and equipment'), ('investing_cash_flow', 'Net cash from investing activities')]),
        ('Financing activities', [('new_borrowing', 'Proceeds from borrowings'), ('principal_paid', 'Principal repayments'), ('financing_cash_flow', 'Net cash from financing activities')]),
        ('Cash reconciliation', [('opening_cash', 'Opening cash'), ('net_cash_change', 'Net change in cash'), ('closing_cash', 'Closing cash')]),
    ]),
]
TOTALS = {'revenue', 'gross_profit', 'operating_profit', 'profit_before_tax', 'net_profit', 'current_assets', 'total_assets', 'current_liabilities', 'total_liabilities', 'total_equity', 'liabilities_and_equity', 'operating_cash_flow', 'investing_cash_flow', 'financing_cash_flow', 'net_cash_change', 'closing_cash'}


@lru_cache(maxsize=1)
def _records():
    records = {}
    for dealer in DEALERS:
        v = dict(cash=8_000_000, receivables=3_000_000, inventory=4_000_000,
                 fixed_assets=5_000_000, payables=2_000_000, current_debt=1_500_000,
                 long_term_debt=3_500_000, capital=10_000_000, retained_earnings=3_000_000)
        if dealer['dealer_id'] == 'DEMO-003':
            v.update(cash=4_000_000, receivables=1_000_000, inventory=2_000_000,
                     fixed_assets=3_000_000, payables=3_000_000, current_debt=2_000_000,
                     long_term_debt=7_000_000, capital=1_000_000, retained_earnings=-3_000_000)
        for index, period in enumerate(PERIODS):
            v = _month(dealer, v, index)
            records[(dealer['dealer_id'], period)] = v
    return records


def get_report(dealer_id, period):
    values = _records().get((dealer_id, period))
    if values is None:
        return None
    values = deepcopy(values)
    dealer = next(d for d in DEALERS if d['dealer_id'] == dealer_id)
    index = PERIODS.index(period)
    prior_period = PERIODS[index - 1] if index else None
    previous = _records().get((dealer_id, prior_period), {})
    date = f'{period[:4]}-{period[4:]}-{monthrange(int(period[:4]), int(period[4:]))[1]}'
    statements = []
    for key, label, groups in STATEMENTS:
        rows = [dict(id=field, label=name, section=section, amount=values[field],
                     prior_amount=previous.get(field), total=field in TOTALS,
                     evidence=['monthly_records', 'payment_activity'] if key == 'cashflow' or field == 'cash' else ['monthly_records'])
                for section, fields in groups for field, name in fields]
        statements.append(dict(id=key, label=label, rows=rows))
    observations = [dict(title='Profit and cash tell different stories' if values['net_profit'] > 0 and values['operating_cash_flow'] < 0 else 'Operations generated cash' if values['operating_cash_flow'] >= 0 else 'Operations consumed cash',
                         detail='Compare net profit with operating cash flow; receivables, inventory and payables explain the working-capital movement.',
                         evidence=['net_profit', 'operating_cash_flow', 'receivables_cash_adjustment', 'inventory_cash_adjustment', 'payables_cash_adjustment'])]
    if values['total_equity'] <= 0:
        observations.append(dict(title='Liabilities exceed assets', detail='Accumulated losses have reduced equity below zero. The debt-to-equity multiple is not meaningful.', evidence=['total_assets', 'total_liabilities', 'total_equity']))
    if values['scheduled_principal'] is None:
        observations.append(dict(title='Repayment capacity needs more evidence', detail='Payments are modeled, but the contractual debt schedule is absent. Debt-service coverage cannot be established.', evidence=['principal_paid', 'scheduled_principal']))
    kpis = calculate_kpis(values)
    prior_kpis = {m['id']: m for m in calculate_kpis(previous)} if previous else {}
    for metric in kpis:
        metric['prior_value'] = prior_kpis.get(metric['id'], {}).get('value')
    return dict(dealer_id=dealer_id, dealer_name=dealer['dealer_name'], scenario=dealer['scenario'],
                source='synthetic', mon_period=period, prior_period=prior_period, as_of=date,
                currency='NGN', scope='Whole dealer business • all outlets and business lines',
                values=values, statements=statements, kpis=kpis, observations=observations,
                evidence=[
                    dict(id='monthly_records', label='Prepared monthly accounting records', as_of=date, status='Synthetic', detail='Modeled sales, costs, inventory, receivables, payables, fixed assets and equity. Includes non-MTN activity; no internal platform connection.'),
                    dict(id='payment_activity', label='Simulated payment activity', as_of=date, status='Synthetic', detail='Modeled cash movements through month end. Demonstrates a future payment feed; no APDP or bank connection is active here.'),
                    dict(id='debt_schedule', label='Debt repayment schedule', as_of=None if values['scheduled_principal'] is None else date, status='Missing in this scenario' if values['scheduled_principal'] is None else 'Synthetic', detail='Contractual principal due, separate from payments observed. Required for debt-service coverage.'),
                ], assumptions=['Monthly figures, not year-to-date. Prior month uses the same business scope.', 'Income statement expenses are shown as positive deductions; cash flow outflows are negative.', 'Interest and tax are paid in-month and classified as operating cash flows. No dividends or owner movements.', 'Tax is a fictional 30% of positive pre-tax profit assumption, not a tax assessment.', 'DSCR uses EBITDA and scheduled principal plus interest; no MTN credit thresholds are applied.'])


def list_dealers(period, search='', sort_by='dealer_name', direction='asc', limit=25, offset=0):
    items = []
    for dealer in DEALERS:
        values = _records().get((dealer['dealer_id'], period))
        if values is None or search.casefold() not in f"{dealer['dealer_id']} {dealer['dealer_name']} {dealer['scenario']}".casefold():
            continue
        items.append({key: dealer[key] for key in ('dealer_id', 'dealer_name', 'scenario')} | {key: values[key] for key in ('revenue', 'net_profit', 'operating_cash_flow')})
    items.sort(key=lambda row: (row[sort_by], row['dealer_id']), reverse=direction == 'desc')
    total = len(items)
    return dict(source='synthetic', mon_period=period, available_periods=PERIODS,
                items=items[offset:offset + limit], pagination=dict(total=total, limit=limit, offset=offset, has_more=offset + limit < total))
