"""Claude-authored answers over bounded, application-owned evidence.

Fact references prevent novel numerical literals and invalid references; they do
not prove semantic entailment. A model can still misdescribe a valid fact. The
public conversation evaluations cover that residual language-model risk.
"""
from __future__ import annotations

import json
import calendar
from backend.terminology import RATE_CARD_MISS_LABEL, normalize_generated_prose
import math
import re
from decimal import Decimal
from html import escape
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


def _bounded(value: Any, key: str = '', *, presentation=None) -> Any:
    """Narrative sees a short record sample; original attachments retain their page."""
    if isinstance(value, dict):
        result = {k: _bounded(v, k, presentation=presentation) for k, v in value.items()}
        products = value.get('products')
        if (isinstance(products, list) and products and all(
                isinstance(product, dict) and isinstance(product.get('change_ngn'), (int, float, Decimal))
                and isinstance(product.get('product'), str) for product in products)):
            largest = max(products, key=lambda product: product['change_ngn'])
            result['all_product_commissions_increased'] = all(product['change_ngn'] > 0 for product in products)
            if all(isinstance(product.get(key), (int, float)) for product in products
                   for key in ('earlier_activations', 'later_activations')):
                result['all_product_activation_counts_increased'] = all(
                    product['later_activations'] > product['earlier_activations'] for product in products)
            if largest['change_ngn'] > 0:
                result['largest_positive_product_contribution'] = {
                    'product': largest['product'], 'change_ngn': largest['change_ngn']}
        if (presentation == 'records' and value.get('status') == 'available'
                and isinstance(value.get('records'), list) and isinstance(value.get('pagination'), dict)):
            page = value['pagination']
            offset, total, shown = page['offset'], page['total'], len(value['records'])
            if (any(isinstance(n, bool) or not isinstance(n, int) or n < 0 for n in (offset, total, shown))
                    or shown and offset + shown > total):
                raise ValueError('Invalid record page bounds')
            result['record_page'] = {'first': offset + 1 if shown else None,
                                     'last': offset + shown if shown else None,
                                     'shown': shown, 'total': total,
                                     'has_more': bool(page.get('has_more'))}
        omitted = {k: len(v) if k == 'records' and presentation == 'records' else len(v) - 12
                   for k, v in value.items()
                   if k in {'rows', 'records', 'steps'} and isinstance(v, list)
                   and (len(v) > 12 or k == 'records' and presentation == 'records' and v)}
        if omitted:
            result['_narrative_omitted_records'] = omitted
        return result
    if isinstance(value, list):
        if key == 'records' and presentation == 'records':
            return []
        selected = value[:12] if key in {'rows', 'records', 'steps'} else value
        return [_bounded(v, key, presentation=presentation) for v in selected]
    if isinstance(value, Decimal):
        return float(value)
    return value


def _financial_meaning(value):
    words = set(re.findall(r'[a-z]+', value.lower()))
    if words & {'change', 'delta'}:
        return 'change'
    if words & {'earlier', 'prior'}:
        return 'prior_level'
    if words & {'later', 'current'}:
        return 'current_level'
    if words & {'outstanding', 'balance'}:
        return 'balance'
    if words & {'paid', 'settled', 'settlement'}:
        return 'paid'
    if words & {'owed', 'payable', 'entitlement'}:
        return 'owed'
    return None


