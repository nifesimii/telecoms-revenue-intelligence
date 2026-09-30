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


class Provider:
    def __init__(self, rounds):
        self.rounds = iter(rounds)
        self.calls = []
        self.messages = self
        self.close = AsyncMock()

    def stream(self, **kwargs):
        self.calls.append(kwargs)
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


def test_chat_stream_yields_partial_before_provider_completion(monkeypatch):
    async def exercise():
        gate = asyncio.Event()
        fake = provider(monkeypatch, Stream('NGN 100.00 recorded; verification pending.', gate=gate))
        stream = agent.run_agent_stream('Explain', [{'role': 'user', 'content': 'Prior question'}])
        first = await anext(stream)
        assert first['type'] == 'status' and first['phase'] == 'thinking'
        text = await asyncio.wait_for(anext(stream), 1)
        assert text == {'type': 'text', 'text': 'NGN 100.00 recorded; verification pending.'}
        gate.set()
        events = [event async for event in stream]
        assert events[-1]['type'] == 'complete'
        assert events[-1]['response'] == text['text']
        assert fake.calls[0]['system'] == inference.cached_system(prompts.get_system_prompt())
        assert fake.calls[0]['max_tokens'] == agent.MAX_TOKENS
        assert fake.calls[0]['model'] == agent.MODEL_NAME
        assert fake.calls[0]['tools'] == agent.TOOLS
        assert fake.calls[0]['messages'][0]['content'] == 'Prior question'
        fake.close.assert_awaited_once()
    asyncio.run(exercise())


def test_chat_stream_tools_reset_planning_and_retain_provenance(monkeypatch):
    tool = ToolUseBlock(type='tool_use', id='tool_1', name='get_dealer_summary', input={'mon_period': '202606'})
    fake = provider(monkeypatch, Stream('I will inspect records.', tool=tool, stop='tool_use'),
        Stream('Recorded amounts are not proof of settlement.'))
    # Only the documented tool executor boundary is replaced; its full envelope is preserved.
    envelope = {'rows': [], 'source': 'sample', 'caveat': 'Fictional evidence is not verified operational evidence.'}
    monkeypatch.setattr(agent.tool_executor, 'execute_tool', lambda call: {
        'type': 'tool_result', 'tool_use_id': call['id'], 'content': json.dumps(envelope)})
    async def exercise():
        return [event async for event in agent.run_agent_stream('Explain June')]
    events = asyncio.run(exercise())
    assert any(e['type'] == 'status' and e['phase'] == 'tool_start' and e['reset'] for e in events)
    evidence = next(e for e in events if e.get('phase') == 'tool_complete')
    assert evidence['tools_called'] == ['get_dealer_summary']
    assert evidence['raw_data']['get_dealer_summary'] == envelope
    assert events[-1] == {'type': 'complete', 'response': 'Recorded amounts are not proof of settlement.',
        'tools_called': ['get_dealer_summary'], 'raw_data': {'get_dealer_summary': envelope}, 'error': None}
    assert json.loads(fake.calls[1]['messages'][-1]['content'][0]['content']) == envelope


@pytest.mark.parametrize('stop,terminal', [('max_tokens', True), ('end_turn', False), ('pause_turn', True)])
def test_chat_stream_never_completes_truncated_or_unconfirmed_answer(monkeypatch, stop, terminal):
    provider(monkeypatch, Stream('Partial answer', stop=stop, terminal=terminal))
    async def exercise():
        return [event async for event in agent.run_agent_stream('Explain')]
    events = asyncio.run(exercise())
    assert events[-1]['type'] == 'error'
    assert not any(e['type'] == 'complete' for e in events)


def test_chat_stream_cancellation_closes_provider_before_next_tool(monkeypatch):
    async def exercise():
        source = Stream('Partial', gate=asyncio.Event())
        fake = provider(monkeypatch, source)
        stream = agent.run_agent_stream('Explain')
        await anext(stream)
        await anext(stream)
        await stream.aclose()
        assert source.closed
        fake.close.assert_awaited_once()
    asyncio.run(exercise())


def test_chat_stream_http_contract_and_period(monkeypatch):
    fake = provider(monkeypatch, Stream('Confirmed final answer.'))
    with TestClient(app) as client:
        response = client.post('/chat/stream', json={'message': 'Explain', 'mon_period': '202606', 'conversation_history': []})
    assert response.status_code == 200
    assert response.headers['content-type'].startswith('application/x-ndjson')
    assert response.headers['x-accel-buffering'] == 'no'
    events = [json.loads(line) for line in response.text.splitlines()]
    assert events[-1]['type'] == 'complete'
    assert fake.calls[0]['messages'][-1]['content'] == 'Context: reporting period is 202606. Question: Explain'


