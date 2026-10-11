import asyncio
import json
from types import SimpleNamespace

import pytest
from backend.agent.answer_evidence import prepare_answer
from backend.agent.inference import InferenceRun
from backend.agent.narrative import compose_answer, NarrativeGroundingError


def run_draft(factory):
    prepared = prepare_answer(scope={'kind': 'measure'}, evidence={'paid': 10, 'owed': 20},
                              tools_called=['payments'], mandatory_caveats=['Settlement coverage is incomplete.'])
    async def create(**kwargs):
        payload = json.loads(kwargs['messages'][0]['content'])
        return SimpleNamespace(stop_reason='tool_use', content=[SimpleNamespace(
            type='tool_use', name='compose_grounded_answer', input=factory(payload))])
    client = SimpleNamespace(messages=SimpleNamespace(create=create))
    return asyncio.run(compose_answer(client, InferenceRun('test'), prepared=prepared,
                                     question='Amounts?', history=[], sample_mode=False, model='test'))


def draft(payload, text='The recorded amounts are available.', claims=None, actions=None):
    return {'headline': None, 'explanation_blocks': [{'text': text,
            'claim_ids': claims if claims is not None else [c['id'] for c in payload['claims']]}],
            'next_step_ids': actions or []}


def test_mandatory_caveat_survives_model_omission():
    assert 'Settlement coverage is incomplete.' in run_draft(draft)


@pytest.mark.parametrize('kind', ['fact', 'claim', 'action', 'uncited'])
def test_unknown_or_uncited_references_are_rejected(kind):
    def factory(payload):
        if kind == 'fact':
            return draft(payload, '{{f999}} was paid.')
        if kind == 'claim':
            return draft(payload, claims=['c999'])
        if kind == 'action':
            return draft(payload, actions=['a999'])
        return draft(payload, '{{f0}} was paid.', claims=[])
    with pytest.raises(NarrativeGroundingError):
        run_draft(factory)


def test_old_unstructured_contract_cannot_publish():
    with pytest.raises(NarrativeGroundingError):
        run_draft(lambda payload: {'answer': 'The recorded amounts are available.'})


def test_prose_cannot_bypass_permitted_action_selection():
    with pytest.raises(NarrativeGroundingError):
        run_draft(lambda payload: draft(payload, 'Finance should approve immediate payment.'))


def test_subscription_revenue_cannot_be_described_as_commission_owed():
    prepared = prepare_answer(scope={'kind': 'measure'}, evidence={'total_subscription_amount_ngn': 100}, tools_called=[])
    from backend.agent.narrative import _validate_text
    with pytest.raises(NarrativeGroundingError):
        _validate_text('Commission owed is {{f0}}.', prepared.facts, prepared.scope, '', prepared.evidence)


@pytest.mark.parametrize('text', ['Finance can release the payment now.',
                                 'I recommend issuing immediate payment.'])
def test_action_modalities_cannot_bypass_permitted_actions(text):
    with pytest.raises(NarrativeGroundingError):
        run_draft(lambda payload: draft(payload, text))


def test_missing_settlement_cannot_be_called_zero_in_plain_prose():
    prepared = prepare_answer(scope={'kind': 'measure'}, evidence={'payment': {'payment_found': False, 'paid': 0, 'balance': 0}}, tools_called=[])
    from backend.agent.narrative import _validate_text
    with pytest.raises(NarrativeGroundingError):
        _validate_text('There is no outstanding balance.', prepared.facts, prepared.scope, '', prepared.evidence)


def test_subscription_commission_cannot_be_relabelled_as_revenue():
    prepared = prepare_answer(scope={'kind': 'measure'}, evidence={'measure': 'subscription_commission', 'unit': 'ngn', 'total': 100}, tools_called=[])
    from backend.agent.narrative import _validate_text
    fact = next(f for f in prepared.facts if f['path'].endswith('.total'))
    with pytest.raises(NarrativeGroundingError):
        _validate_text('Subscription revenue is {{' + fact['id'] + '}}.', prepared.facts, prepared.scope, '', prepared.evidence)


def test_repair_cannot_push_model_input_past_byte_limit():
    prepared = prepare_answer(scope={}, evidence={}, tools_called=[])
    payload = {**prepared.model_payload(), 'question': '', 'history': [], 'sample_mode': False}
    question = 'x' * (180000 - len(json.dumps(payload, ensure_ascii=False).encode('utf-8')) - 5)
    calls = []
    async def create(**kwargs):
        calls.append(kwargs)
        return SimpleNamespace(stop_reason='tool_use', content=[SimpleNamespace(
            type='tool_use', name='compose_grounded_answer',
            input={'headline': None, 'explanation_blocks': [{'text': 'There are 999 records.', 'claim_ids': []}], 'next_step_ids': []})])
    client = SimpleNamespace(messages=SimpleNamespace(create=create))
    with pytest.raises(NarrativeGroundingError, match='capacity'):
        asyncio.run(compose_answer(client, InferenceRun('test'), prepared=prepared,
                                  question=question, history=[], sample_mode=False, model='test'))
    assert len(calls) == 1
