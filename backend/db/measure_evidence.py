"""Bounded projections of recorded measures; no calculation of entitlements."""
import re
from decimal import Decimal
from math import isfinite

import pandas as pd
from backend.db.connection import execute_query
from backend.db import subscription_evidence, financial_health, queries

# IDs are application vocabulary; columns retain the existing query contract.
_MEASURES = {
    'inventory_gap': ('Inventory gap for compared products', 'count', 'fbb_comm_dev_act', 'get_inventory_comparison', 'inventory_gap'),
    'inventory_recorded_purchases': ('Recorded purchases for compared products only', 'count', 'fbb_comm_dev_act', 'get_inventory_comparison', 'total_units_purchased'),
    'activation_qualified_count': ('Qualified activations', 'count', 'fbb_comm_dev_act', 'get_activation_summary', 'qualified_activation_count'),
    'activation_unqualified_count': ('Unqualified activations', 'count', 'fbb_comm_dev_act', 'get_activation_summary', 'non_qualified_activation_count'),
    'payment_status': ('Activation payment status', 'text', 'payment_simulation', 'get_payment_summary', 'payment_status'),
    'financial_revenue': ('Whole-business revenue', 'ngn', 'financial_health', 'get_financial_health_summary', 'revenue'),
    'financial_net_profit': ('Whole-business net profit', 'ngn', 'financial_health', 'get_financial_health_summary', 'net_profit'),
    'financial_statements': ('Whole-business financial statements', 'ngn', 'financial_health', 'get_financial_health_report', 'statements'),
    'financial_kpis': ('Whole-business financial ratios and cash flow', 'text', 'financial_health', 'get_financial_health_report', 'kpis'),
    'activation_count': ('Activations', 'count', 'fbb_comm_dev_act', 'get_dealer_summary', 'total_activations'),
    'activation_commission': ('Activation commission', 'ngn', 'fbb_comm_dev_act', 'get_dealer_summary', 'total_commission_ngn'),
    'zero_commission_count': ('Zero-commission activations', 'count', 'fbb_comm_dev_act', 'get_dealer_summary', 'zero_commission_count'),
    'subscription_revenue': ('Subscription revenue', 'ngn', 'fbb_comm_orsc', 'get_orsc_summary', 'total_subscription_amount_ngn'),
    'subscription_commission': ('Subscription commission', 'ngn', 'fbb_comm_orsc', 'get_orsc_summary', 'subscription_commission_ngn'),
    'subscription_settled': ('Subscription settled', 'ngn', 'fbb_comm_orsc', 'get_orsc_summary', 'subscription_settled_ngn'),
    'subscription_outstanding': ('Subscription outstanding', 'ngn', 'fbb_comm_orsc', 'get_orsc_summary', 'subscription_outstanding_ngn'),
    'payment_paid': ('Activation payments paid', 'ngn', 'payment_simulation', 'get_payment_summary', 'amount_paid'),
    'payment_owed': ('Activation commission owed', 'ngn', 'payment_simulation', 'get_payment_summary', 'commission_owed'),
    'payment_outstanding': ('Activation payments outstanding', 'ngn', 'payment_simulation', 'get_payment_summary', 'amount_unpaid'),
}
# Neutral source names: the workspace header, not each answer, marks demo data.
_SOURCE_NAMES = {
    'fbb_comm_dev_act': 'Activation records',
    'fbb_comm_orsc': 'Subscription records',
    'payment_simulation': 'Payment records',
    'financial_health': 'Whole-business financial statements · includes non-MTN activity',
}
_UNAVAILABLE = {
    'retail_sales_units': ('Retail sales units', 'count', 'Retail sales are unavailable through Atlas. Dated customer sales transactions with products, quantities and returns are missing.'),
    'retail_sales_value': ('Retail sales value', 'ngn', 'Retail sales value is unavailable through Atlas. Dated customer transactions with actual selling amounts and returns are missing.'),
    'dealer_purchases': ('Dealer purchases', 'count', 'Complete dealer purchase totals are unavailable. Inventory comparisons omit products without activations and use cumulative purchase snapshots; dated complete purchase records are required.'),
}


def _empty(period: str, source: str, note: str, tool: str | None = None) -> dict:
    return dict(period=period, status='unavailable', source=source, rows=[], total=None,
                note=note, tool=tool, total_rows=0, truncated=False)


