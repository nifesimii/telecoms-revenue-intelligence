"""Read-only investigations over recorded inputs; never calculate entitlement."""
from __future__ import annotations

from collections import Counter
from hashlib import sha256
import json
import re

import pandas as pd

from backend import config
from backend.db.connection import execute_query
from backend.db import queries

CAUSES = ('USP_SNAPSHOT_MISS', 'OUTSIDE_6_MONTH_WINDOW', 'NULL_PROFILE_CLASS',
          'HYNEX_DENOMINATION_SPLIT')
FINGERPRINT_FIELDS = ('imei', 'product_code', 'product_name', 'invoice_date',
                      'first_activation_date', 'unit_selling_price', 'commission_rate')


def fingerprint(row: dict) -> str:
    values = []
    for key in FINGERPRINT_FIELDS:
        value = row.get(key)
        if value is None or pd.isna(value):
            value = ''
        elif key in {'unit_selling_price', 'commission_rate'}:
            value = format(float(value), '.4f')
        elif key in {'imei', 'product_code'}:
            value = str(value).removesuffix('.0')
        values.append(str(value))
    return sha256(json.dumps(values, ensure_ascii=False).encode()).hexdigest()


def gap_days(row: dict) -> int | None:
    dates = [pd.to_datetime(str(row.get(key, '')), format='mixed', errors='coerce')
             for key in ('invoice_date', 'first_activation_date')]
    return None if any(pd.isna(d) for d in dates) else (dates[1].date() - dates[0].date()).days


def _support(period, dealer_id, source='calculation'):
    try:
        return queries.investigation_support(period, dealer_id, source).to_dict('records')
    except (OSError, ValueError, KeyError, NotImplementedError):
        return []


def _recorded_cause(row, evidence, period, gap):
    if (not evidence or evidence.get('source_fingerprint') != fingerprint(row)
            or evidence.get('usp_snapshot_period') != period
            or evidence.get('rule_version') != 'activation-180d-v1'
            or not evidence.get('evidence_ref') or gap is None or gap < 0):
        return None
    reason = evidence.get('recorded_reason')
    supported = {
        'USP_SNAPSHOT_MISS': evidence.get('usp_lookup') == 'NO_MATCH',
        'OUTSIDE_6_MONTH_WINDOW': gap > 180,
        'NULL_PROFILE_CLASS': evidence.get('profile_lookup') == 'NO_MATCH' and not evidence.get('profile_at_calculation'),
        'HYNEX_DENOMINATION_SPLIT': (
            {evidence.get('calculation_denomination'), evidence.get('canonical_denomination')} == {'Hynex', 'Hynex_1'}
            and bool(evidence.get('product_mapping_ref'))),
    }
    return reason if supported.get(reason) else None


def investigate(dealer_id: str, periods: list[str], family: str = 'zero_commission',
                offset: int = 0, limit: int = 20) -> dict:
    if (isinstance(limit, bool) or not isinstance(limit, int) or not 1 <= limit <= 100
            or isinstance(offset, bool) or not isinstance(offset, int) or offset < 0):
        raise ValueError('Investigation pages require limit 1–100 and nonnegative offset')
    if (not dealer_id or not periods or len(periods) != (2 if family == 'commission_variance' else 1)
            or len(set(periods)) != len(periods)
            or any(not re.fullmatch(r'\d{4}(0[1-9]|1[0-2])', p) for p in periods)
            or family not in {'zero_commission', 'commission_variance', 'payment'}):
        raise ValueError('Invalid investigation scope')
    result = dict(dealer_id=dealer_id, periods=sorted(periods), family=family, status='unavailable',
                  total_records=0, causes=[], unresolved_count=0, records=[], tools=[],
                  eligibility=dict(inside=0, outside=0, invalid=0),
                  pagination=dict(offset=offset, limit=limit, total=0, has_more=False))
    if family == 'payment':
        return _payment(result)
    if not config.USE_SAMPLE_DATA:
        result['note'] = 'Investigation source adapter is unavailable; no sample evidence was used.'
        return result
    if family == 'commission_variance':
        return _variance(result)
    if not queries.has_source_period('fbb_comm_dev_act', periods[0]):
        result['note'] = 'No activation records cover this month.'
        return result
    summary = execute_query('get_dealer_summary', {'mon_period': periods[0], 'distributor_code': dealer_id})
    if summary.empty:
        result['note'] = 'No activation records for this account and month.'
        return result
    result['dealer_name'] = str(summary.iloc[0]['dealer_name'])
    frame = execute_query('get_zero_commission_records',
                          {'mon_period': periods[0], 'distributor_code': dealer_id})
    support = _support(periods[0], dealer_id)
    keys = Counter(r['imei'] for r in support)
    by_imei = {r['imei']: r for r in support if keys[r['imei']] == 1}
    result['tools'] = ['get_dealer_summary', 'get_zero_commission_records', 'investigation_support']
    result['policy_version'] = 'activation-180d-v1'
    rows, counts = [], Counter()
    for record in frame.to_dict('records'):
        gap = gap_days(record)
        valid = gap is not None and gap >= 0
        bucket = 'invalid' if not valid else 'outside' if gap > 180 else 'inside'
        result['eligibility'][bucket] += 1
        evidence = by_imei.get(str(record['imei']))
        cause = _recorded_cause(record, evidence, periods[0], gap)
        if not cause and bucket == 'outside':
            cause = 'OUTSIDE_6_MONTH_WINDOW'
        if cause:
            counts[cause] += 1
        rows.append(dict(imei=str(record['imei']), product_code=str(record['product_code']),
                         invoice_date=str(record['invoice_date']),
                         activation_date=str(record['first_activation_date']), gap_days=gap,
                         cause=cause, evidence_ref=(evidence['evidence_ref'] if evidence and _recorded_cause(record, evidence, periods[0], gap)
                                                     else 'activation dates' if cause else None)))
    rows.sort(key=lambda r: r['imei'])
    result.update(status='available', total_records=len(rows),
                  causes=[dict(cause=c, count=counts[c]) for c in CAUSES if counts[c]],
                  unresolved_count=len(rows)-sum(counts.values()), records=rows[offset:offset+limit])
    result['pagination'].update(total=len(rows), has_more=offset+limit < len(rows))
    return result


