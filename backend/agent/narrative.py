"""Claude-authored answers over bounded, application-owned evidence.

Fact references prevent novel numerical literals and invalid references; they do
not prove semantic entailment. A model can still misdescribe a valid fact. The
public conversation evaluations cover that residual language-model risk.
"""
from __future__ import annotations

import json
import math
import re
from decimal import Decimal
from typing import Any

from backend.agent import prompts
from backend.agent.inference import cached_system

NARRATIVE_FALLBACK = 'I could not complete a reliable answer. Please retry.'


class NarrativeGroundingError(ValueError):
    """No publishable narrative after the bounded repair attempt."""


ANSWER_TOOL = {
    'name': 'compose_grounded_answer',
    'description': 'Write the final conversational answer, using supplied fact placeholders for factual values.',
    'input_schema': {'type': 'object', 'properties': {
        'answer': {'type': 'string', 'minLength': 1, 'maxLength': 12000},
    }, 'required': ['answer'], 'additionalProperties': False},
}
_TOKEN = re.compile(r'\{\{(f\d+)\}\}')
_NUMBER = re.compile(r'(?<![\w])(?:NGN\s*)?-?\d[\d,]*(?:\.\d+)?%?')
_CAUSES = {
    'USP_SNAPSHOT_MISS': 'a product lookup miss in the calculation-month USP snapshot',
    'OUTSIDE_6_MONTH_WINDOW': 'activation outside the invoice-to-activation eligibility window',
    'NULL_PROFILE_CLASS': 'a missing account profile at calculation time',
    'HYNEX_DENOMINATION_SPLIT': 'the Hynex / Hynex_1 denomination split',
}
_CAUSE_PATTERNS = {
    'USP_SNAPSHOT_MISS': r'\b(?:USP|snapshot|lookup miss)',
    'OUTSIDE_6_MONTH_WINDOW': r'\b(?:outside|beyond|exceed\w*)\b.{0,55}\b(?:window|eligib|day|month)',
    'NULL_PROFILE_CLASS': r'\b(?:missing|null)\b.{0,35}\b(?:profile|account class)',
    'HYNEX_DENOMINATION_SPLIT': r'\b(?:Hynex|denomination split)',
}
# These represent known unsupported assertions, not a general semantic validator.
_UNSUPPORTED_CAUSE = re.compile(r'\b(?:fraud\w*|network outage|system outage|bank delay|banking delay|'
                                r'insufficient funds|cash[- ]flow problem|budget shortfall|technical glitch)\b', re.I)
_INTERNAL = re.compile(r'```(?:sql|presto)|\bSELECT\b[\s\S]*?\bFROM\b|\b(?:POLICY_MET|POLICY_VIOLATED|MIXED_ATTRIBUTION)\b', re.I)
_IDENTIFIERS = {'dealer_id', 'dealer_name', 'dealer_code', 'distributor_code', 'account_code',
                'period', 'periods', 'mon_period', 'imei', 'product_code', 'product',
                'product_name', 'batch_reference', 'evidence_ref', 'reference',
                'invoice_date', 'first_activation_date', 'activation_date', 'process_state'}


def _bounded(value: Any, key: str = '') -> Any:
    """Narrative sees a short record sample; original attachments retain their page."""
    if isinstance(value, dict):
        result = {k: _bounded(v, k) for k, v in value.items()}
        omitted = {k: len(v) - 12 for k, v in value.items()
                   if k in {'rows', 'records', 'steps'} and isinstance(v, list) and len(v) > 12}
        if omitted:
            result['_narrative_omitted_records'] = omitted
        return result
    if isinstance(value, list):
        selected = value[:12] if key in {'rows', 'records', 'steps'} else value
        return [_bounded(v, key) for v in selected]
    if isinstance(value, Decimal):
        return float(value)
    return value


def _financial_meaning(value):
    words = set(re.findall(r'[a-z]+', value.lower()))
    if words & {'outstanding', 'balance'}:
        return 'balance'
    if words & {'paid', 'settled', 'settlement'}:
        return 'paid'
    if words & {'owed', 'payable', 'entitlement'}:
        return 'owed'
    return None


