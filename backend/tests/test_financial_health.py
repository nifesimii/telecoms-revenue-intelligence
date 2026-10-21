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
    report = finance.get_report('74050', '202603')
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
    assert finance.get_report('74050', '202601')['prior_period'] is None


def test_missing_schedule_and_negative_equity_are_not_healthy_ratios():
    report = finance.get_report('19649', '202603')
    dscr = next(m for m in report['kpis'] if m['id'] == 'dscr')
    assert dscr['value'] is None and dscr['status'] == 'unavailable'
    assert 'schedule' in dscr['reason'].lower()
    loss = finance.get_report('379102', '202603')
    leverage = next(m for m in loss['kpis'] if m['id'] == 'debt_to_equity')
    assert leverage['value'] is None and leverage['status'] == 'not_meaningful'
    assert loss['values']['net_profit'] < 0


def test_ratio_zero_denominators_and_missing_inputs():
    values = finance.get_report('74050', '202603')['values'].copy()
    values.update(revenue=0, current_liabilities=0, scheduled_principal=0, interest=0)
    metrics = {m['id']: m for m in finance.calculate_kpis(values)}
    assert metrics['net_margin']['value'] is None
    assert metrics['current_ratio']['value'] is None
    assert metrics['dscr']['status'] == 'not_applicable'
    values['scheduled_principal'] = None
    assert next(m for m in finance.calculate_kpis(values) if m['id'] == 'dscr')['status'] == 'unavailable'


def test_collection_bounded_search_sort_and_detail():
    first = client.get('/financial-health', params={'mon_period': '202603', 'limit': 2}).json()
    assert first['pagination']['total'] == 20 and len(first['items']) == 2
    second = client.get('/financial-health', params={'mon_period': '202603', 'limit': 2, 'offset': 2}).json()
    assert not ({x['dealer_id'] for x in first['items']} & {x['dealer_id'] for x in second['items']})
    assert 'statements' not in first['items'][0]
    result = client.get('/financial-health', params={'mon_period': '202603', 'search': '19649'}).json()
    assert result['pagination']['total'] == 1
    result = client.get('/financial-health', params={'mon_period': '202603', 'sort_by': 'revenue', 'direction': 'desc'}).json()
    assert [x['revenue'] for x in result['items']] == sorted([x['revenue'] for x in result['items']], reverse=True)
    assert client.get('/financial-health/74050?mon_period=202603').json()['source'] == 'synthetic'


@pytest.mark.parametrize('params', [{'limit': 101}, {'offset': -1}, {'sort_by': 'anything'}, {'direction': 'random'}, {'mon_period': '202613'}, {'mon_period': '2026'}])
def test_invalid_inputs(params):
    assert client.get('/financial-health', params={'mon_period': '202603', **params}).status_code == 422


def test_empty_period_missing_dealer_and_independence_from_live_mode(monkeypatch):
    from backend import config
    monkeypatch.setattr(config, 'USE_SAMPLE_DATA', False)
    monkeypatch.setattr(config, 'PAYMENT_SOURCE', 'apdp')
    assert client.get('/financial-health?mon_period=202603').json()['source'] == 'synthetic'
    assert client.get('/financial-health?mon_period=202607').json()['items'] == []
    assert client.get('/financial-health/74050?mon_period=202607').status_code == 404
    assert client.get('/financial-health/not-a-dealer?mon_period=202603').status_code == 404


def test_twenty_shared_dealer_identities_have_synthetic_reports():
    import csv
    from pathlib import Path
    samples = Path(__file__).resolve().parents[2] / 'data' / 'samples'
    for period in finance.PERIODS:
        with (samples / f'fbb_comm_dev_act_{period}.csv').open() as source:
            identities = {row['distributor_code']: row['distributor_name'] for row in csv.DictReader(source)}
        response = client.get('/financial-health', params={'mon_period': period}).json()
        assert response['pagination']['total'] == 20
        assert len({row['dealer_id'] for row in response['items']}) == 20
        for row in response['items']:
            assert identities[row['dealer_id']] == row['dealer_name']
            report = client.get(f"/financial-health/{row['dealer_id']}", params={'mon_period': period}).json()
            assert report['source'] == 'synthetic'
            assert 'not actual' in report['provenance'].lower()


def financial_tool(name, **parameters):
    import json
    from backend.agent.tool_executor import execute_tool
    result = execute_tool({'id': 'financial-test', 'name': name, 'input': parameters})
    assert not result.get('is_error'), result
    return json.loads(result['content'])


def test_atlas_reads_exact_workspace_report_and_bounded_comparison():
    from backend.agent.tools import TOOL_NAMES
    assert {'get_financial_health_report', 'get_financial_health_summary'} <= set(TOOL_NAMES)
    report = financial_tool('get_financial_health_report', distributor_code='74050', mon_period='202603')
    assert report['report'] == client.get('/financial-health/74050?mon_period=202603').json()
    summary = financial_tool('get_financial_health_summary', mon_period='202603', limit=3)
    assert summary['pagination']['total'] == 20
    assert len(summary['items']) == 3
    assert summary['pagination']['has_more']
    for row in summary['items']:
        detail = client.get(f"/financial-health/{row['dealer_id']}?mon_period=202603").json()
        assert row['net_profit'] == detail['values']['net_profit']
        assert row['kpis'] == detail['kpis']
    missing = financial_tool('get_financial_health_report', distributor_code='not-in-cohort', mon_period='202603')
    assert missing['status'] == 'unavailable' and missing['report'] is None
    assert missing['available_periods'] == list(finance.PERIODS)


@pytest.mark.parametrize('name,parameters', [
    ('get_financial_health_summary', {'mon_period': '202613'}),
    ('get_financial_health_summary', {'mon_period': '202603', 'limit': 101}),
    ('get_financial_health_summary', {'mon_period': '202603', 'offset': -1}),
    ('get_financial_health_summary', {'mon_period': '202603', 'sort_by': 'unknown'}),
    ('get_financial_health_summary', {'mon_period': '202603', 'direction': 'unknown'}),
    ('get_financial_health_report', {'mon_period': '202603'}),
    ('get_financial_health_report', {'mon_period': '202603', 'distributor_code': ''}),
])
def test_atlas_rejects_invalid_financial_requests(name, parameters):
    from backend.agent.tool_executor import execute_tool
    result = execute_tool({'id': 'financial-test', 'name': name, 'input': parameters})
    assert result.get('is_error') is True
