"""Provider-boundary checks: retry amplification, deadlines and safe telemetry."""
import asyncio
import logging
from unittest.mock import AsyncMock

import anthropic
import httpx
import pytest

from backend.agent import inference


def test_persistent_rate_limit_has_only_two_http_attempts(monkeypatch):
    attempts = []

    def respond(request):
        attempts.append(request)
        return httpx.Response(429, headers={"retry-after": "2"}, json={"error": {"type": "rate_limit_error", "message": "secret record"}})

    sleep = AsyncMock()
    monkeypatch.setattr(inference.asyncio, "sleep", sleep)

    async def exercise():
        async with anthropic.AsyncAnthropic(api_key="test", max_retries=0, http_client=httpx.AsyncClient(transport=httpx.MockTransport(respond))) as client:
            with pytest.raises(anthropic.RateLimitError):
                await inference.InferenceRun("test").create(client, model="claude-sonnet-4-5", max_tokens=10, messages=[{"role": "user", "content": "private prompt"}])

    asyncio.run(exercise())
    assert len(attempts) == 2
    sleep.assert_awaited_once_with(2.0)


def test_provider_retry_wait_cannot_exceed_request_deadline(monkeypatch):
    request = httpx.Request("POST", "https://api.anthropic.com/v1/messages")
    response = httpx.Response(429, request=request, headers={"retry-after": "120"})
    client = type("Client", (), {"messages": type("Messages", (), {"create": AsyncMock(side_effect=anthropic.RateLimitError("private error", response=response, body=None))})()})()
    sleep = AsyncMock()
    monkeypatch.setattr(inference.asyncio, "sleep", sleep)
    with pytest.raises(TimeoutError):
        asyncio.run(inference.InferenceRun("test").create(client))
    assert client.messages.create.await_count == 1
    sleep.assert_not_awaited()


def test_hung_provider_is_cancelled_at_overall_deadline(monkeypatch):
    monkeypatch.setattr(inference, "REQUEST_DEADLINE_SECONDS", 0.01)
    cancelled = []

    async def hang(**kwargs):
        try:
            await asyncio.Event().wait()
        finally:
            cancelled.append(True)

    client = type("Client", (), {"messages": type("Messages", (), {"create": staticmethod(hang)})()})()
    with pytest.raises(TimeoutError):
        asyncio.run(inference.InferenceRun("test").create(client))
    assert cancelled == [True]


def test_stream_failure_after_visible_text_never_replays(monkeypatch):
    from types import SimpleNamespace
    request = httpx.Request("POST", "https://api.anthropic.com/v1/messages")

    class Stream:
        async def __aenter__(self):
            return self

        async def __aexit__(self, *args):
            pass

        async def __aiter__(self):
            yield SimpleNamespace(type="text", text="Evidence starts here")
            raise anthropic.APIConnectionError(request=request)

    calls = []
    def stream(**kwargs):
        calls.append(kwargs)
        return Stream()

    client = SimpleNamespace(messages=SimpleNamespace(stream=stream))
    sleep = AsyncMock()
    monkeypatch.setattr(inference.asyncio, "sleep", sleep)
    received = []

    async def exercise():
        with pytest.raises(anthropic.APIConnectionError):
            async for chunk in inference.InferenceRun("test").stream_text(client):
                received.append(chunk)

    asyncio.run(exercise())
    assert received == ["Evidence starts here"]
    assert len(calls) == 1
    sleep.assert_not_awaited()


def test_usage_logs_do_not_contain_prompt_or_response(caplog):
    from types import SimpleNamespace
    response = SimpleNamespace(content="PRIVATE FINANCIAL RECORD", usage=SimpleNamespace(input_tokens=10, output_tokens=4, cache_read_input_tokens=8, cache_creation_input_tokens=0))
    client = SimpleNamespace(messages=SimpleNamespace(create=AsyncMock(return_value=response)))
    with caplog.at_level(logging.INFO, logger=inference.__name__):
        asyncio.run(inference.InferenceRun("test").create(client, messages=[{"role": "user", "content": "SECRET PROMPT"}]))
    assert '"cache_read_input_tokens": 8' in caplog.text
    assert '"request_id":' in caplog.text
    assert "SECRET" not in caplog.text
    assert "PRIVATE" not in caplog.text


