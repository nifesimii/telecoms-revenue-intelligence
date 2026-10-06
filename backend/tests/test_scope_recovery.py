"""Scope recovery through real public chat, with only provider I/O replaced."""
import asyncio
from backend.agent import agent
from backend.tests.test_chat_stream import provider, Stream, scope_tool


def test_captured_portfolio_investigation_completes_without_composition(monkeypatch):
    fake = provider(monkeypatch, Stream('', tool=scope_tool(
        measures=['dealer_investigation'], dealer_id=None, periods=['202606'],
        investigation_family='zero_commission', presentation='explanation'), stop='tool_use'))
    async def exercise():
        return [event async for event in agent.run_agent_stream(
            'Investigate zero-commission records using only documented KB causes.',
            reporting_period='202606', investigation_context='Portfolio-level investigation. Activation commission.')]
    events = asyncio.run(exercise())
    assert events[-1]['type'] == 'complete'
    assert 'exact dealer account' in events[-1]['response']
    assert events[-1]['raw_data'] == {}
    assert events[-1]['tools_called'] == []
    assert len(fake.calls) == 1


def test_missing_dealer_clarifies_without_evidence_or_composition(monkeypatch):
    fake = provider(monkeypatch, Stream('', tool=scope_tool(
        measures=['dealer_investigation'], dealer_id=None,
        investigation_family='zero_commission'), stop='tool_use'))
    events = asyncio.run(_events())
    assert events[-1]['type'] == 'complete'
    assert 'exact dealer account' in events[-1]['response']
    assert events[-1]['raw_data'] == {}
    assert len(fake.calls) == 1


async def _events():
    return [event async for event in agent.run_agent_stream('Investigate this account')]


def test_missing_period_clarifies_without_second_provider_call(monkeypatch):
    fake = provider(monkeypatch, Stream('', tool=scope_tool(periods=[]), stop='tool_use'))
    result = asyncio.run(_events())[-1]
    assert result['type'] == 'complete'
    assert 'reporting month' in result['response']
    assert result['tools_called'] == []
    assert len(fake.calls) == 1


def test_malformed_scope_repairs_once_and_repeated_invalid_clarifies(monkeypatch):
    fake = provider(monkeypatch, *[Stream('', tool=scope_tool(measures=['invented']), stop='tool_use') for _ in range(2)])
    result = asyncio.run(_events())[-1]
    assert result['type'] == 'complete'
    assert 'cannot resolve' in result['response']
    assert result['tools_called'] == []
    assert len(fake.calls) == 2


def test_repaired_scope_is_validated_before_discovery(monkeypatch):
    fake = provider(monkeypatch,
        Stream('', tool=scope_tool(measures=['invented'], dealer_id=None), stop='tool_use'),
        Stream('', tool=scope_tool(measures=['portfolio_discovery'], dealer_id=None), stop='tool_use'))
    result = asyncio.run(_events())[-1]
    assert result['type'] == 'complete'
    assert result['raw_data']['portfolio_discovery']['status'] == 'available'
    assert len(fake.calls) == 2


def test_buffered_missing_scope_matches_stream_without_composition(monkeypatch):
    from types import SimpleNamespace
    from unittest.mock import AsyncMock
    block = scope_tool(periods=[])
    client = SimpleNamespace(messages=SimpleNamespace(create=AsyncMock(return_value=
        SimpleNamespace(content=[block], stop_reason='tool_use', usage=None))), close=AsyncMock())
    monkeypatch.setattr(agent, 'new_client', lambda key: client)
    result = asyncio.run(agent.run_agent('How many?'))
    assert 'reporting month' in result['response']
    assert result['tools_called'] == []
    assert client.messages.create.await_count == 1


def test_portfolio_context_never_broadens_omitted_named_account(monkeypatch):
    fake = provider(monkeypatch, Stream('', tool=scope_tool(
        measures=['dealer_investigation'], dealer_id=None,
        investigation_family='zero_commission'), stop='tool_use'))
    async def exercise():
        return [event async for event in agent.run_agent_stream(
            'Investigate zero commissions for River Isle.', reporting_period='202606',
            investigation_context='Portfolio-level investigation. Activation commission.')]
    result = asyncio.run(exercise())[-1]
    assert result['type'] == 'complete'
    assert 'exact dealer account' in result['response']
    assert result['raw_data'] == {} and result['tools_called'] == []
    assert len(fake.calls) == 1


import pytest