def _period_evidence(measure: str, period: str, dealer_id: str | None,
                     breakdown: str, cache: dict, requested_filter: str, selectors: dict) -> dict:
    if measure in _UNAVAILABLE:
        return _empty(period, 'No supported evidence', _UNAVAILABLE[measure][2])
    _, unit, source, tool, field = _MEASURES[measure]
    statements = measure in {'subscription_commission', 'subscription_settled', 'subscription_outstanding'}
    inventory = tool == 'get_inventory_comparison'
    label = ('Inventory comparison records' if inventory
             else _SOURCE_NAMES[source] + (' · subscription statements' if statements else ''))
    supported_filters = {'all'}
    if tool == 'get_payment_summary':
        supported_filters.update({'disputed', 'unpaid'})
    if tool == 'get_dealer_summary':
        supported_filters.add('zero_commission')
    if tool == 'get_activation_summary':
        supported_filters.update({'low_qualification', 'zero_commission'})
    if requested_filter not in supported_filters:
        return _empty(period, label, 'This requested filter is not supported by this measure projection.')
    denominations = breakdown == 'product' and measure == 'activation_commission'
    if breakdown == 'product' and not inventory and not denominations:
        return _empty(period, label, 'This measure has no complete product breakdown in the available query contract.')
    if not (period in financial_health.PERIODS if source == 'financial_health' else queries.has_source_period(source, period)):
        return _empty(period, label, 'No source coverage for this requested month; missing evidence is not zero.')
    if statements and not queries.has_source_period('subscription_commission_demo', period):
        return _empty(period, label, 'Recorded subscription statements are unavailable for this month.')
    key = (tool, period, dealer_id)
    try:
        if key not in cache:
            if source == 'financial_health':
                records = []
                offset = 0
                while True:
                    page = financial_health.list_dealers(period, limit=100, offset=offset)
                    records.extend(page['items'])
                    if not page['pagination']['has_more']:
                        break
                    offset += 100
            else:
                frame = execute_query(tool, {'mon_period': period, 'distributor_code': dealer_id})
                records = frame.to_dict(orient='records')
            cache[key] = [row for row in records if dealer_id is None or str(row['dealer_id']) == dealer_id]
        records = cache[key]
        if requested_filter == 'disputed':
            records = [r for r in records if r.get('payment_status') == 'DISPUTED']
        elif requested_filter == 'unpaid':
            records = [r for r in records if r.get('amount_unpaid', 0) > 0]
        elif requested_filter == 'zero_commission':
            records = [r for r in records if r.get('zero_commission_count', r.get('non_qualified_activation_count', 0)) > 0]
        elif requested_filter == 'low_qualification':
            records = [r for r in records if r.get('qualification_rate_pct', 100) < 50]
        if not records and source == 'financial_health' and dealer_id is not None:
            return _empty(period, label, f'No financial statement on record for account {dealer_id}. '
                          'Recorded activations or commission for this account are available on request.', tool)
        if not records:
            return _empty(period, label, 'No matching dealer records in this month; absence is not a verified zero.', tool)
        evidence_key = ('subscription_statements', period)
        if statements and evidence_key not in cache:
            cache[evidence_key] = subscription_evidence.summaries(period)
        rows = []
        for record in records:
            identity = str(record['dealer_id'])
            if measure == 'financial_kpis':
                report = financial_health.get_report(identity, period)
                if not report:
                    return _empty(period, label, 'Requested financial ratios are unavailable.', tool)
                for kpi in report['kpis']:
                    if selectors['kpi_ids'] and kpi['id'] not in selectors['kpi_ids']:
                        continue
                    value = (f"{kpi['status']}: {kpi['reason']}" if kpi['status'] != 'available' or kpi['value'] is None
                             else f"NGN {kpi['value']:,.2f}" if kpi['unit'] == 'ngn'
                             else f"{kpi['value']:,.2f}%" if kpi['unit'] == 'percent'
                             else f"{kpi['value']:,.2f}×")
                    rows.append(dict(dealer_id=identity, dealer_name=str(record['dealer_name']),
                                     dimension=kpi['label'], value=value))
                continue
            if measure == 'financial_statements':
                report = financial_health.get_report(identity, period)
                if not report:
                    return _empty(period, label, 'Requested financial statements are unavailable.', tool)
                rows.extend(dict(dealer_id=identity, dealer_name=str(record['dealer_name']),
                                 dimension=f"{statement['label']}: {line['label']}", value=line['amount'])
                            for statement in report['statements']
                            if not selectors['statement_ids'] or statement['id'] in selectors['statement_ids']
                            for line in statement['rows']
                            if not selectors['line_ids'] or line['id'] in selectors['line_ids'])
                continue
            if denominations:
                values = record.get('commission_by_denomination')
                recorded_total = record.get('total_commission_ngn')
                if (not isinstance(values, dict) or recorded_total is None or not isfinite(float(recorded_total))
                        or any(value is None or not isfinite(float(value)) for value in values.values())):
                    return _empty(period, label, 'A complete denomination breakdown is unavailable.', tool)
                rows.extend(dict(dealer_id=identity, dealer_name=str(record['dealer_name']),
                                 dimension=str(dimension) or 'Unspecified denomination', value=float(value))
                            for dimension, value in values.items())
                remainder = (Decimal(str(recorded_total)) - sum((Decimal(str(v)) for v in values.values()), Decimal(0))).quantize(Decimal('0.01'))
                if remainder or not values:
                    rows.append(dict(dealer_id=identity, dealer_name=str(record['dealer_name']),
                                     dimension='Unattributed denomination', value=float(remainder)))
                continue
            value = (cache[evidence_key].get(identity, {}).get(field) if statements else record.get(field))
            if value is None or (unit != 'text' and not isfinite(float(value))):
                return _empty(period, label, 'Requested amount lacks complete recorded evidence for the selected accounts.', tool)
            rows.append(dict(dealer_id=identity, dealer_name=str(record['dealer_name']),
                             dimension=(f"{record['product_name']} ({record['product_code']})" if inventory else None),
                             value=(str(value) if unit == 'text' else int(value) if unit == 'count' else float(value))))
        if not rows:
            return _empty(period, label, 'No recorded rows match the requested selectors.', tool)
        if inventory:
            # Name which purchase dataset the comparison used, without demo wording.
            label += (' · purchase scenarios' if any(r.get('scenario_id') for r in records) else ' · IFS invoices')
        if measure != 'financial_statements':
            rows.sort(key=lambda row: (row['value'] if unit == 'text' else -row['value'], row['dealer_id'], row['dimension'] or ''))
        total = None if unit == 'text' or measure == 'financial_statements' else sum((Decimal(str(row['value'])) for row in rows), Decimal(0))
        if denominations:
            total = sum((Decimal(str(record['total_commission_ngn'])) for record in records), Decimal(0))
        return dict(period=period, status='available', source=label, rows=rows[:100],
                    total=None if total is None else int(total) if unit == 'count' else float(total), tool=tool,
                    total_rows=len(rows), truncated=len(rows) > 100,
                    note='Source records cover this month; no completeness claim beyond the supplied dataset.'
                         + (' Purchases are cumulative shared snapshots, not monthly purchases; do not sum across months. '
                            'Only products with activations are compared.' if inventory else '')
                         + (' Showing the first 100 evidence rows; any total includes all matching records.' if len(rows) > 100 else ''))
    except (ValueError, KeyError, OSError, NotImplementedError):
        return _empty(period, label, 'The requested evidence could not be read or validated.', tool)


