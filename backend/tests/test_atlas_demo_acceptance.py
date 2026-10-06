"""Demo shortcut contract matrix: fake interpretation, real sample evidence.

This does not test model understanding of these questions. UI transport and a
small separately recorded live rehearsal cover different acceptance seams.
"""
import asyncio
import json

import pytest

from backend import config
from backend.agent import agent
from backend.tests.test_agent import install_scope_provider


def measure(*names, **options):
    return {'kind': 'measure', 'measures': list(names), 'periods': ['202606'], **options}


SUBSCRIPTION = 'Summarise subscription revenue, recorded commission, settlement and outstanding amounts. State any missing evidence.'
ZERO = 'Investigate zero-commission records using only documented KB causes. State what remains unverified.'
MATRIX = [
    ('activation-all-comparison', 'Explain the commission change by denomination between these periods.', {'kind': 'clarification', 'clarification': 'dealer'}, False),
    ('activation-selected-comparison', 'Explain the commission change by denomination between these periods.', measure('commission_variance', periods=['202605', '202606'], operation='compare', dealer_id='296065'), True),
    ('activation-all-breakdown', 'Explain the recorded commission breakdown.', measure('activation_commission', operation='breakdown', breakdown='dealer', limit=20), False),
    ('activation-selected-breakdown', 'Explain the recorded commission breakdown.', measure('activation_commission', operation='breakdown', breakdown='product', dealer_id='296065'), True),
    ('activation-all-zero', 'List dealer accounts with zero-commission records, ranked by record count. Let me select an account to investigate.', measure('portfolio_discovery'), False),
    ('activation-all-original-typed', ZERO, measure('portfolio_discovery'), False),
    ('activation-selected-zero', ZERO, measure('dealer_investigation', investigation_family='zero_commission', dealer_id='296065'), True),
    ('subscription-all', SUBSCRIPTION, measure('subscription_revenue', 'subscription_commission', 'subscription_settled', 'subscription_outstanding'), False),
    ('subscription-selected', SUBSCRIPTION, measure('subscription_revenue', 'subscription_commission', 'subscription_settled', 'subscription_outstanding', dealer_id='296065'), True),
    ('payment-selected', 'Explain this account’s recorded commission, paid amount and outstanding balance. State what remains unverified.', measure('dealer_statement', dealer_id='296065'), True),
    ('financial-all-profit-cash', 'Compare profitability and operating cash flow across the 20 dealers.', measure('financial_kpis', kpi_ids=['net_margin', 'operating_cash_flow'], operation='breakdown'), False),
    ('financial-all-missing', 'Which dealers have missing repayment evidence or ratios that are not meaningful?', measure('financial_kpis', operation='breakdown'), False),
    ('financial-selected-statements', 'Explain this dealer’s income statement, balance sheet and cash flow.', measure('financial_statements', dealer_id='74050'), True),
    ('financial-selected-profit-cash', 'Why does net profit differ from operating cash flow?', measure('financial_statements', line_ids=['net_profit', 'operating_cash_flow'], dealer_id='74050'), True),
    ('financial-selected-change', 'What changed since the prior month, and which indicators need more evidence?', measure('financial_kpis', periods=['202605', '202606'], operation='compare', dealer_id='74050'), True),
    # Exact product/finding interpretation is not represented by a guessed broad
    # measure: safe clarification is an acceptable terminal contract for ambiguity.
    ('inventory-exact', 'Explain this dealer-product Inventory comparison and identify the evidence still needed.', {'kind': 'clarification', 'clarification': 'request'}, True),
    ('finding-exact-typed', 'Explain the selected finding and identify the evidence still needed.', {'kind': 'clarification', 'clarification': 'request'}, True),
]


@pytest.fixture(autouse=True)
def sample_only(monkeypatch):
    monkeypatch.setattr(config, 'USE_SAMPLE_DATA', True)
    monkeypatch.setattr(config, 'PAYMENT_SOURCE', 'simulated')
    # Saved audit provenance is optional and must not contact local Postgres.
    from backend.db import audit_store
    monkeypatch.setattr(audit_store, 'healthcheck', lambda: False)


