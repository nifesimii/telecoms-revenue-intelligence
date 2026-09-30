"""Bounded provider I/O and privacy-safe latency telemetry shared by agents."""
from __future__ import annotations

import asyncio
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
import json
import logging
import math
import time
from typing import Any, AsyncIterator
from uuid import uuid4

import anthropic
import httpx

logger = logging.getLogger(__name__)
REQUEST_DEADLINE_SECONDS = 90.0
HTTP_TIMEOUT = httpx.Timeout(connect=5.0, read=30.0, write=10.0, pool=5.0)


def new_client(api_key: str) -> anthropic.AsyncAnthropic:
    # The application owns the only retry budget; SDK retries must stay off.
    return anthropic.AsyncAnthropic(api_key=api_key, max_retries=0, timeout=HTTP_TIMEOUT)


def cached_system(prompt: str) -> list[dict[str, Any]]:
    # The system breakpoint also caches preceding tool definitions. Keep the KB whole.
    return [{"type": "text", "text": prompt, "cache_control": {"type": "ephemeral"}}]


def _retry_delay(exc: Exception) -> float | None:
    if isinstance(exc, anthropic.APIStatusError):
        if exc.status_code not in (408, 409, 429) and exc.status_code < 500:
            return None
        headers = exc.response.headers
        try:
            if "retry-after-ms" in headers:
                delay = float(headers["retry-after-ms"]) / 1000
            elif "retry-after" in headers:
                try:
                    delay = float(headers["retry-after"])
                except ValueError:
                    target = parsedate_to_datetime(headers["retry-after"])
                    delay = (target - datetime.now(timezone.utc)).total_seconds()
            else:
                delay = 1.0
            return max(0.0, delay) if math.isfinite(delay) else 1.0
        except (ValueError, TypeError, OverflowError):
            return 1.0
    if isinstance(exc, anthropic.APIConnectionError):
        return 1.0
    return None


class InferenceRun:
    """One request budget across model iterations, evidence work, and retry waits."""

    def __init__(self, entry_point: str):
        self.entry_point = entry_point
        self.request_id = uuid4().hex
        self.started = time.monotonic()
        self.deadline = self.started + REQUEST_DEADLINE_SECONDS
        self.retry_count = 0
        self.model_calls = 0
        self.chat_text_emitted = False

    def remaining(self) -> float:
        remaining = self.deadline - time.monotonic()
        if remaining <= 0:
            raise TimeoutError("Explanation deadline exceeded")
        return remaining

    def log(self, event: str, **fields: Any) -> None:
        """Callers supply only timings, counts, fixed statuses and tool names."""
        logger.info(json.dumps({"event": event, "request_id": self.request_id,
                                "entry_point": self.entry_point, **fields}))

    def record_usage(self, response: Any) -> None:
        usage = getattr(response, "usage", None)
        counts = {name: getattr(usage, name, 0) or 0 for name in (
            "input_tokens", "output_tokens", "cache_creation_input_tokens", "cache_read_input_tokens")}
        self.log("inference_usage", **counts)

    async def _retry(self, exc: Exception, emitted: bool = False) -> bool:
        delay = _retry_delay(exc)
        if emitted or delay is None or self.retry_count >= 1:
            return False
        if delay >= self.remaining():
            raise TimeoutError("Provider retry wait exceeds remaining deadline") from None
        self.retry_count += 1
        self.log("inference_retry", retry_count=self.retry_count, wait_seconds=delay,
                 error_type=type(exc).__name__)
        await asyncio.sleep(delay)
        return True

    async def create(self, client: Any, **kwargs: Any) -> Any:
        while True:
            started = time.monotonic()
            self.model_calls += 1
            status = "failed"
            finished = None
            try:
                async with asyncio.timeout(self.remaining()):
                    response = await client.messages.create(**kwargs)
                status = "complete"
                self.record_usage(response)
                return response
            except Exception as exc:
                finished = time.monotonic()
                if not await self._retry(exc):
                    raise
            finally:
                self.log("inference_call", model_call=self.model_calls, status=status,
                         duration_seconds=round((finished or time.monotonic()) - started, 4))

    async def stream_text(self, client: Any, **kwargs: Any) -> AsyncIterator[str]:
        emitted = False
        while True:
            started = time.monotonic()
            self.model_calls += 1
            status = "failed"
            finished = None
            try:
                async with asyncio.timeout(self.remaining()):
                    async with client.messages.stream(**kwargs) as stream:
                        message_stopped = False
                        async for event in stream:
                            if event.type == "message_stop":
                                message_stopped = True
                            if event.type == "text" and event.text:
                                text = event.text
                                if not emitted:
                                    self.log("inference_first_text", duration_seconds=round(time.monotonic() - self.started, 4))
                                emitted = True
                                yield text
                        response = await stream.get_final_message()
                        self.record_usage(response)
                        if not message_stopped or response.stop_reason not in ("end_turn", "stop_sequence"):
                            raise RuntimeError("Explanation stream did not complete successfully")
                status = "complete"
                return
            except Exception as exc:
                finished = time.monotonic()
                if not await self._retry(exc, emitted=emitted):
                    raise
            finally:
                self.log("inference_call", model_call=self.model_calls, status=status,
                         duration_seconds=round((finished or time.monotonic()) - started, 4))

    async def create_streamed(self, client: Any, emit, **kwargs: Any) -> Any:
        """Tool-enabled generation; text stays provisional until verified end turn."""
        while True:
            started = time.monotonic()
            self.model_calls += 1
            status = "failed"
            finished = None
            try:
                async with asyncio.timeout(self.remaining()):
                    async with client.messages.stream(**kwargs) as stream:
                        message_stopped = False
                        async for event in stream:
                            if event.type == "message_stop":
                                message_stopped = True
                            elif event.type == "text" and event.text:
                                if not self.chat_text_emitted:
                                    self.log("inference_first_text", duration_seconds=round(time.monotonic() - self.started, 4))
                                self.chat_text_emitted = True
                                await emit({"type": "text", "text": event.text})
                            elif event.type == "content_block_start" and event.content_block.type == "tool_use":
                                # Clear planning prose immediately when a tool is selected.
                                await emit({"type": "status", "phase": "tool_start",
                                            "tool": event.content_block.name, "reset": True})
                        response = await stream.get_final_message()
                        self.record_usage(response)
                        if not message_stopped or response.stop_reason not in ("end_turn", "stop_sequence", "tool_use"):
                            raise RuntimeError("Chat stream did not complete successfully")
                status = "complete"
                return response
            except Exception as exc:
                finished = time.monotonic()
                if not await self._retry(exc, emitted=self.chat_text_emitted):
                    raise
            finally:
                self.log("inference_call", model_call=self.model_calls, status=status,
                         duration_seconds=round((finished or time.monotonic()) - started, 4))

    def finish(self, status: str) -> None:
        self.log("inference_request", status=status, model_calls=self.model_calls,
                 retry_count=self.retry_count, duration_seconds=round(time.monotonic() - self.started, 4))
