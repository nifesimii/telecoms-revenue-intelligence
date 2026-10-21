"""Public HTTP regression checks for the finance Overview contract."""
import csv
import io
import os

os.environ["USE_SAMPLE_DATA"] = "true"

import pytest
from fastapi.testclient import TestClient
from backend import config
from backend.main import app


@pytest.fixture
def client(monkeypatch):
    monkeypatch.setattr(config, "USE_SAMPLE_DATA", True)
    monkeypatch.setattr(config, "PAYMENT_SOURCE", "simulated")
    return TestClient(app)


def test_overview_full_counts_and_money_are_not_preview_totals(client):
    response = client.get('/assurance/overview?mon_period=202603&limit=5')
    assert response.status_code == 200
    data = response.json()
    # Enriched March adds three labelled synthetic Inventory findings.
    assert data['finding_count'] == 1679
    assert data['affected_dealers'] == 922
    assert data['total'] == 922
    assert len(data['items']) == 5
    assert data['complete'] is True
    assert data['payment']['total_amount_unpaid'] == 7107305.74
    assert 'records' not in data['payment']
    first = data['items'][0]
    assert first['dealer_id'] == '296065'
    assert first['amount_outstanding'] == 552486.95
    assert first['finding_count'] == 4


def test_queue_pages_do_not_overlap_and_search_is_not_preview_limited(client):
    first = client.get('/assurance/overview?mon_period=202603&limit=5').json()
    second = client.get('/assurance/overview?mon_period=202603&limit=5&offset=5').json()
    assert {r['dealer_id'] for r in first['items']}.isdisjoint(r['dealer_id'] for r in second['items'])
    assert second['finding_count'] == 1679
    # This account is outside the first five; server-side search still finds it.
    code = second['items'][-1]['dealer_id']
    filtered = client.get('/assurance/overview', params={'mon_period': '202603', 'search': code}).json()
    assert any(r['dealer_id'] == code for r in filtered['items'])
    assert filtered['finding_count'] == 1679
    empty = client.get('/assurance/overview?mon_period=202603&search=nonexistent-dealer').json()
    assert empty['total'] == 0
    assert empty['items'] == []
    assert empty['affected_dealers'] == 922


@pytest.mark.parametrize('query', ['limit=101', 'offset=-1', 'severity=URGENT', 'module=unknown'])
def test_queue_rejects_unbounded_or_unknown_filters(client, query):
    assert client.get(f'/assurance/overview?mon_period=202603&{query}').status_code == 422


def test_missing_period_is_not_an_all_clear_assessment(client):
    assert client.get('/assurance/overview?mon_period=209901').status_code == 404


def test_export_contains_full_period_not_only_preview(client):
    response = client.get('/assurance/overview/export?mon_period=202603')
    assert response.status_code == 200
    records = list(csv.DictReader(io.StringIO(response.text)))
    assert len(records) == 1679
    assert {r['period'] for r in records} == {'202603'}
    assert sum(r['module'] == 'commission' for r in records) == 575
    synthetic = [r for r in records if r['description'].startswith('Synthetic scenario')]
    assert len(synthetic) == 3
    assert {r['module'] for r in synthetic} == {'inventory'}
    assert all('Demonstration only' in r['recommended_action'] for r in synthetic)


def test_aggregate_only_position_matches_existing_payments(client):
    data = client.get('/payments/position?mon_period=202602').json()
    assert data['total_amount_unpaid'] == 5246374.49
    assert data['payment_coverage_pct'] == 87.4
    assert data['record_count'] == 939
    assert 'records' not in data


def test_payment_outage_preserves_other_checks_and_blocks_complete_export(client, monkeypatch):
    from backend.db import apdp
    monkeypatch.setattr(config, 'PAYMENT_SOURCE', 'apdp')
    def unavailable(_period):
        raise ConnectionError('offline')
    monkeypatch.setattr(apdp, 'get_partner_settlements', unavailable)
    response = client.get('/assurance/overview?mon_period=202603')
    assert response.status_code == 200
    data = response.json()
    assert data['complete'] is False
    assert data['payment'] is None
    assert data['finding_count'] == 792
    payment = next(m for m in data['modules'] if m['module'] == 'payment')
    assert payment['status'] == 'UNAVAILABLE'
    assert all(row['amount_outstanding'] is None for row in data['items'])
    assert client.get('/assurance/overview/export?mon_period=202603').status_code == 503


def test_module_and_severity_filters_select_the_matching_finding(client):
    data = client.get('/assurance/overview?mon_period=202603&module=inventory&severity=LOW').json()
    assert data['finding_count'] == 1679
    assert data['items']
    for row in data['items']:
        assert row['severity'] == 'LOW'
        assert row['lead_finding']['module'] == 'inventory'
        assert row['lead_finding']['severity'] == 'LOW'
        assert row['lead_finding']['product_code']
        assert row['modules'] == ['inventory']


def test_apdp_position_and_findings_use_the_same_live_source(client, monkeypatch):
    from backend.db import apdp
    monkeypatch.setattr(config, 'PAYMENT_SOURCE', 'apdp')
    monkeypatch.setattr(apdp, 'get_partner_settlements', lambda _period: [{
        'dealer_id': '296065', 'settlement_period': '202603',
        'expected_commission_ngn': 1000, 'total_settled_ngn': 400,
        'reconciliation_status': 'DISPUTED',
    }])
    data = client.get('/assurance/overview?mon_period=202603&module=payment').json()
    assert data['payment']['data_source'] == 'APDP'
    assert data['payment']['total_amount_unpaid'] == 600
    assert data['total'] == 1
    assert data['items'][0]['amount_outstanding'] == 600
    assert '600.00' in data['items'][0]['lead_finding']['description']
