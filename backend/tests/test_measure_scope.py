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
    create = AsyncMock(return_value=response)
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
    assert 'sample' in result['response'].lower()
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
    message = json.loads(create.call_args.kwargs['messages'][-1]['content'])
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
    assert create.call_args.kwargs['messages'][:-1] == history
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
    assert 'synthetic' in result['response'].lower()
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
    assert 'sample' in result['response'].lower()
    assert 'NGN' not in result['response']
    assert '806' not in result['response']
    assert result['tools_called'] == ['get_dealer_codes']


def test_individual_financial_ratio_does_not_expand_into_full_report(monkeypatch):
    install_plan(monkeypatch, {
        'kind': 'measure', 'measures': ['financial_kpis'], 'kpi_ids': ['current_ratio'],
        'dealer_id': '74050', 'periods': ['202603'],
    })
    result = asyncio.run(agent.run_agent('Show only the synthetic current ratio for dealer 74050 in March.'))
    rows = result['raw_data']['measure_evidence']['measures'][0]['periods'][0]['rows']
    assert [row['dimension'] for row in rows] == ['Current ratio']
    assert 'Synthetic' in result['response']
    assert 'profit margin' not in result['response'].lower()
    assert 'NGN' not in result['response']
