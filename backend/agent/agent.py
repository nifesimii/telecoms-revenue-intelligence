"""One scoped Atlas turn, with provider I/O shared by buffered and streamed chat.

The model resolves intent, then composes an answer from validated, bounded
evidence. Calculations and provenance stay application-owned. Candidate prose
never becomes financial evidence or provisional user-visible text.
"""
from __future__ import annotations

import asyncio
import json
import logging
import inspect
import time
from typing import Any

from backend import config
from backend.agent import prompts, tool_executor
from backend.agent.measure_scope import (
    MeasureScope, SCOPE_TOOL, clarification_response, knowledge_response, unsupported_response, recover_missing_scope, repair_preserves_scope,
)
from backend.agent.measure_response import render_measure_response, render_dealer_codes, render_affiliation, render_discovery
from backend.agent.dealer_resolution import resolve_dealer_name
from backend.agent.inference import InferenceRun, cached_system, new_client
from backend.agent.answer_evidence import prepare_answer
from backend.agent.narrative import compose_answer, NarrativeGroundingError, NARRATIVE_FALLBACK

# --- Model config ---
MODEL_NAME = "claude-sonnet-4-5"
MAX_TOKENS = 2048

# --- User-facing fallback ---
FALLBACK_RESPONSE = (
    "I encountered an error retrieving that data. Please try again."
)


async def run_agent(user_message: str, conversation_history: list | None = None, *,
                    reporting_period: str | None = None,
                    investigation_context: str | None = None) -> dict:
    """Run a complete conversation turn within a single 90-second budget."""
    run = InferenceRun("chat")
    client = None
    status = "failed"
    try:
        async with asyncio.timeout(run.remaining()):
            client = new_client(config.ANTHROPIC_API_KEY)
            result = await _run_turn(client, run, user_message, conversation_history or [],
                                     reporting_period=reporting_period,
                                     investigation_context=investigation_context)
            status = "complete" if result["response"].strip() and result["response"] not in (FALLBACK_RESPONSE, NARRATIVE_FALLBACK) else "failed"
            if status == "complete":
                run.log("inference_answer_ready", duration_seconds=round(time.monotonic() - run.started, 4))
            return result
    except asyncio.CancelledError:
        status = "cancelled"
        raise
    except Exception as exc:
        run.log("inference_failure", error_type=type(exc).__name__)
        return {**_error_response(), 'error': 'deadline_exceeded' if isinstance(exc, TimeoutError) else 'chat_failed'}
    finally:
        run.finish(status)
        if client is not None:
            # Real SDK clients close asynchronously; old test doubles may not.
            try:
                closed = client.close()
                if inspect.isawaitable(closed):
                    await closed
            except Exception as exc:
                run.log("inference_close_failure", error_type=type(exc).__name__)


# The browser contract requires a tool name on tool phases; the concrete
# evidence tools are only known after the bounded measure request runs.
MEASURE_STATUS_TOOL = 'measure_evidence'


async def run_agent_stream(user_message: str, conversation_history: list | None = None, *,
                           reporting_period: str | None = None,
                           investigation_context: str | None = None):
    """Progress and validated text from the shared turn; cancellation owns I/O."""
    run = InferenceRun("chat_stream")
    events = asyncio.Queue(maxsize=1)

    async def produce():
        client = None
        status = "failed"
        try:
            async with asyncio.timeout(run.remaining()):
                client = new_client(config.ANTHROPIC_API_KEY)
                result = await _run_turn(client, run, user_message, conversation_history or [],
                                         reporting_period=reporting_period,
                                         investigation_context=investigation_context,
                                         emit=events.put)
                if not result["response"].strip():
                    raise RuntimeError("Empty answer")
                if result["response"] == NARRATIVE_FALLBACK:
                    # Preserve evidence but keep the turn retryable and out of
                    # successful conversation history in the existing browser.
                    await events.put({'type': 'status', 'phase': 'tool_complete',
                                      'tool': MEASURE_STATUS_TOOL, 'reset': True,
                                      'tools_called': result['tools_called'], 'raw_data': result['raw_data']})
                    await events.put({'type': 'error', 'error': 'composition_failed',
                                      'message': NARRATIVE_FALLBACK})
                    return
                status = "complete"
                await events.put({"type": "complete", **result, "error": None})
        except asyncio.CancelledError:
            status = "cancelled"
            raise
        except Exception as exc:
            run.log("inference_failure", error_type=type(exc).__name__)
            code = "deadline_exceeded" if isinstance(exc, TimeoutError) else "chat_failed"
            await events.put({"type": "error", "error": code,
                              "message": "The answer could not be completed. Please retry."})
        finally:
            run.finish(status)
            if client is not None:
                try:
                    await client.close()
                except Exception as exc:
                    run.log("inference_close_failure", error_type=type(exc).__name__)

    task = asyncio.create_task(produce())
    try:
        yield {"type": "status", "phase": "thinking", "reset": False}
        while True:
            event = await events.get()
            if event["type"] in ("complete", "error"):
                await task
            yield event
            if event["type"] in ("complete", "error"):
                break
    finally:
        if not task.done():
            task.cancel()
        await asyncio.gather(task, return_exceptions=True)


