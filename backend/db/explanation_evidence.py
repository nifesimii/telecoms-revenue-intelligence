"""Scoped authoritative finding evidence for deterministic explanations.

Reads existing query/payment/assurance boundaries only; no inference or SQL.
"""
from __future__ import annotations

import json
import time
from typing import Any, Callable

from backend.db.connection import execute_query
from backend.db.commission_workspace import provenance


def _df_to_records(frame):
    return json.loads(frame.to_json(orient='records', date_format='iso', default_handler=str))


class FindingEvidenceUnavailable(ValueError):
    """The requested finding is absent or no longer matches authoritative data."""


def assemble_finding_evidence(
    request: dict[str, Any], *, check_active: Callable[[], None] | None = None,
) -> dict[str, Any]:
    """Retrieve and verify a finding without a model choosing data-access tools.

    This is an application entry point, not an additional model-callable tool.
    Existing assurance services own finding rules; query and payment adapters
    own data access. Filter exact identities before any detail cap is applied.
    check_active guards each operation and its return. Cancellation cannot interrupt
    a blocking source read already running, but prevents subsequent evidence reads.
    """
    import asyncio
    from backend import config
    from backend.assurance.registry import ASSURANCE_REGISTRY
    from backend.assurance.payment_assurance import classify_payment_status
    from backend.audit.payment_data import payment_lookup, RECON_TO_STATUS

    dealer_id, period = request['dealer_id'], request['mon_period']
    scope = request['finding']
    module = scope['module']
    product = scope.get('product_code')
    parameters = {'mon_period': period, 'distributor_code': dealer_id}
    raw_data: dict[str, Any] = {}
    tools_called: list[str] = []
    timings = []

    def timed(name, operation):
        if check_active is not None:
            check_active()
        started = time.monotonic()
        try:
            result = operation()
            if check_active is not None:
                check_active()
            return result
        finally:
            timings.append({'tool': name, 'duration_seconds': round(time.monotonic() - started, 4)})

    caveats = ['Absence of evidence does not establish a zero amount or a root cause.']
    if config.USE_SAMPLE_DATA:
        caveats.append('Activation and inventory evidence uses local sample data, not a live source read.')

    def query_tool(name: str) -> dict[str, Any]:
        frame = timed(name, lambda: execute_query(name, parameters))
        total = len(frame)
        cap = 20 if name == 'get_zero_commission_records' else 500
        envelope = {'tool': name, 'parameters': parameters,
                    'rows': _df_to_records(frame.head(cap)),
                    'row_count': min(total, cap), 'total_rows': total,
                    'truncated': total > cap}
        raw_data[name] = envelope
        tools_called.append(name)
        return envelope

    if module == 'payment':
        frame = timed('get_payment_summary', lambda: payment_lookup(period, config.PAYMENT_SOURCE))
        match = (frame[frame['dealer_id'].astype(str) == dealer_id]
                 if 'dealer_id' in frame else frame.iloc[:0])
        if match.empty or product:
            raise FindingEvidenceUnavailable()
        rows = _df_to_records(match)
        payment = rows[0]
        # Reuse the same source status projection as the Payments API/Overview.
        payment_status = (RECON_TO_STATUS.get(payment.get('reconciliation_status'), 'PENDING')
                          if config.PAYMENT_SOURCE == 'apdp' else payment.get('payment_status'))
        _, finding_type = classify_payment_status(str(payment_status))
        if payment_status == 'FULLY_PAID' or finding_type != scope['type']:
            raise FindingEvidenceUnavailable()
        source = 'APDP' if config.PAYMENT_SOURCE == 'apdp' else 'SIMULATED'
        raw_data['get_payment_summary'] = {
            'tool': 'get_payment_summary', 'parameters': parameters,
            'data_source': source, 'rows': rows, 'row_count': len(rows),
            'payment_status': payment_status,
        }
        tools_called.append('get_payment_summary')
        finding = {'module': module, 'type': finding_type, 'dealer_id': dealer_id,
                   'dealer_name': payment.get('dealer_name') or dealer_id}
        if source == 'SIMULATED':
            caveats.append('Payment figures are SIMULATED, not actual Oracle AP disbursement records.')
        else:
            caveats.append('APDP is recorded settlement evidence; missing statement or settlement records do not establish zero entitlement or payment.')
        # A linked activation/inventory flag is not proof; fetch the actual
        # dealer findings when the source claims such a link.
        linked = payment.get('exception_flag')
        modules = ('activation', 'inventory') if linked else ()
        for linked_module in modules:
            result = timed(linked_module + '_assurance', lambda: asyncio.run(ASSURANCE_REGISTRY[linked_module].run(period, dealer_id)))
            matching = [f for f in result.findings if str(f.get('dealer_id')) == dealer_id]
            key = 'get_' + ('activation_exceptions' if linked_module == 'activation' else 'inventory_comparison')
            raw_data[key] = {'parameters': parameters, 'findings': matching[:50],
                             'total_findings': len(matching), 'truncated': len(matching) > 50,
                             'metadata': result.metadata}
            tools_called.append(key)
    else:
        result = timed(module + '_assurance', lambda: asyncio.run(ASSURANCE_REGISTRY[module].run(period, dealer_id)))
        matching = [f for f in result.findings
                    if str(f.get('dealer_id')) == dealer_id and f.get('type') == scope['type']
                    and (not product or str(f.get('product_code')) == product)]
        if not matching:
            raise FindingEvidenceUnavailable()
        finding = matching[0]
        if module == 'inventory':
            # Assurance evidence is uncapped before matching, unlike the
            # composite dossier's first 15 inventory products.
            name = 'get_inventory_comparison'
            frame = timed(name, lambda: execute_query(name, {'mon_period': period}))
            frame = frame[frame['dealer_id'].astype(str) == dealer_id]
            if product:
                frame = frame[frame['product_code'].astype(str) == product]
            frame = frame[frame['finding_type'] == 'CONFIRMED_MISMATCH']
            raw_data[name] = {'tool': name, 'parameters': {**parameters, 'product_code': product},
                              'rows': _df_to_records(frame.head(50)), 'total_rows': len(frame),
                              'truncated': len(frame) > 50, 'metadata': result.metadata}
            tools_called.append(name)
            caveats.append('Inventory detail is limited to 50 matching products; missing invoices are not confirmed mismatches. Preserve synthetic scenario and data-window notes.')
        else:
            summary = query_tool('get_dealer_summary')
            rows = summary['rows']
            dealer = next((r for r in rows if str(r.get('dealer_id')) == dealer_id), None)
            if dealer is None:
                raise FindingEvidenceUnavailable()
            if module == 'activation':
                raw_data['get_activation_exceptions'] = {'parameters': parameters,
                    'findings': matching, 'metadata': result.metadata}
                tools_called.append('get_activation_exceptions')
            if dealer.get('zero_commission_count', 0):
                zero = query_tool('get_zero_commission_records')
                caveats.append('Zero-record details may be capped at 20; do not extrapolate root-cause counts from a bounded sample. Classify only records supported by the available fields and KB.')
                if zero.get('truncated'):
                    caveats.append(zero.get('truncation_note', 'Zero-record evidence is truncated.'))

    activation_tools = ('get_dealer_summary', 'get_zero_commission_records',
                        'get_activation_exceptions')
    activation_evidence = [raw_data[name] for name in activation_tools if name in raw_data]
    if activation_evidence:
        activation_source = provenance(period, 'activation')
        for envelope in activation_evidence:
            envelope['provenance'] = activation_source
        if 'synthetic' in activation_source['source'].lower():
            caveats.append('Synthetic activation figures are fictional demo records, not evidence of actual partner entitlement or amounts owed.')

    raw_data['explanation_scope'] = {'dealer_id': dealer_id, 'mon_period': period,
                                     'finding': scope, 'verified_finding': finding,
                                     'caveats': caveats}
    return {'tools_called': tools_called, 'raw_data': raw_data, 'timings': timings}
