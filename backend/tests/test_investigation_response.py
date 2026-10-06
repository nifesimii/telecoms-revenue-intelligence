import asyncio
from copy import deepcopy
import json

import pandas as pd
import pytest
from backend import config
from backend.agent.agent import run_agent, run_agent_stream
from backend.agent.measure_scope import MeasureScope
from backend.agent.tool_executor import execute_measure_request
from backend.agent.measure_response import render_measure_response


def request(family='zero_commission', presentation='explanation', **kwargs):
    return MeasureScope(kind='measure', measures=['dealer_investigation'],
        dealer_id='296065', periods=kwargs.pop('periods', ['202606']), investigation_family=family,
        presentation=presentation, **kwargs).model_dump()


@pytest.mark.parametrize('presentation', ['explanation', 'records', 'actions', 'dealer_draft'])
def test_zero_investigation_is_useful_without_repeated_demo_disclaimers(presentation):
    scope = request(presentation=presentation)
    evidence = execute_measure_request(scope)
    text = render_measure_response(scope, evidence)
    assert '50' in text
    assert 'Product not matched to commission rate card' in text
    assert 'USP' not in text
    assert 'unverified' not in text.lower()
    assert not any(word in text.lower() for word in ('synthetic', 'fake', 'demo policy'))
    assert '296065' in text and '202606' in text
    if presentation == 'records':
        assert 'IMEI' in text and 'CALC-' in text.replace('\\', '')
    elif presentation == 'actions':
        assert 'Revenue Assurance' in text
    elif presentation == 'dealer_draft':
        assert 'Dear River Isle Ventures' in text


def test_investigation_rejects_unscoped_or_mixed_contract():
    with pytest.raises(ValueError):
        MeasureScope(kind='measure', measures=['dealer_investigation'], periods=['202606'])
    with pytest.raises(ValueError):
        MeasureScope(kind='measure', measures=['activation_count'], periods=['202606'],
                     investigation_family='zero_commission')


@pytest.fixture(autouse=True)
def sample_investigations(monkeypatch):
    monkeypatch.setattr(config, 'USE_SAMPLE_DATA', True)
    monkeypatch.setattr(config, 'PAYMENT_SOURCE', 'simulation')


@pytest.mark.parametrize('family,periods,question,headline', [
    ('zero_commission', ['202606'], 'Why are these commissions zero?', '50 zero-commission activations'),
    ('commission_variance', ['202605', '202606'], 'Why did commission change?', 'NGN 39,873.42'),
    ('payment', ['202606'], 'Why has this dealer not been paid in full?', 'NGN 594,652.08'),
])
def test_ordinary_chat_exposes_investigation_for_each_finance_question(monkeypatch, family, periods, question, headline):
    from backend.tests.test_agent import install_scope_provider

    scope = request(family=family, periods=periods)
    install_scope_provider(monkeypatch, scope)
    answer = asyncio.run(run_agent(question, reporting_period='202606',
                                   investigation_context='River Isle Ventures, account 296065'))

    assert headline in answer['response']
    investigation = answer['raw_data']['measure_evidence']['investigation']
    assert investigation['dealer_id'] == '296065' and investigation['periods'] == periods
    assert investigation['family'] == family
    assert answer['tools_called']


@pytest.mark.parametrize('family,periods,headline', [
    ('zero_commission', ['202606'], '50 zero-commission activations'),
    ('commission_variance', ['202605', '202606'], 'NGN 39,873.42'),
    ('payment', ['202606'], 'NGN 594,652.08'),
])
def test_stream_publishes_only_completed_investigation(monkeypatch, family, periods, headline):
    from backend.tests.test_chat_stream import Stream, provider, scope_tool

    scope = request(family=family, periods=periods)
    provider(monkeypatch, Stream('Invented adjustment: NGN 999,999,999.00',
                                tool=scope_tool(**scope), stop='tool_use'))

    async def consume():
        return [event async for event in run_agent_stream('Explain this dealer', reporting_period='202606')]

    events = asyncio.run(consume())
    assert events[-1]['type'] == 'complete'
    answer = events[-1]
    assert headline in answer['response']
    assert '999,999,999' not in answer['response']
    assert [event['text'] for event in events if event['type'] == 'text'] == [answer['response']]
    assert answer['raw_data']['measure_evidence']['investigation']['family'] == family


