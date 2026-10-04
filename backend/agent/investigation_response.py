"""Business answers from the shared investigation facts, with bounded evidence."""
from backend.agent.measure_response import _text
from backend.terminology import RATE_CARD_MISS_LABEL, RATE_CARD_MISS_EXPLANATION

LABELS = {
    'USP_SNAPSHOT_MISS': RATE_CARD_MISS_LABEL,
    'OUTSIDE_6_MONTH_WINDOW': 'Outside the eligibility window',
    'NULL_PROFILE_CLASS': 'Missing account profile at calculation time',
    'HYNEX_DENOMINATION_SPLIT': 'Hynex / Hynex_1 denomination split',
}
ACTIONS = {
    'USP_SNAPSHOT_MISS': 'Revenue Assurance: reconcile the affected product codes against the calculation-month commission rate card snapshot and refer confirmed mapping omissions for correction.',
    'OUTSIDE_6_MONTH_WINDOW': 'Finance: retain the invoice and activation dates supporting the exclusion; review only records where the dealer supplies corrected dates.',
    'NULL_PROFILE_CLASS': 'FBB Operations: resolve the historical dealer-profile lookup, then request a review of the affected calculation records.',
    'HYNEX_DENOMINATION_SPLIT': 'Product-master owner: reconcile Hynex / Hynex_1 mappings and return the affected records to Revenue Assurance for review.',
}


def _money(value):
    return f'NGN {value:,.2f}'


