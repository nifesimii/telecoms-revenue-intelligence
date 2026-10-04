"""Provider-only fixtures: independently authored answers over supplied facts.

No production response renderer is invoked. This keeps conversation regressions
sensitive to the evidence actually supplied to the final model call.
"""
import json
import re
from types import SimpleNamespace


def answer_text(payload):
    scope = payload['scope']
    kind = scope['kind']
    measures = scope.get('measures', [])
    if scope.get('dealer_name') and not scope.get('dealer_id') and kind == 'measure':
        return payload['validated_context']
    if kind == 'knowledge' and scope.get('knowledge_quote'):
        return 'The documented activation commission rate is 8,215.81.'
    if kind == 'knowledge' and scope.get('knowledge_topic') == 'zero_commission_causes':
        return 'The documented causes include Product not matched to commission rate card and the Hynex denomination split. A cause remains unverified without supporting records.'
    if kind in ('knowledge', 'unsupported', 'clarification'):
        return 'Here is the relevant detail: ' + payload['validated_context']
    if kind == 'identity':
        return 'Recorded dealer codes include 74050. Source: Recorded dealer records.'
    if kind == 'affiliation':
        if scope.get('dealer_id'):
            return 'Topaz Bridge Trading (19580) has 9 other dealer codes in 202606, including 19577. Their indicative commission is NGN 790,062.67; this is not a verified partner group.'
        return '"Topaz Bridge Trading" has 10 dealer codes in 202606. The indicative total is NGN 938,254.18; this is not a verified partner group. | 19580 |'
    if 'inventory_gap' in measures:
        return 'Stone Wind Communications has a cumulative inventory gap. The product breakdown is below.'
    if 'dealer_purchases' in measures:
        return 'Complete purchases are unavailable; dated complete purchase records are needed.'
    if 'activation_qualified_count' in measures:
        if scope.get('dealer_id') is None:
            return 'Raven View Networks appears in the low-qualification dealer breakdown below.'
        return 'There were 806 activations: 713 qualified and 93 unqualified for dealer 74050 in 202603.'
    if 'payment_status' in measures:
        if scope.get('dealer_id') is None:
            return 'The disputed dealer payments and outstanding amounts are shown below.'
        return 'NGN 368,324.63 was paid and NGN 552,486.95 remains outstanding for dealer 296065 in 202603. The payment is disputed. Source: Payment records.'
    if 'dealer_investigation' in measures:
        if scope.get('presentation') == 'records':
            return 'Here are the requested evidence records.'
        family = scope.get('investigation_family')
        if family == 'payment':
            return 'NGN 594,652.08 remains outstanding for dealer 296065 in 202606.'
        if family == 'commission_variance':
            return 'Commission changed by NGN 39,873.42 for dealer 296065 between 202605 and 202606.'
        presentation = scope.get('presentation')
        if presentation == 'actions':
            return 'Revenue Assurance: review the 50 zero-commission activations for dealer 296065 in 202606.'
        if presentation == 'dealer_draft':
            return 'Draft for Finance review. Dear River Isle Ventures, account 296065 has 50 zero-commission activations in 202606. This does not approve an adjustment or promise payment.'
        return 'I checked the evidence: dealer 296065 has 50 zero-commission activations in 202606.'
    if 'payment_exceptions' in measures:
        dealer = scope.get('dealer_id')
        return f'The payment exceptions for dealer {dealer} in 202606 are available in the supporting evidence.'
    if 'dealer_statement' in measures:
        if scope.get('dealer_id') == '19969':
            return 'The dealer statement for account 19969 in 202606 is in the supporting evidence.'
        if scope.get('dealer_id') == '130062':
            return 'The dealer statement for Amber Arc Communications, account 130062 in 202606, is in the supporting evidence.'
        return 'NGN 994,136.80 is owed, NGN 397,959.72 is paid and NGN 596,177.08 remains outstanding for dealer 296065 in 202606.'
    if 'investigation_priority' in measures:
        return 'Investigation priority for dealer 296065, 202606: HIGH — rank 1 of 922. Commission-module priority: MEDIUM.'
    if 'verification_outcome' in measures:
        return 'The recorded payment is below the recorded amount owed for dealer 296065 in 202606.'
    if 'commission_variance' in measures:
        return 'Commission increased by NGN 39,873.42 for dealer 296065 between 202605 and 202606.'
    if 'data_coverage' in measures:
        return 'Some evidence is unavailable for dealer 296065 in 202606; the supporting records identify the missing sources.'
    if 'investigation_queue' in measures:
        return 'Showing 10 of 61 matching dealers in 202606. The supporting evidence contains the ranked investigation queue.'
    if 'activation_exceptions' in measures:
        return 'The activation exceptions for dealer 296065 in 202606 are in the supporting evidence.'
    if 'financial_statements' in measures:
        if scope.get('dealer_id') == '296065':
            return 'No financial statement on record for account 296065; activations or commission do not establish sales revenue.'
        return 'Sales revenue is NGN 12,600,000.00 for dealer 74050 in 202603.'
    if 'financial_kpis' in measures:
        return 'The supporting records show the current ratio for dealer 74050 in 202603.'
    if 'retail_sales_value' in measures:
        return 'Retail sales value is unavailable because customer transactions are not recorded here.'
    if len(scope.get('periods', [])) == 12:
        return 'Partial total: missing months are unavailable. | 202612 | Unavailable |'
    if 'zero_commission_count' in measures:
        return 'NGN 1,140,192.85 is recorded for dealer 74050 in 202603. There are 93 zero-commission activations; some are unresolved and the evidence includes Product not matched to commission rate card.'
    if measures == ['activation_commission']:
        return 'NGN 1,140,192.85 is the recorded activation commission for dealer 74050 in 202603.'
    if 'activation_commission' in measures:
        return 'Dealer 74050 recorded 806 activations and NGN 1,140,192.85 activation commission in 202603.'
    return 'I checked the records: dealer 74050 had 806 activations in 202603. Source: Activation records.'


def tokenized_answer(payload, text):
    """Encode fixed fixture facts in the application's provider transport format."""
    facts = payload['facts']
    replacements = {}
    for fact in facts:
        for value in (str(fact['value']), str(fact['display'])):
            if re.search(r'\d', value):
                replacements.setdefault(value, '{{' + fact['id'] + '}}')
    if replacements:
        pattern = '|'.join(re.escape(value) for value in sorted(replacements, key=len, reverse=True))
        text = re.sub(pattern, lambda match: replacements[match.group()], text)
    return text


def final_response(kwargs, *, text=None):
    payload = json.loads(kwargs['messages'][-1]['content'])
    answer = tokenized_answer(payload, text if text is not None else answer_text(payload))
    return SimpleNamespace(stop_reason='tool_use', usage=None, content=[SimpleNamespace(
        type='tool_use', id='answer', name='compose_grounded_answer', input={'answer': answer})])


def is_final_call(kwargs):
    return kwargs.get('tools', [{}])[0].get('name') == 'compose_grounded_answer'
