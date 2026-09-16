"""Public saved-evidence workspace contract; no database or audit execution."""
from fastapi.testclient import TestClient
import pytest
from backend.main import app
from backend.db import audit_store

client = TestClient(app)
BASE = '/assurance/audit/records'
PARAMS = {'module': 'inventory_mismatch', 'mon_period': '202603'}

@pytest.fixture
def saved(monkeypatch):
    rows = [dict(trail_id=str(i), partner_code=f'{i // 2}:p{i}', partner_name='Same name',
                 module='inventory_mismatch', mon_period='202603', conclusion='EXCESS_ACTIVATION',
                 confidence='HIGH', caveat_steps=[], caveat_count=0, generated_at='2026-08-05T12:00:00Z',
                 payment_source='ifs', run_id='run-one', pipeline_version='1.0.0',
                 steps=[{'step': 1, 'name': 'mismatch_signal', 'detail': {'dealer_id': str(i // 2), 'product_name': 'Router', 'product_code': f'p{i}', 'activation_count': 8}},
                        {'step': 4, 'name': 'prior_period_stock', 'detail': {'note': 'Misses purchase-only products'}}]) for i in range(60)]
    rows[0]['conclusion'] = 'RECONCILED'
    rows[0]['caveat_steps'] = ['prior_period_stock']
    rows[0]['caveat_count'] = 1
    monkeypatch.setattr(audit_store, 'get_period_trails', lambda period, module: rows)
    return rows

def test_bounded_compact_stable_and_scoped(saved):
    first = client.get(BASE, params=PARAMS).json()
    assert len(first['items']) == 25
    assert 'steps' not in first['items'][0]
    assert first['summary']['trail_count'] == 60
    assert first['summary']['dealer_count'] == 30
    second = client.get(BASE, params={**PARAMS, 'offset': 25}).json()
    assert not ({r['trail_id'] for r in first['items']} & {r['trail_id'] for r in second['items']})
    filtered = client.get(BASE, params={**PARAMS, 'conclusion': 'RECONCILED'}).json()
    assert filtered['filtered_summary']['trail_count'] == 1
    assert filtered['summary']['trail_count'] == 60
    assert filtered['items'][0]['limitations'] == ['Misses purchase-only products']

@pytest.mark.parametrize('params', [{'limit': 101}, {'offset': -1}, {'sort_by': 'steps'}, {'confidence': 'MAGIC'}, {'module': 'unknown'}])
def test_invalid_contract(params, saved):
    assert client.get(BASE, params={**PARAMS, **params}).status_code == 422

def test_search_intersection_and_empty(saved):
    response = client.get(BASE, params={**PARAMS, 'search': 'router', 'caveats': 'with', 'confidence': 'HIGH'}).json()
    assert response['pagination']['total'] == 1
    response = client.get(BASE, params={**PARAMS, 'search': 'missing'}).json()
    assert response['items'] == []
    assert response['summary']['trail_count'] == 60

def test_export_entire_filter_and_formula_safety(saved):
    saved[0]['partner_name'] = '=HYPERLINK("bad")'
    response = client.get(BASE + '/export', params={**PARAMS, 'conclusion': 'EXCESS_ACTIVATION'})
    assert response.status_code == 200
    assert len(response.text.splitlines()) == 60
    response = client.get(BASE + '/export', params=PARAMS)
    assert "'=HYPERLINK" in response.text
    assert '202603' in response.text and 'run-one' in response.text

def test_failure_is_not_empty(monkeypatch):
    def fail(*args):
        raise RuntimeError('password=do-not-expose')
    monkeypatch.setattr(audit_store, 'get_period_trails', fail)
    response = client.get(BASE, params=PARAMS)
    assert response.status_code == 503
    assert 'do-not-expose' not in response.text

def test_exact_subject_filter(saved):
    response = client.get(BASE, params={**PARAMS, 'subject': '0:p1'}).json()
    assert [r['partner_code'] for r in response['items']] == ['0:p1']

def test_exact_detail_preserves_historical_wording_and_identity(monkeypatch):
    original = '1 inside window (should have earned commission)'
    trail = dict(partner_code='D1', partner_name='Dealer', mon_period='202602', module='eligibility_window',
                 conclusion='MIXED_ATTRIBUTION', confidence='HIGH', steps=[dict(step=4, name='classify_against_window', result=original, detail={'inside_window_count': 1})])
    calls = []
    def read(subject, period, module):
        calls.append((subject, period, module))
        return trail if (subject, period, module) == ('D1', '202602', 'eligibility_window') else None
    monkeypatch.setattr(audit_store, 'get_partner_trail', read)
    response = client.get(BASE + '/D1', params={'mon_period': '202602', 'module': 'eligibility_window'})
    assert response.status_code == 200
    step = response.json()['steps'][0]
    assert step['result'] == original
    assert 'other eligibility checks required' in step['presentation_result']
    assert client.get(BASE + '/D1', params={'mon_period': '202603', 'module': 'eligibility_window'}).status_code == 404
    assert len(calls) == 2

def test_not_paid_retains_positive_partial_payment(monkeypatch):
    trail = dict(partner_code='D1', partner_name='Dealer', mon_period='202602', module='zero_commission',
                 conclusion='NOT_PAID', confidence='LOW', steps=[dict(step=5, name='near_match', detail={
                     'partial_payment': True, 'expected_commission_ngn': 1000, 'amount_paid_ngn': 250})])
    monkeypatch.setattr(audit_store, 'get_partner_trail', lambda *args: trail)
    result = client.get(BASE + '/D1', params={'mon_period': '202602'}).json()
    assert result['conclusion'] == 'NOT_PAID'
    assert result['partial_payment'] is True
    assert result['measures']['amount_paid_ngn'] == 250

def test_exact_read_failure_and_empty_success(monkeypatch):
    monkeypatch.setattr(audit_store, 'get_period_trails', lambda *args: [])
    response = client.get(BASE, params=PARAMS)
    assert response.status_code == 200
    assert response.json()['summary']['trail_count'] == 0
    def fail(*args):
        raise RuntimeError('private connection string')
    monkeypatch.setattr(audit_store, 'get_partner_trail', fail)
    response = client.get(BASE + '/D1', params=PARAMS)
    assert response.status_code == 503
    assert 'private connection' not in response.text

def test_duplicate_subject_opens_selected_saved_trail(saved):
    saved[1]['partner_code'] = saved[0]['partner_code']
    response = client.get(BASE + '/0:p0', params={**PARAMS, 'trail_id': '0'})
    assert response.status_code == 200
    assert response.json()['trail_id'] == '0'
    assert response.json()['conclusion'] == 'RECONCILED'
    assert client.get(BASE + '/wrong', params={**PARAMS, 'trail_id': '0'}).status_code == 404