def test_chat_stream_iteration_cap_does_not_complete_planning_text(monkeypatch):
    tool = ToolUseBlock(type='tool_use', id='tool_1', name='get_dealer_summary', input={'mon_period': '202606'})
    fake = provider(monkeypatch, *(Stream('Inspecting records', tool=tool, stop='tool_use') for _ in range(agent.MAX_TOOL_ITERATIONS)))
    monkeypatch.setattr(agent.tool_executor, 'execute_tool', lambda call: {
        'type': 'tool_result', 'tool_use_id': call['id'], 'content': '{}'})
    async def exercise():
        return [event async for event in agent.run_agent_stream('Explain')]
    events = asyncio.run(exercise())
    assert events[-1]['type'] == 'error'
    assert not any(e['type'] == 'complete' for e in events)
    assert len(fake.calls) == agent.MAX_TOOL_ITERATIONS


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


def test_chat_stream_failure_after_text_does_not_replay(monkeypatch):
    import anthropic
    import httpx
    fake = provider(monkeypatch, Stream('Partial draft', failure=anthropic.APIConnectionError(request=httpx.Request('POST', 'https://api.anthropic.com/v1/messages'))))
    async def exercise():
        return [event async for event in agent.run_agent_stream('Explain')]
    events = asyncio.run(exercise())
    assert [e['text'] for e in events if e['type'] == 'text'] == ['Partial draft']
    assert events[-1]['type'] == 'error'
    assert len(fake.calls) == 1


@pytest.mark.parametrize('stop,terminal,success', [('end_turn', True, True), ('max_tokens', True, False), ('end_turn', False, False)])
def test_real_sdk_chat_stream_confirms_terminal_stop(monkeypatch, stop, terminal, success):
    import anthropic
    import httpx
    events = [
        {'type': 'message_start', 'message': {'id': 'msg_test', 'type': 'message', 'role': 'assistant',
            'model': agent.MODEL_NAME, 'content': [], 'stop_reason': None, 'stop_sequence': None,
            'usage': {'input_tokens': 1, 'output_tokens': 0}}},
        {'type': 'content_block_start', 'index': 0, 'content_block': {'type': 'text', 'text': ''}},
        {'type': 'content_block_delta', 'index': 0, 'delta': {'type': 'text_delta', 'text': 'NGN 100.00; evidence caveat.'}},
        {'type': 'content_block_stop', 'index': 0},
        {'type': 'message_delta', 'delta': {'stop_reason': stop, 'stop_sequence': None}, 'usage': {'output_tokens': 8}},
    ]
    if terminal:
        events.append({'type': 'message_stop'})
    body = ''.join(f"event: {event['type']}\ndata: {json.dumps(event)}\n\n" for event in events)
    calls = []
    def respond(request):
        calls.append(json.loads(request.content))
        return httpx.Response(200, headers={'content-type': 'text/event-stream'}, text=body)
    async def exercise():
        client = anthropic.AsyncAnthropic(api_key='test', max_retries=0,
            http_client=httpx.AsyncClient(transport=httpx.MockTransport(respond)))
        monkeypatch.setattr(agent, 'new_client', lambda key: client)
        received = [event async for event in agent.run_agent_stream('Explain')]
        assert received[1] == {'type': 'text', 'text': 'NGN 100.00; evidence caveat.'}
        assert received[-1]['type'] == ('complete' if success else 'error')
    asyncio.run(exercise())
    assert len(calls) == 1
    assert calls[0]['stream'] is True
    assert calls[0]['system'] == inference.cached_system(prompts.get_system_prompt())


def test_chat_stream_never_retries_after_text_in_an_earlier_tool_round(monkeypatch):
    import anthropic
    import httpx
    tool = ToolUseBlock(type='tool_use', id='tool_1', name='get_dealer_summary', input={'mon_period': '202606'})
    fake = provider(monkeypatch, Stream('Checking records', tool=tool, stop='tool_use'),
        Stream('', failure=anthropic.APIConnectionError(request=httpx.Request('POST', 'https://api.anthropic.com/v1/messages'))))
    monkeypatch.setattr(agent.tool_executor, 'execute_tool', lambda call: {
        'type': 'tool_result', 'tool_use_id': call['id'], 'content': '{}'})
    sleep = AsyncMock()
    monkeypatch.setattr(inference.asyncio, 'sleep', sleep)
    async def exercise():
        return [event async for event in agent.run_agent_stream('Explain')]
    events = asyncio.run(exercise())
    assert events[-1]['type'] == 'error'
    sleep.assert_not_awaited()
    assert len(fake.calls) == 2