def render_investigation(result, presentation='explanation'):
    if presentation not in {'explanation', 'records', 'actions', 'dealer_draft'}:
        raise ValueError('Invalid investigation presentation')
    account = _text(result['dealer_id'])
    period = ', '.join(result['periods'])
    if result['status'] != 'available':
        return f"Account {account} · {period}: {_text(result.get('note', 'Investigation evidence is unavailable.'))}"
    family = result['family']
    parts, actions = [], []
    if family == 'zero_commission':
        total = result['total_records']
        explained = sum(c['count'] for c in result['causes'])
        if explained + result['unresolved_count'] != total:
            raise ValueError('Cause counts must reconcile to the affected population')
        parts.append(f"**{total:,} zero-commission activations: {explained:,} explained"
                     + (f", {result['unresolved_count']:,} still unresolved.**" if result['unresolved_count'] else '.**'))
        parts.append('| Reason | Records |\n|---|---:|\n' + '\n'.join(
            f"| {LABELS[c['cause']]} | {c['count']:,} |" for c in result['causes']))
        if any(c['cause'] == 'USP_SNAPSHOT_MISS' for c in result['causes']):
            parts.append(RATE_CARD_MISS_EXPLANATION + ' '
                         'The calculation decision records identify this lookup failure as the reason for zero commission.')
        counts = result['eligibility']
        parts.append(f"The date check places **{counts['outside']:,} outside** and **{counts['inside']:,} inside** "
                     'the invoice-to-activation window (0–180 days inclusive).')
        if counts['invalid']:
            parts.append(f"{counts['invalid']:,} records have missing, invalid or reversed dates.")
        actions = [ACTIONS[c['cause']] for c in result['causes']]
        if result['unresolved_count']:
            actions.append(f"Revenue Assurance: obtain calculation evidence for the {result['unresolved_count']:,} unresolved records; no cause has been assigned to them.")
        if result['unresolved_count']:
            parts.append('Inside-window records still require supporting calculation evidence; eligibility alone does not establish entitlement.')
    elif family == 'commission_variance':
        variance = result['variance']
        totals = variance['totals']
        parts.append(f"**Activation commission changed by {_money(totals['change_ngn'])}**, "
                     f"from {_money(totals['earlier_ngn'])} to {_money(totals['later_ngn'])}.")
        parts.append(f"Recorded activations changed from {totals['earlier_activations']:,} to {totals['later_activations']:,}.")
        parts.append('| Product | Prior commission | Current commission | Contribution to change |\n|---|---:|---:|---:|\n' + '\n'.join(
            f"| {_text(p['product'])} | {_money(p['earlier_ngn'])} | {_money(p['later_ngn'])} | {_money(p['change_ngn'])} |"
            for p in result['records']))
        zeros = result['zero_investigations']
        if all(z['status'] == 'available' for z in zeros):
            parts.append(f"Non-zero commission activations changed from {totals['earlier_activations'] - zeros[0]['total_records']:,} "
                         f"to {totals['later_activations'] - zeros[1]['total_records']:,}.")
        for zero in zeros:
            parts.append(f"{zero['periods'][0]}: {zero['total_records']:,} zero-commission records — " +
                         '; '.join(f"{c['count']:,} {LABELS[c['cause']]}" for c in zero['causes']) +
                         (f"; {zero['unresolved_count']:,} unresolved." if zero['unresolved_count'] else '.'))
        page = result['pagination']
        if len(result['records']) < page['total']:
            shown = sum(p['change_ngn'] for p in result['records'])
            parts.append(f"Showing {len(result['records'])} of {page['total']} products at offset {page['offset']}. "
                         f"Products outside this page contribute {_money(round(totals['change_ngn'] - shown, 2))}. Ask for the next page for more detail.")
        parts.append('The complete product contributions reconcile the recorded change; zero-record causes explain exclusions, not a recalculated loss of commission.')
        actions = ['Finance: review the largest product contributions first, then inspect the affected zero-commission records in each month before proposing an adjustment.']
    else:
        payment = result['payment']
        balance = payment['balance']
        if balance is None:
            parts.append('**Payment balance cannot yet be established.** ' +
                         (f"Recorded owed {_money(payment['owed'])}. " if payment['owed'] is not None else 'Statement evidence unavailable. ') +
                         (f"Recorded paid {_money(payment['paid'])}." if payment['paid'] is not None else 'Settlement evidence unavailable.'))
        else:
            parts.append(f"**{_money(abs(balance))} {'outstanding' if balance > 0 else 'paid above recorded owed' if balance < 0 else 'remaining'}**: "
                     f"recorded owed {_money(payment['owed'])}; recorded paid {_money(payment['paid'])}.")
        process = payment['process']
        if process:
            messages = {
                'SETTLED': 'The settlement record shows the recorded amount has been settled.',
                'AWAITING_RELEASE': 'The settlement workflow records the remaining balance in a batch awaiting release.',
                'DISPUTE_REVIEW': 'The settlement workflow records the remaining balance under dispute review.',
                'EXCESS_REVIEW': 'The settlement workflow records the excess for reconciliation review.',
            }
            parts.append(messages[process['process_state']] + f" Batch **{_text(process['batch_reference'])}**; evidence {_text(process['evidence_ref'])}.")
            actions = [f"{_text(process['owner'])}: " + ('confirm settlement references before closing the review.' if balance == 0 else
                       'review the recorded batch and reconcile the remaining amount.')]
        else:
            if payment['coverage_complete']:
                parts.append('The balance is established by the recorded amounts; no matching workflow evidence establishes the reason for it.')
            actions = ['Finance: reconcile the statement and settlement references with Payment Operations before assigning a payment-delay cause.']
        if not payment['coverage_complete']:
            parts.append('Statement or settlement coverage is incomplete; normalized zero amounts do not establish zero entitlement or non-payment.')
    parts.insert(1, f"{_text(result.get('dealer_name', 'Account'))} · Account {account} · {period}.")
    if presentation == 'records':
        page = result['pagination']
        if family == 'zero_commission':
            parts = parts[:2]
            parts.append('| IMEI | Product code | Invoice date | Activation date | Days | Reason | Evidence |\n|---|---|---|---|---:|---|---|\n' + '\n'.join(
                f"| {_text(r['imei'])} | {_text(r['product_code'])} | {_text(r['invoice_date'])} | {_text(r['activation_date'])} | {r['gap_days'] if r['gap_days'] is not None else 'Unknown'} | "
                f"{LABELS.get(r['cause'], 'Unresolved')} | {_text(r['evidence_ref'] or 'No supporting decision')} |" for r in result['records']))
        parts.append(f"Showing {len(result['records']):,} of {page['total']:,} evidence records, offset {page['offset']:,}. " +
                     ('Ask for the next page to continue.' if page['has_more'] else 'End of evidence.'))
    if presentation == 'actions':
        parts = parts[:2]
        if family == 'zero_commission':
            parts.append('; '.join(f"{c['count']:,} {LABELS[c['cause']]}" for c in result['causes']))
    if actions:
        parts.append('**Next steps**\n\n' + '\n'.join(f'- {action}' for action in actions))
    if presentation == 'dealer_draft':
        parts.insert(0, f"**Draft for Finance review**\n\nDear {_text(result.get('dealer_name', account))},\n\nHere is the breakdown of your commission review.")
        parts.append('Finance will review any correction through the authorized process. This draft does not approve an adjustment or promise payment.')
    parts.append('Sources checked: ' + ', '.join(f'`{tool}`' for tool in result['tools']) + f' · {period}.')
    return '\n\n'.join(parts)