def collect_measure_evidence(request: dict) -> dict:
    """Read only requested fields and retain source-specific missing-data states."""
    periods, measures = request.get('periods'), request.get('measures')
    if (not isinstance(periods, list) or len(periods) > 24
            or any(not isinstance(p, str) or not re.fullmatch(r'[0-9]{4}(0[1-9]|1[0-2])', p) for p in periods)
            or len(set(periods)) != len(periods)):
        raise ValueError('periods must contain 1–24 unique YYYYMM values')
    if (not isinstance(measures, list) or not measures or len(measures) > len(_MEASURES) + len(_UNAVAILABLE)
            or any(not isinstance(m, str) or m not in _MEASURES and m not in _UNAVAILABLE for m in measures)):
        raise ValueError('Unsupported requested measure')
    if not periods and any(measure not in _UNAVAILABLE for measure in measures):
        raise ValueError('Available measures require requested periods')
    allowed_selectors = {
        'kpi_ids': {row['id'] for row in financial_health.calculate_kpis({})},
        'statement_ids': {statement[0] for statement in financial_health.STATEMENTS},
        'line_ids': {field for _, _, groups in financial_health.STATEMENTS for _, fields in groups for field, _ in fields},
    }
    selectors = {}
    for name, allowed in allowed_selectors.items():
        values = request.get(name, [])
        target = 'financial_kpis' if name == 'kpi_ids' else 'financial_statements'
        if (not isinstance(values, list) or len(values) > len(allowed)
                or any(not isinstance(value, str) or value not in allowed for value in values)
                or values and target not in measures):
            raise ValueError(f'Invalid {name} selector for requested measures')
        selectors[name] = values
    dealer_id = request.get('dealer_id')
    if dealer_id is not None and (not isinstance(dealer_id, str) or not dealer_id.strip()):
        raise ValueError('dealer_id must be a nonempty string or None')
    breakdown = request.get('breakdown', 'dealer')
    if breakdown not in {'dealer', 'month', 'product'} or request.get('operation', 'total') not in {'total', 'breakdown', 'compare', 'explain'}:
        raise ValueError('Unsupported evidence operation or breakdown')
    cache: dict = {}
    output = []
    for measure in dict.fromkeys(measures):
        label, unit = (_MEASURES.get(measure) or _UNAVAILABLE[measure])[:2]
        aggregation = ('snapshot' if measure in {'inventory_gap', 'inventory_recorded_purchases'}
                       else 'none' if measure in {'financial_statements', 'financial_kpis', 'payment_status'} else 'sum')
        output.append(dict(measure=measure, label=label, unit=unit, aggregation=aggregation,
                           note=_UNAVAILABLE[measure][2] if measure in _UNAVAILABLE else '',
                           periods=[_period_evidence(measure, period, dealer_id, breakdown, cache, request.get('filter', 'all'), selectors) for period in periods]))
    explanations = []
    if request.get('operation') == 'explain' and dealer_id:
        explainable = {'activation_commission', 'zero_commission_count', 'activation_unqualified_count'}
        available_periods = {period['period'] for measure in output if measure['measure'] in explainable
                             for period in measure['periods'] if period['status'] == 'available'}
        explanations = [_zero_record_observation(period, dealer_id) for period in periods if period in available_periods]
    return dict(requested_periods=periods.copy(), dealer_id=dealer_id, measures=output, explanations=explanations)


