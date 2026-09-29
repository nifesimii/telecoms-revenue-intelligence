"""Structured explanation HTTP contract; provider is replaced, data stays local."""
import json
import os

import pytest

os.environ['USE_SAMPLE_DATA'] = 'true'
os.environ['PAYMENT_SOURCE'] = 'simulated'

from fastapi.testclient import TestClient
from backend.main import app


def test_rejects_invalid_finding_scope_before_inference():
    with TestClient(app) as client:
        response = client.post('/chat/explain', json={
            'dealer_id': '123', 'mon_period': '202613',
            'finding': {'module': 'inventory', 'type': 'COMMISSION_DISPUTE'},
        })
    assert response.status_code == 422


class Provider:
    """Provider boundary fake; captures generation input, emits real NDJSON text."""
    def __init__(self, failure=None):
        self.calls = []
        self.failure = failure
        self.closed = False
        self.messages = self

    async def __aenter__(self):
        return self

    async def __aexit__(self, *args):
        self.closed = True

    def stream(self, **kwargs):
        self.calls.append(kwargs)
        return Stream(self.failure)


class Stream:
    def __init__(self, failure):
        self.failure = failure

    async def __aenter__(self):
        return self

    async def __aexit__(self, *args):
        pass

    def __aiter__(self):
        async def chunks():
            from types import SimpleNamespace
            yield SimpleNamespace(type='text', text='NGN 100.00 — ')
            if self.failure:
                raise self.failure
            yield SimpleNamespace(type='text', text='verified evidence.')
            yield SimpleNamespace(type='message_stop')
        return chunks()

    async def get_final_message(self):
        from types import SimpleNamespace
        return SimpleNamespace(stop_reason='end_turn', usage=None)


def submit(monkeypatch, payload, provider=None):
    from backend.agent import explanation
    provider = provider or Provider()
    monkeypatch.setattr(explanation, 'new_client', lambda key: provider)
    with TestClient(app) as client:
        response = client.post('/chat/explain', json=payload)
    assert response.status_code == 200
    assert response.headers['content-type'].startswith('application/x-ndjson')
    return [json.loads(line) for line in response.text.splitlines()], provider


COMMISSION = {'dealer_id': '74050', 'mon_period': '202606',
              'finding': {'module': 'commission', 'type': 'ZERO_COMMISSION_ACTIVATION'}}


@pytest.mark.parametrize('module', ['commission', 'activation', 'payment'])
@pytest.mark.parametrize('period,synthetic', [('202606', True), ('202602', False)])
def test_activation_provenance_reaches_explanation_prompt(module, period, synthetic):
    import asyncio
    from backend.agent.prompts import build_finding_explanation
    from backend.assurance.registry import ASSURANCE_REGISTRY
    from backend.assurance.payment_assurance import classify_payment_status
    from backend.db.connection import execute_query
    from backend.db.explanation_evidence import assemble_finding_evidence

    if module == 'payment':
        payments = execute_query('get_payment_summary', {'mon_period': period})
        payment = payments.loc[payments['payment_status'] == 'DISPUTED'].iloc[0]
        assert payment['exception_flag']
        dealer_id = str(payment['dealer_id'])
        _, finding_type = classify_payment_status(payment['payment_status'])
    else:
        finding = asyncio.run(ASSURANCE_REGISTRY[module].run(period)).findings[0]
        dealer_id, finding_type = finding['dealer_id'], finding['type']
    evidence = assemble_finding_evidence({'dealer_id': dealer_id, 'mon_period': period,
        'finding': {'module': module, 'type': finding_type}})

    keys = (['get_activation_exceptions'] if module == 'payment' else
            [key for key in evidence['raw_data'] if key != 'explanation_scope'])
    expected_source = 'Sample CSVs · synthetic June 2026 demo data' if synthetic else 'Sample CSVs'
    for key in keys:
        assert evidence['raw_data'][key]['provenance']['source'] == expected_source
        assert evidence['raw_data'][key]['provenance']['generated_at']
    prompt = build_finding_explanation(evidence)
    assert expected_source in prompt
    qualification = 'Synthetic activation figures are fictional demo records, not evidence of actual partner entitlement or amounts owed.'
    assert (qualification in prompt) is synthetic