def _currency_table_cells(context: str) -> list[tuple[int, int]]:
    """Locate cells whose own source table header explicitly supplies NGN units."""
    cells = []
    lines = context.splitlines(keepends=True)
    columns: set[int] = set()
    offset = 0
    for index, line in enumerate(lines):
        if not line.lstrip().startswith('|'):
            columns = set()
        elif index + 1 < len(lines) and re.fullmatch(
                r'\s*\|(?:\s*:?-+:?\s*\|)+\s*', lines[index + 1]):
            columns = {column for column, cell in enumerate(line.split('|'))
                       if re.search(r'\bNGN\b|₦', cell)}
        elif columns:
            cursor = offset
            for column, cell in enumerate(line.split('|')):
                if column in columns and re.fullmatch(r'\s*-?\d[\d,]*(?:\.\d+)?\s*', cell):
                    cells.append((cursor, cursor + len(cell)))
                cursor += len(cell) + 1
        offset += len(line)
    return cells


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
            count_meaning = ('total_activation_count' if '.totals.' in path
                             and key in {'earlier_activations', 'later_activations'} else None)
            add(path, value, display, meaning if monetary else count_meaning)
        elif isinstance(value, str) and (key in _IDENTIFIERS or key == 'cause'):
            # A source label is data, never a new instruction or executable HTML.
            display = _CAUSES.get(value, value)
            if key in {'period', 'periods', 'mon_period'} and re.fullmatch(r'\d{4}(0[1-9]|1[0-2])', value):
                display = f'{calendar.month_name[int(value[4:])]} {value[:4]}'
            display = re.sub(r'[<>\r\n|]', ' ', display)
            add(path, value, display)

    walk(evidence, 'evidence')
    walk({key: scope[key] for key in ('dealer_id', 'dealer_name', 'periods') if key in scope}, 'scope')
    if scope.get('kind') == 'knowledge':
        # Exact identifiers in the validated policy excerpt are source facts too.
        # Hynex_1 and 5G cannot otherwise cross the numeric-literal guard, even
        # though their digits are part of documented names rather than quantities.
        for identifier in dict.fromkeys(re.findall(r'\b[A-Za-z0-9][A-Za-z0-9_-]*\b', context)):
            if (any(c.isdigit() for c in identifier) and any(c.isalpha() for c in identifier)
                    and not any(f['value'] == identifier for f in facts)):
                add('validated_context.identifier', identifier, identifier)
    # Legacy validated rendering currently owns cross-period arithmetic and
    # ranking subtotals. Retain these as explicitly labelled supplemental facts.
    currency_cells = _currency_table_cells(context)
    for match in _NUMBER.finditer(context):
        start, end = max(0, match.start() - 65), min(len(context), match.end() + 65)
        if match.group() in scope.get('periods', []):
            continue
        monetary = (match.group().startswith(('NGN', '₦')) or
                    any(start <= match.start() < end for start, end in currency_cells))
        display = match.group()
        if monetary:
            amount = re.sub(r'^(?:NGN|₦)\s*', '', match.group()).replace(',', '')
            display = f'NGN {Decimal(amount):,.2f}'
        if monetary and any(f['display'] == display for f in facts):
            continue
        prefix = re.split(r'[;\n.!?]', context[:match.start()])[-1][-70:]
        meaning = _financial_meaning(prefix) if monetary else None
        add('validated_context.derived', match.group(), display, meaning)
        facts[-1]['context'] = context[start:end]
    return facts


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
        elif path == 'validated_context.identifier':
            labels = [value]
        for label in labels:
            aliases.setdefault(label, {})[value] = fact['id']
    known = {label: next(iter(ids.values())) for label, ids in aliases.items() if len(ids) == 1}
    if not known:
        return answer
    pattern = re.compile(r'(?<![\w])(?:' + '|'.join(re.escape(label) for label in sorted(known, key=len, reverse=True)) + r')(?![\w])')
    return ''.join(part if _TOKEN.fullmatch(part) else pattern.sub(lambda m: '{{' + known[m.group()] + '}}', part)
                   for part in re.split(r'(\{\{f\d+\}\})', answer))


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
    rendered = _TOKEN.sub(lambda m: ledger[m.group(1)]['display'], normalize_generated_prose(answer)).strip()
    if re.search(r'https?://|www\.|!\[|\]\(', rendered, re.I) or _INTERNAL.search(rendered):
        raise NarrativeGroundingError('Unsafe source text cannot be published through a fact')
    if _asserted(_UNSUPPORTED_CAUSE, rendered):
        raise NarrativeGroundingError('Source text cannot introduce an unsupported cause')
    _check_cause_support(rendered, facts, scope, context)
    return rendered