@pytest.mark.parametrize('case,question,scope,selected', MATRIX, ids=[case[0] for case in MATRIX])
def test_shortcut_evidence_contract(monkeypatch, case, question, scope, selected):
    calls, closed = install_scope_provider(monkeypatch, scope,
        answer='The requested evidence is included below. Missing evidence remains unavailable.')
    context = ('Exact dealer account code ' + scope.get('dealer_id', '296065') + '.'
               if selected else 'Portfolio-level investigation.')
    result = asyncio.run(agent.run_agent(question, reporting_period='202606', investigation_context=context))
    assert result.get('error') is None, case
    assert result['response'] not in (agent.FALLBACK_RESPONSE, agent.NARRATIVE_FALLBACK), case
    assert closed == [True]
    assert len(calls) <= 2, 'No repair should be needed for a valid mocked contract'
    sent = json.loads(calls[0]['messages'][-1]['content'])
    assert sent == {'question': question, 'reporting_period': '202606', 'investigation_context': context}
    if scope['kind'] == 'clarification':
        assert not result['raw_data'] and not result['tools_called']
    else:
        if scope['measures'] == ['portfolio_discovery']:
            evidence = result['raw_data']['portfolio_discovery']
            assert evidence['period'] == '202606' and evidence['status'] == 'available'
            assert 0 < len(evidence['items']) <= 20 < evidence['total_count']
            return
        evidence = result['raw_data']['measure_evidence']
        assert evidence['requested_periods'] == scope['periods']
        assert evidence['dealer_id'] == scope.get('dealer_id')
        if scope['measures'] == ['dealer_investigation']:
            assert evidence['investigation']['family'] == scope['investigation_family']
            assert evidence['investigation']['dealer_id'] == scope['dealer_id']
            return
        assert [item['measure'] for item in evidence['measures']] == scope['measures']
        if scope['measures'] == ['commission_variance']:
            variance = evidence['measures'][0]['periods'][0]['variance']
            assert [variance['earlier'], variance['later']] == scope['periods']
        else:
            for item in evidence['measures']:
                assert [period['period'] for period in item['periods']] == scope['periods']


def test_scope_repair_and_narrative_repair_share_one_budget(monkeypatch):
    from types import SimpleNamespace
    from unittest.mock import AsyncMock
    from backend.tests.narrative_provider import final_response

    def scope_response(scope):
        return SimpleNamespace(content=[SimpleNamespace(type='tool_use', name='resolve_measure_request',
            id='scope', input=scope)], stop_reason='tool_use', usage=None)

    rounds = [scope_response(measure('invented_measure', dealer_id='74050')),
              scope_response(measure('activation_count', dealer_id='74050'))]
    calls = []
    async def create(**kwargs):
        calls.append(kwargs)
        if rounds:
            return rounds.pop(0)
        # A fabricated un-tokenized amount is rejected. The repair budget has
        # already been consumed by scope repair, so no fourth call is allowed.
        return final_response(kwargs, text='The recorded amount is NGN 999,999,999.99.')
    client = SimpleNamespace(messages=SimpleNamespace(create=create), close=AsyncMock())
    monkeypatch.setattr(agent, 'new_client', lambda key: client)
    result = asyncio.run(agent.run_agent('Count activations for dealer 74050 in June 2026.'))
    assert result['response'] == agent.NARRATIVE_FALLBACK
    assert len(calls) == 3
    assert result['raw_data']['measure_evidence']['dealer_id'] == '74050'
    client.close.assert_awaited_once()


