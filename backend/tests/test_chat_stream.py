"""Ordinary chat streams at public agent/API seams, with provider-only fakes."""
import asyncio
import json
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from anthropic.types import TextBlock, ToolUseBlock
from fastapi.testclient import TestClient
from backend.agent import agent, inference, prompts
from backend.main import app
from backend.tests.narrative_provider import final_response, is_final_call


class Provider:
    def __init__(self, rounds):
        self.rounds = iter(rounds)
        self.calls = []
        self.messages = self
        self.close = AsyncMock()

    async def create(self, **kwargs):
        self.calls.append(kwargs)
        return final_response(kwargs)

    def stream(self, **kwargs):
        self.calls.append(kwargs)
        if is_final_call(kwargs):
            response = final_response(kwargs)
            block = response.content[0]
            return Stream('', tool=ToolUseBlock(type='tool_use', id='answer', name=block.name, input=block.input), stop='tool_use')
        return next(self.rounds)


class Stream:
    def __init__(self, text, tool=None, stop='end_turn', terminal=True, gate=None, failure=None):
        self.text, self.tool, self.stop = text, tool, stop
        self.terminal, self.gate, self.failure = terminal, gate, failure
        self.closed = False

    async def __aenter__(self):
        return self

    async def __aexit__(self, *args):
        self.closed = True

    async def __aiter__(self):
        yield SimpleNamespace(type='text', text=self.text)
        if self.tool:
            yield SimpleNamespace(type='content_block_start', content_block=self.tool)
        if self.gate:
            await self.gate.wait()
        if self.failure:
            raise self.failure
        if self.terminal:
            yield SimpleNamespace(type='message_stop')

    async def get_final_message(self):
        return SimpleNamespace(stop_reason=self.stop, usage=None,
            content=[TextBlock(type='text', text=self.text)] + ([self.tool] if self.tool else []))


def provider(monkeypatch, *rounds):
    fake = Provider(rounds)
    monkeypatch.setattr(agent, 'new_client', lambda key: fake)
    return fake


def scope_tool(**overrides):
    scope = {'kind': 'measure', 'measures': ['activation_count'], 'periods': ['202603'],
             'dealer_id': '74050', 'operation': 'total', 'breakdown': 'dealer'}
    scope.update(overrides)
    return ToolUseBlock(type='tool_use', id='scope_1', name='resolve_measure_request', input=scope)


def collect():
    async def exercise():
        return [event async for event in agent.run_agent_stream('How many activations in March?')]
    return asyncio.run(exercise())


def test_followup_includes_selected_account_even_without_opening_context(monkeypatch):
    fake = provider(monkeypatch, Stream('Do not publish this draft.', tool=scope_tool(), stop='tool_use'))
    question = 'what products entitle this dealer for commission this month'
    history = [{'role': 'user', 'content': 'Explain the balance'},
               {'role': 'assistant', 'content': 'Recorded balance explained.'}]
    context = 'Exact dealer account code 296065 (River Isle Ventures); do not combine other accounts with the same name.'
    with TestClient(app) as client:
        response = client.post('/chat/stream', json={
            'message': question, 'mon_period': '202606',
            'conversation_history': history, 'investigation_context': context})
    assert response.status_code == 200
    sent = fake.calls[0]['messages']
    assert sent[:-1] == history
    assert json.loads(sent[-1]['content']) == {
        'question': question, 'reporting_period': '202606', 'investigation_context': context}


def test_buffered_chat_also_receives_active_context(monkeypatch):
    from backend.api import routes
    run = AsyncMock(return_value={'response': 'Answer', 'tools_called': [], 'raw_data': {}, 'error': None})
    monkeypatch.setattr(routes, 'run_agent', run)
    with TestClient(app) as client:
        response = client.post('/chat', json={'message': 'What about this dealer?',
            'mon_period': '202603', 'investigation_context': 'Exact dealer account code 001.'})
    assert response.status_code == 200
    assert run.call_args.args[0] == 'What about this dealer?'
    assert run.call_args.kwargs['investigation_context'] == 'Exact dealer account code 001.'
    assert run.call_args.kwargs['reporting_period'] == '202603'


