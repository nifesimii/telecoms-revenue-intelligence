"""One generation over deterministic, scoped evidence; no model-selected tools."""
from __future__ import annotations

import asyncio
from copy import deepcopy
import time
from threading import Event

from backend import config
from backend.agent import tool_executor
from backend.agent.agent import MODEL_NAME
from backend.agent.inference import InferenceRun, new_client
from backend.agent.narrative import compose_answer
from backend.agent.answer_evidence import prepare_answer


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
            projected = deepcopy(evidence['raw_data'])
            selected = projected['explanation_scope']
            if (selected['dealer_id'] != request['dealer_id']
                    or selected['mon_period'] != request['mon_period']
                    or selected['finding'] != request['finding']):
                raise tool_executor.FindingEvidenceUnavailable()
            scope = {'kind': 'finding', 'presentation': 'summary',
                     'dealer_id': selected['dealer_id'],
                     'periods': [selected['mon_period']],
                     'finding': selected['finding']}
            if selected['finding']['module'] == 'inventory':
                rows = projected['get_inventory_comparison']['rows']
                product = selected['finding']['product_code']
                if not rows or any(str(row.get('product_code')) != product
                                   or str(row.get('dealer_id')) != selected['dealer_id']
                                   for row in rows):
                    raise tool_executor.FindingEvidenceUnavailable()
                scope['product_code'] = product
                scope['product_name'] = rows[0].get('product_name')
            caveats = list(selected['caveats'])
            # Assurance metadata covers the whole dealer or reporting period.
            # It is provenance, never evidence for the selected inventory product.
            for envelope in projected.values():
                if isinstance(envelope, dict):
                    metadata = envelope.pop('metadata', {})
                    for key in ('coverage_note', 'synthetic_note'):
                        if metadata.get(key) and metadata[key] not in caveats:
                            caveats.append(metadata[key])
            projected['mandatory_disclosures'] = caveats
            context = ('Explain the server-verified finding using its exact account, period and product. '
                       'Only the retrieved investigation establishes population-level causes. '
                       'Payment exception flags do not establish causation.')
            prepared = prepare_answer(
                scope=scope, evidence=projected, tools_called=evidence['tools_called'],
                validated_context=context, mandatory_caveats=caveats,
            )
            async with new_client(config.ANTHROPIC_API_KEY) as client:
                yield {'type': 'status', 'phase': 'thinking', 'reset': False}
                answer = await compose_answer(
                    client, run, question='Explain this verified finding.', history=[],
                    prepared=prepared, sample_mode=config.USE_SAMPLE_DATA,
                    model=MODEL_NAME,
                )
            # Nothing authored by the model crosses the transport until the
            # shared composer has validated the complete answer and attachments.
            yield {'type': 'text', 'text': answer}
            status = 'complete'
            yield {'type': 'complete', 'response': answer,
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