def _facts(evidence: dict, scope: dict, context: str) -> list[dict]:
    facts: list[dict] = []

    def add(path, value, display, meaning=None):
        facts.append({'id': f'f{len(facts)}', 'path': path, 'value': value, 'display': display, 'meaning': meaning})

    def walk(value, path, unit=None, key='', meaning=None):
        if isinstance(value, dict):
            unit = value.get('unit', unit)
            meaning = _financial_meaning(value.get('measure', '')) or meaning
            for child, item in value.items():
                if child in {'offset', 'limit', 'record_offset', 'page', 'page_size'} and scope.get('presentation') != 'records':
                    continue
                walk(item, path + '.' + child, unit, child, _financial_meaning(child) or meaning)
        elif isinstance(value, list):
            for i, item in enumerate(value):
                walk(item, f'{path}[{i}]', unit, key, meaning)
        elif isinstance(value, (int, float, Decimal)) and not isinstance(value, bool):
            if not math.isfinite(float(value)):
                raise ValueError('Non-finite narrative evidence')
            monetary = ('ngn' in key or key in {'owed', 'paid', 'balance', 'outstanding'}
                        or unit == 'ngn' and key in {'total', 'value'})
            display = f'NGN {value:,.2f}' if monetary else f'{value:,}'
            add(path, value, display, meaning if monetary else None)
        elif isinstance(value, str) and (key in _IDENTIFIERS or key == 'cause'):
            # A source label is data, never a new instruction or executable HTML.
            display = _CAUSES.get(value, value)
            display = re.sub(r'[<>\r\n|]', ' ', display)
            add(path, value, display)

    walk(evidence, 'evidence')
    walk({key: scope[key] for key in ('dealer_id', 'dealer_name', 'periods') if key in scope}, 'scope')
    # Legacy validated rendering currently owns cross-period arithmetic and
    # ranking subtotals. Retain these as explicitly labelled supplemental facts.
    for match in _NUMBER.finditer(context):
        start, end = max(0, match.start() - 65), min(len(context), match.end() + 65)
        if match.group().startswith('NGN') and any(f['display'] == match.group() for f in facts):
            continue
        prefix = re.split(r'[;\n.!?]', context[:match.start()])[-1][-70:]
        meaning = _financial_meaning(prefix) if match.group().startswith('NGN') else None
        add('validated_context.derived', match.group(), match.group(), meaning)
        facts[-1]['context'] = context[start:end]
    return facts


def _attachments(scope, context, tools_called):
    body, marker, audit = context.partition('### Verification evidence')
    if scope.get('kind') == 'knowledge':
        marker, audit = '', ''
    parts = []
    if scope.get('presentation') == 'records' or scope.get('operation') == 'breakdown' or 'financial_statements' in scope.get('measures', []):
        tables = re.findall(r'(?:^\|.*(?:\n|$))+', body, re.M)
        parts.extend(table.strip() for table in tables)
    provenance = ''
    if tools_called:
        provenance = 'Tools: ' + ', '.join(tools_called) + '.'
        if scope.get('periods'):
            provenance += ' Periods: ' + ', '.join(scope['periods']) + '.'
    if marker or provenance:
        parts.append('### Verification evidence\n\n' + '\n\n'.join(p for p in [provenance, audit.strip()] if p))
    return '\n\n'.join(parts)


def _availability(value):
    if isinstance(value, dict):
        result = [value['status']] if value.get('status') in {'available', 'unavailable'} else []
        if 'measure' in value and value.get('periods') == []:
            result.append('unavailable')
        return result + [state for child in value.values() for state in _availability(child)]
    if isinstance(value, list):
        return [state for child in value for state in _availability(child)]
    return []


