"""Complete counts and bounded pages at the discovery collection seam."""
import pandas as pd
import pytest
from backend.db import portfolio_discovery as discovery


def test_discovery_complete_count_ranking_ties_paging_and_period(monkeypatch):
    calls = []
    monkeypatch.setattr(discovery.queries, 'has_source_period', lambda source, period: period == '202606')
    def read(tool, params):
        calls.append((tool, params))
        return pd.DataFrame([
            {'dealer_id': '001', 'dealer_name': 'Same name', 'zero_commission_count': 3},
            {'dealer_id': '010', 'dealer_name': 'Same name', 'zero_commission_count': 7},
            {'dealer_id': '002', 'dealer_name': 'Other', 'zero_commission_count': 7},
            {'dealer_id': '003', 'dealer_name': 'Clear', 'zero_commission_count': 0}])
    monkeypatch.setattr(discovery, 'execute_query', read)
    result = discovery.discover_zero_commission('202606', limit=2)
    assert result['total_count'] == 3
    assert [r['dealer_id'] for r in result['items']] == ['002', '010']
    assert result['has_more'] is True
    second = discovery.discover_zero_commission('202606', limit=2, offset=2)
    assert [r['dealer_id'] for r in second['items']] == ['001']
    assert second['has_more'] is False
    assert second['total_count'] == 3
    assert calls == [('get_dealer_summary', {'mon_period':'202606', 'distributor_code':None})] * 2
    assert discovery.discover_zero_commission('202605')['total_count'] is None
    assert len(calls) == 2


@pytest.mark.parametrize('rows,expected', [([], None),
    ([{'dealer_id':'001', 'dealer_name':'Account', 'zero_commission_count':0}], 0),
    ([{'dealer_id':'001', 'dealer_name':'Account', 'zero_commission_count':None}], None),
    ([{'dealer_id':'001', 'dealer_name':'Account', 'zero_commission_count':float('nan')}], None)])
def test_missing_evidence_never_becomes_confirmed_zero(monkeypatch, rows, expected):
    monkeypatch.setattr(discovery.queries, 'has_source_period', lambda *a: True)
    monkeypatch.setattr(discovery, 'execute_query', lambda *a: pd.DataFrame(rows))
    result = discovery.discover_zero_commission('202606')
    assert result['total_count'] == expected
    assert result['status'] == ('available' if expected == 0 else 'unavailable')


def test_source_failure_is_unavailable(monkeypatch):
    def fail(*args):
        raise OSError('private source path')
    monkeypatch.setattr(discovery.queries, 'has_source_period', fail)
    result = discovery.discover_zero_commission('202606')
    assert result['status'] == 'unavailable'
    assert result['total_count'] is None
    assert 'private' not in str(result)


def test_collection_enforces_maximum(monkeypatch):
    with pytest.raises(ValueError):
        discovery.discover_zero_commission('202606', limit=101)
