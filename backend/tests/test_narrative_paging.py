from backend.tests.narrative_provider import draft_payload
"""Conversational record pages retain exact application-owned ranges and tables."""
import asyncio
import json
from types import SimpleNamespace

import pytest

from backend.agent.inference import InferenceRun
from backend.agent.answer_evidence import prepare_answer
from backend.agent.narrative import NarrativeGroundingError, compose_answer


def run(answer, *, presentation='records', unavailable=False):
    calls = []
    async def create(**kwargs):
        payload = json.loads(kwargs['messages'][-1]['content'])
        calls.append(payload)
        return SimpleNamespace(stop_reason='tool_use', content=[SimpleNamespace(
            type='tool_use', name='compose_grounded_answer', input=draft_payload(payload, answer(payload)))])
    client = SimpleNamespace(messages=SimpleNamespace(create=create))
    evidence = {'investigation': {'family': 'zero_commission', 'status': 'available',
        'total_records': 50, 'causes': [{'cause': 'USP_SNAPSHOT_MISS', 'count': 48}],
        'pagination': {'offset': 20, 'limit': 20, 'total': 50, 'has_more': True},
        'records': [{'imei': f'800000000000{i:03}', 'product_code': 'PRODUCT-A'} for i in range(20)]}}
    context = '50 zero-commission records.\n\n| IMEI | Product code |\n|---|---|\n' + '\n'.join(
        f'| {r["imei"]} | {r["product_code"]} |' for r in evidence['investigation']['records'])
    if unavailable:
        evidence['investigation'].update(status='unavailable', records=[], total_records=0,
            pagination={'offset': 0, 'limit': 20, 'total': 0, 'has_more': False})
        context = 'No activation records cover this month.'
    result = asyncio.run(compose_answer(client, InferenceRun('test'), question='Next page please', history=[],
        prepared=prepare_answer(scope={'kind': 'measure', 'presentation': presentation, 'periods': ['202606'], 'dealer_id': '296065'},
        evidence=evidence, tools_called=['get_zero_commission_records'], validated_context=context),
        sample_mode=True, model='test'))
    return result, calls


def test_second_record_page_has_exact_app_owned_range_and_one_complete_table():
    def answer(payload):
        assert payload['evidence'] == {'investigation': {'family': 'zero_commission', 'status': 'available'}}
        assert {fact['path'] for fact in payload['facts']} == {'scope.dealer_id', 'scope.periods[0]'}
        return 'Here are the next records.'
    result, _ = run(answer)
    assert 'Showing records 21–40 of 50.' in result
    assert result.count('| IMEI |') == 1
    assert result.count('| PRODUCT-A |') == 20


def test_provider_record_table_is_rejected_instead_of_duplicated():
    with pytest.raises(NarrativeGroundingError):
        run(lambda payload: '| IMEI | Cause |\n|---|---|\n| unknown | missing |')


def test_unavailable_record_page_does_not_publish_a_zero_population():
    result, _ = run(lambda payload: 'Activation records are unavailable.', unavailable=True)
    assert '0 total' not in result
    assert 'Showing records' not in result


def test_provider_cannot_relabel_offset_as_page_range():
    def answer(payload):
        assert not any(f['path'].endswith('.offset') for f in payload['facts'])
        return 'Showing records 20–20 of 50.'
    with pytest.raises(NarrativeGroundingError):
        run(answer)


def test_record_count_cannot_become_a_distinct_product_code_count():
    def answer(payload):
        count = next(f for f in payload['facts'] if f['path'].endswith('.causes[0].count'))
        return 'Reconcile the {{' + count['id'] + '}} affected product codes.'
    with pytest.raises(NarrativeGroundingError):
        run(answer, presentation='actions')
