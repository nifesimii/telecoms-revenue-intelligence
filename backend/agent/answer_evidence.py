"""Application-owned facts, supported claims, disclosures and answer attachments.

Nothing in this module accepts a model-authored fact or computes from generated
prose. Decimal values remain Decimal until the model payload is serialized.
"""
from __future__ import annotations

import calendar
from copy import deepcopy
from dataclasses import dataclass
from decimal import Decimal
import re
from typing import Any

from backend.terminology import RATE_CARD_MISS_LABEL

IDENTIFIERS = {'dealer_id', 'dealer_name', 'dealer_code', 'distributor_code', 'account_code',
               'period', 'periods', 'mon_period', 'imei', 'product_code', 'product',
               'product_name', 'batch_reference', 'evidence_ref', 'reference',
               'invoice_date', 'first_activation_date', 'activation_date', 'process_state'}
CAUSES = {'USP_SNAPSHOT_MISS': RATE_CARD_MISS_LABEL,
          'OUTSIDE_6_MONTH_WINDOW': 'activation outside the invoice-to-activation eligibility window',
          'NULL_PROFILE_CLASS': 'a missing account profile at calculation time',
          'HYNEX_DENOMINATION_SPLIT': 'the Hynex / Hynex_1 denomination split'}


def financial_meaning(label: str) -> str | None:
    words = set(re.findall(r'[a-z]+', label.lower()))
    for terms, meaning in [({'change', 'delta'}, 'change'), ({'earlier', 'prior'}, 'prior_level'),
                           ({'later', 'current'}, 'current_level'),
                           ({'outstanding', 'balance'}, 'balance'),
                           ({'paid', 'settled', 'settlement'}, 'paid'),
                           ({'owed', 'payable', 'entitlement'}, 'owed'),
                           ({'subscription'}, 'subscription_revenue'),
                           ({'commission'}, 'commission'), ({'revenue'}, 'revenue')]:
        if words & terms:
            return meaning
    return None