def test_record_followup_preserves_context_and_gets_the_next_evidence_page(monkeypatch):
    from backend.tests.test_agent import install_scope_provider

    history = [
        {'role': 'user', 'content': 'Show the first 20 zero-commission records for 296065 in June 2026.'},
        {'role': 'assistant', 'content': 'Showing records 1–20 of 50.'},
    ]
    original = deepcopy(history)
    scope = request(presentation='records', record_offset=20, limit=20)
    calls, _ = install_scope_provider(monkeypatch, scope)
    answer = asyncio.run(run_agent('Next page please', history, reporting_period='202606'))

    result = answer['raw_data']['measure_evidence']['investigation']
    first = execute_measure_request(request(presentation='records', limit=20))['investigation']
    assert result['pagination']['offset'] == 20
    assert result['total_records'] == 50 and len(result['records']) == 20
    assert not {r['imei'] for r in result['records']} & {r['imei'] for r in first['records']}
    assert 'Showing records 21–40 of 50.' in answer['response']
    assert answer['response'].count('| IMEI |') == 1
    assert all(answer['response'].count(record['imei']) == 1 for record in result['records'])
    assert not any(record['imei'] in answer['response'] for record in first['records'])
    assert calls[0]['messages'][:-1] == original and history == original
    assert json.loads(calls[0]['messages'][-1]['content'])['question'] == 'Next page please'


@pytest.mark.parametrize('presentation,question,expected', [
    ('actions', 'What should we do next?', 'Revenue Assurance:'),
    ('dealer_draft', 'Draft an explanation for the dealer', 'Dear River Isle Ventures'),
])
def test_action_and_draft_followups_keep_the_investigated_account(monkeypatch, presentation, question, expected):
    from backend.tests.test_agent import install_scope_provider

    history = [{'role': 'user', 'content': 'Explain the 50 zero-commission records for account 296065 in June.'},
               {'role': 'assistant', 'content': 'There are 50 zero-commission activations in 202606.'}]
    install_scope_provider(monkeypatch, request(presentation=presentation))
    answer = asyncio.run(run_agent(question, history, reporting_period='202606'))
    assert expected in answer['response']
    assert '296065' in answer['response'] and '202606' in answer['response']
    if presentation == 'dealer_draft':
        assert 'Draft for Finance review' in answer['response']
        assert 'does not approve an adjustment or promise payment' in answer['response']


def test_apdp_payment_amounts_cannot_inherit_sample_workflow_reasons(monkeypatch):
    from backend.audit import payment_data
    from backend.db import queries

    monkeypatch.setattr(config, 'PAYMENT_SOURCE', 'apdp')
    monkeypatch.setattr(payment_data, 'payment_lookup', lambda period, source: pd.DataFrame([{
        'dealer_id': '296065', 'dealer_name': 'River Isle Ventures',
        'expected_commission_ngn': 100, 'total_settled_ngn': 30,
        'statement_count': 1, 'settlement_count': 1, 'reconciliation_status': 'UNDERPAID',
    }]))

    def forbidden_support(*args, **kwargs):
        pytest.fail('APDP investigations must not read sample settlement workflow evidence')

    monkeypatch.setattr(queries, 'investigation_support', forbidden_support)
    scope = request(family='payment')
    result = execute_measure_request(scope)
    text = render_measure_response(scope, result)
    assert 'NGN 70.00' in text
    assert result['investigation']['payment']['process'] is None
    assert 'no matching workflow evidence' in text
    assert 'dispute review' not in text and 'FBB-202606' not in text


