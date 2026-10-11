"""Application-owned arithmetic shared by answer facts and presentation.

Preparation copies retrieved evidence; it never reads sources or treats missing
values as recorded zero. Callers still validate source shapes and exact scope.
"""
from __future__ import annotations

from copy import deepcopy
from decimal import Decimal
from typing import Any


MONEY_FIELDS = {'owed', 'paid', 'balance', 'outstanding', 'commission_owed',
                'amount_paid', 'amount_outstanding', 'amount_unpaid', 'unit_selling_price'}


def _decimal(value: object) -> Decimal:
    return Decimal(str(value))


def _money_fields(value: object) -> None:
    if isinstance(value, dict):
        for key, child in value.items():
            if (key.endswith('_ngn') or key in MONEY_FIELDS) and isinstance(child, (int, float, Decimal)) and not isinstance(child, bool):
                value[key] = _decimal(child)
            else:
                _money_fields(child)
    elif isinstance(value, list):
        for child in value:
            _money_fields(child)


def _variance(variance: dict) -> None:
    for line in [variance.get('totals', {}), *variance.get('products', [])]:
        if 'earlier_ngn' not in line or 'change_ngn' not in line:
            continue
        base = _decimal(line['earlier_ngn']).quantize(Decimal('0.01'))
        change = _decimal(line['change_ngn']).quantize(Decimal('0.01'))
        line['prepared'] = {'change_pct': abs(change / base * 100).quantize(Decimal('0.1')) if base else None,
                            'change_kind': 'percentage' if base else 'new' if change else 'unchanged'}
    variance['prepared'] = {'movers': sorted(
        (p for p in variance.get('products', []) if _decimal(p['change_ngn']).quantize(Decimal('0.01'))),
        key=lambda p: (-abs(_decimal(p['change_ngn']).quantize(Decimal('0.01'))), p['product']))}


def _investigation(result: dict) -> None:
    if result.get('status') != 'available':
        return
    rows = result.get('records')
    page = result.get('pagination')
    derived: dict[str, Any] = {}
    if isinstance(rows, list) and isinstance(page, dict) and 'offset' in page:
        derived.update(page_count=len(rows), page_start=page['offset'] + 1 if rows else 0,
                       page_end=page['offset'] + len(rows))
    if result.get('family') == 'zero_commission':
        causes = result.get('causes')
        if isinstance(causes, list) and all('count' in cause for cause in causes):
            derived['explained_count'] = sum(c['count'] for c in causes)
    elif result.get('family') == 'commission_variance':
        variance = result.get('variance')
        if isinstance(variance, dict):
            _variance(variance)
        totals = variance.get('totals', {}) if isinstance(variance, dict) else {}
        if isinstance(rows, list) and 'change_ngn' in totals and all('change_ngn' in p for p in rows):
            shown = sum((_decimal(p['change_ngn']) for p in rows), Decimal(0))
            derived['shown_change_ngn'] = shown
            derived['outside_page_change_ngn'] = _decimal(totals['change_ngn']) - shown
        zeros = result.get('zero_investigations', [])
        for zero in zeros:
            _investigation(zero)
        if (len(zeros) == 2 and all(z.get('status') == 'available' and 'total_records' in z for z in zeros)
                and all(key in totals for key in ('earlier_activations', 'later_activations'))):
            derived['earlier_nonzero_activations'] = totals['earlier_activations'] - zeros[0]['total_records']
            derived['later_nonzero_activations'] = totals['later_activations'] - zeros[1]['total_records']
    result['prepared'] = derived


