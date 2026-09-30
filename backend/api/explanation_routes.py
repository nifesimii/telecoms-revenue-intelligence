"""NDJSON transport for scoped findings and ordinary tool-enabled Atlas chat."""
import asyncio
from contextlib import aclosing
import json

from fastapi import APIRouter, Request
from fastapi.responses import StreamingResponse

from backend.agent.explanation import explain_finding
from backend.agent.agent import run_agent_stream
from backend.api.schemas import ExplainFindingRequest, ChatRequest

router = APIRouter()


@router.post('/chat/explain')
async def explain(payload: ExplainFindingRequest, request: Request):
    return streaming_response(explain_finding(payload.model_dump()), request)


@router.post('/chat/stream')
async def chat_stream(payload: ChatRequest, request: Request):
    message = (f"Context: reporting period is {payload.mon_period}. Question: {payload.message}"
               if payload.mon_period else payload.message)
    return streaming_response(run_agent_stream(message, list(payload.conversation_history)), request)


def streaming_response(source, request: Request):
    async def events():
        # Some ASGI servers only discover disconnects on send. Watch receive
        # too, so a browser leaving before the first model token cancels I/O.
        producer = asyncio.current_task()
        disconnected = False

        async def watch_disconnect():
            nonlocal disconnected
            while (await request.receive())['type'] != 'http.disconnect':
                pass
            disconnected = True
            producer.cancel()

        watcher = asyncio.create_task(watch_disconnect())
        try:
            async with aclosing(source) as stream:
                async for event in stream:
                    yield json.dumps(event, ensure_ascii=False, allow_nan=False) + '\n'
        except asyncio.CancelledError:
            if not disconnected:
                raise
        finally:
            watcher.cancel()
            await asyncio.gather(watcher, return_exceptions=True)

    return StreamingResponse(events(), media_type='application/x-ndjson', headers={
        'Cache-Control': 'no-store', 'X-Accel-Buffering': 'no',
    })