def test_chat_stream_withholds_draft_until_provider_and_evidence_complete(monkeypatch):
    async def exercise():
        gate, draft_seen = asyncio.Event(), asyncio.Event()
        class GatedStream(Stream):
            async def __aiter__(self):
                draft_seen.set()
                async for event in super().__aiter__():
                    yield event
        source = GatedStream('Sales NGN 999,999,999.00 invented.', tool=scope_tool(), stop='tool_use', gate=gate)
        fake = provider(monkeypatch, source)
        events = []
        async def consume():
            async for event in agent.run_agent_stream('How many activations in March?',
                    [{'role': 'user', 'content': 'Prior question'}]):
                events.append(event)
        task = asyncio.create_task(consume())
        await asyncio.wait_for(draft_seen.wait(), 1)
        await asyncio.sleep(0)
        assert not any(e['type'] == 'text' for e in events)
        gate.set()
        await asyncio.wait_for(task, 3)
        assert events[-1]['type'] == 'complete'
        texts = [e['text'] for e in events if e['type'] == 'text']
        assert texts == [events[-1]['response']]
        assert '999,999,999' not in texts[0]
        assert 'activation' in texts[0].lower()
        assert 'measure_evidence' in events[-1]['raw_data']
        assert events[-1]['tools_called'] == ['get_dealer_summary']
        assert len(fake.calls) == 2
        assert fake.calls[0]['system'] == inference.cached_system(prompts.get_measure_system_prompt())
        assert fake.calls[0]['max_tokens'] == agent.MAX_TOKENS
        assert fake.calls[0]['model'] == agent.MODEL_NAME
        assert [t['name'] for t in fake.calls[0]['tools']] == ['resolve_measure_request']
        assert fake.calls[0]['messages'][0]['content'] == 'Prior question'
        assert source.closed
        fake.close.assert_awaited_once()
    asyncio.run(exercise())


@pytest.mark.parametrize('stop,terminal', [('max_tokens', True), ('tool_use', False), ('pause_turn', True)])
def test_chat_stream_never_completes_truncated_or_unconfirmed_answer(monkeypatch, stop, terminal):
    provider(monkeypatch, Stream('Partial invented answer', tool=scope_tool(), stop=stop, terminal=terminal))
    events = collect()
    assert events[-1]['type'] == 'error'
    assert not any(e['type'] in ('text', 'complete') for e in events)


def test_chat_stream_cancellation_closes_provider_before_evidence(monkeypatch):
    async def exercise():
        entered = asyncio.Event()
        class WaitingStream(Stream):
            async def __aiter__(self):
                entered.set()
                async for event in super().__aiter__():
                    yield event
        source = WaitingStream('Partial', gate=asyncio.Event())
        fake = provider(monkeypatch, source)
        stream = agent.run_agent_stream('Explain')
        assert (await anext(stream))['type'] == 'status'
        pending = asyncio.create_task(anext(stream))
        await asyncio.wait_for(entered.wait(), 1)
        pending.cancel()
        with pytest.raises(asyncio.CancelledError):
            await pending
        await stream.aclose()
        assert source.closed
        fake.close.assert_awaited_once()
    asyncio.run(exercise())


def test_chat_stream_http_contract_and_period(monkeypatch):
    fake = provider(monkeypatch, Stream('Unvalidated final answer.', tool=scope_tool(), stop='tool_use'))
    with TestClient(app) as client:
        response = client.post('/chat/stream', json={'message': 'Explain', 'mon_period': '202603', 'conversation_history': []})
    assert response.status_code == 200
    assert response.headers['content-type'].startswith('application/x-ndjson')
    assert response.headers['x-accel-buffering'] == 'no'
    events = [json.loads(line) for line in response.text.splitlines()]
    assert events[-1]['type'] == 'complete'
    assert 'Unvalidated' not in response.text
    assert json.loads(fake.calls[0]['messages'][-1]['content']) == {
        'question': 'Explain', 'reporting_period': '202603', 'investigation_context': None}


@pytest.mark.parametrize('tool', [None, ToolUseBlock(type='tool_use', id='bad', name='get_dealer_summary', input={'mon_period': '202603'}),
    scope_tool(measures=['invented_sales_metric'])])