def test_sdk_defaults_are_explicit_and_cache_preserves_whole_prompt(monkeypatch):
    from unittest.mock import Mock
    constructor = Mock()
    monkeypatch.setattr(inference.anthropic, "AsyncAnthropic", constructor)
    inference.new_client("test")
    options = constructor.call_args.kwargs
    assert options["max_retries"] == 0
    assert options["timeout"].read == 30.0
    assert options["timeout"].connect == 5.0
    assert inference.cached_system("whole knowledge base") == [{"type": "text", "text": "whole knowledge base", "cache_control": {"type": "ephemeral"}}]


@pytest.mark.parametrize('stop_reason,message_stop,valid', [
    (None, False, False), ('end_turn', False, False),
    ('max_tokens', True, False), ('tool_use', True, False),
    ('end_turn', True, True), ('stop_sequence', True, True),
])
def test_real_sdk_requires_terminal_event_and_success_reason(stop_reason, message_stop, valid):
    import json
    events = [
        {'type': 'message_start', 'message': {'id': 'msg_test', 'type': 'message',
         'role': 'assistant', 'model': 'claude-sonnet-4-5', 'content': [],
         'stop_reason': None, 'stop_sequence': None,
         'usage': {'input_tokens': 1, 'output_tokens': 0}}},
        {'type': 'content_block_start', 'index': 0, 'content_block': {'type': 'text', 'text': ''}},
        {'type': 'content_block_delta', 'index': 0,
         'delta': {'type': 'text_delta', 'text': 'Partial financial explanation'}},
        {'type': 'content_block_stop', 'index': 0},
    ]
    if stop_reason:
        events.append({'type': 'message_delta', 'delta': {'stop_reason': stop_reason,
                       'stop_sequence': None}, 'usage': {'output_tokens': 4}})
    if message_stop:
        events.append({'type': 'message_stop'})
    body = ''.join(f"event: {event['type']}\ndata: {json.dumps(event)}\n\n" for event in events)
    attempts = []
    def respond(request):
        attempts.append(request)
        return httpx.Response(200, headers={'content-type': 'text/event-stream'}, text=body)
    async def exercise():
        async with anthropic.AsyncAnthropic(api_key='test', max_retries=0,
                http_client=httpx.AsyncClient(transport=httpx.MockTransport(respond))) as client:
            async def consume():
                return [chunk async for chunk in inference.InferenceRun('test').stream_text(
                    client, model='claude-sonnet-4-5', max_tokens=100,
                    messages=[{'role': 'user', 'content': 'Explain'}])]
            if valid:
                assert await consume() == ['Partial financial explanation']
            else:
                with pytest.raises(RuntimeError):
                    await consume()
    asyncio.run(exercise())
    assert len(attempts) == 1


@pytest.mark.parametrize('outcome', ['success', 'provider_error', 'empty_answer'])
def test_buffered_chat_logs_answer_ready_only_for_success(monkeypatch, caplog, outcome):
    from types import SimpleNamespace
    from backend.agent import agent

    response = SimpleNamespace(
        content=[SimpleNamespace(type='text', text='NGN 100.00 recorded commission.')]
        if outcome == 'success' else [],
        stop_reason='end_turn', usage=None,
    )
    create = AsyncMock(return_value=response)
    if outcome == 'provider_error':
        create.side_effect = RuntimeError('PRIVATE provider failure')
    client = SimpleNamespace(messages=SimpleNamespace(create=create), close=AsyncMock())
    monkeypatch.setattr(agent, 'new_client', lambda key: client)
    with caplog.at_level(logging.INFO, logger=inference.__name__):
        result = asyncio.run(agent.run_agent('PRIVATE question'))

    import json
    events = [json.loads(record.message) for record in caplog.records
              if record.name == inference.__name__]
    ready = [event for event in events if event['event'] == 'inference_answer_ready']
    assert not any(event['event'] == 'inference_first_text' for event in events)
    if outcome == 'success':
        assert result['response'] == 'NGN 100.00 recorded commission.'
        assert len(ready) == 1
        assert ready[0]['entry_point'] == 'chat'
        assert ready[0]['duration_seconds'] >= 0
        assert ready[0]['request_id'] == events[-1]['request_id']
    else:
        assert result['response'] == ('' if outcome == 'empty_answer' else agent.FALLBACK_RESPONSE)
        assert ready == []
    assert 'PRIVATE' not in caplog.text
    client.close.assert_awaited_once()
