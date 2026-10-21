"""Subscription workspace contracts against explicit fictional source statements."""
import csv
import io

import pandas as pd
import pytest
from fastapi.testclient import TestClient

from backend import config
from backend.db import commission_workspace, queries
from backend.main import app


@pytest.fixture
def demo(tmp_path, monkeypatch):
    source = tmp_path / 'revenue.csv'
    source.write_text('mon_period,distributor_code,distributor_name,account_profile_class,imei,data_subscription_amount\n'
                      '202606,D1,Dealer One,DATA PARTNERS,111,1000\n'
                      '202606,D1,Dealer One,DATA PARTNERS,222,2000\n'
                      '202606,D2,Dealer Two,DATA PARTNERS,333,3000\n')
    statements = tmp_path / 'statements.csv'
    rows = [
        ['202606', 'D1', '111', '100', '100', 'S1', 'P1'],
        ['202606', 'D1', '222', '200', '50', 'S1', 'P2'],
        ['202606', 'D2', '333', '300', '0', 'S2', ''],
    ]
    def write_statements(values):
        with statements.open('w', newline='') as handle:
            writer = csv.writer(handle)
            writer.writerow(['mon_period', 'dealer_id', 'imei', 'subscription_commission_ngn',
                             'subscription_settled_ngn', 'statement_reference', 'settlement_reference'])
            writer.writerows(values)
    write_statements(rows)
    monkeypatch.setattr(config, 'USE_SAMPLE_DATA', True)
    monkeypatch.setitem(config.SAMPLE_DATA_PATHS, 'fbb_comm_orsc', {'202606': source})
    monkeypatch.setitem(config.SAMPLE_DATA_PATHS, 'subscription_commission_demo', statements)
    queries._clear_csv_cache()
    with TestClient(app) as client:
        yield client, rows, write_statements, statements
    queries._clear_csv_cache()


PARAMS = {'mon_period': '202606', 'stream': 'orsc'}


def test_account_totals_filter_and_device_pages_reconcile(demo):
    client, _, _, _ = demo
    response = client.get('/commissions', params={**PARAMS, 'limit': 1})
    assert response.status_code == 200
    page = response.json()
    assert page['total'] == 2 and len(page['items']) == 1
    assert page['summary']['amount_ngn'] == 6000
    assert page['summary']['subscription_commission_ngn'] == 600
    assert page['summary']['subscription_settled_ngn'] == 150
    assert page['summary']['subscription_outstanding_ngn'] == 450
    filtered = client.get('/commissions', params={**PARAMS, 'search': 'D1', 'limit': 1}).json()
    assert filtered['filtered_summary']['amount_ngn'] == 3000
    assert filtered['filtered_summary']['subscription_commission_ngn'] == 300
    assert filtered['filtered_summary']['subscription_outstanding_ngn'] == 150
    detail = client.get('/commissions/D1/detail', params=PARAMS).json()
    assert detail['account']['subscription_commission_ngn'] == 300
    evidence = client.get('/commissions/D1/subscription-records', params={**PARAMS, 'limit': 1, 'offset': 1}).json()
    assert evidence['total'] == 2
    assert evidence['items'][0]['imei'] == '222'
    assert evidence['items'][0]['subscription_outstanding_ngn'] == 150
    assert client.get('/commissions/D1/subscription-records', params={**PARAMS, 'limit': 101}).status_code == 422
    exported = client.get('/commissions/export', params={**PARAMS, 'search': 'D1'})
    row = next(csv.DictReader(io.StringIO(exported.text)))
    assert row['amount_ngn'] == '3000.0'
    assert row['subscription_commission_ngn'] == '300.0'
    assert 'revenue' in row['amount_basis']
    assert 'Fictional upstream' in row['subscription_commission_basis']


def test_missing_settlement_preserves_known_commission(demo):
    client, rows, write, _ = demo
    rows[0][4] = ''
    rows[0][6] = ''
    write(rows)
    page = client.get('/commissions', params=PARAMS).json()
    assert page['summary']['subscription_commission_ngn'] == 600
    assert page['summary']['subscription_settled_ngn'] is None
    assert page['summary']['subscription_outstanding_ngn'] is None
    evidence = client.get('/commissions/D1/subscription-records', params=PARAMS).json()
    assert evidence['items'][0]['subscription_commission_ngn'] == 100
    assert evidence['items'][0]['subscription_settled_ngn'] is None


def test_missing_commission_is_not_zero_or_partial_total(demo):
    client, rows, write, _ = demo
    write(rows[1:])
    page = client.get('/commissions', params=PARAMS).json()
    assert page['summary']['subscription_commission_ngn'] is None
    assert page['summary']['subscription_commission_record_count'] == 2
    assert not page['summary']['subscription_commission_complete']
    assert page['summary']['amount_ngn'] == 6000
    unaffected = client.get('/commissions/D2/detail', params=PARAMS).json()['account']
    assert unaffected['subscription_commission_ngn'] == 300
    assert unaffected['subscription_settled_ngn'] == 0


def test_absent_fixture_retains_revenue_with_unavailable_commission(demo):
    client, _, _, statements = demo
    statements.unlink()
    page = client.get('/commissions', params=PARAMS).json()
    assert page['summary']['amount_ngn'] == 6000
    assert page['summary']['subscription_commission_ngn'] is None
    assert page['summary']['subscription_commission_record_count'] == 0


def test_live_revenue_never_joins_sample_statements(demo, monkeypatch):
    client, _, _, _ = demo
    monkeypatch.setattr(config, 'USE_SAMPLE_DATA', False)
    monkeypatch.setattr(commission_workspace, 'execute_query', lambda *_: pd.DataFrame([{
        'dealer_id': 'D1', 'dealer_name': 'Live dealer', 'account_profile_class': 'DATA PARTNERS',
        'total_subscription_amount_ngn': 9000, 'device_count': 2, 'zero_amount_count': 0}]))
    monkeypatch.setattr(queries, 'get_available_periods', lambda: ['202606'])
    page = client.get('/commissions', params=PARAMS).json()
    assert page['summary']['amount_ngn'] == 9000
    assert page['summary']['subscription_commission_ngn'] is None
    assert page['summary']['subscription_settled_ngn'] is None
    evidence = client.get('/commissions/D1/subscription-records', params=PARAMS).json()
    assert evidence['items'] == []
