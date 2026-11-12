"""Claude-authored answers over bounded, application-owned evidence.

Fact references prevent novel numerical literals and invalid references; they do
not prove semantic entailment. A model can still misdescribe a valid fact. The
public conversation evaluations cover that residual language-model risk.
"""
from __future__ import annotations

import json
import calendar
from backend.terminology import RATE_CARD_MISS_LABEL, normalize_generated_prose
import re
from decimal import Decimal
from html import escape
from typing import Any
from pydantic import BaseModel, ConfigDict, Field

from backend.agent.answer_evidence import PreparedAnswer, bounded as _bounded, build_facts as _facts

from backend.agent import prompts
from backend.agent.inference import cached_system, strict_tool

NARRATIVE_FALLBACK = 'I could not complete a reliable answer. Please retry.'


class NarrativeGroundingError(ValueError):
    """No publishable narrative after the bounded repair attempt."""


class ExplanationBlock(BaseModel):
    model_config = ConfigDict(extra='forbid', strict=True)
    text: str = Field(min_length=1, max_length=12000)
    claim_ids: list[str] = Field(max_length=2000)


class AnswerDraft(BaseModel):
    model_config = ConfigDict(extra='forbid', strict=True)
    headline: ExplanationBlock | None
    explanation_blocks: list[ExplanationBlock] = Field(max_length=40)
    next_step_ids: list[str] = Field(max_length=30)