def test_chat_stream_rejects_unscoped_model_figures_without_exposing_draft(monkeypatch, tool):
    fake = provider(monkeypatch, *[Stream('Sales are NGN 999,999,999.00.', tool=tool, stop='tool_use' if tool else 'end_turn') for _ in range(2)])
    events = collect()
    assert '999,999,999' not in str(events)
    assert events[-1]['type'] == 'complete'
    assert 'cannot resolve' in events[-1]['response']
    assert events[-1]['tools_called'] == []
    assert len(fake.calls) == 2


def test_chat_stream_measure_status_events_satisfy_browser_contract(monkeypatch):
    # Mirrors frontend/src/api/explanationStream.js: tool phases must name a tool.
    provider(monkeypatch, Stream('Draft', tool=scope_tool(), stop='tool_use'))
    events = collect()
    phases = [e for e in events if e['type'] == 'status' and e['phase'] != 'thinking']
    assert [e['phase'] for e in phases] == ['tool_start', 'tool_complete']
    assert all(isinstance(e['tool'], str) and e['tool'] for e in phases)
    assert all(isinstance(e['reset'], bool) for e in phases)
    assert events[-1]['type'] == 'complete'


def test_chat_stream_priority_question_streams_queue_rank(monkeypatch):
    from backend.tests.test_measure_scope import install_priority
    calls = install_priority(monkeypatch)
    provider(monkeypatch, Stream('Draft: LOW priority.', stop='tool_use', tool=scope_tool(
        measures=['investigation_priority'], periods=['202606'], dealer_id='296065')))
    events = collect()
    phases = [e for e in events if e['type'] == 'status' and e['phase'] != 'thinking']
    assert [e['phase'] for e in phases] == ['tool_start', 'tool_complete']
    assert all(e['tool'] == 'measure_evidence' for e in phases)
    text = ''.join(e['text'] for e in events if e['type'] == 'text')
    assert 'rank 1 of 922' in text and 'Draft' not in text
    assert calls == [('202606', '296065')]
    assert events[-1]['type'] == 'complete'


def test_chat_stream_statement_question_streams_owed_paid_outstanding(monkeypatch):
    from backend import config
    from backend.db import audit_store
    monkeypatch.setattr(config, 'PAYMENT_SOURCE', 'simulated')
    monkeypatch.setattr(audit_store, 'healthcheck', lambda: True)
    monkeypatch.setattr(audit_store, 'get_partner_trail', lambda *args: None)
    provider(monkeypatch, Stream('Draft: NGN 0.00 owed.', stop='tool_use', tool=scope_tool(
        measures=['dealer_statement'], periods=['202606'], dealer_id='296065')))
    events = collect()
    phases = [e for e in events if e['type'] == 'status' and e['phase'] != 'thinking']
    assert [e['phase'] for e in phases] == ['tool_start', 'tool_complete']
    assert all(e['tool'] == 'measure_evidence' for e in phases)
    text = ''.join(e['text'] for e in events if e['type'] == 'text')
    assert 'NGN 596,177.08' in text and 'NGN 994,136.80' in text and 'NGN 397,959.72' in text
    assert 'Draft' not in text
    assert events[-1]['type'] == 'complete'
    assert events[-1]['tools_called'] == ['dealer_statement']


def test_chat_stream_verification_question_streams_audit_verdicts(monkeypatch):
    from backend.tests.test_verification_outcome import install_verification
    calls = install_verification(monkeypatch)
    provider(monkeypatch, Stream('Draft: the dealer was paid correctly.', stop='tool_use', tool=scope_tool(
        measures=['verification_outcome'], periods=['202606'], dealer_id='296065')))
    events = collect()
    phases = [e for e in events if e['type'] == 'status' and e['phase'] != 'thinking']
    assert [e['phase'] for e in phases] == ['tool_start', 'tool_complete']
    assert all(e['tool'] == 'measure_evidence' for e in phases)
    text = ''.join(e['text'] for e in events if e['type'] == 'text')
    assert 'below the recorded amount owed' in text and '296065' in text and '202606' in text
    assert 'UNDERPAID' not in text and 'Draft' not in text
    assert 'UNDERPAID' in json.dumps(events[-1]['raw_data'])
    assert calls == [('202606', '296065')]
    assert events[-1]['type'] == 'complete'


