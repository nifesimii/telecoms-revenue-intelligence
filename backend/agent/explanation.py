"""One generation over deterministic, scoped evidence; no model-selected tools."""
from __future__ import annotations

import asyncio
import time
from threading import Event

from backend import config
from backend.agent import prompts, tool_executor
from backend.agent.agent import MAX_TOKENS, MODEL_NAME
from backend.agent.inference import InferenceRun, cached_system, new_client


async def explain_finding(request: dict):
    run = InferenceRun('explain_finding')
    status = 'error'
    evidence_stopped = Event()

    def check_evidence_active():
        if evidence_stopped.is_set():
            raise TimeoutError('Evidence request ended')
        run.remaining()

    try:
        async with asyncio.timeout(run.remaining()):
            started = time.monotonic()
            try:
                evidence = await asyncio.to_thread(
                    tool_executor.execute_explanation_evidence, request,
                    check_active=check_evidence_active,
                )
            finally:
                # Cancelling to_thread only cancels the await. Signal its worker
                # before yielding a terminal event so it cannot begin another read.
                evidence_stopped.set()
            run.log('evidence_complete', duration_ms=round((time.monotonic() - started) * 1000))
            for timing in evidence.pop('timings', []):
                run.log('tool_complete', **timing)
            prompt = prompts.build_finding_explanation(evidence)
            parts = []
            async with new_client(config.ANTHROPIC_API_KEY) as client:
                async for text in run.stream_text(
                    client, model=MODEL_NAME, max_tokens=MAX_TOKENS,
                    system=cached_system(prompts.get_system_prompt()),
                    messages=[{'role': 'user', 'content': prompt}],
                ):
                    if text:
                        parts.append(text)
                        yield {'type': 'text', 'text': text}
            if not ''.join(parts).strip():
                raise ValueError('empty generation')
            status = 'complete'
            yield {'type': 'complete', 'response': ''.join(parts),
                   'tools_called': evidence['tools_called'],
                   'raw_data': evidence['raw_data'], 'error': None}
    except (asyncio.CancelledError, GeneratorExit):
        status = 'cancelled'
        raise
    except TimeoutError:
        status = 'deadline_exceeded'
        yield {'type': 'error', 'error': status,
               'message': 'The explanation timed out. Please try again.'}
    except tool_executor.FindingEvidenceUnavailable:
        status = 'invalid_evidence'
        yield {'type': 'error', 'error': status,
               'message': 'This finding could not be verified for the selected dealer and period. Refresh the evidence and try again.'}
    except Exception as exc:
        run.log('explanation_failure', error_type=type(exc).__name__)
        yield {'type': 'error', 'error': 'explanation_failed',
               'message': 'The explanation could not be completed. Please try again.'}
    finally:
        run.finish(status)
