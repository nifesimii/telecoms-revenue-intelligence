"""Measure enforcement at the public agent boundary, using real sample evidence."""
import asyncio
import json
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from anthropic.types import TextBlock, ToolUseBlock

from backend.agent import agent


def install_plan(monkeypatch, plan, *, draft='Commission NGN 999,999,999.00; investigate disputes.'):
    response = SimpleNamespace(
        content=[TextBlock(type='text', text=draft), ToolUseBlock(
            type='tool_use', id='scope', name='resolve_measure_request', input=plan)],
        stop_reason='tool_use', usage=None,
    )
    from backend.tests.narrative_provider import final_response, is_final_call
    async def reply(**kwargs):
        return final_response(kwargs) if is_final_call(kwargs) else response
    create = AsyncMock(side_effect=reply)
    client = SimpleNamespace(messages=SimpleNamespace(create=create), close=AsyncMock())
    monkeypatch.setattr(agent, 'new_client', lambda key: client)
    return create


def test_activation_answer_comes_from_evidence_not_model_prose(monkeypatch):
    install_plan(monkeypatch, {
        'kind': 'measure', 'measures': ['activation_count'], 'periods': ['202603'],
        'dealer_id': '74050', 'operation': 'total', 'breakdown': 'dealer',
    })
    result = asyncio.run(agent.run_agent('How many activations did dealer 74050 have in March 2026?'))
    assert '806' in result['response']
    assert '74050' in result['response']
    assert '202603' in result['response']
    assert 'Source: Activation records' in result['response']
    assert 'sample' not in result['response'].lower()
    assert '999,999,999' not in result['response']
    assert 'commission' not in result['response'].lower()
    assert 'dispute' not in result['response'].lower()
    evidence = result['raw_data']['measure_evidence']
    assert [item['measure'] for item in evidence['measures']] == ['activation_count']
    assert 'total_commission_ngn' not in json.dumps(evidence)


def test_explicit_unavailable_measure_does_not_require_an_irrelevant_period(monkeypatch):
    install_plan(monkeypatch, {
        'kind': 'measure', 'measures': ['retail_sales_value'], 'dealer_id': '74050',
    })
    result = asyncio.run(agent.run_agent('What are this dealer\'s actual customer sales?'))
    assert result['tools_called'] == []
    assert 'unavailable' in result['response'].lower()
    assert 'customer transactions' in result['response'].lower()
    assert 'NGN' not in result['response']


def test_clarification_preserves_exact_context_and_withholds_all_figures(monkeypatch):
    create = install_plan(monkeypatch, {
        'kind': 'clarification', 'clarification': 'sales_meaning',
        'dealer_id': '00123', 'periods': ['202606'],
    })
    result = asyncio.run(agent.run_agent('What sales did this dealer make?',
        reporting_period='202606', investigation_context='Exact dealer account 00123. Payment workspace.'))
    assert '00123' in result['response']
    assert 'sales' in result['response'] and '?' in result['response']
    assert 'NGN' not in result['response']
    assert result['tools_called'] == [] and result['raw_data'] == {}
    message = json.loads(create.call_args_list[0].kwargs['messages'][-1]['content'])
    assert message == {'question': 'What sales did this dealer make?', 'reporting_period': '202606',
                       'investigation_context': 'Exact dealer account 00123. Payment workspace.'}


def test_established_meaning_and_acceptance_remain_in_active_conversation(monkeypatch):
    create = install_plan(monkeypatch, {
        'kind': 'measure', 'measures': ['activation_count'], 'periods': ['202603'],
        'dealer_id': '74050',
    })
    history = [
        {'role': 'user', 'content': 'By sales here I mean recorded activations, for dealer 74050.'},
        {'role': 'assistant', 'content': 'I will label those as activations, not customer sales.'},
    ]
    result = asyncio.run(agent.run_agent('And March 2026?', history,
        reporting_period='202603', investigation_context='Exact dealer account 74050.'))
    assert '806' in result['response'] and '74050' in result['response']
    assert '?' not in result['response']
    assert create.call_args_list[0].kwargs['messages'][:-1] == history
    assert len(history) == 2


