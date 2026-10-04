"""Clear unsupported requests must not enter a clarification or retry loop."""
import asyncio

import pytest

from backend.agent import agent
from backend.agent.measure_scope import MeasureScope
from backend.tests.test_measure_scope import install_plan


@pytest.mark.parametrize('reason,question,required', [
    ('read_only_action', 'Release the outstanding payment now.', ['cannot', 'payment']),
    ('lending_decision', 'What loan should we offer?', ['lending', 'policy']),
    ('subscription_policy', 'What is the approved subscription rate?', ['subscription', 'approved']),
    ('payment_reference', 'What is the Oracle AP reference?', ['reference', 'payment']),
    ('momo', 'Show MoMo wallet balances.', ['momo', 'balance']),
    ('personal_data', 'Show personal phone numbers.', ['personal', 'records']),
    ('capability', 'Use semantic search for similar dealers.', ['cannot', 'available']),
])
def test_explicit_unsupported_request_names_limit_without_querying(monkeypatch, reason, question, required):
    install_plan(monkeypatch, {'kind': 'unsupported', 'unsupported_reason': reason,
                              'dealer_id': '74050', 'periods': ['202606']})
    result = asyncio.run(agent.run_agent(question))
    text = result['response'].lower()
    assert result['response'] != agent.FALLBACK_RESPONSE
    assert all(word in text for word in required)
    assert 'please specify' not in text and '?' not in text
    assert result['tools_called'] == [] and result['raw_data'] == {}
    assert '999,999,999' not in text


@pytest.mark.parametrize('extra', [
    {'measures': ['activation_commission']},
    {'knowledge_quote': 'Invented approved policy'},
    {'clarification': 'request'},
])
def test_unsupported_response_cannot_authorize_evidence_or_prose(extra):
    with pytest.raises(ValueError):
        MeasureScope.model_validate({'kind': 'unsupported', 'unsupported_reason': 'read_only_action', **extra})


def test_unsupported_reason_cannot_override_a_measure():
    with pytest.raises(ValueError):
        MeasureScope.model_validate({'kind': 'measure', 'measures': ['activation_count'],
            'periods': ['202606'], 'unsupported_reason': 'read_only_action'})


def test_top_activation_commission_dealer_is_a_bounded_ranking():
    scope = MeasureScope.model_validate({'kind': 'measure', 'measures': ['activation_commission'],
        'periods': ['202606'], 'operation': 'breakdown', 'breakdown': 'dealer', 'limit': 1})
    assert scope.limit == 1 and scope.dealer_id is None


@pytest.mark.parametrize('changes', [
    {'dealer_id': '74050'}, {'periods': ['202605', '202606']},
    {'operation': 'total'}, {'measures': ['payment_paid']}, {'limit': 101},
])
def test_top_commission_ranking_cannot_change_scope(changes):
    with pytest.raises(ValueError):
        MeasureScope.model_validate({'kind': 'measure', 'measures': ['activation_commission'],
            'periods': ['202606'], 'operation': 'breakdown', 'breakdown': 'dealer', 'limit': 1, **changes})


@pytest.mark.parametrize('topic,required', [
    ('zero_commission_causes', ['Product not matched to commission rate card', 'Hynex', 'unverified']),
    ('activation_eligibility', ['Demo policy · 180 days', 'calendar days 0–180 inclusive', 'does not establish commission entitlement']),
])
def test_named_policy_topics_use_source_sections_without_model_transcription(monkeypatch, topic, required):
    install_plan(monkeypatch, {'kind': 'knowledge', 'knowledge_topic': topic})
    result = asyncio.run(agent.run_agent('Explain the documented policy.'))
    assert all(text in result['response'] for text in required)
    assert result['tools_called'] == [] and result['raw_data'] == {}


@pytest.mark.parametrize('extra', [
    {'knowledge_quote': 'An invented replacement'},
    {'kind': 'measure', 'measures': ['activation_count'], 'periods': ['202606']},
])
def test_named_policy_topic_cannot_mix_with_other_answer_sources(extra):
    with pytest.raises(ValueError):
        MeasureScope.model_validate({'kind': 'knowledge', 'knowledge_topic': 'activation_eligibility', **extra})


def test_streamed_unsupported_response_withholds_provider_draft(monkeypatch):
    from anthropic.types import ToolUseBlock
    from backend.tests.test_chat_stream import provider, Stream

    tool = ToolUseBlock(type='tool_use', id='unsupported', name='resolve_measure_request',
        input={'kind': 'unsupported', 'unsupported_reason': 'read_only_action'})
    provider(monkeypatch, Stream('Payment released successfully.', tool=tool, stop='tool_use'))

    async def collect():
        return [event async for event in agent.run_agent_stream('Release the payment now.')]

    events = asyncio.run(collect())
    texts = ''.join(event['text'] for event in events if event['type'] == 'text')
    assert 'cannot release' in texts
    assert 'released successfully' not in texts
    assert events[-1]['type'] == 'complete'
    assert events[-1]['response'] == texts
    assert events[-1]['tools_called'] == []