@pytest.mark.parametrize('repaired', [
    {'measures': ['portfolio_discovery'], 'dealer_id': None},
    {'dealer_id': '99999'},
    {'periods': ['202605']},
    {'dealer_id': None, 'dealer_name': 'Different dealer'},
])
def test_scope_repair_cannot_change_account_or_period(monkeypatch, repaired):
    fake = provider(monkeypatch,
        Stream('', tool=scope_tool(measures=['invented']), stop='tool_use'),
        Stream('', tool=scope_tool(**repaired), stop='tool_use'))
    async def exercise():
        return [event async for event in agent.run_agent_stream(
            'Investigate zero commissions for account 74050 only.',
            reporting_period='202603', investigation_context='Exact dealer account code 74050.')]
    result = asyncio.run(exercise())[-1]
    assert result['type'] == 'complete'
    assert result['tools_called'] == [] and result['raw_data'] == {}
    assert 'cannot resolve' in result['response']
    assert len(fake.calls) == 2


def test_scope_repair_without_original_bounds_cannot_authorize_reads(monkeypatch):
    fake = provider(monkeypatch,
        Stream('Malformed scope', stop='end_turn'),
        Stream('', tool=scope_tool(), stop='tool_use'))
    result = asyncio.run(_events())[-1]
    assert result['type'] == 'complete'
    assert result['tools_called'] == [] and result['raw_data'] == {}
    assert len(fake.calls) == 2


def test_scope_repair_preserves_named_account_boundary(monkeypatch):
    fake = provider(monkeypatch,
        Stream('', tool=scope_tool(measures=['invented'], dealer_id=None, dealer_name='River Isle'), stop='tool_use'),
        Stream('', tool=scope_tool(dealer_id='74050'), stop='tool_use'))
    result = asyncio.run(_events())[-1]
    assert result['type'] == 'complete'
    assert result['tools_called'] == [] and result['raw_data'] == {}
    assert len(fake.calls) == 2


def test_scope_repair_can_fix_measure_with_same_exact_account_and_period(monkeypatch):
    fake = provider(monkeypatch,
        Stream('', tool=scope_tool(measures=['invented']), stop='tool_use'),
        Stream('', tool=scope_tool(), stop='tool_use'))
    result = asyncio.run(_events())[-1]
    assert result['type'] == 'complete'
    assert result['tools_called'] == ['get_dealer_summary']
    assert result['raw_data']['measure_evidence']['dealer_id'] == '74050'
    assert result['raw_data']['measure_evidence']['requested_periods'] == ['202603']
    assert len(fake.calls) == 3


@pytest.mark.parametrize('original', [
    {'dealer_id': None}, {'periods': []}, {'periods': ['invalid']},
])
def test_scope_repair_cannot_invent_missing_account_or_period(monkeypatch, original):
    fake = provider(monkeypatch,
        Stream('', tool=scope_tool(measures=['invented'], **original), stop='tool_use'),
        Stream('', tool=scope_tool(), stop='tool_use'))
    result = asyncio.run(_events())[-1]
    assert result['type'] == 'complete'
    assert result['tools_called'] == [] and result['raw_data'] == {}
    assert len(fake.calls) == 2


def test_captured_discovery_zero_filter_completes_without_repair(monkeypatch):
    fake = provider(monkeypatch, Stream('', tool=scope_tool(
        measures=['portfolio_discovery'], dealer_id=None, periods=['202606'],
        filter='zero_commission'), stop='tool_use'))
    async def exercise():
        return [event async for event in agent.run_agent_stream(
            'Investigate zero-commission records using only documented KB causes. State what remains unverified.',
            reporting_period='202606', investigation_context='Portfolio-level investigation. Activation commission.')]
    result = asyncio.run(exercise())[-1]
    assert result['type'] == 'complete'
    assert result['raw_data']['portfolio_discovery']['status'] == 'available'
    assert result['raw_data']['portfolio_discovery']['period'] == '202606'
    assert result['tools_called'] == ['get_dealer_summary']
    assert len(fake.calls) == 1


@pytest.mark.parametrize('filter_value', ['disputed', 'unpaid', 'low_qualification'])
def test_discovery_rejects_unrelated_filters(monkeypatch, filter_value):
    fake = provider(monkeypatch, *[Stream('', tool=scope_tool(
        measures=['portfolio_discovery'], dealer_id=None, filter=filter_value), stop='tool_use') for _ in range(2)])
    result = asyncio.run(_events())[-1]
    assert result['type'] == 'complete'
    assert result['tools_called'] == [] and result['raw_data'] == {}
    assert len(fake.calls) == 2