def test_explicit_multi_measure_has_only_requested_metrics(monkeypatch):
    install_plan(monkeypatch, {'kind': 'measure', 'measures': ['activation_count', 'activation_commission'],
                              'periods': ['202603'], 'dealer_id': '74050'})
    result = asyncio.run(agent.run_agent('Give activations and activation commission for 74050 in 202603.'))
    assert '806' in result['response']
    assert 'NGN 1,140,192.85' in result['response']
    assert 'payment' not in result['response'].lower()
    assert [m['measure'] for m in result['raw_data']['measure_evidence']['measures']] == [
        'activation_count', 'activation_commission']


def test_full_year_keeps_missing_months_distinct_from_zero(monkeypatch):
    periods = [f'2026{month:02d}' for month in range(1, 13)]
    install_plan(monkeypatch, {'kind': 'measure', 'measures': ['activation_count'],
                              'periods': periods, 'dealer_id': '74050',
                              'operation': 'breakdown', 'breakdown': 'month'})
    result = asyncio.run(agent.run_agent('Give activations for the full calendar year 2026 for 74050 by month.'))
    assert 'Partial total' in result['response']
    assert '| 202612 | Unavailable |' in result['response']
    assert '| 202612 | 0 |' not in result['response']
    assert 'synthetic' not in result['response'].lower()
    assert result['raw_data']['measure_evidence']['requested_periods'] == periods


@pytest.mark.parametrize('changes', [
    {'measures': ['unknown']}, {'periods': ['202613']}, {'periods': ['202603', '202603']},
    {'answer': 'NGN 900.00'}, {'dealer_id': '74050 other'},
])
def test_invalid_scope_never_calls_data_tools(monkeypatch, changes):
    install_plan(monkeypatch, {'kind': 'measure', 'measures': ['activation_count'],
                              'periods': ['202603'], 'dealer_id': '74050', **changes})
    calls = []
    monkeypatch.setattr(agent.tool_executor, 'execute_measure_request', lambda request: calls.append(request))
    result = asyncio.run(agent.run_agent('Activation count for 74050, 202603'))
    assert result['response'] == agent.FALLBACK_RESPONSE
    assert calls == []


def test_no_unverified_knowledge_quote_crosses_output_boundary(monkeypatch):
    install_plan(monkeypatch, {'kind': 'knowledge', 'knowledge_quote': 'Dealer 74050 earned NGN 900,000.00.'})
    result = asyncio.run(agent.run_agent('What commission is owed to 74050?'))
    assert result['response'] == agent.FALLBACK_RESPONSE


def test_name_code_lookup_remains_available_without_unrelated_figures(monkeypatch):
    install_plan(monkeypatch, {'kind': 'identity', 'dealer_name': 'Stone Light Networks'})
    result = asyncio.run(agent.run_agent('List dealer codes recorded for Stone Light Networks.'))
    assert '74050' in result['response']
    assert 'Source: Recorded dealer records.' in result['response']
    assert 'NGN' not in result['response']
    assert '806' not in result['response']
    assert result['tools_called'] == ['get_dealer_codes']


def test_individual_financial_ratio_does_not_expand_into_full_report(monkeypatch):
    install_plan(monkeypatch, {
        'kind': 'measure', 'measures': ['financial_kpis'], 'kpi_ids': ['current_ratio'],
        'dealer_id': '74050', 'periods': ['202603'],
    })
    result = asyncio.run(agent.run_agent('Show only the current ratio for dealer 74050 in March.'))
    rows = result['raw_data']['measure_evidence']['measures'][0]['periods'][0]['rows']
    assert [row['dimension'] for row in rows] == ['Current ratio']
    assert 'synthetic' not in result['response'].lower()
    assert 'profit margin' not in result['response'].lower()
    assert 'NGN' not in result['response']


def test_sales_revenue_reads_income_statement_line_and_names_missing_statement(monkeypatch):
    install_plan(monkeypatch, {
        'kind': 'measure', 'measures': ['financial_statements'], 'line_ids': ['sales_revenue'],
        'dealer_id': '296065', 'periods': ['202606'],
    })
    result = asyncio.run(agent.run_agent('I mean the sales revenue for June 2026'))
    assert 'No financial statement on record for account 296065' in result['response']
    assert 'activations or commission' in result['response']
    assert 'NGN' not in result['response']


