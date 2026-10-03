"""Affiliated dealer codes: name-grouped sibling codes with month commission."""
from __future__ import annotations

import pandas as pd
import pytest

from backend import config
from backend.db import affiliation_evidence, measure_evidence
from backend.db.affiliation_evidence import collect_affiliation
from backend.db.connection import execute_query

PERIOD = '202606'
SHARED_NAME = 'Topaz Bridge Trading'
ENVELOPE_KEYS = {
    'anchor_type', 'anchor_id', 'anchor_query', 'anchor_name', 'period', 'status', 'found',
    'resolved_names', 'rows', 'total_codes', 'other_count', 'indicative_total_ngn',
    'others_with_commission', 'others_unavailable', 'truncated', 'source', 'tools', 'note',
}


@pytest.fixture(autouse=True)
def sample_mode(monkeypatch):
    monkeypatch.setattr(config, 'USE_SAMPLE_DATA', True)


@pytest.fixture(scope='module')
def summary() -> dict[str, dict]:
    frame = execute_query('get_dealer_summary', {'mon_period': PERIOD, 'distributor_code': None})
    return {str(r['dealer_id']): r for r in frame.to_dict(orient='records')}


def _codes(name: str) -> list[str]:
    lookup = measure_evidence.collect_dealer_codes({'dealer_name': name, 'periods': [PERIOD], 'match': 'exact'})
    return [str(row['dealer_id']) for row in lookup['rows']]


def _assert_consistent(result: dict) -> None:
    assert set(result) == ENVELOPE_KEYS
    rows = result['rows']
    assert len(rows) <= 100
    assert result['truncated'] == (result['total_codes'] > 100)
    others = [row for row in rows if not row['is_anchor']]
    available = [row for row in others if row['commission_status'] == 'available']
    assert result['indicative_total_ngn'] == sum(row['commission_ngn'] for row in available)
    assert result['others_with_commission'] == len(available)
    assert result['others_unavailable'] == len(others) - len(available)
    for row in rows:
        if row['commission_status'] == 'unavailable':
            assert row['commission_ngn'] is None
        else:
            assert isinstance(row['commission_ngn'], float)
    ranked = [row['commission_ngn'] for row in others]
    present = [value for value in ranked if value is not None]
    assert present == sorted(present, reverse=True)
    assert ranked == present + [None] * (len(ranked) - len(present))


def test_name_anchor_reports_every_code_sharing_the_name(summary):
    result = collect_affiliation({'dealer_id': None, 'dealer_name': SHARED_NAME, 'periods': [PERIOD]})
    _assert_consistent(result)
    expected = set(_codes(SHARED_NAME))
    assert result['found'] is True
    assert result['status'] == 'available'
    assert result['anchor_type'] == 'name'
    assert result['anchor_id'] is None
    assert result['anchor_query'] == SHARED_NAME == result['anchor_name']
    assert result['resolved_names'] == [SHARED_NAME]
    assert {row['dealer_id'] for row in result['rows']} == expected
    assert result['total_codes'] == len(expected) > 1
    assert all(row['is_anchor'] is False for row in result['rows'])
    assert result['other_count'] == result['total_codes']
    assert result['indicative_total_ngn'] == sum(
        float(summary[code]['total_commission_ngn']) for code in expected if code in summary)
    assert result['tools'] == ['get_dealer_codes', 'get_dealer_summary']
    assert result['source'] == 'Recorded dealer records'


def test_code_anchor_is_listed_first_and_excluded_from_others(summary):
    codes = _codes(SHARED_NAME)
    anchor = codes[-1]
    result = collect_affiliation({'dealer_id': anchor, 'periods': [PERIOD]})
    _assert_consistent(result)
    assert result['anchor_type'] == 'code'
    assert result['anchor_id'] == anchor
    assert result['anchor_query'] is None
    assert result['anchor_name'] == SHARED_NAME
    anchors = [row for row in result['rows'] if row['is_anchor']]
    assert len(anchors) == 1 and result['rows'][0] is anchors[0]
    assert anchors[0]['dealer_id'] == anchor
    assert anchors[0]['commission_ngn'] == float(summary[anchor]['total_commission_ngn'])
    assert result['total_codes'] == len(set(codes))
    assert result['other_count'] == result['total_codes'] - 1
    assert result['indicative_total_ngn'] == sum(
        float(summary[code]['total_commission_ngn']) for code in codes if code != anchor and code in summary)


