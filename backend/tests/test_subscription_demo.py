"""Approved seams: offline fixture examples, bounded API, assistant provenance."""
from backend.data.generate_subscription_demo import generate_records


def test_fixture_records_full_revenue_commission_and_threshold_per_device():
    records = {r['scenario']: r for r in generate_records('202606')}
    assert records['eligible']['recorded_subscription_revenue_ngn'] == 10000
    assert records['eligible']['simulated_commission_ngn'] == 500
    assert records['threshold']['simulated_commission_ngn'] == 250
    assert records['below_minimum']['simulated_commission_ngn'] == 0
    assert records['below_minimum']['reason'] == 'below_minimum'
    assert records['below_minimum']['dealer_expectation_ngn'] == 200
    assert records['below_minimum']['variance_ngn'] == -200


def test_fixture_evidence_states_remain_distinct():
    records = {r['scenario']: r for r in generate_records('202605')}
    assert records['eligible']['payment_status'] == 'paid'
    assert records['overdue']['payment_status'] == 'overdue'
    assert records['overdue']['outstanding_ngn'] == 600
    assert records['unknown_payment']['amount_paid_ngn'] is None
    assert records['unknown_payment']['outstanding_ngn'] is None
    assert records['unknown_payment']['payment_status'] == 'unknown'
    assert records['no_renewal']['reason'] == 'no_paid_subscription'
    assert records['no_renewal']['churn_indicator'] is False
    assert records['churn_context']['churn_indicator'] is True
    assert records['churn_context']['reason'] == 'no_paid_subscription'
    assert {r['scenario']: r for r in generate_records('202601')}['missing_history']['churn_indicator'] is None
    assert records['missing_history']['churn_indicator'] is True
    assert records['unknown_activity']['paid_subscription_count'] is None
    assert records['unknown_activity']['simulated_commission_ngn'] is None
    assert records['unknown_activity']['recorded_subscription_revenue_ngn'] is None
    assert records['expired']['reason'] == 'expired_eligibility'
    assert records['expired']['simulated_commission_ngn'] == 0
    june = {r['scenario']: r for r in generate_records('202606')}
    assert june['overdue']['payment_status'] == 'not_yet_due'
    assert june['overdue']['due_date'] == '2026-07-31'
    assert june['eligible']['evidence_as_of'] == '2026-07-15'


def test_anniversary_is_exclusive_and_renewal_does_not_restart_eligibility():
    from backend.data.generate_subscription_demo import calculate_record
    row = calculate_record(mon_period='202606', first_activation_date='2025-06-15',
        purchases=[{'date': '2026-06-14', 'status': 'PAID', 'amount_ngn': 5000},
                   {'date': '2026-06-15', 'status': 'PAID', 'amount_ngn': 10000},
                   {'date': '2026-06-20', 'status': 'FAILED', 'amount_ngn': 20000}],
        dealer_expectation_ngn=750)
    assert row['recorded_subscription_revenue_ngn'] == 15000
    assert row['eligible_revenue_ngn'] == 5000
    assert row['simulated_commission_ngn'] == 250
    assert row['variance_ngn'] == -500
    assert row['eligibility_end_exclusive'] == '2026-06-15'


def test_bounded_collection_detail_and_lazy_device_evidence(monkeypatch):
    from fastapi.testclient import TestClient
    from backend.main import app
    from backend import config
    monkeypatch.setattr(config, 'USE_SAMPLE_DATA', True)
    client = TestClient(app)
    response = client.get('/subscriptions', params={'mon_period': '202605', 'limit': 2})
    assert response.status_code == 200
    page = response.json()
    assert len(page['items']) == 2
    assert page['total'] == 8
    assert page['summary']['device_count'] == 10
    assert page['summary']['simulated_commission_ngn'] is None  # incomplete evidence is not zero
    assert page['summary']['known_simulated_commission_ngn'] == 1750
    assert page['synthetic'] is True
    assert page['commission_available'] is True
    assert page['policy_label'] == 'Illustrative subscription commission policy—not confirmed MTN terms.'
    filtered = client.get('/subscriptions', params={'mon_period': '202605', 'search': 'Threshold'}).json()
    assert filtered['total'] == 1
    assert filtered['filtered_summary']['simulated_commission_ngn'] == 250
    detail = client.get('/subscriptions/SYN-SUB-002/detail', params={'mon_period': '202605'}).json()
    assert detail['account']['recorded_subscription_revenue_ngn'] == 9000
    assert detail['account']['simulated_commission_ngn'] == 250
    assert detail['account']['variance_ngn'] == -200
    assert 'devices' not in detail
    evidence = client.get('/subscriptions/SYN-SUB-002/devices', params={'mon_period': '202605', 'limit': 1}).json()
    assert len(evidence['items']) == 1
    assert evidence['total'] == 2
    assert evidence['items'][0]['selling_dealer_id'] == 'SYN-SUB-002'
    assert evidence['items'][0]['policy_label'] == page['policy_label']
    assert client.get('/subscriptions', params={'mon_period': '202605', 'limit': 101}).status_code == 422
    assert client.get('/subscriptions', params={'mon_period': '202613'}).status_code == 422
    assert client.get('/subscriptions', params={'mon_period': '202605', 'sort_by': 'SQL'}).status_code == 422
    assert client.get('/subscriptions/absent/detail', params={'mon_period': '202605'}).status_code == 404