def test_stale_payment_workflow_does_not_explain_a_changed_balance(monkeypatch):
    from backend.db import queries

    original = queries.investigation_support

    def stale_support(period, dealer, source):
        records = original(period, dealer, source).copy()
        if source == 'settlement':
            records['recorded_paid'] = '0.01'
        return records

    monkeypatch.setattr(queries, 'investigation_support', stale_support)
    scope = request(family='payment')
    result = execute_measure_request(scope)
    text = render_measure_response(scope, result)
    assert 'NGN 594,652.08' in text
    assert result['investigation']['payment']['process'] is None
    assert 'no matching workflow evidence' in text
    assert 'under dispute review' not in text


def test_incomplete_apdp_coverage_does_not_establish_outstanding(monkeypatch):
    import pandas as pd
    from backend import config
    from backend.audit import payment_data
    from backend.db.investigation_evidence import investigate
    from backend.agent.investigation_response import render_investigation
    monkeypatch.setattr(config, 'PAYMENT_SOURCE', 'apdp')
    monkeypatch.setattr(payment_data, 'payment_lookup', lambda *a: pd.DataFrame([dict(
        dealer_id='296065', expected_commission_ngn=1000, total_settled_ngn=0,
        statement_count=1, settlement_count=0, reconciliation_status='STATEMENT_WITHOUT_PAYMENT')]))
    text = render_investigation(investigate('296065', ['202606'], 'payment'))
    assert 'outstanding**' not in text and 'balance is established' not in text
    assert 'settlement evidence unavailable' in text.lower()


def test_contradictory_settlement_process_is_not_a_verified_reason(monkeypatch):
    from backend.db import queries
    from backend.db.investigation_evidence import investigate
    original = queries.investigation_support
    def contradictory(*a, **kw):
        frame = original(*a, **kw)
        frame['process_state'] = 'SETTLED'
        return frame
    monkeypatch.setattr(queries, 'investigation_support', contradictory)
    assert investigate('296065', ['202606'], 'payment')['payment']['process'] is None


def test_legacy_assistant_history_is_presented_without_rewriting_user_or_original(monkeypatch):
    from backend.tests.test_agent import install_scope_provider
    history = [
        {'role': 'user', 'content': 'Explain USP snapshot miss and `usp_dimension`.'},
        {'role': 'assistant', 'content': '48 USP snapshot misses. Source quote: "First line\nUSP snapshot miss". Code: ``first ` USP snapshot miss``.'},
    ]
    original = deepcopy(history)
    calls, _ = install_scope_provider(monkeypatch, request())
    asyncio.run(run_agent('Explain that again', history, reporting_period='202606'))
    assert calls[0]['messages'][0] == original[0]
    assert calls[0]['messages'][1]['content'] == (
        '48 Product not matched to commission rate card. Source quote: "First line\nUSP snapshot miss". Code: ``first ` USP snapshot miss``.')
    assert history == original


def test_mixed_supported_causes_need_additional_evidence_only_for_unresolved_records():
    scope = {**request(), 'dealer_id': '74050'}
    evidence = execute_measure_request(scope)
    investigation = evidence['investigation']
    assert investigation['total_records'] == 104
    assert investigation['unresolved_count'] == 1
    assert {cause['cause']: cause['count'] for cause in investigation['causes']} == {
        'USP_SNAPSHOT_MISS': 23, 'OUTSIDE_6_MONTH_WINDOW': 50,
        'NULL_PROFILE_CLASS': 3, 'HYNEX_DENOMINATION_SPLIT': 27,
    }
    text = render_measure_response(scope, evidence)
    assert 'Additional calculation evidence is needed for the 1 unresolved record.' in text
    assert 'The other 103 records have supported cause attributions.' in text
    assert 'eligibility alone does not establish entitlement' in text.lower()
    assert 'Inside-window records still require supporting calculation evidence' not in text
