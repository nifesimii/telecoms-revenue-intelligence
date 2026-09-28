"""Bounded presentation of recorded subscription evidence, never policy calculation.

Only sums, filters and sorting happen at runtime. Activation settlements are
intentionally absent: the subscription fixtures supply their own payment evidence.
"""
from collections import Counter
from datetime import datetime
from decimal import Decimal

from backend import config
from backend.api.subscription_schemas import DealerSort, DeviceSort, PaymentFilter, ReasonFilter
from backend.db import queries
from backend.db.connection import execute_query
from backend.models.subscription import POLICY_LABEL
from typing import get_args

AMOUNTS = ('recorded_subscription_revenue_ngn', 'eligible_revenue_ngn', 'simulated_commission_ngn',
           'dealer_expectation_ngn', 'variance_ngn', 'amount_paid_ngn', 'outstanding_ngn')


def validate_period(period):
    if len(period) != 6 or not period.isdigit():
        raise ValueError('Expected reporting month YYYYMM')
    datetime.strptime(period, '%Y%m')


def selection(period):
    validate_period(period)
    if config.USE_SAMPLE_DATA:
        payload = queries.get_subscription_demo_records(period)
        records = payload['records'] if payload else []
        if payload and (payload.get('policy_label') != POLICY_LABEL or
                        any(row.get('policy_label') != POLICY_LABEL for row in records)):
            raise ValueError('Subscription fixture policy provenance does not match the approved demo')
        metadata = {'mon_period': period, 'source': 'Synthetic subscription commission fixtures',
                    'synthetic': True, 'policy_label': payload['policy_label'] if payload else POLICY_LABEL,
                    'evidence_as_of': payload['evidence_as_of'] if payload else None,
                    'commission_available': bool(records), 'availability': 'demo' if records else 'no_source_records',
                    'eligibility_boundary': payload['eligibility_boundary'] if payload else None}
        return metadata, records
    return {'mon_period': period, 'source': 'Presto · development · recorded subscription revenue only',
            'synthetic': False, 'policy_label': None, 'evidence_as_of': None,
            'commission_available': False, 'availability': 'revenue_only',
            'eligibility_boundary': None}, None


def sum_known(rows, field, strict=True):
    values = [r.get(field) for r in rows]
    if not values or (strict and any(v is None for v in values)):
        return None
    known = [Decimal(str(v)) for v in values if v is not None]
    return float(sum(known)) if known else None


def accounts(period):
    metadata, records = selection(period)
    if records is None:
        frame = execute_query('get_orsc_summary', {'mon_period': period})
        rows = []
        for r in frame.astype(object).where(frame.notna(), None).to_dict(orient='records'):
            rows.append({**dict.fromkeys(AMOUNTS), 'dealer_id': str(r['dealer_id']),
                         'dealer_name': r['dealer_name'], 'account_profile_class': r['account_profile_class'],
                         'device_count': int(r['device_count']), 'reason_counts': {},
                         'recorded_subscription_revenue_ngn': r['total_subscription_amount_ngn'],
                         'payment_status': 'unknown', 'unknown_commission_count': int(r['device_count'])})
        if not rows:
            metadata['availability'] = 'no_source_records'
        return metadata, rows, []
    groups = {}
    for record in records:
        groups.setdefault(record['dealer_id'], []).append(record)
    rows = []
    for dealer, devices in groups.items():
        first = devices[0]
        statuses = {r['payment_status'] for r in devices if r['payment_status'] != 'not_applicable'}
        payment_status = (next(iter(statuses)) if len(statuses) == 1 else 'mixed' if statuses else 'not_applicable')
        rows.append({'dealer_id': dealer, 'dealer_name': first['dealer_name'],
                     'account_profile_class': first['account_profile_class'], 'device_count': len(devices),
                     **{key: sum_known(devices, key) for key in AMOUNTS},
                     'payment_status': payment_status, 'reason_counts': dict(Counter(r['reason'] for r in devices)),
                     'unknown_commission_count': sum(r['simulated_commission_ngn'] is None for r in devices)})
    return metadata, rows, records