def test_provider_retry_exhausts_scope_repair_budget(monkeypatch):
    import anthropic
    import httpx
    from types import SimpleNamespace
    from unittest.mock import AsyncMock

    failure = anthropic.RateLimitError('private provider payload', body=None,
        response=httpx.Response(429, request=httpx.Request('POST', 'https://api.anthropic.com/v1/messages'),
                                headers={'retry-after': '0'}))
    invalid = SimpleNamespace(content=[SimpleNamespace(type='tool_use', name='resolve_measure_request',
        id='scope', input=measure('invented_measure'))], stop_reason='tool_use', usage=None)
    create = AsyncMock(side_effect=[failure, invalid])
    client = SimpleNamespace(messages=SimpleNamespace(create=create), close=AsyncMock())
    monkeypatch.setattr(agent, 'new_client', lambda key: client)
    result = asyncio.run(agent.run_agent('Count activations.'))
    assert 'cannot resolve' in result['response']
    assert 'private provider payload' not in result['response']
    assert not result['raw_data'] and not result['tools_called']
    assert create.await_count == 2
    client.close.assert_awaited_once()


def test_deadline_during_scope_repair_is_terminal_and_closes_provider(monkeypatch):
    from backend.agent import inference
    from backend.tests.test_chat_stream import Stream, provider, scope_tool
    monkeypatch.setattr(inference, 'REQUEST_DEADLINE_SECONDS', .03)
    repair = Stream('', gate=asyncio.Event())
    fake = provider(monkeypatch,
        Stream('', tool=scope_tool(measures=['invented']), stop='tool_use'), repair)
    async def exercise():
        return [event async for event in agent.run_agent_stream('Explain this account')]
    events = asyncio.run(exercise())
    assert events[-1]['type'] == 'error'
    assert events[-1]['error'] == 'deadline_exceeded'
    assert not any(event['type'] in ('text', 'complete') for event in events)
    assert len(fake.calls) == 2
    assert repair.closed
    fake.close.assert_awaited_once()


def test_cancellation_during_scope_repair_stops_before_evidence(monkeypatch):
    from backend.tests.test_chat_stream import Stream, provider, scope_tool
    async def exercise():
        entered = asyncio.Event()
        class WaitingRepair(Stream):
            async def __aiter__(self):
                entered.set()
                async for event in super().__aiter__():
                    yield event
        repair = WaitingRepair('', gate=asyncio.Event())
        fake = provider(monkeypatch,
            Stream('', tool=scope_tool(measures=['invented']), stop='tool_use'), repair)
        stream = agent.run_agent_stream('Explain this account')
        assert (await anext(stream))['phase'] == 'thinking'
        pending = asyncio.create_task(anext(stream))
        await asyncio.wait_for(entered.wait(), 1)
        pending.cancel()
        with pytest.raises(asyncio.CancelledError):
            await pending
        await stream.aclose()
        assert len(fake.calls) == 2
        assert repair.closed
        fake.close.assert_awaited_once()
    asyncio.run(exercise())


def test_scope_recovery_logs_categories_without_model_payload(monkeypatch, caplog):
    import logging
    from backend.tests.test_chat_stream import Stream, provider, scope_tool
    secret = 'private-untrusted-contract-and-account-payload'
    provider(monkeypatch, *[Stream(secret, tool=scope_tool(measures=[secret]), stop='tool_use') for _ in range(2)])
    async def exercise():
        return [event async for event in agent.run_agent_stream(secret)]
    with caplog.at_level(logging.INFO, logger='backend.agent.inference'):
        events = asyncio.run(exercise())
    assert events[-1]['type'] == 'complete'
    logs = [json.loads(record.message) for record in caplog.records if record.name == 'backend.agent.inference']
    validation = [record for record in logs if record['event'] == 'scope_validation']
    assert [(record['stage'], record['reason'], record['repair_count']) for record in validation] == [
        ('scope', 'invalid_contract', 0), ('scope', 'invalid_contract', 1)]
    assert len({record['request_id'] for record in logs}) == 1
    assert all(record['request_id'] for record in logs)
    assert secret not in caplog.text
    assert secret not in json.dumps(events)
