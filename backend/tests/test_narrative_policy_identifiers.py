"""Final generation can reference numeric KB identifiers without inventing facts."""
import asyncio
import json
from types import SimpleNamespace

from backend.agent.inference import InferenceRun
from backend.agent.narrative import compose_answer


def test_documented_denomination_identifier_has_a_grounded_reference():
    async def create(**kwargs):
        payload = json.loads(kwargs['messages'][-1]['content'])
        identifier = next(f for f in payload['facts'] if f['value'] == 'Hynex_1')
        text = 'The documented denomination split is Hynex / {{' + identifier['id'] + '}}.'
        return SimpleNamespace(stop_reason='tool_use', content=[SimpleNamespace(
            type='tool_use', name='compose_grounded_answer', input={'answer': text})])
    client = SimpleNamespace(messages=SimpleNamespace(create=create))
    result = asyncio.run(compose_answer(client, InferenceRun('test'), question='What causes are documented?',
        history=[], scope={'kind': 'knowledge', 'knowledge_topic': 'zero_commission_causes'}, evidence={},
        tools_called=[], validated_context='Known denomination split: Hynex / Hynex_1.',
        sample_mode=True, model='test'))
    assert result == 'The documented denomination split is Hynex / Hynex_1.'


def test_unsupported_question_identifiers_do_not_become_financial_evidence():
    async def create(**kwargs):
        payload = json.loads(kwargs['messages'][-1]['content'])
        assert payload['evidence'] == {}
        assert not any(str(f['value']) == '74050' for f in payload['facts'])
        return SimpleNamespace(stop_reason='tool_use', content=[SimpleNamespace(
            type='tool_use', name='compose_grounded_answer', input={
                'answer': 'I cannot perform semantic similarity searches across dealers.'})])
    client = SimpleNamespace(messages=SimpleNamespace(create=create))
    result = asyncio.run(compose_answer(client, InferenceRun('test'),
        question='Find dealers similar to 74050.', history=[],
        scope={'kind': 'unsupported', 'unsupported_reason': 'capability'}, evidence={}, tools_called=[],
        validated_context='Semantic similarity search is unavailable.', sample_mode=True, model='test'))
    assert result == 'I cannot perform semantic similarity searches across dealers.'


def test_exact_documented_product_and_scoped_period_literals_are_grounded():
    from backend.tests.test_narrative import compose, provider
    client, calls = provider(lambda payload, attempt: 'MIFI_1 records cover June 2026.')
    answer = compose(client, evidence={'product': 'MIFI_1'}, validated_context='')
    assert answer.startswith('MIFI_1 records cover June 2026.')
    assert len(calls) == 1


def test_ungrounded_product_or_month_literal_still_fails():
    import pytest
    from backend.tests.test_narrative import compose, provider
    from backend.agent.narrative import NarrativeGroundingError
    for text in ('MIFI_2 records cover June 2026.', 'MIFI_1 records cover July 2026.'):
        client, _ = provider(lambda payload, attempt: text)
        with pytest.raises(NarrativeGroundingError):
            compose(client, evidence={'product': 'MIFI_1'}, validated_context='')


def test_numeric_source_identifiers_cannot_become_literal_counts():
    import pytest
    from backend.tests.test_narrative import compose, provider
    from backend.agent.narrative import NarrativeGroundingError
    for value in ('1283280', '202606'):
        client, _ = provider(lambda payload, attempt: f'There were {value} activations.')
        with pytest.raises(NarrativeGroundingError):
            compose(client, evidence={'product_code': '1283280', 'total_records': 50}, validated_context='')