def test_chat_stream_variance_question_streams_change_by_product(monkeypatch):
    provider(monkeypatch, Stream('Draft: commission fell.', stop='tool_use', tool=scope_tool(
        measures=['commission_variance'], periods=['202605', '202606'], dealer_id='296065',
        operation='explain')))
    events = collect()
    text = ''.join(e['text'] for e in events if e['type'] == 'text')
    assert 'NGN 39,873.42' in text and 'Draft' not in text
    assert events[-1]['type'] == 'complete'
    assert events[-1]['tools_called'] == ['get_month_on_month_variance']


def test_chat_stream_coverage_question_streams_named_gaps(monkeypatch):
    provider(monkeypatch, Stream('Draft: data is fine.', stop='tool_use', tool=scope_tool(
        measures=['data_coverage'], periods=['202606'], dealer_id='296065')))
    events = collect()
    text = ''.join(e['text'] for e in events if e['type'] == 'text')
    assert 'unavailable' in text and '296065' in text and 'Draft' not in text
    assert events[-1]['raw_data']['measure_evidence']['measures'][0]['measure'] == 'data_coverage'
    assert events[-1]['type'] == 'complete'
    assert events[-1]['tools_called'] == ['data_coverage']


def test_chat_stream_sales_clarification_has_no_evidence_or_invented_figures(monkeypatch):
    tool = ToolUseBlock(type='tool_use', id='scope_1', name='resolve_measure_request',
        input={'kind': 'clarification', 'clarification': 'sales_meaning'})
    provider(monkeypatch, Stream('Assume sales mean commissions NGN 100.00', tool=tool, stop='tool_use'))
    events = collect()
    result = events[-1]
    assert result['type'] == 'complete'
    assert result['tools_called'] == []
    assert result['raw_data'] == {}
    assert '100.00' not in result['response']
    assert 'sales' in result['response'].lower()


def test_chat_stream_http_disconnect_cancels_before_first_text(monkeypatch):
    async def exercise():
        entered = asyncio.Event()
        class WaitingStream(Stream):
            async def __aiter__(self):
                entered.set()
                await asyncio.Event().wait()
                yield None
        source = WaitingStream('')
        fake = provider(monkeypatch, source)
        first = True
        async def receive():
            nonlocal first
            if first:
                first = False
                return {'type': 'http.request', 'body': json.dumps({'message': 'Explain'}).encode(), 'more_body': False}
            await entered.wait()
            return {'type': 'http.disconnect'}
        async def send(message):
            if message.get('body'):
                assert json.loads(message['body'])['type'] == 'status'
        scope = {'type': 'http', 'asgi': {'version': '3.0', 'spec_version': '2.4'},
            'http_version': '1.1', 'method': 'POST', 'scheme': 'http',
            'path': '/chat/stream', 'raw_path': b'/chat/stream', 'query_string': b'',
            'root_path': '', 'headers': [(b'content-type', b'application/json')],
            'client': ('127.0.0.1', 123), 'server': ('test', 80)}
        await asyncio.wait_for(app(scope, receive, send), 2)
        assert source.closed
        fake.close.assert_awaited_once()
    asyncio.run(exercise())


def test_chat_stream_failure_after_provider_draft_does_not_leak_or_replay(monkeypatch):
    import anthropic
    import httpx
    fake = provider(monkeypatch, Stream('Partial draft', failure=anthropic.APIConnectionError(
        request=httpx.Request('POST', 'https://api.anthropic.com/v1/messages'))))
    events = collect()
    assert not any(e['type'] == 'text' for e in events)
    assert events[-1]['type'] == 'error'
    assert len(fake.calls) == 1


