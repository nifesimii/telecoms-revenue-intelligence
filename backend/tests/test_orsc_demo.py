"""The default demo month must support both commission workspace streams."""
import os

os.environ['USE_SAMPLE_DATA'] = 'true'

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from backend import config
from backend.api.commission_routes import router
from backend.db import queries
from backend.db.connection import execute_query


@pytest.fixture
def client(monkeypatch):
    monkeypatch.setattr(config, 'USE_SAMPLE_DATA', True)
    queries._clear_csv_cache()
    app = FastAPI()
    app.include_router(router)
    with TestClient(app) as client:
        yield client
    queries._clear_csv_cache()


def test_default_demo_month_has_both_streams_and_orsc_comparison(client):
    period, prior = queries.get_available_periods()[:2]
    for stream in ('activation', 'orsc'):
        response = client.get('/commissions', params={
            'mon_period': period, 'prior_period': prior, 'stream': stream,
        })
        assert response.status_code == 200
        data = response.json()
        assert data['summary']['record_count'] > 0
        assert data['summary']['amount_ngn'] > 0
        assert 0 < len(data['items']) <= 25
        if stream == 'orsc':
            assert 'synthetic' in data['source'].lower()
            assert data['summary']['prior_amount_ngn'] > 0
            assert data['summary']['delta_ngn'] != 0
            assert 0 < data['summary']['zero_count'] < data['summary']['record_count']
            dealer = data['items'][0]['dealer_id']
            detail = client.get(f'/commissions/{dealer}/detail', params={
                'mon_period': period, 'prior_period': prior, 'stream': stream,
            }).json()
            assert detail['account']['prior_amount_ngn'] is not None
            assert 'synthetic' in detail['source'].lower()
            export = client.get('/commissions/export', params={
                'mon_period': period, 'stream': stream,
            })
            assert export.status_code == 200
            assert 'synthetic' in export.text.lower()


def test_february_orsc_is_preserved_and_missing_month_stays_empty(client):
    response = client.get('/commissions', params={'mon_period': '202602', 'stream': 'orsc'})
    summary = response.json()['summary']
    assert summary['record_count'] == 200
    assert summary['account_count'] == 157
    assert summary['amount_ngn'] == 1964280.90
    assert summary['zero_count'] == 69
    assert execute_query('get_orsc_summary', {'mon_period': '190001'}).empty


@pytest.mark.parametrize('period', ['202601', '202602', '202603', '202604', '202605', '202606'])
def test_half_year_has_commissions_inventory_and_reconciled_payments(client, period):
    assert period in queries.get_available_periods()
    for stream in ('activation', 'orsc'):
        response = client.get('/commissions', params={'mon_period': period, 'stream': stream})
        assert response.status_code == 200
        assert response.json()['summary']['amount_ngn'] > 0
        if period in {'202601', '202604', '202605', '202606'}:
            assert 'synthetic' in response.json()['source'].lower()
    dealers = execute_query('get_dealer_summary', {'mon_period': period})
    payments = execute_query('get_payment_summary', {'mon_period': period})
    assert set(payments['dealer_id'].astype(str)) == set(dealers['dealer_id'].astype(str))
    assert payments['commission_owed'].sum() == pytest.approx(dealers['total_commission_ngn'].sum())
    assert (payments['amount_paid'] + payments['amount_unpaid']).tolist() == pytest.approx(payments['commission_owed'].tolist())
    assert not execute_query('get_inventory_comparison', {'mon_period': period}).empty
    base = '202602' if period == '202601' else '202603'
    if period in {'202601', '202604', '202605', '202606'}:
        reference = execute_query('get_dealer_summary', {'mon_period': base})
        identities = lambda frame: set(zip(frame['dealer_id'].astype(str), frame['dealer_name']))
        assert identities(dealers) == identities(reference)