def test_code_anchor_with_unique_name_has_no_others(summary):
    name = 'Ember Hill Networks'
    codes = _codes(name)
    assert len(codes) == 1
    result = collect_affiliation({'dealer_id': codes[0], 'periods': [PERIOD]})
    _assert_consistent(result)
    assert result['found'] is True
    assert result['total_codes'] == 1
    assert result['other_count'] == 0
    assert result['indicative_total_ngn'] == 0
    assert result['others_with_commission'] == result['others_unavailable'] == 0
    assert [row['dealer_id'] for row in result['rows']] == codes
    assert result['rows'][0]['is_anchor'] is True


@pytest.mark.parametrize('code', ['00000000'])
def test_unresolved_code_anchor_is_not_found_and_explained(code):
    result = collect_affiliation({'dealer_id': code, 'periods': [PERIOD]})
    assert set(result) == ENVELOPE_KEYS
    assert result['status'] == 'available'
    assert result['found'] is False
    assert result['rows'] == []
    assert result['total_codes'] == result['other_count'] == 0
    assert code in result['note'] and PERIOD in result['note']
    assert 'not zero' in result['note']


def test_unmatched_name_anchor_is_not_found():
    result = collect_affiliation({'dealer_name': 'No Such Dealer Name', 'periods': [PERIOD]})
    _assert_consistent(result)
    assert result['found'] is False
    assert result['rows'] == []
    assert result['total_codes'] == 0


def test_sibling_without_activation_commission_is_unavailable_not_zero(summary):
    # This name has one activation code plus a subscription-only code in the month.
    name = 'Indigo Arc Communications'
    codes = _codes(name)
    missing = [code for code in codes if code not in summary]
    assert missing, 'sample data should hold a subscription-only sibling'
    anchor = next(code for code in codes if code in summary)
    result = collect_affiliation({'dealer_id': anchor, 'periods': [PERIOD]})
    _assert_consistent(result)
    rows = {row['dealer_id']: row for row in result['rows']}
    for code in missing:
        assert rows[code]['commission_status'] == 'unavailable'
        assert rows[code]['commission_ngn'] is None
    assert result['others_unavailable'] == len(missing)
    assert result['indicative_total_ngn'] == sum(
        float(summary[code]['total_commission_ngn']) for code in codes if code != anchor and code in summary)
    assert result['rows'][-1]['commission_ngn'] is None


def test_large_sets_are_bounded_and_flagged(monkeypatch):
    # The real lookup caps at a 100-row page but reports the true total; the result stays
    # honest and partial — the count reflects the whole set, totals cover the fetched page,
    # and truncation flags the rest (full-set aggregation over >100 codes is post-MVP).
    codes = [f'C{index:04d}' for index in range(150)]
    summary_rows = [{'dealer_id': code, 'dealer_name': 'Wide Dealer', 'total_commission_ngn': float(index)}
                    for index, code in enumerate(codes) if index % 3]
    by_comm = {row['dealer_id']: row['total_commission_ngn'] for row in summary_rows}

    def fake_query(name, params):
        assert name == 'get_dealer_summary'
        return pd.DataFrame(summary_rows)

    def fake_codes(request):
        return {'rows': [{'dealer_id': code, 'recorded_names': ['Wide Dealer']} for code in codes[:100]],
                'total_codes': len(codes)}

    monkeypatch.setattr(affiliation_evidence, 'execute_query', fake_query)
    monkeypatch.setattr(affiliation_evidence, 'has_source_period', lambda source, period: True)
    monkeypatch.setattr(measure_evidence, 'collect_dealer_codes', fake_codes)
    result = collect_affiliation({'dealer_id': 'C0001', 'periods': [PERIOD]})
    assert len(result['rows']) == 100
    assert result['truncated'] is True
    assert result['total_codes'] == 150            # the count reflects the whole set
    assert result['other_count'] == 149
    assert result['rows'][0]['dealer_id'] == 'C0001' and result['rows'][0]['is_anchor']
    # Totals cover only the fetched page; truncation signals the remainder is not included.
    fetched_others = [code for code in codes[:100] if code != 'C0001']
    available = [by_comm[code] for code in fetched_others if code in by_comm]
    assert result['others_with_commission'] == len(available)
    assert result['others_unavailable'] == len(fetched_others) - len(available)
    assert result['indicative_total_ngn'] == sum(available)


