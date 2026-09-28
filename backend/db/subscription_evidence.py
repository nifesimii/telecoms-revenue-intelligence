"""Sample-only recorded statement evidence. No rate or entitlement calculation."""
from decimal import Decimal

from backend import config
from backend.db.connection import execute_query

MONEY_FIELDS = ('subscription_commission_ngn', 'subscription_settled_ngn',
                'subscription_outstanding_ngn')


def unavailable() -> dict:
    return {**dict.fromkeys(MONEY_FIELDS), 'subscription_commission_record_count': 0,
            'subscription_commission_complete': False}


def records(period: str, dealer_id: str | None = None) -> list[dict]:
    if not config.USE_SAMPLE_DATA:
        return []
    frame = execute_query('get_subscription_demo_records',
                          {'mon_period': period, 'distributor_code': dealer_id})
    result = []
    for record in frame.to_dict(orient='records'):
        statement = record
        evidence = {**dict.fromkeys(MONEY_FIELDS), 'statement_reference': None,
                    'settlement_reference': None}
        if statement and statement['subscription_commission_ngn']:
            commission = Decimal(statement['subscription_commission_ngn'])
            settled = Decimal(statement['subscription_settled_ngn']) if statement['subscription_settled_ngn'] else None
            if not commission.is_finite() or commission < 0 or not statement['statement_reference']:
                raise ValueError('Invalid subscription statement amount or reference')
            if settled is not None and (not settled.is_finite() or not 0 <= settled <= commission):
                raise ValueError('Invalid subscription settlement amount')
            if settled and not statement['settlement_reference']:
                raise ValueError('Missing subscription settlement reference')
            evidence = {'subscription_commission_ngn': float(commission),
                        'subscription_settled_ngn': float(settled) if settled is not None else None,
                        'subscription_outstanding_ngn': float(commission - settled) if settled is not None else None,
                        'statement_reference': statement['statement_reference'],
                        'settlement_reference': statement['settlement_reference'] or None}
        result.append({**record, 'subscription_revenue_ngn': float(record['subscription_revenue_ngn']), **evidence})
    return result


def summaries(period: str) -> dict[str, dict]:
    """Return per-dealer complete totals; uncovered source records stay unknown."""
    groups = {}
    for row in records(period):
        groups.setdefault(row['dealer_id'], []).append(row)
    result = {}
    for dealer, rows in groups.items():
        covered = [r for r in rows if r['subscription_commission_ngn'] is not None]
        complete = len(covered) == len(rows)
        result[dealer] = {
            **{field: money_total(rows, field) for field in MONEY_FIELDS},
            'subscription_commission_record_count': sum(r['source_record_count'] for r in covered),
            'subscription_commission_complete': complete,
        }
    return result


def money_total(rows: list[dict], field: str) -> float | None:
    if not rows or any(row.get(field) is None for row in rows):
        return None
    return float(sum((Decimal(str(row[field])) for row in rows), Decimal(0)).quantize(Decimal('0.01')))