@pytest.mark.parametrize('stop,terminal,success', [('tool_use', True, True), ('max_tokens', True, False), ('tool_use', False, False)])
def test_real_sdk_chat_stream_confirms_terminal_scope_before_rendering(monkeypatch, stop, terminal, success):
    import anthropic
    import httpx
    events = [
        {'type': 'message_start', 'message': {'id': 'msg_test', 'type': 'message', 'role': 'assistant',
            'model': agent.MODEL_NAME, 'content': [], 'stop_reason': None, 'stop_sequence': None,
            'usage': {'input_tokens': 1, 'output_tokens': 0}}},
        {'type': 'content_block_start', 'index': 0, 'content_block': {'type': 'text', 'text': ''}},
        {'type': 'content_block_delta', 'index': 0, 'delta': {'type': 'text_delta', 'text': 'Invented sales NGN 999,999,999.00'}},
        {'type': 'content_block_stop', 'index': 0},
        {'type': 'content_block_start', 'index': 1, 'content_block': {'type': 'tool_use', 'id': 'scope_1', 'name': 'resolve_measure_request', 'input': {}}},
        {'type': 'content_block_delta', 'index': 1, 'delta': {'type': 'input_json_delta', 'partial_json': json.dumps(scope_tool().input)}},
        {'type': 'content_block_stop', 'index': 1},
        {'type': 'message_delta', 'delta': {'stop_reason': stop, 'stop_sequence': None}, 'usage': {'output_tokens': 8}},
    ]
    if terminal:
        events.append({'type': 'message_stop'})
    body = ''.join(f"event: {event['type']}\ndata: {json.dumps(event)}\n\n" for event in events)
    calls = []
    def respond(request):
        calls.append(json.loads(request.content))
        if is_final_call(calls[-1]):
            block = final_response(calls[-1]).content[0]
            return httpx.Response(200, json={'id': 'msg_answer', 'type': 'message', 'role': 'assistant',
                'model': agent.MODEL_NAME, 'content': [{'type': 'tool_use', 'id': 'answer', 'name': block.name, 'input': block.input}],
                'stop_reason': 'tool_use', 'stop_sequence': None, 'usage': {'input_tokens': 1, 'output_tokens': 20}})
        return httpx.Response(200, headers={'content-type': 'text/event-stream'}, text=body)
    async def exercise():
        client = anthropic.AsyncAnthropic(api_key='test', max_retries=0,
            http_client=httpx.AsyncClient(transport=httpx.MockTransport(respond)))
        monkeypatch.setattr(agent, 'new_client', lambda key: client)
        received = [event async for event in agent.run_agent_stream('How many activations in March?')]
        assert received[-1]['type'] == ('complete' if success else 'error')
        assert '999,999,999' not in json.dumps(received)
        texts = [event['text'] for event in received if event['type'] == 'text']
        assert texts == ([received[-1]['response']] if success else [])
    asyncio.run(exercise())
    assert len(calls) == (2 if success else 1)
    assert calls[0]['stream'] is True
    assert calls[0]['system'] == inference.cached_system(prompts.get_measure_system_prompt())


def test_chat_stream_retries_connection_failure_before_draft_once(monkeypatch):
    import anthropic
    import httpx
    failure = anthropic.APIConnectionError(request=httpx.Request('POST', 'https://api.anthropic.com/v1/messages'))
    fake = provider(monkeypatch, Stream('', failure=failure), Stream('', tool=scope_tool(), stop='tool_use'))
    sleep = AsyncMock()
    monkeypatch.setattr(inference.asyncio, 'sleep', sleep)
    events = collect()
    assert events[-1]['type'] == 'complete'
    assert len(fake.calls) == 3
    sleep.assert_awaited_once()


def test_chat_stream_evidence_failure_withholds_provider_figures(monkeypatch):
    provider(monkeypatch, Stream('Activations 999999.', tool=scope_tool(), stop='tool_use'))
    def unavailable(scope):
        raise RuntimeError('Evidence read failed')
    monkeypatch.setattr(agent.tool_executor, 'execute_measure_request', unavailable)
    events = collect()
    assert events[-1]['type'] == 'error'
    assert not any(event['type'] in ('text', 'complete') for event in events)


def test_chat_stream_activation_exceptions_question_streams_the_findings(monkeypatch):
    provider(monkeypatch, Stream('Draft: no exceptions.', stop='tool_use', tool=scope_tool(
        measures=['activation_exceptions'], periods=['202606'], dealer_id='296065')))
    events = collect()
    text = ''.join(e['text'] for e in events if e['type'] == 'text')
    assert 'activation exceptions' in text and '296065' in text and 'Draft' not in text
    assert events[-1]['raw_data']['measure_evidence']['measures'][0]['measure'] == 'activation_exceptions'
    assert events[-1]['type'] == 'complete'
    assert events[-1]['tools_called'] == ['activation_exceptions']