def test_uncovered_month_is_unavailable_not_zero():
    # A month with no source records must not be reported as "no codes recorded" (missing != zero).
    for request in ({'dealer_name': SHARED_NAME, 'periods': ['209901']},
                    {'dealer_id': '19580', 'periods': ['209901']}):
        result = collect_affiliation(request)
        assert result['status'] == 'unavailable'
        assert result['found'] is False
        assert result['rows'] == []
        assert 'not zero' in result['note'].lower()
        assert result['tools'] == ['get_dealer_summary']  # discovery never ran


def test_code_anchor_outside_first_lookup_page_is_not_double_counted(monkeypatch):
    # A real anchor beyond the lookup's 100-row page is already in the reported total; count it once.
    codes = [f'C{index:04d}' for index in range(150)]
    summary_rows = [{'dealer_id': code, 'dealer_name': 'Wide Dealer', 'total_commission_ngn': float(i)}
                    for i, code in enumerate(codes)]

    def fake_query(name, params):
        assert name == 'get_dealer_summary'
        return pd.DataFrame(summary_rows)

    def fake_codes(request):
        return {'rows': [{'dealer_id': code, 'recorded_names': ['Wide Dealer']} for code in codes[:100]],
                'total_codes': len(codes)}

    monkeypatch.setattr(affiliation_evidence, 'execute_query', fake_query)
    monkeypatch.setattr(affiliation_evidence, 'has_source_period', lambda source, period: True)
    monkeypatch.setattr(measure_evidence, 'collect_dealer_codes', fake_codes)
    result = collect_affiliation({'dealer_id': 'C0149', 'periods': [PERIOD]})  # anchor beyond the page
    assert result['total_codes'] == 150   # not 151
    assert result['other_count'] == 149   # not 150
    assert result['truncated'] is True
    anchor_rows = [row for row in result['rows'] if row['is_anchor']]
    assert len(anchor_rows) == 1 and anchor_rows[0]['dealer_id'] == 'C0149'


def test_partial_paths_report_summary_tool_only(summary):
    # An unresolved anchor returns before discovery, so get_dealer_codes must not be reported.
    unresolved = collect_affiliation({'dealer_id': '00000000', 'periods': [PERIOD]})
    assert unresolved['found'] is False
    assert unresolved['tools'] == ['get_dealer_summary']
    # A resolved lookup reports both tools in execution order.
    resolved = collect_affiliation({'dealer_name': SHARED_NAME, 'periods': [PERIOD]})
    assert resolved['tools'] == ['get_dealer_codes', 'get_dealer_summary']


def test_failed_discovery_retains_attempted_discovery_tool(monkeypatch):
    # The summary read succeeds but code discovery raises; both tools were attempted.
    def ok_summary(name, params):
        assert name == 'get_dealer_summary'
        return pd.DataFrame([{'dealer_id': '19580', 'dealer_name': 'Wide Dealer',
                              'total_commission_ngn': 1.0}])

    def boom(request):
        raise OSError('discovery failed')

    monkeypatch.setattr(affiliation_evidence, 'execute_query', ok_summary)
    monkeypatch.setattr(affiliation_evidence, 'has_source_period', lambda source, period: True)
    monkeypatch.setattr(measure_evidence, 'collect_dealer_codes', boom)
    result = collect_affiliation({'dealer_id': '19580', 'periods': [PERIOD]})
    assert result['status'] == 'unavailable'
    assert result['tools'] == ['get_dealer_codes', 'get_dealer_summary']


def test_source_read_failure_returns_unavailable(monkeypatch):
    def broken(name, params):
        raise OSError('source unreadable')

    monkeypatch.setattr(affiliation_evidence, 'execute_query', broken)
    result = collect_affiliation({'dealer_name': SHARED_NAME, 'periods': [PERIOD]})
    assert set(result) == ENVELOPE_KEYS
    assert result['status'] == 'unavailable'
    assert result['found'] is False
    assert result['rows'] == []


@pytest.mark.parametrize('request_', [
    {'dealer_id': '19577', 'dealer_name': SHARED_NAME, 'periods': [PERIOD]},
    {'periods': [PERIOD]},
    {'dealer_id': ' ', 'dealer_name': None, 'periods': [PERIOD]},
    {'dealer_id': '19577', 'periods': ['202613']},
    {'dealer_id': '19577', 'periods': ['2026-06']},
    {'dealer_id': '19577', 'periods': [PERIOD, '202605']},
    {'dealer_id': '19577', 'periods': []},
    {'dealer_id': '19577', 'periods': PERIOD},
])
def test_invalid_requests_raise(request_):
    with pytest.raises(ValueError):
        collect_affiliation(request_)