def _zero_record_observation(period: str, dealer_id: str) -> dict:
    observation = dict(period=period, dealer_id=dealer_id, records_checked=0, records_with_dates=0,
                       total_records=0, bounded=False, source='Zero-commission activation records',
                       tool='get_zero_commission_records', status='unavailable', note='')
    try:
        frame = execute_query('get_zero_commission_records', {'mon_period': period, 'distributor_code': dealer_id})
        checked = frame.head(100)
        dates = []
        for column in ('invoice_date', 'first_activation_date'):
            dates.append(pd.to_datetime(checked[column].astype(str), errors='coerce', format='mixed').notna())
        observation.update(records_checked=len(checked), records_with_dates=int((dates[0] & dates[1]).sum()),
                           total_records=len(frame), bounded=len(frame) > 100, status='available',
                           note='Historical USP, account-profile and denomination evidence is required to verify a cause. '
                           'The KB describes both a reporting-month lookback and an invoice-to-activation 180-day window; '
                           'an authoritative eligibility rule is needed before attributing a cause. Date availability alone verifies no cause.')
    except (ValueError, KeyError, OSError, NotImplementedError):
        observation['note'] = 'Scoped zero-commission evidence could not be read; causes remain unverified.'
    return observation


def collect_dealer_codes(request: dict) -> dict:
    """Bounded name associations (exact unless match='contains'), retaining coverage metadata."""
    periods = request.get('periods', [])
    if (not isinstance(periods, list) or len(periods) > 24
            or any(not isinstance(p, str) or not re.fullmatch(r'[0-9]{4}(0[1-9]|1[0-2])', p) for p in periods)
            or len(set(periods)) != len(periods)):
        raise ValueError('periods must contain up to 24 unique YYYYMM values')
    indices = sorted(int(period[:4]) * 12 + int(period[4:]) for period in periods)
    if indices and indices[-1] - indices[0] + 1 != len(indices):
        raise ValueError('Dealer lookup periods must be contiguous; gapped periods cannot be broadened')
    match = request.get('match', 'exact')
    if match not in ('exact', 'contains'):
        raise ValueError("match must be 'exact' or 'contains'")
    params = {'dealer_name': request.get('dealer_name'), 'match': match, 'page_size': 100, 'page': 1}
    if periods:
        params.update(start_period=min(periods), end_period=max(periods))
    frame = execute_query('get_dealer_codes', params)
    return {'tool': 'get_dealer_codes', 'parameters': params, 'requested_periods': periods.copy(),
            'rows': frame.to_dict(orient='records'), **frame.attrs.get('lookup_metadata', {})}