def test_scope_contract_maps_sales_revenue_to_the_statement_line():
    description = agent.SCOPE_TOOL['description']
    assert '"Sales revenue"' in description
    assert "line_ids ['sales_revenue']" in description
    assert 'never customer sales' not in description


PRIORITY_FINDINGS = [
    {'module': 'payment', 'severity': 'HIGH', 'type': 'COMMISSION_DISPUTE',
     'description': 'NGN 594,652.08 outstanding · disputed'},
    {'module': 'inventory', 'severity': 'MEDIUM', 'type': 'INVENTORY_MISMATCH',
     'description': 'product 1299801: 42 activations vs 20 purchased, 110.0% excess'},
    {'module': 'commission', 'severity': 'MEDIUM', 'type': 'ZERO_COMMISSION_ACTIVATION',
     'description': '50 of 495 activations recorded zero commission'},
    {'module': 'activation', 'severity': 'LOW', 'type': 'UNUSUAL_VOLUME',
     'description': '495 activations, 89.90% qualified'},
]


def fake_priority_evidence(period, dealer_id):
    """CONTRACT-shaped stand-in for backend.assurance.overview.investigation_priority_evidence."""
    base = {'period': period, 'source': 'Investigation queue', 'tool': 'investigation_queue',
            'total': None, 'truncated': False}
    if dealer_id is None or period != '202606':
        return {**base, 'status': 'unavailable', 'total_rows': 0, 'rows': [], 'priority': None,
                'note': 'The investigation queue is unavailable for this month.'}
    if dealer_id != '296065':
        return {**base, 'status': 'available', 'total_rows': 0, 'rows': [], 'note': '', 'priority': {
            'in_queue': False, 'severity': None, 'rank': None, 'queue_size': 922,
            'lead_module': None, 'lead_type': None, 'findings': [], 'finding_count': 0,
            'commission': None, 'commission_module_status': 'FLAG', 'unchecked_modules': [],
            'payment_status': None, 'amount_outstanding': None}}
    rows = [{'dealer_id': '296065', 'dealer_name': 'River Isle Ventures',
             'dimension': f"{f['module'].capitalize()} · {f['type']}",
             'value': f"{f['severity']}: {f['description']}"} for f in PRIORITY_FINDINGS]
    return {**base, 'status': 'available', 'total_rows': len(rows), 'rows': rows, 'note': '', 'priority': {
        'in_queue': True, 'severity': 'HIGH', 'rank': 1, 'queue_size': 922,
        'lead_module': 'payment', 'lead_type': 'COMMISSION_DISPUTE',
        'findings': [dict(f) for f in PRIORITY_FINDINGS], 'finding_count': 4,
        'commission': {k: PRIORITY_FINDINGS[2][k] for k in ('severity', 'type', 'description')},
        'commission_module_status': 'FLAG', 'unchecked_modules': [],
        'payment_status': 'DISPUTED', 'amount_outstanding': 594652.08}}


def install_priority(monkeypatch):
    import backend.assurance.overview as overview
    calls = []
    def fake(period, dealer_id):
        calls.append((period, dealer_id))
        return fake_priority_evidence(period, dealer_id)
    monkeypatch.setattr(overview, 'investigation_priority_evidence', fake, raising=False)
    return calls


def test_priority_question_answers_from_the_investigation_queue(monkeypatch):
    calls = install_priority(monkeypatch)
    install_plan(monkeypatch, {'kind': 'measure', 'measures': ['investigation_priority'],
                               'periods': ['202606'], 'dealer_id': '296065'})
    result = asyncio.run(agent.run_agent('is this dealer a high priority for investigation on commission'))
    response = result['response']
    assert calls == [('202606', '296065')]
    assert response.startswith('Investigation priority for dealer 296065, June 2026: HIGH — rank 1 of 922')
    assert 'Commission-module priority: MEDIUM' in response
    assert 'knowledge base defines no' not in response
    assert '999,999,999' not in response
    assert result['tools_called'] == ['investigation_queue']