def _population_and_pages(value: object) -> None:
    if isinstance(value, list):
        for child in value:
            _population_and_pages(child)
        return
    if not isinstance(value, dict):
        return
    for child in list(value.values()):
        _population_and_pages(child)
    products = value.get('products')
    if isinstance(products, list) and products and all(
            isinstance(p, dict) and isinstance(p.get('change_ngn'), (int, float, Decimal))
            and isinstance(p.get('product'), str) for p in products):
        value['all_product_commissions_increased'] = all(p['change_ngn'] > 0 for p in products)
        if all(isinstance(p.get(key), (int, float)) for p in products
               for key in ('earlier_activations', 'later_activations')):
            value['all_product_activation_counts_increased'] = all(
                p['later_activations'] > p['earlier_activations'] for p in products)
        largest = max(products, key=lambda p: p['change_ngn'])
        if largest['change_ngn'] > 0:
            value['largest_positive_product_contribution'] = {
                'product': largest['product'], 'change_ngn': largest['change_ngn']}
    if (value.get('status') == 'available' and isinstance(value.get('records'), list)
            and isinstance(value.get('pagination'), dict)):
        page = value['pagination']
        offset, total, shown = page['offset'], page['total'], len(value['records'])
        if (any(isinstance(n, bool) or not isinstance(n, int) or n < 0 for n in (offset, total, shown))
                or shown and offset + shown > total):
            raise ValueError('Invalid record page bounds')
        value['record_page'] = {'first': offset + 1 if shown else None,
                                'last': offset + shown if shown else None,
                                'shown': shown, 'total': total, 'has_more': bool(page.get('has_more'))}


def prepare_evidence(evidence: dict, request: dict | None = None) -> dict:
    """Return a detached evidence tree with deterministic derived values."""
    result = deepcopy(evidence)
    if isinstance(result.get('measure_evidence'), dict):
        result['measure_evidence'] = prepare_evidence(result['measure_evidence'], request)
    _money_fields(result)
    _population_and_pages(result)
    if 'investigation' in result:
        _investigation(result['investigation'])
    for observation in result.get('explanations', []):
        if 'investigation' in observation:
            _investigation(observation['investigation'])
    for measure in result.get('measures', []):
        periods = measure['periods']
        for period in periods:
            if measure.get('unit') == 'ngn':
                if period.get('total') is not None:
                    period['total'] = _decimal(period['total'])
                for row in period['rows']:
                    if row.get('value') is not None:
                        row['value'] = _decimal(row['value'])
            if period.get('variance'):
                _variance(period['variance'])
            verification = period.get('verification')
            if verification and verification.get('found', True):
                modules = verification.get('modules', [])
                focus = (request or {}).get('verification_focus')
                selected = [m for m in modules if not focus or m['module'] == focus]
                verification['prepared'] = {'status_counts': {status: sum(m['status'] == status for m in selected)
                                                             for status in ('verified', 'no_subject', 'unavailable')}}
                for module in modules:
                    module['prepared'] = {'withheld_count': sum(t.get('withheld', 0) for t in module.get('trails', []))}
        row_only = measure.get('unit') == 'text' or measure.get('aggregation') == 'none'
        available = [p for p in periods if p['status'] == 'available' and (
            any(r.get('value') is not None for r in p['rows']) if row_only else p.get('total') is not None)]
        covered = [p['period'] for p in available]
        requested = (request or {}).get('periods', result.get('requested_periods', [p['period'] for p in periods]))
        derived: dict[str, Any] = {'covered_periods': covered, 'missing_periods': [p for p in requested if p not in covered],
                   'total': sum((_decimal(p['total']) for p in available), Decimal(0)) if available and not row_only else None,
                   'ranked_rows': [], 'ranked_total': None, 'comparison': None}
        if len(requested) == 2 and len(available) == 2 and not row_only:
            earlier, later = sorted(available, key=lambda p: p['period'])
            derived['comparison'] = {'earlier': earlier['period'], 'later': later['period'],
                                     'delta': _decimal(later['total']) - _decimal(earlier['total'])}
        if (request and measure['measure'] == 'activation_commission' and request.get('limit') is not None
                and request.get('operation') == 'breakdown' and request.get('breakdown') == 'dealer' and available):
            rows = sorted(available[0]['rows'], key=lambda r: (-_decimal(r['value']), str(r['dealer_id'])))[:request['limit']]
            derived['ranked_rows'] = rows
            derived['ranked_total'] = sum((_decimal(r['value']) for r in rows), Decimal(0))
        measure['prepared'] = derived
    return result
