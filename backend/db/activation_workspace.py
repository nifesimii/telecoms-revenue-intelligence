"""Bounded presentation of existing activation reads; no commission recalculation."""
from backend.assurance.activation_assurance import (
    ACTION_BY_EXCEPTION,
    SEVERITY_BY_EXCEPTION,
)
from backend.db.commission_workspace import provenance
from backend.db.connection import execute_query


_FINDING_LABELS = {
    'ALL_UNQUALIFIED': 'All activations have zero commission',
    'HIGH_UNQUALIFIED_RATE': 'More than half have zero commission',
    'UNUSUAL_VOLUME': 'Unusual activation volume',
}
_SEVERITY_RANK = {'HIGH': 3, 'MEDIUM': 2, 'LOW': 1}


def activation_provenance(period: str, prior_period: str | None) -> dict:
    metadata = provenance(period)
    if prior_period:
        metadata['source'] = (
            f"Reporting {period}: {metadata['source']} · "
            f"Comparison {prior_period}: {provenance(prior_period)['source']}"
        )
    return metadata


def account_rows(period: str) -> list[dict]:
    frame = execute_query('get_activation_summary', {'mon_period': period})
    rows = frame.astype(object).where(frame.notna(), None).to_dict(orient='records')
    for row in rows:
        row['dealer_id'] = str(row['dealer_id'])
        row['dealer_name'] = str(row['dealer_name'] or '')
        row['account_profile_class'] = str(row['account_profile_class'] or '')
        row['report_month'] = str(row['report_month'])
    return rows


def enrich_accounts(period: str, prior_period: str | None) -> list[dict]:
    rows = account_rows(period)
    prior = {r['dealer_id']: r for r in account_rows(prior_period)} if prior_period else {}
    exceptions = execute_query('get_activation_exceptions', {'mon_period': period})
    findings: dict[str, dict[str, dict]] = {}
    for record in exceptions.to_dict(orient='records'):
        kind = record['exception_type']
        findings.setdefault(str(record['dealer_id']), {})[kind] = {
            'type': kind, 'label': _FINDING_LABELS[kind],
            'severity': SEVERITY_BY_EXCEPTION[kind],
            'recommended_action': ACTION_BY_EXCEPTION[kind],
        }
    for row in rows:
        row['findings'] = sorted(findings.get(row['dealer_id'], {}).values(),
                                 key=lambda f: (-_SEVERITY_RANK[f['severity']], f['type']))
        previous = prior.get(row['dealer_id'])
        row['prior_activation_count'] = previous['activation_count'] if previous else None
        row['prior_qualification_rate_pct'] = previous['qualification_rate_pct'] if previous else None
        row['prior_commission_amount'] = previous['activation_commission_amount'] if previous else None
        row['delta_activations'] = row['activation_count'] - previous['activation_count'] if previous else None
        row['delta_qualification_rate'] = round(
            row['qualification_rate_pct'] - previous['qualification_rate_pct'], 2
        ) if previous else None
        row['delta_commission_ngn'] = round(
            row['activation_commission_amount'] - previous['activation_commission_amount'], 2
        ) if previous else None
    return rows


def totals(rows: list[dict]) -> dict:
    count = sum(r['activation_count'] for r in rows)
    qualified = sum(r['qualified_activation_count'] for r in rows)
    return {
        'account_count': len(rows), 'activation_count': count,
        'qualified_activation_count': qualified,
        'non_qualified_activation_count': sum(r['non_qualified_activation_count'] for r in rows),
        'qualification_rate_pct': round(qualified / count * 100, 2) if count else None,
        'activation_commission_amount': round(sum(r['activation_commission_amount'] for r in rows), 2),
        'accounts_with_zero': sum(r['non_qualified_activation_count'] > 0 for r in rows),
        'all_zero_accounts': sum(r['activation_count'] > 0 and
                                 r['non_qualified_activation_count'] == r['activation_count'] for r in rows),
        'finding_count': sum(len(r['findings']) for r in rows),
        'flagged_accounts': sum(bool(r['findings']) for r in rows),
    }


def collection(period: str, prior_period: str | None, view: str, search: str,
               partner_class: str, finding: str, sort_by: str, direction: str) -> dict:
    rows = enrich_accounts(period, prior_period)
    term = search.strip().casefold()
    filtered = [r for r in rows if
                (view != 'comparison' or r['prior_activation_count'] is not None)
                and (view != 'exceptions' or r['findings'])
                and (not term or term in r['dealer_name'].casefold() or term in r['dealer_id'].casefold())
                and (not partner_class or r['account_profile_class'] == partner_class)
                and (finding != 'with_zero' or r['non_qualified_activation_count'] > 0)
                and (finding != 'all_zero' or (r['activation_count'] > 0 and
                     r['non_qualified_activation_count'] == r['activation_count']))
                and (finding in ('all', 'with_zero', 'all_zero') or
                     any(f['type'] == finding for f in r['findings']))]

    def sort_value(row: dict):
        if sort_by == 'severity':
            return max((_SEVERITY_RANK[f['severity']] for f in row['findings']), default=0)
        if sort_by == 'dealer_name':
            return row['dealer_name'].casefold()
        return row[sort_by]

    # Account-code ties stay deterministic in both directions; absent prior data is last.
    filtered.sort(key=lambda r: r['dealer_id'])
    present = [r for r in filtered if sort_value(r) is not None]
    absent = [r for r in filtered if sort_value(r) is None]
    present.sort(key=sort_value, reverse=direction == 'desc')
    return {'mon_period': period, 'prior_period': prior_period, 'view': view,
            **activation_provenance(period, prior_period), 'summary': totals(rows), 'filtered_summary': totals(filtered),
            'comparison_account_count': sum(r['prior_activation_count'] is not None for r in rows),
            'partner_classes': sorted({r['account_profile_class'] for r in rows}),
            'items': present + absent, 'total': len(filtered)}


def detail(period: str, prior_period: str | None, dealer_id: str) -> dict | None:
    # Volume findings require the entire peer set; existing queries own that rule.
    row = next((r for r in enrich_accounts(period, prior_period) if r['dealer_id'] == dealer_id), None)
    if row is None:
        return None
    return {'mon_period': period, 'prior_period': prior_period, **activation_provenance(period, prior_period), 'account': row}