def test_executor_skips_measure_collection_for_priority_only(monkeypatch):
    from backend.agent import tool_executor
    from backend.db import measure_evidence
    install_priority(monkeypatch)
    monkeypatch.setattr(measure_evidence, 'collect_measure_evidence',
                        lambda request: pytest.fail('no other measures were requested'))
    evidence = tool_executor.execute_measure_request({
        'measures': ['investigation_priority'], 'periods': ['202606'], 'dealer_id': '777'})
    assert evidence['measures'][0]['periods'][0]['priority']['in_queue'] is False


def test_scope_contract_routes_priority_questions_to_the_queue_measure():
    description = agent.SCOPE_TOOL['description']
    assert "['investigation_priority']" in description
    assert 'criterion' not in description
    assert 'no documented rule' not in description
    assert 'investigation_priority' in json.dumps(agent.SCOPE_TOOL['input_schema'])


@pytest.mark.parametrize('plan', [
    {'kind': 'measure', 'measures': ['activation_count'], 'periods': ['202606'],
     'criterion': 'investigation_priority'},
    {'kind': 'clarification', 'clarification': 'request', 'criterion': 'investigation_priority'},
    {'kind': 'measure', 'measures': ['investigation_priority'], 'periods': ['202606']},
    {'kind': 'measure', 'measures': ['investigation_priority'], 'periods': ['202606'],
     'dealer_id': '296065', 'operation': 'compare'},
    # One Overview run per answer: the queue measure stands alone for one month.
    {'kind': 'measure', 'measures': ['activation_count', 'investigation_priority'],
     'periods': ['202606'], 'dealer_id': '296065'},
    {'kind': 'measure', 'measures': ['investigation_priority'], 'periods': ['202605', '202606'],
     'dealer_id': '296065'},
])
def test_priority_scope_rejects_removed_criterion_and_unscoped_requests(monkeypatch, plan):
    install_priority(monkeypatch)
    install_plan(monkeypatch, plan)
    result = asyncio.run(agent.run_agent('Is this dealer a priority?'))
    assert result['response'] == agent.FALLBACK_RESPONSE


def test_priority_scope_validates_alone_and_leaves_other_combos_intact():
    alone = agent.MeasureScope.model_validate({'kind': 'measure', 'measures': ['investigation_priority'],
                                               'periods': ['202606'], 'dealer_id': '296065'})
    assert alone.measures == ['investigation_priority'] and alone.operation == 'total'
    other = agent.MeasureScope.model_validate({'kind': 'measure', 'periods': ['202605', '202606'],
        'measures': ['zero_commission_count', 'activation_commission'], 'operation': 'compare'})
    assert other.dealer_id is None


def test_standalone_measures_are_registered_at_every_seam():
    from typing import get_args
    from backend.agent import measure_response, tool_executor
    from backend.agent.measure_scope import STANDALONE_MEASURES, Measure
    assert STANDALONE_MEASURES <= set(get_args(Measure))
    assert set(tool_executor._STANDALONE_EVIDENCE) == STANDALONE_MEASURES
    assert set(measure_response._STANDALONE) == STANDALONE_MEASURES
    payloads = [payload for payload, _, _ in measure_response._STANDALONE.values()]
    assert len(payloads) == len(set(payloads))


def test_affiliation_scope_accepts_one_anchor_and_one_month():
    from backend.agent.measure_scope import MeasureScope
    by_code = MeasureScope.model_validate(
        {'kind': 'affiliation', 'dealer_id': '74050', 'periods': ['202606']})
    assert by_code.kind == 'affiliation' and by_code.dealer_id == '74050'
    by_name = MeasureScope.model_validate(
        {'kind': 'affiliation', 'dealer_name': 'Topaz Bridge Trading', 'periods': ['202606']})
    assert by_name.dealer_name == 'Topaz Bridge Trading' and by_name.dealer_id is None