def _asserted(pattern, text):
    # A clearly marked lack of confirmation is not an attribution. Check each
    # sentence separately so one denial cannot authorize another asserted cause.
    for sentence in re.split(r'[.!?;,\n]|\b(?:but|although|however|whereas|yet)\b', text, flags=re.I):
        if (pattern.search(sentence) if hasattr(pattern, 'search') else re.search(pattern, sentence, re.I)) and not re.search(
                r'cannot (?:be )?(?:confirm|establish|determine)|not (?:confirmed|established|supported)|'
                r'no (?:supporting )?evidence|without supporting|unconfirmed|unverified|'
                r'(?:cannot|does not|do not) (?:prove|establish)|not (?:a |the )?cause', sentence, re.I):
            return True
    return False


def _check_cause_support(text, facts, scope, context):
    # Causes must be supported for this request. Knowledge answers may discuss
    # all documented possibilities; data answers may discuss only returned ones.
    supported = {f['value'] for f in facts if f['path'].endswith('.cause')}
    if scope.get('kind') == 'knowledge':
        supported = set(_CAUSES)
    for cause, pattern in _CAUSE_PATTERNS.items():
        if cause not in supported and _asserted(pattern, text):
            # Eligibility verification carries policy and date classifications,
            # rather than an investigation cause enum.
            if cause == 'OUTSIDE_6_MONTH_WINDOW' and ('eligibility' in context.lower()):
                continue
            raise NarrativeGroundingError('Cause is not supported by this evidence')
    process_states = {f['value'] for f in facts if f['path'].endswith('.process_state')}
    for state, pattern in {
        'AWAITING_RELEASE': r'awaiting release|waiting for release|pending release',
        'DISPUTE_REVIEW': r'under dispute review|in dispute review',
        'EXCESS_REVIEW': r'excess.{0,20}reconciliation review',
    }.items():
        if state not in process_states and _asserted(pattern, text):
            raise NarrativeGroundingError('Payment process is not supported by workflow evidence')


def _candidate(response, facts, scope, context, evidence):
    blocks = [b for b in response.content if b.type == 'tool_use']
    if response.stop_reason != 'tool_use' or len(blocks) != 1 or blocks[0].name != ANSWER_TOOL['name']:
        raise NarrativeGroundingError('Expected one complete answer contract')
    value = blocks[0].input
    if not isinstance(value, dict) or set(value) != {'answer'}:
        raise NarrativeGroundingError('Invalid answer shape')
    answer = value['answer']
    if not isinstance(answer, str) or not 0 < len(answer.strip()) <= 12000:
        raise NarrativeGroundingError('Empty or oversized answer')
    ledger = {fact['id']: fact for fact in facts}
    ids = _TOKEN.findall(answer)
    if any(i not in ledger for i in ids):
        raise NarrativeGroundingError('Unknown fact reference')
    plain = _TOKEN.sub('', answer)
    if '{{' in plain or '}}' in plain or re.search(r'\d|[₦$€£]', plain):
        raise NarrativeGroundingError('Factual values must use supplied placeholders')
    if scope.get('kind') == 'measure' and re.search(
            r'\b(?:zero|one|two|three|four|five|six|seven|eight|nine|ten|eleven|twelve|'
            r'thirteen|fourteen|fifteen|sixteen|seventeen|eighteen|nineteen|twenty|thirty|'
            r'forty|fifty|sixty|seventy|eighty|ninety|hundred|thousand|million|billion)'
            r'(?:[- ](?:and|one|two|three|four|five|six|seven|eight|nine|hundred))*\s+'
            r'(?:records?|activations?|dealers?|naira|percent|days?|months?|units?)\b', plain, re.I):
        raise NarrativeGroundingError('Spelled factual quantities must use supplied placeholders')
    availability = _availability(evidence)
    if 'unavailable' in availability and re.search(
            r'\bnothing is missing\b|\bno (?:data |source )?gaps\b|\bfully (?:verified|complete)\b', plain, re.I):
        raise NarrativeGroundingError('Unavailable evidence cannot establish completeness')
    if availability and set(availability) == {'unavailable'} and re.search(
            r'\b(?:is|are|was|were|equals?|totals?|balance)\s+(?:zero|nil|nothing)\b|'
            r'\b(?:fully paid|fully settled|all settled|no outstanding|no balance)\b', plain, re.I):
        raise NarrativeGroundingError('Unavailable evidence cannot establish a zero balance')
    if _INTERNAL.search(plain) or re.search(r'\bNGN\b|https?://|www\.|!\[|\]\(|<[^>]+>', plain, re.I):
        raise NarrativeGroundingError('Raw financial or internal syntax')
    if _asserted(_UNSUPPORTED_CAUSE, plain):
        raise NarrativeGroundingError('Unsupported causal assertion')
    # Reject known direct relabelling of payment amounts even when the number
    # itself is real. This is deliberately a narrow check, not an entailment proof.
    for match in re.finditer(r'(?P<label>outstanding(?: balance)?|paid|owed)\s*(?:is|was|:|of)?\s*\{\{(?P<id>f\d+)\}\}', answer, re.I):
        fact = ledger[match['id']]
        field = fact.get('meaning')
        meaning = 'balance' if match['label'].lower().startswith('outstanding') else match['label'].lower()
        if field in {'paid', 'owed', 'balance', 'outstanding'} and field != meaning and {field, meaning} != {'balance', 'outstanding'}:
            raise NarrativeGroundingError('Payment amount has the wrong meaning')
    _check_cause_support(plain, facts, scope, context)
    # Block novel references and month names: use scope/reference tokens instead.
    if re.search(r'\b(?:January|February|March|April|May|June|July|August|September|October|November|December)\b', plain):
        raise NarrativeGroundingError('Periods must use supplied placeholders')
    if re.search(r'\b(?:account|dealer code|batch|reference)\s*(?:#|:)?\s+[A-Z][A-Z_-]{2,}\b', plain):
        raise NarrativeGroundingError('Identifiers must use supplied placeholders')
    rendered = _TOKEN.sub(lambda m: ledger[m.group(1)]['display'], answer).strip()
    if re.search(r'https?://|www\.|!\[|\]\(', rendered, re.I) or _INTERNAL.search(rendered):
        raise NarrativeGroundingError('Unsafe source text cannot be published through a fact')
    if _asserted(_UNSUPPORTED_CAUSE, rendered):
        raise NarrativeGroundingError('Source text cannot introduce an unsupported cause')
    _check_cause_support(rendered, facts, scope, context)
    return rendered


