"""The assistant and commission workspace must explain the same recorded figures."""
import json

import pandas as pd
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from backend import config
from backend.agent.tool_executor import execute_tool
from backend.api.commission_routes import router
from backend.db import connection


def test_internal_subscription_fixture_query_is_not_an_agent_tool():
    result = execute_tool({'id': 'internal', 'name': 'get_subscription_demo_records',
                           'input': {'mon_period': '202606'}})
    assert result.get('is_error') is True
    assert 'Unknown tool' in result['content']
    valid_tools = result['content'].split('Valid tools: ')[1]
    assert 'get_subscription_demo_records' not in valid_tools


@pytest.mark.parametrize('period', ['202601', '202602', '202603', '202604', '202605', '202606'])
def test_subscription_tool_matches_workspace_without_relabelling_revenue(monkeypatch, period):
    monkeypatch.setattr(config, 'USE_SAMPLE_DATA', True)
    app = FastAPI()
    app.include_router(router)
    result = execute_tool({'id': 'subscription', 'name': 'get_orsc_summary',
                           'input': {'mon_period': period, 'distributor_code': '296065'}})
    assert not result.get('is_error')
    envelope = json.loads(result['content'])
    assert envelope['row_count'] == 1
    row = envelope['rows'][0]
    with TestClient(app) as client:
        response = client.get('/commissions/296065/detail', params={'mon_period': period, 'stream': 'orsc'})
    assert response.status_code == 200
    account = response.json()['account']
    assert row['total_subscription_amount_ngn'] == account['amount_ngn']
    for field in ('subscription_commission_ngn', 'subscription_settled_ngn',
                  'subscription_outstanding_ngn'):
        assert row[field] == account[field]
    assert 0 < row['subscription_commission_ngn'] < row['total_subscription_amount_ngn']
    if period == '202606':
        # Recorded fixture values, not a commission rate applied to revenue.
        assert row['subscription_commission_ngn'] == 3050.0
        assert row['subscription_settled_ngn'] == 1525.0
        assert row['subscription_outstanding_ngn'] == 1525.0


def test_live_subscription_tool_does_not_attach_same_dealers_demo_commission(monkeypatch):
    monkeypatch.setattr(config, 'USE_SAMPLE_DATA', False)
    # Replace the external database boundary while exercising the real tool adapter.
    monkeypatch.setattr(connection, '_run_presto', lambda *_: pd.DataFrame([{
        'dealer_id': '296065', 'dealer_name': 'Live account', 'account_profile_class': 'DEALER',
        'device_count': 1, 'total_subscription_amount_ngn': 123.45, 'zero_amount_count': 0,
    }]))
    result = execute_tool({'id': 'live-subscription', 'name': 'get_orsc_summary',
                           'input': {'mon_period': '202606', 'distributor_code': '296065'}})
    assert not result.get('is_error')
    row = json.loads(result['content'])['rows'][0]
    assert row['total_subscription_amount_ngn'] == 123.45
    assert row['subscription_commission_ngn'] is None
    assert row['subscription_settled_ngn'] is None
    assert row['subscription_outstanding_ngn'] is None
    assert row['subscription_commission_complete'] is False