def test_streams_one_generation_with_exact_scope_whole_kb_and_completion_metadata(monkeypatch):
    from backend.agent import prompts
    events, provider = submit(monkeypatch, COMMISSION)
    assert [event['type'] for event in events] == ['text', 'text', 'complete']
    assert events[-1]['response'] == 'NGN 100.00 — verified evidence.'
    assert all(set(event) == {'type', 'text'} for event in events[:-1])
    assert len(provider.calls) == 1
    assert 'tools' not in provider.calls[0]
    assert prompts.KB_CONTENT in provider.calls[0]['system'][0]['text']
    assert provider.calls[0]['system'][0]['cache_control'] == {'type': 'ephemeral'}
    raw = events[-1]['raw_data']
    assert raw['get_dealer_summary']['parameters'] == {'mon_period': '202606', 'distributor_code': '74050'}
    assert {r['dealer_id'] for r in raw['get_dealer_summary']['rows']} == {'74050'}
    assert raw['get_zero_commission_records']['row_count'] == 20
    assert raw['get_zero_commission_records']['total_rows'] == 104
    assert raw['get_zero_commission_records']['truncated'] is True
    assert provider.closed


def test_missing_or_changed_finding_does_not_call_provider(monkeypatch):
    events, provider = submit(monkeypatch, {**COMMISSION, 'dealer_id': 'does-not-exist'})
    assert events[0]['error'] == 'invalid_evidence'
    assert provider.calls == []


def test_cross_module_finding_is_not_trusted(monkeypatch):
    events, provider = submit(monkeypatch, {**COMMISSION,
        'finding': {'module': 'inventory', 'type': 'ZERO_COMMISSION_ACTIVATION', 'product_code': '1186254'}})
    assert events[0]['error'] == 'invalid_evidence'
    assert provider.calls == []


def test_inventory_product_scope_preserves_synthetic_and_coverage_evidence(monkeypatch):
    events, provider = submit(monkeypatch, {'dealer_id': '98052', 'mon_period': '202606',
        'finding': {'module': 'inventory', 'type': 'INVENTORY_MISMATCH', 'product_code': '1186254'}})
    assert events[-1]['type'] == 'complete'
    data = events[-1]['raw_data']['get_inventory_comparison']
    assert {r['product_code'] for r in data['rows']} == {'1186254'}
    assert {r['dealer_id'] for r in data['rows']} == {'98052'}
    assert data['rows'][0]['scenario_id']
    assert data['metadata']['synthetic_note']
    assert 'not authentic IFS' in provider.calls[0]['messages'][0]['content']


def test_unknown_inventory_product_is_not_explained(monkeypatch):
    events, provider = submit(monkeypatch, {'dealer_id': '98052', 'mon_period': '202606',
        'finding': {'module': 'inventory', 'type': 'INVENTORY_MISMATCH', 'product_code': 'missing'}})
    assert events[0]['error'] == 'invalid_evidence'
    assert not provider.calls


def test_partial_stream_failure_is_sanitized_and_never_completed(monkeypatch):
    events, provider = submit(monkeypatch, COMMISSION, Provider(RuntimeError('secret SQL SELECT password')))
    assert [event['type'] for event in events] == ['text', 'error']
    assert events[-1]['error'] == 'explanation_failed'
    assert 'password' not in json.dumps(events)
    assert len(provider.calls) == 1
    assert provider.closed


def test_evidence_deadline_does_not_start_provider(monkeypatch):
    import time
    from backend.agent import inference, tool_executor
    monkeypatch.setattr(inference, 'REQUEST_DEADLINE_SECONDS', 0.01)
    monkeypatch.setattr(tool_executor, 'execute_explanation_evidence', lambda request, **kwargs: time.sleep(0.03))
    events, provider = submit(monkeypatch, COMMISSION)
    assert events[0]['error'] == 'deadline_exceeded'
    assert not provider.calls


