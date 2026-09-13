"""Read-only presentation of existing commission queries; no recalculation."""
from datetime import datetime, timezone

from backend import config
from backend.db.connection import execute_query


STREAMS = {
    'activation': ('get_dealer_summary', 'total_commission_ngn', 'total_activations', 'zero_commission_count'),
    'orsc': ('get_orsc_summary', 'total_subscription_amount_ngn', 'device_count', 'zero_amount_count'),
}


def provenance() -> dict:
    return {'source': 'Sample CSVs' if config.USE_SAMPLE_DATA else 'Presto · development',
            'generated_at': datetime.now(timezone.utc).isoformat()}


def account_rows(period: str, stream: str, dealer_id: str | None = None) -> list[dict]:
    query, amount, count, zero = STREAMS[stream]
    frame = execute_query(query, {'mon_period': period, 'distributor_code': dealer_id})
    return [{
        'dealer_id': str(row['dealer_id']), 'dealer_name': str(row['dealer_name']),
        'account_profile_class': str(row['account_profile_class']),
        'amount_ngn': round(float(row[amount]), 2),
        'record_count': int(row[count]), 'zero_count': int(row[zero]),
        'denominations': row.get('commission_by_denomination', {}),
    } for row in frame.to_dict(orient='records')]


def compare_accounts(current: list[dict], prior: list[dict]) -> list[dict]:
    earlier = {row['dealer_id']: row for row in prior}
    for row in current:
        previous = earlier.get(row['dealer_id'])
        amount = previous['amount_ngn'] if previous else None
        row['prior_amount_ngn'] = amount
        row['delta_ngn'] = round(row['amount_ngn'] - amount, 2) if amount is not None else None
        row['delta_pct'] = round(row['delta_ngn'] / amount * 100, 2) if amount else None
    return current


def totals(rows: list[dict], prior: list[dict] | None) -> dict:
    amount = round(sum(r['amount_ngn'] for r in rows), 2)
    prior_amount = round(sum(r['amount_ngn'] for r in prior), 2) if prior else None
    return {'account_count': len(rows), 'amount_ngn': amount,
            'record_count': sum(r['record_count'] for r in rows),
            'zero_count': sum(r['zero_count'] for r in rows),
            'accounts_with_zero': sum(r['zero_count'] > 0 for r in rows),
            'all_zero_accounts': sum(r['amount_ngn'] == 0 for r in rows),
            'prior_account_count': len(prior) if prior is not None else None,
            'prior_amount_ngn': prior_amount,
            'delta_ngn': round(amount - prior_amount, 2) if rows and prior_amount is not None else None}


def collection(period: str, prior_period: str | None, stream: str, search: str,
               partner_class: str, status: str, sort_by: str, direction: str) -> dict:
    rows = account_rows(period, stream)
    prior = account_rows(prior_period, stream) if prior_period else None
    compare_accounts(rows, prior or [])
    summary = totals(rows, prior)
    classes = sorted({r['account_profile_class'] for r in rows})
    term = search.strip().casefold()
    filtered = [r for r in rows if
                (not term or term in r['dealer_name'].casefold() or term in r['dealer_id'].casefold())
                and (not partner_class or r['account_profile_class'] == partner_class)
                and (status != 'with_zero' or r['zero_count'] > 0)
                and (status != 'all_zero' or r['amount_ngn'] == 0)]
    ids = {r['dealer_id'] for r in filtered}
    matching_prior = [r for r in prior if r['dealer_id'] in ids] if prior is not None else None
    # Stable account-code tie break; missing comparisons always sort last.
    filtered.sort(key=lambda r: r['dealer_id'])
    present = [r for r in filtered if r.get(sort_by) is not None]
    absent = [r for r in filtered if r.get(sort_by) is None]
    present.sort(key=lambda r: r[sort_by], reverse=direction == 'desc')
    return {'mon_period': period, 'prior_period': prior_period, 'stream': stream,
            **provenance(), 'summary': summary,
            'filtered_summary': totals(filtered, matching_prior),
            'partner_classes': classes, 'items': present + absent, 'total': len(filtered)}


def detail(period: str, prior_period: str | None, stream: str, dealer_id: str) -> dict | None:
    rows = account_rows(period, stream, dealer_id)
    if not rows:
        return None
    prior = account_rows(prior_period, stream, dealer_id) if prior_period else []
    row = compare_accounts(rows, prior)[0]
    denominations = row['denominations']
    previous = prior[0]['denominations'] if prior else {}
    breakdown = []
    for name in sorted(set(denominations) | set(previous)):
        amount = round(float(denominations.get(name, 0)), 2)
        before = round(float(previous.get(name, 0)), 2) if prior else None
        breakdown.append({'denomination': name, 'amount_ngn': amount,
                          'prior_amount_ngn': before,
                          'delta_ngn': round(amount - before, 2) if before is not None else None})
    unassigned = round(row['amount_ngn'] - sum(float(v) for v in denominations.values()), 2)
    prior_unassigned = round(prior[0]['amount_ngn'] - sum(float(v) for v in previous.values()), 2) if prior else None
    if stream == 'activation' and (unassigned or prior_unassigned):
        breakdown.append({'denomination': 'Unattributed denomination', 'amount_ngn': unassigned,
                          'prior_amount_ngn': prior_unassigned,
                          'delta_ngn': round(unassigned - prior_unassigned, 2) if prior_unassigned is not None else None})
    return {'mon_period': period, 'prior_period': prior_period, 'stream': stream,
            **provenance(), 'account': row, 'denominations': breakdown,
            'unattributed_amount_ngn': unassigned if stream == 'activation' else 0}
