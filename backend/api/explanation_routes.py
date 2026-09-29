"""NDJSON transport for the deterministic finding explanation service."""
import asyncio
from contextlib import aclosing
import json

from fastapi import APIRouter, Request
from fastapi.responses import StreamingResponse

from backend.agent.explanation import explain_finding
from backend.api.schemas import ExplainFindingRequest

router = APIRouter()


@router.post('/chat/explain')
async def explain(payload: ExplainFindingRequest, request: Request):
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
            async with aclosing(explain_finding(payload.model_dump())) as stream:
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