async def _run_turn(client: Any, run: InferenceRun, user_message: str,
                    conversation_history: list, *, reporting_period=None,
                    investigation_context=None, emit=None) -> dict:
    # Keep the latest question distinct from contextual workspace terminology.
    # A presentation overlay keeps historical assistant language current without
    # mutating original messages or rewriting user-authored questions.
    from backend.terminology import normalize_generated_prose
    conversation_history = [
        {**message, 'content': normalize_generated_prose(message['content'])}
        if message.get('role') == 'assistant' and isinstance(message.get('content'), str)
        else dict(message)
        for message in conversation_history
    ]
    messages = list(conversation_history)
    messages.append({'role': 'user', 'content': json.dumps({
        'question': user_message, 'reporting_period': reporting_period,
        'investigation_context': investigation_context,
    }, ensure_ascii=False)})

    async def discard_draft(event):
        # The provider can emit text before the scope tool. None of it is safe
        # to publish, even as provisional text that would later be cleared.
        run.remaining()

    generate = run.create if emit is None else run.create_streamed
    scope = None
    original_candidate = None
    for attempt in range(2):
        response = await generate(
            client, **({'emit': discard_draft} if emit is not None else {}),
            model=MODEL_NAME, max_tokens=MAX_TOKENS,
            system=cached_system(prompts.get_measure_system_prompt()),
            # Not strict: the provider transform loosens fields MeasureScope then rejects.
            tools=[SCOPE_TOOL], tool_choice={'type': 'tool', 'name': SCOPE_TOOL['name']},
            messages=messages,
        )
        blocks = [block for block in response.content if block.type == 'tool_use']
        candidate = (blocks[0].input if response.stop_reason == 'tool_use' and len(blocks) == 1
                     and blocks[0].name == SCOPE_TOOL['name'] else None)
        if attempt == 0:
            original_candidate = candidate
        try:
            scope = MeasureScope.model_validate(candidate)
            if scope.kind == 'knowledge':
                # A paraphrased KB quote is an invalid scope; repair it here
                # rather than fail the turn after scope resolution.
                knowledge_response(scope, prompts.KB_CONTENT, sample_mode=config.USE_SAMPLE_DATA)
            if attempt and not repair_preserves_scope(original_candidate, scope):
                run.log('scope_validation', stage='scope', reason='repair_scope_changed', repair_count=attempt)
                scope = MeasureScope(kind='clarification', clarification='request')
        except ValueError:
            scope = recover_missing_scope(candidate)
            reason = 'missing_scope' if scope is not None else 'invalid_contract'
            run.log('scope_validation', stage='scope', reason=reason, repair_count=attempt)
            if scope is None:
                if attempt or not run.claim_recovery('scope_repair'):
                    scope = MeasureScope(kind='clarification', clarification='request')
                else:
                    messages.append({'role': 'user', 'content':
                        'Return one valid scope contract for the original request. If information is missing, '
                        'use clarification. Do not invent an account, period, or broaden scope.'})
                    continue
        break
    request = scope.model_dump()
    tools_called, raw_data = [], {}

    async def finish_answer(validated_context):
        # Prepare source facts before generation. Rendered prose supplies only
        # application-owned attachments, never additional model facts.
        try:
            answer = await compose_answer(
                client, run, question=user_message, history=conversation_history,
                prepared=prepare_answer(scope=request, evidence=raw_data, tools_called=tools_called,
                                        validated_context=validated_context), sample_mode=config.USE_SAMPLE_DATA,
                model=MODEL_NAME,
            )
        except NarrativeGroundingError:
            run.log('inference_narrative_rejected')
            answer = NARRATIVE_FALLBACK
        except Exception as exc:
            # Retrieval succeeded. Preserve its provenance if only composition
            # fails, without publishing a partial or unvalidated candidate.
            run.log('inference_narrative_failure', error_type=type(exc).__name__)
            answer = NARRATIVE_FALLBACK
        if emit is not None and answer != NARRATIVE_FALLBACK:
            await emit({'type': 'text', 'text': answer})
        return {'response': answer, 'tools_called': tools_called, 'raw_data': raw_data,
                'error': 'composition_failed' if answer == NARRATIVE_FALLBACK else None}

    if scope.kind == 'clarification':
        answer = clarification_response(scope)
        if emit is not None:
            await emit({'type': 'text', 'text': answer})
        return {'response': answer, 'tools_called': [], 'raw_data': {}}
    elif scope.measures == ['portfolio_discovery']:
        if emit is not None:
            await emit({'type': 'status', 'phase': 'tool_start', 'reset': True, 'tool': MEASURE_STATUS_TOOL})
        discovery = await asyncio.to_thread(tool_executor.execute_portfolio_discovery, request)
        run.remaining()
        answer = render_discovery(discovery)
        result = {'response': answer, 'tools_called': discovery['tools'],
                  'raw_data': {'portfolio_discovery': discovery}}
        if emit is not None:
            await emit({'type': 'status', 'phase': 'tool_complete', 'reset': True,
                        'tool': MEASURE_STATUS_TOOL, 'tools_called': result['tools_called'], 'raw_data': result['raw_data']})
            await emit({'type': 'text', 'text': answer})
        return result
    elif scope.kind == 'unsupported':
        answer = unsupported_response(scope, prompts.KB_CONTENT)
    elif scope.kind == 'knowledge':
        answer = knowledge_response(scope, prompts.KB_CONTENT, sample_mode=config.USE_SAMPLE_DATA)
    elif scope.kind == 'identity':
        evidence = await asyncio.to_thread(tool_executor.execute_dealer_lookup, scope.model_dump())
        run.remaining()
        answer = render_dealer_codes(evidence)
        tools_called = ['get_dealer_codes']
        raw_data = {'get_dealer_codes': evidence}
    elif scope.kind == 'affiliation':
        # Group the sibling account codes recorded under one dealer for a single month; the
        # collector discovers codes by recorded name, so no prior name-to-code resolution is needed.
        evidence = await asyncio.to_thread(tool_executor.execute_affiliation, scope.model_dump())
        run.remaining()
        answer = render_affiliation(evidence)
        tools_called = list(evidence['tools'])  # only the reads that actually ran
        raw_data = {'affiliation': evidence}
    else:
        if emit is not None:
            await emit({'type': 'status', 'phase': 'tool_start', 'reset': True,
                        'tool': MEASURE_STATUS_TOOL})
        resolution = None
        if request.get('dealer_name'):
            # A named dealer becomes one recorded code before any evidence read.
            resolution = await asyncio.to_thread(resolve_dealer_name, request)
            run.remaining()
            if resolution.status != 'matched':
                tools_called = ['get_dealer_codes'] if resolution.lookup else []
                raw_data = {'get_dealer_codes': resolution.lookup} if resolution.lookup else {}
                if emit is not None:
                    await emit({'type': 'status', 'phase': 'tool_complete', 'reset': True,
                                'tool': MEASURE_STATUS_TOOL, 'tools_called': tools_called, 'raw_data': raw_data})
                if emit is not None:
                    await emit({'type': 'text', 'text': resolution.text})
                return {'response': resolution.text, 'tools_called': tools_called, 'raw_data': raw_data}
            request = {**request, 'dealer_id': resolution.dealer_id, 'dealer_name': None}
        evidence = await asyncio.to_thread(tool_executor.execute_measure_request, request)
        run.remaining()
        answer = render_measure_response(request, evidence)
        # Preserve every requested month in a single bounded evidence envelope.
        # Only projected fields cross the public response boundary.
        evidence_tools = [
            item['tool'] for measure in evidence['measures'] for item in measure['periods']
            if item.get('tool')
        ]
        evidence_tools.extend(item['tool'] for item in evidence.get('explanations', []) if item.get('tool'))
        evidence_tools.extend(evidence.get('investigation', {}).get('tools', []))
        for item in evidence.get('explanations', []):
            evidence_tools.extend(item.get('investigation', {}).get('tools', []))
        tools_called = list(dict.fromkeys(evidence_tools))
        raw_data = {'measure_evidence': evidence}
        if resolution is not None:
            answer = resolution.text + '\n\n' + answer
            tools_called = ['get_dealer_codes', *tools_called]
            raw_data = {'get_dealer_codes': resolution.lookup, **raw_data}
        if emit is not None:
            await emit({'type': 'status', 'phase': 'tool_complete', 'reset': True,
                        'tool': MEASURE_STATUS_TOOL, 'tools_called': tools_called, 'raw_data': raw_data})
    return await finish_answer(answer)


def _error_response() -> dict[str, Any]:
    return {
        "response": FALLBACK_RESPONSE,
        "tools_called": [],
        "raw_data": {},
    }


# ---------------------------------------------------------------------------
# Inline smoke test
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    import sys

    # Windows default stdout is cp1252, which cannot encode the Naira symbol
    # (U+20A6). Force UTF-8 so the smoke-test print() calls don't crash.
    # Only runs in CLI mode — the FastAPI process is unaffected.
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")

    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )

    async def _smoke() -> None:
        question = "Summarise dealer commissions for 202603"
        print(f"USER QUESTION: {question}\n")
        result = await run_agent(question)
        print("=" * 70)
        print("RESPONSE:")
        print("=" * 70)
        print(result["response"])
        print()
        print("=" * 70)
        print(f"TOOLS CALLED  : {result['tools_called']}")
        print(f"RAW DATA KEYS : {list(result['raw_data'].keys())}")
        for name, payload in result["raw_data"].items():
            if isinstance(payload, dict) and "row_count" in payload:
                print(f"  {name}: row_count={payload['row_count']}")

    asyncio.run(_smoke())