def amount_totals(rows):
    return {**{key: sum_known(rows, key) for key in AMOUNTS},
            'known_simulated_commission_ngn': sum_known(rows, 'simulated_commission_ngn', strict=False),
            'known_recorded_subscription_revenue_ngn': sum_known(rows, 'recorded_subscription_revenue_ngn', strict=False)}


def totals(rows):
    reasons = Counter()
    for row in rows:
        reasons.update(row['reason_counts'])
    return {**amount_totals(rows), 'account_count': len(rows),
            'device_count': sum(r['device_count'] for r in rows),
            'unknown_commission_count': sum(r['unknown_commission_count'] for r in rows),
            'payment_status_counts': dict(Counter(r['payment_status'] for r in rows)), 'reason_counts': dict(reasons)}


def device_totals(rows):
    return {**amount_totals(rows), 'device_count': len(rows),
            'unknown_commission_count': sum(r['simulated_commission_ngn'] is None for r in rows),
            'payment_status_counts': dict(Counter(r['payment_status'] for r in rows)),
            'reason_counts': dict(Counter(r['reason'] for r in rows))}


def sorted_rows(rows, sort_by, direction, identity):
    if direction not in ('asc', 'desc'):
        raise ValueError('Unknown sort direction')
    # Stable identity tie-break; unknown values remain last in both directions.
    ordered = sorted(rows, key=lambda r: r[identity])
    known = [r for r in ordered if r.get(sort_by) is not None]
    missing = [r for r in ordered if r.get(sort_by) is None]
    return sorted(known, key=lambda r: r[sort_by], reverse=direction == 'desc') + missing


def collection(period, search='', payment_status='all', sort_by='simulated_commission_ngn', direction='desc'):
    if sort_by not in get_args(DealerSort) or payment_status not in get_args(PaymentFilter):
        raise ValueError('Unknown subscription filter or sort')
    metadata, all_rows, _ = accounts(period)
    rows = [r for r in all_rows if search.casefold() in f"{r['dealer_id']} {r['dealer_name']}".casefold()
            and (payment_status == 'all' or r['payment_status'] == payment_status)]
    rows = sorted_rows(rows, sort_by, direction, 'dealer_id')
    return {**metadata, 'summary': totals(all_rows), 'filtered_summary': totals(rows), 'items': rows, 'total': len(rows)}


def page(period, limit=25, offset=0, **filters):
    validate_page(limit, offset)
    data = collection(period, **filters)
    return {**data, 'items': data['items'][offset:offset + limit], 'limit': limit, 'offset': offset}


def detail(period, dealer_id):
    metadata, rows, _ = accounts(period)
    account = next((r for r in rows if r['dealer_id'] == dealer_id), None)
    return {**metadata, 'account': account} if account else None


def validate_page(limit, offset):
    if not isinstance(limit, int) or not isinstance(offset, int) or not 1 <= limit <= 100 or offset < 0:
        raise ValueError('limit must be 1–100 and offset nonnegative')


def devices(period, dealer_id, limit=25, offset=0, reason='all', search='', sort_by='imei', direction='asc'):
    validate_page(limit, offset)
    if reason not in get_args(ReasonFilter) or sort_by not in get_args(DeviceSort):
        raise ValueError('Unknown device filter or sort')
    metadata, records = selection(period)
    available = records is not None and bool(records)
    rows = [r for r in records or [] if r['dealer_id'] == dealer_id
            and (reason == 'all' or r['reason'] == reason)
            and search.casefold() in f"{r['imei']} {r['product_name']}".casefold()]
    rows = sorted_rows(rows, sort_by, direction, 'imei')
    return {**metadata, 'dealer_id': dealer_id, 'evidence_available': available,
            'filtered_summary': device_totals(rows),
            'unavailable_reason': None if available else 'Recorded device commission evidence unavailable; revenue alone does not establish commission payable.',
            'items': rows[offset:offset + limit], 'total': len(rows), 'limit': limit, 'offset': offset}