def test_histories_agree_with_other_months_and_never_predate_activation():
    from datetime import date
    from backend.data.generate_subscription_demo import PERIODS
    rows = {(r['imei'], p): r for p in PERIODS for r in generate_records(p)}
    for row in rows.values():
        for h in row['history']:
            if h['has_paid_subscription']:
                assert h['mon_period'] >= row['first_activation_date'].replace('-', '')[:6]
            prior = rows.get((row['imei'], h['mon_period']))
            if prior:
                observed = None if prior['paid_subscription_count'] is None else prior['paid_subscription_count'] > 0
                assert h['has_paid_subscription'] == observed


def test_unknown_inputs_and_leap_anniversary_are_preserved():
    from backend.data.generate_subscription_demo import calculate_record
    row = calculate_record(mon_period='202502', first_activation_date='2024-02-29',
        purchases=[{'date': '2025-02-28', 'status': 'PAID', 'amount_ngn': 6000}], dealer_expectation_ngn=300)
    assert row['eligibility_end_exclusive'] == '2025-02-28'
    assert row['simulated_commission_ngn'] == 0
    row = calculate_record(mon_period='202606', first_activation_date=None,
        purchases=[{'date': '2026-06-10', 'status': 'PAID', 'amount_ngn': 6000}], dealer_expectation_ngn=None)
    assert row['recorded_subscription_revenue_ngn'] == 6000
    assert row['simulated_commission_ngn'] is None
    assert row['variance_ngn'] is None
    assert row['reason'] == 'unknown_evidence'


def test_export_filters_unknown_evidence_and_live_revenue_only(monkeypatch):
    import csv
    import io
    import pandas as pd
    from fastapi.testclient import TestClient
    from backend.main import app
    from backend import config
    from backend.db import connection
    monkeypatch.setattr(config, 'USE_SAMPLE_DATA', True)
    client = TestClient(app)
    rows = list(csv.DictReader(io.StringIO(client.get('/subscriptions/export', params={
        'mon_period': '202605', 'payment_status': 'unknown'}).text)))
    assert len(rows) == 2
    assert all(r['amount_paid_ngn'] == '' for r in rows)
    assert all(r['policy_label'] == 'Illustrative subscription commission policy—not confirmed MTN terms.' for r in rows)
    assert all(r['synthetic'] == 'True' for r in rows)
    empty = client.get('/subscriptions', params={'mon_period': '190001'}).json()
    assert empty['total'] == 0
    assert empty['summary']['simulated_commission_ngn'] is None
    assert empty['availability'] == 'no_source_records'
    monkeypatch.setattr(config, 'USE_SAMPLE_DATA', False)
    # Presto is the external read boundary; no production connection is made.
    monkeypatch.setattr(connection, '_run_presto', lambda *a: pd.DataFrame([{
        'dealer_id': 'live', 'dealer_name': 'Live revenue', 'account_profile_class': None,
        'device_count': 2, 'total_subscription_amount_ngn': 15000, 'zero_amount_count': 0}]))
    page = client.get('/subscriptions', params={'mon_period': '202605'}).json()
    assert page['availability'] == 'revenue_only'
    assert page['synthetic'] is False
    assert page['commission_available'] is False
    assert page['items'][0]['recorded_subscription_revenue_ngn'] == 15000
    for key in ('simulated_commission_ngn', 'eligible_revenue_ngn', 'amount_paid_ngn', 'outstanding_ngn', 'variance_ngn'):
        assert page['items'][0][key] is None
    evidence = client.get('/subscriptions/live/devices', params={'mon_period': '202605'}).json()
    assert evidence['evidence_available'] is False
    assert evidence['items'] == []
    assert evidence['policy_label'] is None