async def compose_answer(client, run, *, question, history, scope, evidence,
                         tools_called, validated_context, sample_mode, model) -> str:
    """Compose, check, and at most once repair without publishing a draft."""
    projected = _bounded(evidence)
    context = (validated_context if scope.get('kind') == 'knowledge' else
               validated_context.partition('### Verification evidence')[0])
    # Tables are application-owned attachments, not a second narrative source.
    if scope.get('kind') != 'knowledge':
        context = re.sub(r'(?:^\|.*(?:\n|$))+', '', context, flags=re.M)
    facts = _facts(projected, scope, context)
    payload = {'question': question, 'history': history[-12:], 'scope': scope,
               'evidence': projected, 'facts': facts, 'validated_context': context,
               'tools_called': tools_called, 'sample_mode': sample_mode}
    if len(json.dumps(payload, ensure_ascii=False, default=str)) > 180000:
        raise NarrativeGroundingError('Evidence exceeds bounded narrative capacity')
    for attempt in range(2):
        run.remaining()
        response = await run.create(client, model=model, max_tokens=2400,
            system=cached_system(prompts.get_narrative_system_prompt()),
            tools=[ANSWER_TOOL], tool_choice={'type': 'tool', 'name': ANSWER_TOOL['name']},
            messages=[{'role': 'user', 'content': json.dumps(payload, ensure_ascii=False, default=str, allow_nan=False)}])
        try:
            answer = _candidate(response, facts, scope, context, projected)
        except NarrativeGroundingError as exc:
            run.log('narrative_rejected', attempt=attempt + 1)
            if attempt:
                raise
            payload['repair'] = str(exc) + '. Compose a fresh answer using the supplied facts.'
            continue
        attachments = _attachments(scope, validated_context, tools_called)
        return answer + ('\n\n' + attachments if attachments else '')
    raise NarrativeGroundingError('No publishable answer')