@pytest.mark.parametrize('changes', [
    {},  # no anchor
    {'dealer_id': '74050', 'dealer_name': 'Topaz Bridge Trading'},  # both anchors
    {'dealer_id': '74050', 'periods': ['202605', '202606']},  # two months
    {'dealer_id': '74050', 'periods': []},  # no month
    {'dealer_id': '74050', 'measures': ['activation_commission']},  # measures forbidden
    {'dealer_id': '74050', 'clarification': 'dealer'},  # clarification forbidden
    {'dealer_id': '74050', 'operation': 'breakdown'},  # must be total
    {'dealer_id': '74050', 'filter': 'unpaid'},  # must be all
    {'dealer_id': '74050', 'limit': 5},  # limit forbidden
    {'dealer_id': '74050', 'knowledge_quote': 'x'},  # knowledge forbidden
])
def test_affiliation_scope_rejects_invalid_shapes(changes):
    from backend.agent.measure_scope import MeasureScope
    with pytest.raises(ValueError):
        MeasureScope.model_validate({'kind': 'affiliation', 'periods': ['202606'], **changes})


def test_affiliation_code_anchor_runs_end_to_end_without_leaking_draft(monkeypatch):
    # Anchor on an active code; the collector groups sibling codes by recorded name.
    install_plan(monkeypatch, {'kind': 'affiliation', 'dealer_id': '19580', 'periods': ['202606']})
    result = asyncio.run(agent.run_agent('How many other dealer codes are under this dealer, '
                                         'and what is their total commission?'))
    response = result['response']
    assert 'Topaz Bridge Trading' in response
    assert '9 other dealer codes' in response and '202606' in response
    assert 'NGN 790,062.67' in response and 'indicative' in response.lower()
    # The anchor code appears once (headline), never re-listed as its own sibling.
    assert response.split('### Verification evidence')[0].count('19580') == 1
    assert '19577' in response  # a sibling code is listed
    assert result['tools_called'] == ['get_dealer_codes', 'get_dealer_summary']
    assert '999,999,999' not in response  # model draft must not leak
    assert 'sample' not in response.lower()
    assert result['raw_data']['affiliation']['anchor_type'] == 'code'


def test_affiliation_name_anchor_counts_every_code(monkeypatch):
    install_plan(monkeypatch, {'kind': 'affiliation', 'dealer_name': 'Topaz Bridge Trading',
                               'periods': ['202606']})
    result = asyncio.run(agent.run_agent('How many dealer codes are addressed to Topaz Bridge '
                                         'Trading and what do they earn together?'))
    response = result['response']
    assert '"Topaz Bridge Trading"' in response
    assert '10 dealer codes' in response
    assert 'NGN 938,254.18' in response and 'indicative' in response.lower()
    assert '999,999,999' not in response
    assert result['raw_data']['affiliation']['anchor_type'] == 'name'


def test_explicit_partner_total_from_selected_account_includes_selected_code(monkeypatch):
    create = install_plan(monkeypatch, {'kind': 'affiliation', 'dealer_name': 'Topaz Bridge Trading',
                                       'periods': ['202606']})
    question = 'Give the partner total activation commission across all associated codes, including this account.'
    context = ('Reporting period 202606. Comparison period 202605. '
               'Selected account 19580 (Topaz Bridge Trading) is the default scope. '
               'Broaden only on an explicit request; recorded-name associations are unverified.')
    result = asyncio.run(agent.run_agent(question, reporting_period='202606',
                                        investigation_context=context))
    sent = create.call_args_list[0].kwargs
    assert json.loads(sent['messages'][-1]['content']) == {
        'question': question, 'reporting_period': '202606', 'investigation_context': context}
    # Inspect the public provider contract as well as the evidence-bound result:
    # a mocked interpretation alone cannot prove the provider received the rule.
    assert 'including the selected account' in sent['tools'][0]['description']
    assert 'dealer_name from the active context' in sent['tools'][0]['description']
    response = result['response']
    assert 'NGN 938,254.18' in response and '| 19580 |' in response
    assert '10 dealer codes' in response
    assert 'not a verified' in response
    assert result['tools_called'] == ['get_dealer_codes', 'get_dealer_summary']