async def compose_answer(client, run, *, question, history, scope, evidence,
                         tools_called, validated_context, sample_mode, model) -> str:
    """Compose, check, and at most once repair without publishing a draft."""
    projected = _bounded(evidence, presentation=scope.get('presentation'))
    context = (validated_context if scope.get('kind') == 'knowledge' else
               validated_context.partition('### Verification evidence')[0])
    # Tables are application-owned attachments, not a second narrative source.
    if scope.get('kind') != 'knowledge':
        context = re.sub(r'(?:^\|.*(?:\n|$))+', '', context, flags=re.M)
        if scope.get('presentation') not in {'actions', 'dealer_draft'}:
            context = context.partition('**Next steps**')[0].rstrip()
    generation_evidence = projected
    if scope.get('presentation') == 'records':
        # The model introduces the page; the application alone presents its
        # exact bounds and rows. Do not offer numeric page facts it must not use.
        envelope = projected.get('measure_evidence', projected)
        investigation = envelope.get('investigation', {})
        generation_evidence = {'investigation': {
            'status': investigation.get('status', 'unavailable'),
            'family': investigation.get('family'),
        }}
        context = ('The application appends the requested record table and exact page range.'
                   if investigation.get('status') == 'available' else 'Record evidence is unavailable.')
    facts = _facts(generation_evidence, scope, context)
    payload = {'question': question, 'history': history[-12:], 'scope': scope,
               'evidence': generation_evidence, 'facts': facts, 'validated_context': context,
               'tools_called': tools_called, 'sample_mode': sample_mode}
    if scope.get('presentation') == 'records':
        # Interpretation already resolved the next page using the full history.
        # Old assistant tables/provenance are not material for this introduction
        # and otherwise invite the model to reproduce application-owned output.
        payload['history'] = []
        payload['scope'] = {key: value for key, value in scope.items()
                            if key not in {'record_offset', 'limit'}}
        payload['answer_constraints'] = (
            'Write one brief introductory sentence only. The application adds the complete record table, '
            'exact page range and evidence disclosure. Do not repeat tables, quantities, ranges, '
            'provenance or previous answers. Use the supplied dealer and period placeholders if useful.')
    identifier_placeholders = {fact['value']: '{{' + fact['id'] + '}}' for fact in facts
                               if isinstance(fact['value'], str) and re.search(r'\d', fact['value'])
                               and (fact['path'] == 'validated_context.identifier'
                                    or fact['path'].rsplit('.', 1)[-1] in _IDENTIFIERS)}
    if identifier_placeholders:
        payload['identifier_placeholders'] = identifier_placeholders
        payload['identifier_instruction'] = ('These documented names contain digits. Use their supplied '
            'placeholders instead of spelling their literal names in the answer, including on the first attempt.')
    if scope.get('kind') == 'unsupported':
        payload['answer_constraints'] = (
            'Explain this capability boundary directly. Do not repeat numbers or identifiers from the '
            'question unless supplied as scope facts. No records were retrieved. Do not invent another '
            'capability, add unsolicited alternatives, or ask for scope for an operation Atlas cannot perform.')
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
            run.log('narrative_rejected', attempt=attempt + 1, reason=str(exc))  # raises take string literals only (AST-tested)
            if attempt or not run.claim_recovery('narrative_repair'):
                raise
            payload['repair'] = str(exc) + '. Compose a fresh answer using the supplied facts.'
            if identifier_placeholders:
                payload['repair'] += ' Replace digit-containing source names using identifier_placeholders.'
            continue
        attachments = _attachments(scope, validated_context, tools_called, evidence=projected)
        return answer + ('\n\n' + attachments if attachments else '')
    raise NarrativeGroundingError('No publishable answer')