def test_chat_stream_payment_exceptions_question_streams_the_exceptions(monkeypatch):
    from backend import config
    monkeypatch.setattr(config, 'PAYMENT_SOURCE', 'simulated')
    provider(monkeypatch, Stream('Draft: all paid.', stop='tool_use', tool=scope_tool(
        measures=['payment_exceptions'], periods=['202606'], dealer_id='296065')))
    events = collect()
    text = ''.join(e['text'] for e in events if e['type'] == 'text')
    assert 'payment exceptions' in text and '296065' in text and 'Draft' not in text
    assert events[-1]['raw_data']['measure_evidence']['measures'][0]['measure'] == 'payment_exceptions'
    assert events[-1]['type'] == 'complete'
    assert events[-1]['tools_called'] == ['payment_exceptions']


def test_chat_stream_payment_exceptions_by_dealer_name_resolves_to_the_code(monkeypatch):
    from backend import config
    monkeypatch.setattr(config, 'PAYMENT_SOURCE', 'simulated')
    provider(monkeypatch, Stream('Draft', stop='tool_use', tool=scope_tool(
        measures=['payment_exceptions'], periods=['202606'], dealer_id=None, dealer_name='Amber Arc')))
    events = collect()
    text = ''.join(e['text'] for e in events if e['type'] == 'text')
    assert '130062' in text and 'payment exceptions' in text and 'Draft' not in text
    assert events[-1]['raw_data']['measure_evidence']['dealer_id'] == '130062'
    assert events[-1]['tools_called'] == ['get_dealer_codes', 'payment_exceptions']


def test_chat_stream_named_dealer_resolves_before_evidence(monkeypatch):
    from backend import config
    from backend.db import audit_store
    monkeypatch.setattr(config, 'PAYMENT_SOURCE', 'simulated')
    monkeypatch.setattr(audit_store, 'healthcheck', lambda: True)
    monkeypatch.setattr(audit_store, 'get_partner_trail', lambda *args: None)
    provider(monkeypatch, Stream('Draft: NGN 0.00 owed.', stop='tool_use', tool=scope_tool(
        measures=['dealer_statement'], periods=['202606'], dealer_id=None, dealer_name='Amber Arc')))
    events = collect()
    phases = [e for e in events if e['type'] == 'status' and e['phase'] != 'thinking']
    assert [e['phase'] for e in phases] == ['tool_start', 'tool_complete']
    assert all(e['tool'] == 'measure_evidence' for e in phases)
    text = ''.join(e['text'] for e in events if e['type'] == 'text')
    assert 'Amber Arc Communications' in text and '130062' in text and '202606' in text
    assert events[-1]['raw_data']['measure_evidence']['dealer_id'] == '130062'
    assert 'Draft' not in text
    assert events[-1]['type'] == 'complete'
    assert events[-1]['tools_called'] == ['get_dealer_codes', 'dealer_statement']


def test_chat_stream_ambiguous_dealer_name_asks_and_reads_no_evidence(monkeypatch):
    provider(monkeypatch, Stream('Draft', stop='tool_use', tool=scope_tool(
        measures=['dealer_statement'], periods=['202606'], dealer_id=None, dealer_name='River Isle')))
    monkeypatch.setattr(agent.tool_executor, 'execute_measure_request',
                        lambda request: pytest.fail('evidence read for an ambiguous name'))
    events = collect()
    assert events[-1]['type'] == 'complete'
    phases = [e['phase'] for e in events if e['type'] == 'status' and e['phase'] != 'thinking']
    assert phases == ['tool_start', 'tool_complete']
    text = ''.join(e['text'] for e in events if e['type'] == 'text')
    assert text.startswith('Several recorded dealers match “River Isle” for 202606')
    assert 'Which dealer do you mean? Give the dealer code.' in text
    assert events[-1]['tools_called'] == ['get_dealer_codes']