def test_apdp_payment_uses_same_status_mapping_and_keeps_missing_record_caveats(monkeypatch):
    from backend import config
    from backend.db import apdp
    monkeypatch.setattr(config, 'PAYMENT_SOURCE', 'apdp')
    monkeypatch.setattr(apdp, 'get_partner_settlements', lambda period: [
        {'dealer_id': 'APDP_ONLY', 'settlement_period': period,
         'expected_commission_ngn': 0, 'total_settled_ngn': 0,
         'reconciliation_status': 'SALES_WITHOUT_STATEMENT',
         'statement_count': 0, 'settlement_count': 0, 'sale_count': 3},
        {'dealer_id': 'OTHER', 'settlement_period': period,
         'reconciliation_status': 'RECONCILED', 'expected_commission_ngn': 999},
    ])
    events, provider = submit(monkeypatch, {'dealer_id': 'APDP_ONLY', 'mon_period': '202606',
        'finding': {'module': 'payment', 'type': 'PENDING_SETTLEMENT'}})
    assert events[-1]['type'] == 'complete'
    payment = events[-1]['raw_data']['get_payment_summary']
    assert payment['data_source'] == 'APDP'
    assert payment['payment_status'] == 'PENDING'
    assert payment['rows'][0]['statement_count'] == 0
    assert len(payment['rows']) == 1
    prompt = provider.calls[0]['messages'][0]['content']
    assert 'do not establish zero entitlement or payment' in prompt
    assert 'OTHER' not in prompt


def test_disconnect_closes_provider_and_does_not_complete(monkeypatch):
    import asyncio
    from backend.agent import explanation
    provider = Provider()
    monkeypatch.setattr(explanation, 'new_client', lambda key: provider)

    async def exercise():
        body = json.dumps(COMMISSION).encode()
        first = True
        disconnected = asyncio.Event()
        sent = []
        async def receive():
            nonlocal first
            if first:
                first = False
                return {'type': 'http.request', 'body': body, 'more_body': False}
            await disconnected.wait()
            return {'type': 'http.disconnect'}
        async def send(message):
            if message['type'] == 'http.response.body' and message.get('body'):
                sent.append(json.loads(message['body']))
                disconnected.set()
                await asyncio.sleep(0)
        scope = {'type': 'http', 'asgi': {'version': '3.0', 'spec_version': '2.3'},
                 'http_version': '1.1', 'method': 'POST', 'scheme': 'http',
                 'path': '/chat/explain', 'raw_path': b'/chat/explain', 'query_string': b'',
                 'root_path': '', 'headers': [(b'content-type', b'application/json')],
                 'client': ('127.0.0.1', 123), 'server': ('test', 80)}
        await app(scope, receive, send)
        # Closing a suspended async generator runs its cancellation finalizer.
        await asyncio.sleep(0)
        assert not any(event['type'] == 'complete' for event in sent)
    asyncio.run(exercise())
    assert provider.closed


def test_disconnect_before_first_text_cancels_provider_on_asgi_24(monkeypatch):
    import asyncio
    from backend.agent import explanation

    async def exercise():
        entered = asyncio.Event()
        closed = asyncio.Event()
        class WaitingStream(Stream):
            async def __aenter__(self):
                entered.set()
                return self
            async def __aexit__(self, *args):
                closed.set()
            def __aiter__(self):
                async def chunks():
                    await asyncio.Event().wait()
                    yield 'unreachable'
                return chunks()
        provider = Provider()
        provider.stream = lambda **kwargs: WaitingStream(None)
        monkeypatch.setattr(explanation, 'new_client', lambda key: provider)
        first = True
        async def receive():
            nonlocal first
            if first:
                first = False
                return {'type': 'http.request', 'body': json.dumps(COMMISSION).encode(), 'more_body': False}
            await entered.wait()
            return {'type': 'http.disconnect'}
        async def send(message):
            pass
        scope = {'type': 'http', 'asgi': {'version': '3.0', 'spec_version': '2.4'},
                 'http_version': '1.1', 'method': 'POST', 'scheme': 'http',
                 'path': '/chat/explain', 'raw_path': b'/chat/explain', 'query_string': b'',
                 'root_path': '', 'headers': [(b'content-type', b'application/json')],
                 'client': ('127.0.0.1', 123), 'server': ('test', 80)}
        await asyncio.wait_for(app(scope, receive, send), 2)
        assert closed.is_set()
        assert provider.closed
    asyncio.run(exercise())