ANSWER_TOOL = {
    'name': 'compose_grounded_answer',
    'description': 'Compose supported explanation blocks and select application-owned next steps.',
    'input_schema': AnswerDraft.model_json_schema(),
}
_TOKEN = re.compile(r'\{\{(f\d+)\}\}')
_NUMBER = re.compile(r'(?<![\w])(?:(?:NGN|₦)\s*)?-?\d[\d,]*(?:\.\d+)?%?')
_CAUSES = {
    'USP_SNAPSHOT_MISS': RATE_CARD_MISS_LABEL,
    'OUTSIDE_6_MONTH_WINDOW': 'activation outside the invoice-to-activation eligibility window',
    'NULL_PROFILE_CLASS': 'a missing account profile at calculation time',
    'HYNEX_DENOMINATION_SPLIT': 'the Hynex / Hynex_1 denomination split',
}
_CAUSE_PATTERNS = {
    'USP_SNAPSHOT_MISS': r'\b(?:USP|snapshot|lookup miss|(?:commission )?rate[- ]card)',
    'OUTSIDE_6_MONTH_WINDOW': r'\b(?:outside|beyond|exceed\w*)\b.{0,55}\b(?:window|eligib|day|month)',
    'NULL_PROFILE_CLASS': r'\b(?:missing|null)\b.{0,35}\b(?:profile|account class|partner classification)',
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


def _attachments(scope, context, tools_called, *, evidence=None):
    body, marker, audit = context.partition('### Verification evidence')
    if scope.get('kind') == 'knowledge':
        marker, audit = '', ''
    parts = []
    if scope.get('presentation') == 'records':
        envelope = (evidence or {}).get('measure_evidence', evidence or {})
        page = envelope.get('investigation', {}).get('record_page')
        if page:
            parts.append(f"Showing records {page['first']:,}–{page['last']:,} of {page['total']:,}."
                         if page['shown'] else f"No records on this page ({page['total']:,} total).")
    if scope.get('presentation') == 'records' or scope.get('operation') == 'breakdown' or 'financial_statements' in scope.get('measures', []):
        tables = re.findall(r'(?:^\|.*(?:\n|$))+', body, re.M)
        parts.extend(table.strip() for table in tables)
    provenance = ''
    if tools_called:
        provenance = 'Tools: ' + ', '.join(tools_called) + '.'
    if scope.get('dealer_id'):
        account = escape(str(scope['dealer_id']), quote=False)
        account = re.sub(r'([\\`*_{}\[\]()!|~])', r'\\\1', account)
        provenance += ' Account: ' + account + '.'
    if scope.get('periods'):
        provenance += ' Periods: ' + ', '.join(scope['periods']) + '.'
    provenance = provenance.strip()
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


def _check_population_claims(text, evidence, facts):
    """Reject observed population overclaims; this is not general entailment."""
    def objects(value):
        if isinstance(value, dict):
            yield value
            for child in value.values():
                yield from objects(child)
        elif isinstance(value, list):
            for child in value:
                yield from objects(child)

    rows = list(objects(evidence))
    if any('causes' in row and 'total_records' in row for row in rows):
        for sentence in re.split(r'[.!?;\n]', text):
            whole_dealer = _asserted(r'\b(?:dealer|partner|account)\s+(?:\{\{f\d+\}\}\s+)?(?:earned|received|had)\s+(?:no|zero)\s+commission\b', sentence)
            explicit_subset = re.search(r'\b(?:on|for)\s+\{\{f\d+\}\}\s+(?:activation\s+)?records\b', sentence, re.I)
            if whole_dealer and not explicit_subset:
                raise NarrativeGroundingError('Zero-commission evidence describes affected records, not the dealer\'s entire month; state the subset explicitly')
        if _asserted(r'\b(?:dealer|partner|account)\b.{0,45}\bhad\s+\{\{f\d+\}\}\s+activations\b.{0,45}\ball\s+(?:earned|with)\s+(?:no|zero)\s+commission\b|'
                     r'\ball\s+(?:\{\{f\d+\}\}\s+)?activations\s+(?:failed|earned no|earned zero)', text):
            raise NarrativeGroundingError('Zero-commission evidence describes affected records, not the dealer\'s entire month; state the subset explicitly')
    products = [product for row in rows for product in row.get('products', [])
                if isinstance(product, dict)]
    if products and _asserted(
            r'\b(?:concentrat\w*|shift\w*|mix)\b.{0,70}\b(?:higher|lower)[- ](?:value|rate|priced)\b|'
            r'\b(?:higher|lower)[- ](?:value|rate|priced)\b.{0,50}\b(?:mix|drove|driven)\b', text):
        raise NarrativeGroundingError('Product contributions do not establish a product-mix shift; explain the supplied per-product changes only')
    for sentence in re.split(r'[.!?;\n]', text):
        if re.search(r'\bnot\s+(?:all|every|each)\b', sentence, re.I):
            continue
        if not _asserted(r'\b(?:higher|increas\w*|grew|growth)\b.{0,100}\b(?:all|every|each)\b.{0,35}\b(?:tiers?|products?|denominations?)\b|'
                         r'\b(?:all|every|each)\b.{0,35}\b(?:tiers?|products?|denominations?)\b.{0,65}\b(?:increas\w*|grew|growth)\b', sentence):
            continue
        volume_claim = bool(re.search(r'\b(?:activations?|volume)\b', sentence, re.I))
        not_increased = any(
            product.get('earlier_activations') is not None and product.get('later_activations') is not None
            and product['later_activations'] <= product['earlier_activations']
            if volume_claim else product.get('change_ngn') is not None and product['change_ngn'] <= 0
            for product in products)
        if not_increased:
            raise NarrativeGroundingError('At least one product is flat or down; do not claim every product increased')
    ledger = {fact['id']: fact for fact in facts}
    for pattern in (
        r'\b(?:qualified|commission[- ]bearing|non[- ]zero)\s+activation\w*\b[^.;,\n]{0,65}?\{\{(?P<id>f\d+)\}\}',
        r'\{\{(?P<id>f\d+)\}\}\s+(?:qualified|commission[- ]bearing|non[- ]zero)\s+activations?\b',
    ):
        for match in re.finditer(pattern, text, re.I):
            if ledger[match['id']].get('meaning') == 'total_activation_count':
                raise NarrativeGroundingError('Total activation counts include zero-commission records; do not describe them as qualified or commission-bearing counts')
    for match in re.finditer(r'\b(?:remained|stayed|was|is)\s+(?:flat|unchanged)\s+at\s+\{\{(?P<id>f\d+)\}\}', text, re.I):
        if ledger[match['id']].get('meaning') == 'change':
            raise NarrativeGroundingError('A zero change is not a zero commission level; describe no change or use the earlier/later amount')
    for clause in re.split(r'[.!?;,\n]|\b(?:but|while|whereas)\b', text, flags=re.I):
        claim = re.search(r'\b(?:largest|biggest|highest)\s+(?:absolute\s+)?(?:commission\s+)?(?:increase|contribution|contributor)\b', clause, re.I)
        if not claim or re.search(r'\bnot\s+(?:the\s+)?(?:largest|biggest|highest)\b', clause, re.I):
            continue
        references = [match for match in _TOKEN.finditer(clause)
                      if ledger[match[1]]['path'].endswith('.product')]
        preceding = [match for match in references if match.end() <= claim.start()]
        if references:
            reference = preceding[-1] if preceding else references[0]
            fact = ledger[reference[1]]
            path = fact.get('path', '')
            if '.products[' not in path or not path.endswith('.product'):
                continue
            group = path.split('.products[')[0] + '.products['
            own_path = path.rsplit('.', 1)[0] + '.change_ngn'
            changes = [f for f in facts if f['path'].startswith(group) and f['path'].endswith('.change_ngn')]
            own = next((f['value'] for f in changes if f['path'] == own_path), None)
            magnitude = abs if 'absolute' in claim.group().lower() else lambda value: value
            if own is not None and changes and magnitude(own) < max(magnitude(f['value']) for f in changes):
                raise NarrativeGroundingError('The named product is not the largest commission increase; use the supplied product contributions')


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


def _reference_known_labels(answer, facts):
    """Canonicalize exact source product/date labels, never novel quantities.

    Claude sometimes copies a correct product label instead of its reference.
    These aliases identify the same ledger fact; ambiguous month/year aliases
    and all counts/amounts still require explicit references.
    """
    aliases = {}
    for fact in facts:
        value, path = fact['value'], fact['path']
        if not isinstance(value, str):
            continue
        labels = []
        if path.rsplit('.', 1)[-1] in {'product', 'product_name', 'product_code'} and re.search(r'[A-Za-z]', value):
            labels = [value]
        elif 'period' in path and re.fullmatch(r'\d{4}(0[1-9]|1[0-2])', value):
            labels = [fact['display'], calendar.month_name[int(value[4:])]]
        elif path == 'policy.identifier':
            labels = [value]
        for label in labels:
            aliases.setdefault(label, {})[value] = fact['id']
    known = {label: next(iter(ids.values())) for label, ids in aliases.items() if len(ids) == 1}
    if not known:
        return answer
    pattern = re.compile(r'(?<![\w])(?:' + '|'.join(re.escape(label) for label in sorted(known, key=len, reverse=True)) + r')(?![\w])')
    return ''.join(part if _TOKEN.fullmatch(part) else pattern.sub(lambda m: '{{' + known[m.group()] + '}}', part)
                   for part in re.split(r'(\{\{f\d+\}\})', answer))


def _validate_text(answer, facts, scope, context, evidence):
    answer = _reference_known_labels(answer, facts)
    if re.search(r'^\s*\||^\s*:?-{2,}\s*\|', answer, re.M):
        raise NarrativeGroundingError('Tables are application-owned; provide narrative only')
    ledger = {fact['id']: fact for fact in facts}
    ids = _TOKEN.findall(answer)
    if any(i not in ledger for i in ids):
        raise NarrativeGroundingError('Unknown fact reference')
    if scope.get('presentation') == 'records':
        for fact_id in ids:
            fact = ledger[fact_id]
            if (isinstance(fact['value'], (int, float, Decimal)) and not isinstance(fact['value'], bool)
                    or fact['path'] == 'validated_context.derived' and _NUMBER.fullmatch(str(fact['value']))):
                raise NarrativeGroundingError('Record-page quantities and ranges are application-owned; introduce the table without numbers')
    product_count_patterns = (
        r'\{\{(?P<id>f\d+)\}\}\s+(?:(?:affected|distinct|unique)\s+)*(?:product codes?|products?)\b',
        r'\bproduct codes?\s*(?:count|total)?\s*(?:is|are|:)?\s*\{\{(?P<id>f\d+)\}\}',
    )
    for pattern in product_count_patterns:
        for match in re.finditer(pattern, answer, re.I):
            field = ledger[match['id']]['path'].rsplit('.', 1)[-1]
            if field not in {'distinct_product_code_count', 'unique_product_code_count', 'distinct_product_count'}:
                raise NarrativeGroundingError('Activation-record counts cannot establish distinct product-code counts')
    plain = _TOKEN.sub('', answer)
    action_prose = plain.replace(_TOKEN.sub('', _reference_known_labels(context, facts)), '') if context else plain
    if _asserted(r'\brecommend\w*\b|\b(?:should|must|can|may|could|please)\b.{0,65}\b(?:pay|release|approve|adjust|correct|reconcile|review|escalate|contact|send|obtain|request)\b|'
                 r'(?:^|[.!?;\n]|:\s*)\s*(?:pay|release|approve|adjust|correct|reconcile|review|escalate|contact|send|obtain|request)\b|'
                 r'\b(?:will|shall)\s+(?:pay|release|approve|adjust|correct)\b', action_prose):
        raise NarrativeGroundingError('Next steps must use permitted action IDs, not model-authored instructions')

    _check_population_claims(answer, evidence, facts)
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
    unknown_balance = any(fact['availability'] == 'unavailable' and fact.get('meaning') in {'paid', 'balance'} for fact in facts)
    if unknown_balance and _asserted(r'\b(?:fully paid|fully settled|all settled|no outstanding|no balance)\b|'
                                    r'\b(?:paid|outstanding|balance)\b.{0,25}\b(?:zero|nil|nothing)\b', plain):
        raise NarrativeGroundingError('Unavailable settlement evidence cannot establish a zero balance')
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
        if field in {'paid', 'owed', 'balance', 'outstanding', 'subscription_revenue', 'revenue'} and field != meaning and {field, meaning} != {'balance', 'outstanding'}:
            raise NarrativeGroundingError('Payment amount has the wrong meaning')
    for match in re.finditer(r'(?P<label>commission|subscription revenue)\s*(?:owed|is|was|:|of)?\s*(?:is\s+)?\{\{(?P<id>f\d+)\}\}', answer, re.I):
        field = ledger[match['id']].get('meaning')
        if ((match['label'].lower() == 'commission' and field == 'subscription_revenue')
                or (match['label'].lower() == 'subscription revenue' and field in {'commission', 'owed', 'paid', 'balance'})):
            raise NarrativeGroundingError('Subscription revenue and commission have different financial meanings')
    _check_cause_support(plain, facts, scope, context)
    # Block novel references and month names: use scope/reference tokens instead.
    if re.search(r'\b(?:January|February|March|April|May|June|July|August|September|October|November|December)\b', plain):
        raise NarrativeGroundingError('Periods must use supplied placeholders')
    if re.search(r'\b(?:account|dealer code|batch|reference)\s*(?:#|:)?\s+[A-Z][A-Z_-]{2,}\b', plain):
        raise NarrativeGroundingError('Identifiers must use supplied placeholders')
    rendered = _TOKEN.sub(lambda m: ledger[m.group(1)]['display'], normalize_generated_prose(answer)).strip()
    if re.search(r'https?://|www\.|!\[|\]\(', rendered, re.I) or _INTERNAL.search(rendered):
        raise NarrativeGroundingError('Unsafe source text cannot be published through a fact')
    if _asserted(_UNSUPPORTED_CAUSE, rendered):
        raise NarrativeGroundingError('Source text cannot introduce an unsupported cause')
    _check_cause_support(rendered, facts, scope, context)
    return rendered


def _candidate(response, prepared: PreparedAnswer):
    blocks = [b for b in response.content if b.type == 'tool_use']
    if response.stop_reason != 'tool_use' or len(blocks) != 1 or blocks[0].name != ANSWER_TOOL['name']:
        raise NarrativeGroundingError('Expected one complete answer contract')
    try:
        draft = AnswerDraft.model_validate(blocks[0].input)
    except ValueError:
        raise NarrativeGroundingError('Invalid answer shape') from None
    explanation = ([draft.headline] if draft.headline is not None else []) + draft.explanation_blocks
    if not explanation or not any(block.text.strip() for block in explanation):
        raise NarrativeGroundingError('Empty or oversized answer')
    if sum(len(block.text) for block in explanation) > 12000:
        raise NarrativeGroundingError('Empty or oversized answer')
    claims = {claim['id']: claim for claim in prepared.claims}
    facts = {fact['id']: fact for fact in prepared.facts}
    actions = {action['id']: action['text'] for action in prepared.permitted_actions}
    rendered = []
    for block in explanation:
        if any(claim_id not in claims for claim_id in block.claim_ids):
            raise NarrativeGroundingError('Unknown claim reference')
        text = _reference_known_labels(block.text, prepared.facts)
        ids = _TOKEN.findall(text)
        if any(fact_id not in facts for fact_id in ids):
            raise NarrativeGroundingError('Unknown fact reference')
        # Every placeholder is an application-supplied fact. Claim grouping is by
        # source path, so a sentence naming a figure, its dealer and month spans
        # claims; requiring each fact's own claim rejected ordinary answers.
        if not block.claim_ids and prepared.claims:
            raise NarrativeGroundingError('Explanation requires a supported claim')
        # Citations are necessary, not sufficient. Keep semantic guards on both
        # the placeholders and substituted source values.
        rendered.append(_validate_text(text, prepared.facts, prepared.scope,
                                       prepared.source_context, prepared.evidence))
    if any(action_id not in actions for action_id in draft.next_step_ids):
        raise NarrativeGroundingError('Unknown or unsupported action reference')
    if draft.next_step_ids:
        rendered.append('**Next steps**\n\n' + '\n'.join('- ' + actions[key] for key in dict.fromkeys(draft.next_step_ids)))
    return '\n\n'.join(rendered)


async def compose_answer(client, run, *, question, history, prepared: PreparedAnswer,
                         sample_mode, model) -> str:
    """Generate and validate a complete draft before rendering owned attachments."""
    if not isinstance(prepared, PreparedAnswer):
        raise TypeError('Composition requires application-prepared evidence')
    payload = {**prepared.model_payload(), 'question': question, 'history': history[-12:],
               'sample_mode': sample_mode}
    if prepared.scope.get('presentation') == 'records':
        payload['history'] = []
        payload['scope'] = {k: v for k, v in payload['scope'].items() if k not in {'record_offset', 'limit'}}
        payload['answer_constraints'] = (
            'Write a brief introduction without numbers. The application appends exact page ranges and records.')
    identifier_placeholders = {fact['value']: '{{' + fact['id'] + '}}' for fact in prepared.facts
                               if isinstance(fact['value'], str) and re.search(r'\d', fact['value'])
                               and (fact['path'] == 'policy.identifier'
                                    or fact['path'].rsplit('.', 1)[-1] in _IDENTIFIERS)}
    if identifier_placeholders:
        payload['identifier_placeholders'] = identifier_placeholders
    if prepared.scope.get('kind') == 'unsupported':
        payload['answer_constraints'] = (
            'Explain only the documented capability boundary. No records were retrieved. '
            'Do not invent capabilities, alternatives or requests for unsupported operations.')
    for attempt in range(2):
        if len(json.dumps(payload, ensure_ascii=False, default=str).encode('utf-8')) > 180000:
            raise NarrativeGroundingError('Evidence exceeds bounded narrative capacity')
        run.remaining()
        response = await run.create(client, model=model, max_tokens=2400,
            system=cached_system(prompts.get_narrative_system_prompt()),
            tools=[strict_tool(ANSWER_TOOL)], tool_choice={'type': 'tool', 'name': ANSWER_TOOL['name']},
            messages=[{'role': 'user', 'content': json.dumps(payload, ensure_ascii=False, default=str, allow_nan=False)}])
        try:
            answer = _candidate(response, prepared)
        except NarrativeGroundingError as exc:
            run.log('narrative_rejected', attempt=attempt + 1, reason=str(exc))
            if attempt or not run.claim_recovery('narrative_repair'):
                raise
            payload['repair'] = str(exc) + '. Compose a fresh draft using the supplied supported claims.'
            continue
        run.remaining()
        parts = [answer, *prepared.mandatory_caveats,
                 *(attachment['text'] for attachment in prepared.attachments if attachment.get('text'))]
        rendered = '\n\n'.join(dict.fromkeys(part for part in parts if part))
        if len(rendered) > 12000:
            raise NarrativeGroundingError('Empty or oversized answer')
        return rendered
    raise NarrativeGroundingError('No publishable answer')