def test_chat_stream_investigation_queue_question_streams_the_bounded_queue(monkeypatch):
    from backend import config
    monkeypatch.setattr(config, 'PAYMENT_SOURCE', 'simulated')
    provider(monkeypatch, Stream('Draft: nobody to investigate.', stop='tool_use', tool=scope_tool(
        measures=['investigation_queue'], periods=['202606'], dealer_id=None, queue_severity='HIGH')))
    events = collect()
    phases = [e for e in events if e['type'] == 'status' and e['phase'] != 'thinking']
    assert [e['phase'] for e in phases] == ['tool_start', 'tool_complete']
    text = ''.join(e['text'] for e in events if e['type'] == 'text')
    assert 'ranked investigation queue' in text
    assert 'Showing 10 of 61 matching dealers' in text and 'Draft' not in text
    assert events[-1]['type'] == 'complete'
    assert events[-1]['tools_called'] == ['investigation_queue']


def test_chat_stream_investigation_queue_for_one_dealer_reads_no_evidence(monkeypatch):
    provider(monkeypatch, Stream('Draft: rank 1.', stop='tool_use', tool=scope_tool(
        measures=['investigation_queue'], periods=['202606'], dealer_id='296065')))
    monkeypatch.setattr(agent.tool_executor, 'execute_measure_request',
                        lambda request: pytest.fail('queue read for a single dealer'))
    events = collect()
    assert not any(event['type'] in ('text', 'complete') for event in events)
    assert events[-1]['type'] == 'error'


def test_final_generation_is_buffered_until_validated_and_preserves_evidence(monkeypatch):
    async def exercise():
        entered, gate = asyncio.Event(), asyncio.Event()
        class FinalGateProvider(Provider):
            async def create(self, **kwargs):
                self.calls.append(kwargs)
                entered.set()
                await gate.wait()
                return final_response(kwargs, text='I counted 806 activations for dealer 74050 in 202603.')
        fake = FinalGateProvider([Stream('Private interpretation.', tool=scope_tool(), stop='tool_use')])
        monkeypatch.setattr(agent, 'new_client', lambda key: fake)
        events = []
        async def consume():
            async for event in agent.run_agent_stream('How many activations?'):
                events.append(event)
        task = asyncio.create_task(consume())
        await asyncio.wait_for(entered.wait(), 3)
        assert any(e['type'] == 'status' and e['phase'] == 'tool_complete' for e in events)
        assert not any(e['type'] == 'text' for e in events)
        gate.set()
        await asyncio.wait_for(task, 3)
        assert [e['text'] for e in events if e['type'] == 'text'] == [
            events[-1]['response']]
        assert events[-1]['response'].split('\n\n')[0] == 'I counted 806 activations for dealer 74050 in March 2026.'
        assert events[-1]['raw_data']['measure_evidence']['measures'][0]['periods'][0]['total'] == 806
        assert len(fake.calls) == 2
    asyncio.run(exercise())


def test_cancelling_final_generation_closes_client_without_publishing(monkeypatch):
    async def exercise():
        entered, cancelled = asyncio.Event(), asyncio.Event()
        class WaitingFinalProvider(Provider):
            async def create(self, **kwargs):
                self.calls.append(kwargs)
                entered.set()
                try:
                    await asyncio.Event().wait()
                finally:
                    cancelled.set()
        fake = WaitingFinalProvider([Stream('Private draft', tool=scope_tool(), stop='tool_use')])
        monkeypatch.setattr(agent, 'new_client', lambda key: fake)
        events = []
        async def consume():
            async for event in agent.run_agent_stream('How many activations?'):
                events.append(event)
        task = asyncio.create_task(consume())
        await asyncio.wait_for(entered.wait(), 3)
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task
        assert cancelled.is_set()
        assert not any(e['type'] in ('text', 'complete') for e in events)
        fake.close.assert_awaited_once()
    asyncio.run(exercise())


def test_failed_final_composition_emits_retryable_error_with_evidence(monkeypatch):
    fake = provider(monkeypatch, Stream('', tool=scope_tool(), stop='tool_use'))
    fake.create = AsyncMock(side_effect=RuntimeError('private provider detail'))
    events = collect()
    assert events[-1]['type'] == 'error'
    assert events[-1]['error'] == 'composition_failed'
    assert not any(event['type'] in {'text', 'complete'} for event in events)
    evidence = next(event['raw_data'] for event in events if event.get('raw_data'))
    assert evidence['measure_evidence']['measures'][0]['periods'][0]['total'] == 806
    assert 'private provider detail' not in str(events)
    fake.close.assert_awaited_once()