def _page(result, rows):
    page = result['pagination']
    result['total_records'] = len(rows)
    result['records'] = rows[page['offset']:page['offset'] + page['limit']]
    page.update(total=len(rows), has_more=page['offset'] + page['limit'] < len(rows))


def _variance(result):
    from backend.db.variance_evidence import commission_variance_evidence
    earlier, later = result['periods']
    evidence = commission_variance_evidence(earlier, later, result['dealer_id'])
    if evidence['status'] != 'available' or not evidence['variance']['found']:
        result['note'] = evidence.get('note') or 'No recorded activation activity in these months.'
        return result
    variance = evidence['variance']
    # Arithmetic contributions are not claims about counterfactual entitlement.
    result.update(status='available', variance=variance,
                  tools=['get_month_on_month_variance'], zero_investigations=[])
    for period in (earlier, later):
        zeros = investigate(result['dealer_id'], [period], limit=1)
        zeros['records'] = []  # Counts only; drill-down requests read a dedicated page.
        result['zero_investigations'].append(zeros)
        if zeros.get('dealer_name'):
            result['dealer_name'] = zeros['dealer_name']
        result['tools'].extend(zeros['tools'])
    result['tools'] = list(dict.fromkeys(result['tools']))
    _page(result, sorted(variance['products'], key=lambda p: (-abs(p['change_ngn']), p['product'])))
    return result


def _payment(result):
    from backend.audit.payment_data import payment_lookup
    from decimal import Decimal
    period, dealer = result['periods'][0], result['dealer_id']
    try:
        frame = payment_lookup(period, config.PAYMENT_SOURCE)
        rows = frame[frame['dealer_id'].astype(str) == dealer]
        if len(rows) != 1:
            result['note'] = 'No unique payment statement for this account and month.'
            return result
        row = rows.iloc[0].to_dict()
        apdp = config.PAYMENT_SOURCE == 'apdp'
        keys = ('expected_commission_ngn', 'total_settled_ngn') if apdp else ('commission_owed', 'amount_paid')
        owed, paid = [Decimal(str(row[key])).quantize(Decimal('.01')) for key in keys]
        if not owed.is_finite() or not paid.is_finite():
            raise ValueError('Incomplete payment amounts')
        balance = owed - paid
        statement_available = not apdp or (int(row.get('statement_count') or 0) > 0
                                            and row.get('reconciliation_status') != 'SALES_WITHOUT_STATEMENT')
        settlement_available = not apdp or (int(row.get('settlement_count') or 0) > 0
                                             and row.get('reconciliation_status') != 'STATEMENT_WITHOUT_PAYMENT')
        coverage = statement_available and settlement_available
        process = (_settlement_process(period, dealer, owed, paid, row['payment_status'])
                   if config.USE_SAMPLE_DATA and not apdp else None)
        result.update(status='available', dealer_name=str(row.get('dealer_name', dealer)),
                      tools=['payment_lookup'] + (['investigation_support'] if config.USE_SAMPLE_DATA and not apdp else []),
                      payment=dict(owed=float(owed) if statement_available else None,
                                   paid=float(paid) if settlement_available else None,
                                   balance=float(balance) if coverage else None,
                                   coverage_complete=coverage, process=process,
                                   status=str(row.get('reconciliation_status') if apdp else row.get('payment_status'))))
        _page(result, [dict(statement_period=period, owed=result['payment']['owed'], paid=result['payment']['paid'],
                            balance=result['payment']['balance'], evidence_ref=process['evidence_ref'] if process else None)])
    except (OSError, ValueError, KeyError, TypeError, ArithmeticError, NotImplementedError):
        result['note'] = 'The configured payment source could not supply complete statement evidence.'
    return result


def _settlement_process(period, dealer, owed, paid, status):
    from decimal import Decimal
    supporting = _support(period, dealer, 'settlement')
    if len(supporting) != 1:
        return None
    candidate = supporting[0]
    balance = owed - paid
    allowed = ('SETTLED' if balance == 0 else 'EXCESS_REVIEW' if balance < 0 else
               'DISPUTE_REVIEW' if status == 'DISPUTED' else 'AWAITING_RELEASE')
    try:
        if (Decimal(candidate['recorded_owed']) == owed and Decimal(candidate['recorded_paid']) == paid
                and Decimal(candidate['remaining_amount']) == balance
                and candidate['recorded_status'] == status and candidate['process_state'] == allowed
                and candidate['evidence_ref'] and candidate['batch_reference'] and candidate['owner']):
            return {**candidate, 'remaining_amount': float(balance)}
    except (KeyError, ValueError, ArithmeticError):
        pass
    return None