def test_product_scope_validation_precedes_evidence(monkeypatch):
    from unittest.mock import Mock
    from backend.agent import tool_executor
    evidence = Mock(side_effect=AssertionError('must not read evidence'))
    monkeypatch.setattr(tool_executor, 'execute_explanation_evidence', evidence)
    findings = [{'module': 'inventory', 'type': 'INVENTORY_MISMATCH'}]
    findings += [{'module': module, 'type': 'EXAMPLE', 'product_code': '123'}
                 for module in ('commission', 'activation', 'payment')]
    with TestClient(app) as client:
        for finding in findings:
            response = client.post('/chat/explain', json={**COMMISSION, 'finding': finding})
            assert response.status_code == 422
    evidence.assert_not_called()


@pytest.mark.parametrize('termination', ['cancel', 'deadline', 'disconnect'])
def test_ended_evidence_cannot_start_next_read(monkeypatch, termination):
    import asyncio
    import threading
    import pytest
    from backend.agent import explanation, inference
    from backend.assurance.registry import ASSURANCE_REGISTRY
    from backend.assurance.base import AssuranceResult
    from backend.db import explanation_evidence
    from unittest.mock import Mock
    entered, release = threading.Event(), threading.Event()
    if termination == 'deadline':
        monkeypatch.setattr(inference, 'REQUEST_DEADLINE_SECONDS', 0.1)
    async def blocking_assurance(*args):
        entered.set()
        assert release.wait(2)
        return AssuranceResult(module='Commission Assurance', status='FLAG', summary='',
            findings=[{'dealer_id': '74050', 'type': 'ZERO_COMMISSION_ACTIVATION'}])
    monkeypatch.setattr(ASSURANCE_REGISTRY['commission'], 'run', blocking_assurance)
    next_read = Mock(side_effect=AssertionError('read after cancellation'))
    monkeypatch.setattr(explanation_evidence, 'execute_query', next_read)
    async def exercise():
        stream = explanation.explain_finding(COMMISSION)
        task = asyncio.create_task(anext(stream))
        try:
            assert await asyncio.to_thread(entered.wait, 2)
            if termination == 'deadline':
                event = await asyncio.wait_for(task, 1)
                assert event['error'] == 'deadline_exceeded'
                await stream.aclose()
            else:
                task.cancel()
                with pytest.raises(asyncio.CancelledError):
                    await task
        finally:
            release.set()

    async def disconnect():
        first = True
        async def receive():
            nonlocal first
            if first:
                first = False
                return {'type': 'http.request', 'body': json.dumps(COMMISSION).encode(), 'more_body': False}
            assert await asyncio.to_thread(entered.wait, 2)
            return {'type': 'http.disconnect'}
        async def send(message):
            assert not message.get('body')
        scope = {'type': 'http', 'asgi': {'version': '3.0', 'spec_version': '2.4'},
                 'http_version': '1.1', 'method': 'POST', 'scheme': 'http',
                 'path': '/chat/explain', 'raw_path': b'/chat/explain', 'query_string': b'',
                 'root_path': '', 'headers': [(b'content-type', b'application/json')],
                 'client': ('127.0.0.1', 123), 'server': ('test', 80)}
        try:
            await asyncio.wait_for(app(scope, receive, send), 2)
        finally:
            release.set()

    # asyncio.run waits for worker shutdown before checking subsequent reads.
    asyncio.run(disconnect() if termination == 'disconnect' else exercise())
    next_read.assert_not_called()
