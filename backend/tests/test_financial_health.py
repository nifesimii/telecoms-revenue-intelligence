"""Synthetic business reports must reconcile without external data sources."""
import pytest
from fastapi.testclient import TestClient
from backend.main import app
from backend.db import financial_health as finance

client = TestClient(app)


def test_all_statements_reconcile_across_months():
    for dealer in finance.DEALERS:
        previous = None
        for period in finance.PERIODS:
            report = finance.get_report(dealer['dealer_id'], period)
            values = report['values']
            assert values['total_assets'] == values['total_liabilities'] + values['total_equity']
            assert values['closing_cash'] == values['cash']
            assert values['opening_cash'] + values['net_cash_change'] == values['cash']
            assert values['net_cash_change'] == values['operating_cash_flow'] + values['investing_cash_flow'] + values['financing_cash_flow']
            assert values['net_profit'] == values['revenue'] - values['cost_of_sales'] - values['operating_expenses'] - values['depreciation'] - values['interest'] - values['tax']
            if previous:
                assert values['opening_cash'] == previous['cash']
                assert values['retained_earnings'] == previous['retained_earnings'] + values['net_profit']
            previous = values


def test_known_figures_and_kpi_evidence():
    report = finance.get_report('DEMO-001', '202603')
    assert report['values']['revenue'] == 14_000_000
    assert report['values']['net_profit'] == 2_240_000
    metrics = {m['id']: m for m in report['kpis']}
    assert metrics['gross_margin']['value'] == 40
    assert metrics['net_margin']['value'] == 16
    assert metrics['dscr']['value'] == 17.5
    assert all(m['formula'] and m['inputs'] for m in metrics.values())
    assert report['source'] == 'synthetic'
    assert len(report['statements']) == 3
    assert report['prior_period'] == '202602'
    assert finance.get_report('DEMO-001', '202601')['prior_period'] is None


def test_missing_schedule_and_negative_equity_are_not_healthy_ratios():
    report = finance.get_report('DEMO-004', '202603')
    dscr = next(m for m in report['kpis'] if m['id'] == 'dscr')
    assert dscr['value'] is None and dscr['status'] == 'unavailable'
    assert 'schedule' in dscr['reason'].lower()
    loss = finance.get_report('DEMO-003', '202603')
    leverage = next(m for m in loss['kpis'] if m['id'] == 'debt_to_equity')
    assert leverage['value'] is None and leverage['status'] == 'not_meaningful'
    assert loss['values']['net_profit'] < 0


def test_ratio_zero_denominators_and_missing_inputs():
    values = finance.get_report('DEMO-001', '202603')['values'].copy()
    values.update(revenue=0, current_liabilities=0, scheduled_principal=0, interest=0)
    metrics = {m['id']: m for m in finance.calculate_kpis(values)}
    assert metrics['net_margin']['value'] is None
    assert metrics['current_ratio']['value'] is None
    assert metrics['dscr']['status'] == 'not_applicable'
    values['scheduled_principal'] = None
    assert next(m for m in finance.calculate_kpis(values) if m['id'] == 'dscr')['status'] == 'unavailable'


def test_collection_bounded_search_sort_and_detail():
    first = client.get('/financial-health', params={'mon_period': '202603', 'limit': 2}).json()
    assert first['pagination']['total'] == 4 and len(first['items']) == 2
    second = client.get('/financial-health', params={'mon_period': '202603', 'limit': 2, 'offset': 2}).json()
    assert not ({x['dealer_id'] for x in first['items']} & {x['dealer_id'] for x in second['items']})
    assert 'statements' not in first['items'][0]
    result = client.get('/financial-health', params={'mon_period': '202603', 'search': 'DEMO-004'}).json()
    assert result['pagination']['total'] == 1
    result = client.get('/financial-health', params={'mon_period': '202603', 'sort_by': 'revenue', 'direction': 'desc'}).json()
    assert [x['revenue'] for x in result['items']] == sorted([x['revenue'] for x in result['items']], reverse=True)
    assert client.get('/financial-health/DEMO-001?mon_period=202603').json()['source'] == 'synthetic'


@pytest.mark.parametrize('params', [{'limit': 101}, {'offset': -1}, {'sort_by': 'anything'}, {'direction': 'random'}, {'mon_period': '202613'}, {'mon_period': '2026'}])
def test_invalid_inputs(params):
    assert client.get('/financial-health', params={'mon_period': '202603', **params}).status_code == 422


def test_empty_period_missing_dealer_and_independence_from_live_mode(monkeypatch):
    from backend import config
    monkeypatch.setattr(config, 'USE_SAMPLE_DATA', False)
    monkeypatch.setattr(config, 'PAYMENT_SOURCE', 'apdp')
    assert client.get('/financial-health?mon_period=202603').json()['source'] == 'synthetic'
    assert client.get('/financial-health?mon_period=202607').json()['items'] == []
    assert client.get('/financial-health/DEMO-001?mon_period=202607').status_code == 404
    assert client.get('/financial-health/not-a-dealer?mon_period=202603').status_code == 404
