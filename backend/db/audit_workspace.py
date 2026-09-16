"""Read-only presentation of saved assessments; never compile or persist trails."""
from collections import Counter
from datetime import datetime, timezone
from backend.db import audit_store

FIELDS = ('trail_id', 'partner_code', 'partner_name', 'mon_period', 'module',
          'conclusion', 'confidence', 'caveat_count', 'caveat_steps', 'generated_at',
          'payment_source', 'run_id', 'pipeline_version')
MEASURES = {
    'inventory_mismatch': ('total_units_purchased', 'activation_count', 'inventory_gap'),
    'eligibility_window': ('zero_commission_count', 'inside_window_count', 'outside_window_count',
                           'future_dated_count', 'without_dates_count', 'attributed_count', 'unexplained_count'),
    'zero_commission': ('expected_commission_ngn', 'amount_paid_ngn'),
    'payment_reconciliation': ('expected_commission_ngn', 'amount_paid_ngn', 'delta_ngn'),
}


def compact(trail):
    details = {}
    limitations = []
    for step in trail.get('steps') or []:
        detail = step.get('detail') or {}
        details.update(detail)
        for key, value in detail.items():
            if key in ('note', 'limitation', 'limitations') and value:
                limitations.extend(value if isinstance(value, list) else [str(value)])
    module = trail.get('module', 'zero_commission')
    row = {key: trail.get(key) for key in FIELDS}
    row.update(dealer_id=str(details.get('dealer_id') or str(trail['partner_code']).split(':')[0]),
               dealer_name=details.get('dealer_name') or trail.get('partner_name'),
               product_code=details.get('product_code'), product_name=details.get('product_name'),
               measures={key: details.get(key) for key in MEASURES.get(module, ())},
               limitations=list(dict.fromkeys(limitations)), partial_payment=bool(details.get('partial_payment')))
    row['caveat_steps'] = row['caveat_steps'] or []
    return row


def summary(rows):
    counts = Counter((r['conclusion'], r['confidence']) for r in rows)
    return dict(trail_count=len(rows), subject_count=len({r['partner_code'] for r in rows}),
                dealer_count=len({r['dealer_id'] for r in rows}),
                caveat_trail_count=sum(bool(r['caveat_steps']) for r in rows),
                breakdown=[dict(conclusion=c, confidence=f, count=n) for (c, f), n in sorted(counts.items())])


def collection(params):
    rows = [compact(row) for row in audit_store.get_period_trails(params.mon_period, params.module)]
    full_summary = summary(rows)
    search = params.search.strip().casefold()
    matching = [r for r in rows if
                (not search or search in ' '.join(str(r.get(k) or '') for k in ('partner_code', 'partner_name', 'product_name', 'product_code')).casefold())
                and (not params.subject or r['partner_code'] == params.subject)
                and (not params.conclusion or r['conclusion'] == params.conclusion)
                and (not params.confidence or r['confidence'] == params.confidence)
                and (not params.caveat_step or params.caveat_step in r['caveat_steps'])
                and (params.caveats == 'all' or bool(r['caveat_steps']) == (params.caveats == 'with'))]
    matching.sort(key=lambda r: (str(r['partner_code']), str(r['trail_id'])))
    matching.sort(key=lambda r: str(r.get(params.sort_by) or '').casefold(), reverse=params.sort_direction == 'desc')
    return dict(mon_period=params.mon_period, module=params.module,
                retrieved_at=datetime.now(timezone.utc).isoformat(), summary=full_summary,
                filtered_summary=summary(matching), items=matching)


def detail(subject, period, module, trail_id=None):
    if trail_id is None:
        trail = audit_store.get_partner_trail(subject, period, module)
    else:
        trail = next((row for row in audit_store.get_period_trails(period, module)
                      if row['partner_code'] == subject and str(row['trail_id']) == trail_id), None)
    if trail is None:
        return None
    result = {**trail, **compact(trail)}
    result['steps'] = []
    for step in trail.get('steps') or []:
        presented = dict(step)
        text = step.get('result', '')
        if module == 'eligibility_window' and 'should have earned commission' in text:
            presented['presentation_result'] = text.replace('should have earned commission', 'other eligibility checks required')
            presented['presentation_qualification'] = 'Historical wording qualified for display: being inside the window alone does not establish entitlement. The recorded text is preserved.'
        result['steps'].append(presented)
    return result