def model_value(value: Any) -> Any:
    if isinstance(value, Decimal):
        return str(value)
    if isinstance(value, dict):
        return {key: model_value(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [model_value(item) for item in value]
    return value


@dataclass(frozen=True)
class PreparedAnswer:
    scope: dict
    evidence: dict
    facts: list[dict]
    claims: list[dict]
    permitted_actions: list[dict]
    mandatory_caveats: list[str]
    attachments: list[dict]
    tools_called: list[str]
    source_context: str

    def model_payload(self) -> dict:
        return model_value({'scope': self.scope, 'evidence': self.evidence,
                            'facts': self.facts, 'claims': self.claims,
                            'permitted_actions': self.permitted_actions,
                            'mandatory_caveats': self.mandatory_caveats,
                            'validated_context': self.source_context,
                            'tools_called': self.tools_called})


def bounded(value: Any, key: str = '', *, presentation=None) -> Any:
    if isinstance(value, dict):
        result = {k: bounded(v, k, presentation=presentation) for k, v in value.items()}
        omitted = {k: len(v) if k == 'records' and presentation == 'records' else len(v) - 12
                   for k, v in value.items() if k in {'rows', 'records', 'steps'} and isinstance(v, list)
                   and (len(v) > 12 or k == 'records' and presentation == 'records' and v)}
        if omitted:
            result['_narrative_omitted_records'] = omitted
        return result
    if isinstance(value, list):
        selected = [] if key == 'records' and presentation == 'records' else value[:12] if key in {'rows', 'records', 'steps'} else value
        return [bounded(item, key, presentation=presentation) for item in selected]
    return value


def build_facts(evidence: dict, scope: dict, context: str = '', sources=()) -> list[dict]:
    facts: list[dict] = []

    def add(path, value, display, meaning, unit, status, source, coverage, derivation=()):
        facts.append({'id': f'f{len(facts)}', 'path': path, 'value': value,
                      'display': display, 'meaning': meaning, 'unit': unit,
                      'availability': status, 'source_refs': [source],
                      'coverage': coverage, 'derivation_refs': list(derivation)})

    def walk(value, path, key='', unit=None, meaning=None, status='available', source='validated_scope', coverage='supplied evidence'):
        if isinstance(value, dict):
            unit = value.get('unit', unit)
            meaning = financial_meaning(value.get('measure', '')) or meaning
            status = value.get('status', status)
            if status not in {'available', 'unavailable', 'not_meaningful', 'not_recorded'}:
                status = 'available'
            source = str(value.get('source') or value.get('tool') or source)
            if value.get('coverage_complete') is False:
                coverage = 'incomplete source coverage'
            if value.get('truncated') or value.get('_narrative_omitted_records'):
                coverage = 'bounded sample; aggregates retain their source coverage'
            for child, item in value.items():
                if child in {'offset', 'limit', 'record_offset', 'page', 'page_size'} and scope.get('presentation') != 'records':
                    continue
                walk(item, path + '.' + child, child, unit, financial_meaning(child) or meaning, status, source, coverage)
        elif isinstance(value, list):
            for i, item in enumerate(value):
                walk(item, f'{path}[{i}]', key, unit, meaning, status, source, coverage)
        elif (isinstance(value, (int, float, Decimal)) and not isinstance(value, bool)) or value is None:
            monetary = ('ngn' in key or key in {'owed', 'paid', 'balance', 'outstanding'}
                        or unit == 'ngn' and key in {'total', 'value', 'available_total', 'ranked_total', 'delta'})
            percent = key.endswith(('_pct', '_percent', '_percentage'))
            if value is None and not monetary:
                return
            number = Decimal(str(value)) if value is not None else None
            if number is not None and not number.is_finite():
                raise ValueError('Non-finite answer evidence')
            available = (status == 'available' or key == 'dealer_count') and number is not None
            actual = (number if monetary else value) if available else None
            display = (f'NGN {number:,.2f}' if monetary else f'{value:,}%' if percent else f'{value:,}') if available else 'Unknown'
            count_meaning = 'total_activation_count' if '.totals.' in path and key in {'earlier_activations', 'later_activations'} else None
            add(path, actual, display, (meaning or key) if monetary else count_meaning,
                'ngn' if monetary else 'percent' if percent else 'count' if key.endswith(('_count', '_activations', '_records')) else unit or 'count', 'available' if available else 'unavailable', source, coverage,
                [path.split('.prepared')[0]] if '.prepared' in path else [])
        elif isinstance(value, str) and (key in IDENTIFIERS or key == 'cause'):
            display = CAUSES.get(value, value)
            if key in {'period', 'periods', 'mon_period'} and re.fullmatch(r'\d{4}(0[1-9]|1[0-2])', value):
                display = f'{calendar.month_name[int(value[4:])]} {value[:4]}'
            add(path, value, re.sub(r'[<>\r\n|]', ' ', display), None, 'identifier', 'available', source, coverage)

    walk(evidence, 'evidence', source=', '.join(sources) or 'validated_evidence')
    walk({key: scope[key] for key in ('dealer_id', 'dealer_name', 'periods', 'product_name') if scope.get(key) is not None}, 'scope')
    return facts


def _policy_facts(blocks: list[str], facts: list[dict]) -> None:
    # Only exact authoritative KB blocks reach this parser, never rendered answers.
    for index, block in enumerate(blocks):
        currency_columns: set[int] = set()
        for line in block.splitlines():
            if '|' in line and re.search(r'NGN|₦', line):
                currency_columns = {i for i, cell in enumerate(line.split('|')) if re.search(r'NGN|₦', cell)}
            for match in re.finditer(r'(?<![\w])(?:(?:NGN|₦)\s*)?-?\d[\d,]*(?:\.\d+)?%?', line):
                literal = match.group()
                money = literal.startswith(('NGN', '₦')) or line[:match.start()].count('|') in currency_columns
                amount = Decimal(re.sub(r'^(?:NGN|₦)\s*', '', literal).replace(',', '')) if money else None
                facts.append({'id': f'f{len(facts)}', 'path': f'policy.blocks[{index}]',
                              'value': amount if money else literal,
                              'display': f'NGN {amount:,.2f}' if money else literal,
                              'meaning': 'documented_policy_amount' if money else 'documented_policy_value',
                              'unit': 'ngn' if money else 'percent' if literal.endswith('%') else 'policy',
                              'availability': 'available', 'source_refs': ['core_kb'],
                              'coverage': 'documented policy, not observed dealer evidence',
                              'derivation_refs': [], 'context': block})
        for identifier in dict.fromkeys(re.findall(r'\b[A-Za-z0-9][A-Za-z0-9_-]*\b', block)):
            if any(c.isdigit() for c in identifier) and any(c.isalpha() for c in identifier):
                facts.append({'id': f'f{len(facts)}', 'path': 'policy.identifier', 'value': identifier,
                              'display': identifier, 'meaning': None, 'unit': 'identifier',
                              'availability': 'available', 'source_refs': ['core_kb'],
                              'coverage': 'documented policy', 'derivation_refs': [], 'context': block})


def _check_scope(scope: dict, evidence: dict) -> None:
    if scope.get('kind') not in {'measure', 'finding'}:
        return
    periods = scope.get('periods', [])
    def check(value):
        if isinstance(value, list):
            for item in value:
                check(item)
        elif isinstance(value, dict):
            for key in ('dealer_id', 'distributor_code', 'account_code'):
                if scope.get('dealer_id') and value.get(key) is not None and value[key] != scope['dealer_id']:
                    raise ValueError('Evidence account differs from validated scope')
            for key in ('period', 'mon_period', 'current_period', 'prior_period'):
                if value.get(key) and periods and value[key] not in periods:
                    raise ValueError('Evidence period differs from validated scope')
            for key in ('periods', 'requested_periods'):
                listed = value.get(key)
                if isinstance(listed, list) and all(isinstance(p, str) for p in listed):
                    if periods and not set(listed) <= set(periods):
                        raise ValueError('Evidence periods differ from validated scope')
            for child in value.values():
                check(child)
    # Lookup coverage is explicitly cross-period and may list sibling accounts;
    # only the resolved measure envelope supplies scoped financial facts.
    check(evidence.get('measure_evidence', evidence))


def _preserve_unknowns(value: Any) -> None:
    """Strip normalized placeholders only where source flags deny availability."""
    if isinstance(value, list):
        for item in value:
            _preserve_unknowns(item)
    elif isinstance(value, dict):
        payment = value.get('payment')
        if isinstance(payment, dict) and payment.get('payment_found') is False:
            for group in ('position', 'combined'):
                for field in value.get(group, {}):
                    if financial_meaning(field) in {'paid', 'balance'} or field == 'variance_pct':
                        value[group][field] = None
        if value.get('payment_found') is False:
            for field in value:
                if financial_meaning(field) in {'paid', 'balance'}:
                    value[field] = None
        for child in value.values():
            _preserve_unknowns(child)


def prepare_answer(*, scope: dict, evidence: dict, tools_called: list[str],
                   validated_context: str = '', mandatory_caveats=(), attachments=None) -> PreparedAnswer:
    _check_scope(scope, evidence)
    from backend.agent.answer_preparation import prepare_evidence
    prepared = prepare_evidence(evidence, scope)
    _preserve_unknowns(prepared)
    projected = bounded(prepared, presentation=scope.get('presentation'))
    generation_evidence = projected
    if scope.get('presentation') == 'records':
        investigation = projected.get('measure_evidence', projected).get('investigation', {})
        generation_evidence = {'investigation': {'status': investigation.get('status', 'unavailable'),
                                                'family': investigation.get('family')}}
    facts = build_facts(generation_evidence, scope, sources=tools_called)
    context = ''
    policy_caveats = []
    if scope.get('kind') == 'knowledge':
        from backend.agent import prompts
        from backend.agent.measure_scope import MeasureScope
        from backend.agent.knowledge_response import knowledge_response
        from backend import config
        context = knowledge_response(MeasureScope.model_validate(scope), prompts.KB_CONTENT, sample_mode=config.USE_SAMPLE_DATA)
        blocks = context.removeprefix('Documented policy:\n\n').split('\n\n')
        _policy_facts(blocks, facts)
        from backend.agent.knowledge_response import _ELIGIBILITY, eligibility_policy
        if _ELIGIBILITY.search(context):
            policy_caveats.append(eligibility_policy(prompts.KB_CONTENT, config.USE_SAMPLE_DATA))
    elif scope.get('kind') == 'unsupported':
        context = validated_context
    claims = []
    groups: dict[str, list[dict]] = {}
    for fact in facts:
        groups.setdefault(fact['path'].rsplit('.', 1)[0], []).append(fact)
    for path, members in groups.items():
        claims.append({'id': f'c{len(claims)}', 'fact_ids': [fact['id'] for fact in members],
                       'statement': 'Supported source fields at ' + path,
                       'source_refs': list(dict.fromkeys(s for fact in members for s in fact['source_refs'])),
                       'scope_ref': 'validated_scope',
                       'constraints': 'Describe only these fields with their stated meaning, availability and coverage; references do not establish causes or authorize other assertions.'})
    if context:
        claims.append({'id': f'c{len(claims)}', 'fact_ids': [f['id'] for f in facts if f['path'].startswith('policy.')],
                       'statement': context, 'source_refs': ['core_kb'], 'scope_ref': 'validated_scope'})
    caveats = [*mandatory_caveats, *policy_caveats]
    from backend import config
    payment_scope = (any(name.startswith('payment_') or name == 'dealer_statement' for name in scope.get('measures', []))
                     or scope.get('investigation_family') == 'payment'
                     or scope.get('finding', {}).get('module') == 'payment')
    if payment_scope and config.PAYMENT_SOURCE == 'simulated':
        caveats.append('Settlement amounts use simulated payment evidence; they do not establish live payments.')
    actions: list[dict] = []

    def visit(value):
        if isinstance(value, dict):
            source = value.get('source') or value.get('tool') or value.get('measure') or 'Evidence'
            if value.get('payment_found') is False:
                caveats.append(f'{source}: no payment record is available; paid and outstanding amounts are unknown, not zero.')
            if value.get('data_source') == 'simulated' or value.get('payment_source') == 'simulated' or source == 'simulated':
                caveats.append('Settlement amounts use simulated payment evidence; they do not establish live payments.')
            if value.get('status') == 'unavailable':
                caveats.append(f'{source}: evidence is unavailable; missing evidence is not zero.')
            for key in ('caveats', 'disclosures', 'mandatory_disclosures'):
                if isinstance(value.get(key), list):
                    caveats.extend(str(item) for item in value[key])
            for key in ('note', 'association_note', 'coverage_note'):
                if isinstance(value.get(key), str) and value[key].strip():
                    caveats.append(f'{source}: {value[key]}')
            if value.get('coverage_complete') is False:
                caveats.append(f'{source}: coverage is incomplete; normalized zero amounts do not establish zero entitlement or non-payment.')
            if value.get('truncated') or value.get('_narrative_omitted_records'):
                caveats.append(f'{source}: displayed evidence is bounded; it does not represent the complete population.')
            if value.get('family') == 'zero_commission':
                from backend.agent.investigation_response import ACTIONS
                for cause in value.get('causes', []):
                    if cause.get('cause') in ACTIONS:
                        actions.append({'id': f'a{len(actions)}', 'text': ACTIONS[cause['cause']]})
                caveats.append('Zero-commission records are an affected subset of activations. Eligibility alone does not establish entitlement.')
            if value.get('family') == 'commission_variance':
                actions.append({'id': f'a{len(actions)}', 'text': 'Finance: review the largest product contributions and the supporting zero-commission evidence before considering an adjustment.'})
            if value.get('family') == 'payment':
                actions.append({'id': f'a{len(actions)}', 'text': 'Finance: reconcile the statement and settlement references with Payment Operations before assigning a payment-delay cause.'})
            for child in value.values():
                visit(child)
        elif isinstance(value, list):
            for child in value:
                visit(child)
    visit(projected)
    if scope.get('presentation') == 'dealer_draft':
        caveats.append('Draft for Finance review. This draft does not approve an adjustment or promise payment.')
    # Existing deterministic renderers remain the authority for tables and audit
    # attachments. They are not used to discover factual values for the model.
    if attachments is None:
        from backend.agent.narrative import _attachments
        rendered = _attachments(scope, validated_context, tools_called, evidence=prepared)
        attachments = [{'kind': 'evidence', 'text': rendered}] if rendered else []
    if scope.get('presentation') not in {'actions', 'dealer_draft'}:
        actions = []
    return PreparedAnswer(deepcopy(scope), generation_evidence, facts, claims, actions,
                          list(dict.fromkeys(caveats)), attachments, list(tools_called), context)