def test_subscription_assistant_tools_return_bounded_provenance(monkeypatch):
    import json
    from backend import config
    from backend.agent.tool_executor import execute_tool
    from backend.agent.tools import TOOL_NAMES
    monkeypatch.setattr(config, 'USE_SAMPLE_DATA', True)
    assert 'get_subscription_summary' in TOOL_NAMES
    summary = execute_tool({'id': 's', 'name': 'get_subscription_summary', 'input': {'mon_period': '202605', 'limit': 1}})
    payload = json.loads(summary['content'])
    assert payload['synthetic'] is True
    assert payload['policy_label'] == 'Illustrative subscription commission policy—not confirmed MTN terms.'
    assert len(payload['items']) == 1
    assert payload['total'] == 8
    evidence = execute_tool({'id': 'e', 'name': 'get_subscription_devices', 'input': {
        'mon_period': '202605', 'distributor_code': 'SYN-SUB-002', 'limit': 1}})
    assert len(json.loads(evidence['content'])['items']) == 1
    assert execute_tool({'id': 'e', 'name': 'get_subscription_devices', 'input': {
        'mon_period': '202605', 'distributor_code': 'SYN-SUB-002', 'limit': 101}})['is_error'] is True


import pytest


@pytest.mark.parametrize('mode', ['tool_answer', 'history_followup', 'failure', 'iteration_limit'])
def test_chat_always_retains_synthetic_policy_provenance(monkeypatch, mode):
    from types import SimpleNamespace
    from unittest.mock import AsyncMock, MagicMock
    from fastapi.testclient import TestClient
    from backend.main import app
    from backend.agent import agent
    from backend import config
    monkeypatch.setattr(config, 'USE_SAMPLE_DATA', True)
    label = 'Illustrative subscription commission policy—not confirmed MTN terms.'
    text = SimpleNamespace(type='text', text='Recorded commission: NGN 500.00.',
        model_dump=lambda: {'type': 'text', 'text': 'Recorded commission: NGN 500.00.'})
    tool = SimpleNamespace(type='tool_use', id='s', name='get_subscription_summary',
        input={'mon_period': '202605', 'distributor_code': 'SYN-SUB-001'},
        model_dump=lambda: {'type': 'tool_use', 'id': 's', 'name': 'get_subscription_summary',
                            'input': {'mon_period': '202605', 'distributor_code': 'SYN-SUB-001'}})
    history = []
    if mode in {'history_followup', 'failure'}:
        history = [{'role': 'assistant', 'content': f'Synthetic demo data. {label} NGN 500.00.'}]
    responses = ([SimpleNamespace(content=[tool]), SimpleNamespace(content=[text])] if mode == 'tool_answer'
                 else [SimpleNamespace(content=[text, tool])] * agent.MAX_TOOL_ITERATIONS if mode == 'iteration_limit'
                 else [RuntimeError('external service unavailable')] if mode == 'failure'
                 else [SimpleNamespace(content=[text])])
    sdk = MagicMock()
    sdk.messages.create = AsyncMock(side_effect=responses)
    monkeypatch.setattr(agent.anthropic, 'AsyncAnthropic', lambda **kwargs: sdk)
    response = TestClient(app).post('/chat', json={'message': 'Explain that amount.',
        'mon_period': '202605', 'conversation_history': history})
    assert response.status_code == 200
    answer = response.json()['response']
    assert label in answer
    assert 'Synthetic demo data' in answer


def test_live_null_revenue_and_classification_do_not_become_zero(monkeypatch):
    import pandas as pd
    from fastapi.testclient import TestClient
    from backend.main import app
    from backend import config
    from backend.db import connection
    monkeypatch.setattr(config, 'USE_SAMPLE_DATA', False)
    monkeypatch.setattr(connection, '_run_presto', lambda *a: pd.DataFrame([{
        'dealer_id': 'unknown', 'dealer_name': 'Unverified', 'account_profile_class': float('nan'),
        'device_count': 1, 'total_subscription_amount_ngn': float('nan'), 'zero_amount_count': 0}]))
    response = TestClient(app).get('/subscriptions', params={'mon_period': '202605'})
    assert response.status_code == 200
    row = response.json()['items'][0]
    assert row['recorded_subscription_revenue_ngn'] is None
    assert row['account_profile_class'] is None
