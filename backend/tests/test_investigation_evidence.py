"""Investigations explain complete populations while paging record evidence."""
import csv
from datetime import date, timedelta

import pytest
import pandas as pd

from backend import config
from backend.db import queries


@pytest.fixture(autouse=True)
def sample_mode(monkeypatch):
    monkeypatch.setattr(config, "USE_SAMPLE_DATA", True)


def test_screenshot_dealer_gets_date_classification_instead_of_date_availability():
    from backend.db.investigation_evidence import investigate

    result = investigate("296065", ["202606"])

    assert result["dealer_id"] == "296065"
    assert result["periods"] == ["202606"]
    assert result["family"] == "zero_commission"
    assert result["status"] == "available"
    assert result["total_records"] == 50
    assert result["eligibility"] == {"inside": 48, "outside": 2, "invalid": 0}
    assert sum(item["count"] for item in result["causes"]) + result["unresolved_count"] == 50
    causes = {item["cause"]: item["count"] for item in result["causes"]}
    assert causes.get("OUTSIDE_6_MONTH_WINDOW") == 2
    assert causes.get("NULL_PROFILE_CLASS", 0) == 0
    assert len(result["records"]) == 20
    assert result["pagination"] == {"offset": 0, "limit": 20, "total": 50, "has_more": True}
    assert "get_zero_commission_records" in result["tools"]


def test_later_evidence_page_keeps_the_same_population_conclusions():
    from backend.db.investigation_evidence import investigate

    first = investigate("296065", ["202606"], limit=20)
    last = investigate("296065", ["202606"], offset=40, limit=20)

    assert len(last["records"]) == 10
    assert last["pagination"] == {"offset": 40, "limit": 20, "total": 50, "has_more": False}
    assert last["eligibility"] == first["eligibility"]
    assert last["causes"] == first["causes"]
    assert last["unresolved_count"] == first["unresolved_count"]
    assert not any(record in first["records"] for record in last["records"])


def test_all_records_are_classified_beyond_page_cap_and_window_is_inclusive(tmp_path, monkeypatch):
    from backend.db.investigation_evidence import investigate

    path = tmp_path / "activations.csv"
    fields = ["mon_period", "distributor_code", "distributor_name", "account_profile_class",
              "commission_rate", "product_denomination", "imei", "product_name", "product_code",
              "invoice_date", "first_activation_date", "unit_selling_price"]
    with path.open("w", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        for index, gap in enumerate([1] * 100 + [180, 181, -1]):
            writer.writerow(dict(mon_period="202606", distributor_code="123", distributor_name="Boundary Dealer",
                                 account_profile_class="ENTERPRISE BUSINESS", commission_rate=0,
                                 product_denomination="Router", imei=str(index), product_name="Boundary Router",
                                 product_code="boundary-product", invoice_date="2026-01-01",
                                 first_activation_date=(date(2026, 1, 1) + timedelta(days=gap)).isoformat(),
                                 unit_selling_price=1000))
    paths = {**config.SAMPLE_DATA_PATHS, "fbb_comm_dev_act": {"202606": path}}
    monkeypatch.setattr(config, "SAMPLE_DATA_PATHS", paths)
    queries._clear_csv_cache()
    try:
        result = investigate("123", ["202606"], limit=100)
        assert result["total_records"] == 103
        assert result["eligibility"] == {"inside": 101, "outside": 1, "invalid": 1}
        assert len(result["records"]) == 100
        assert result["pagination"] == {"offset": 0, "limit": 100, "total": 103, "has_more": True}
        assert sum(item["count"] for item in result["causes"]) + result["unresolved_count"] == 103
        causes = {item["cause"]: item["count"] for item in result["causes"] if item["count"]}
        assert causes == {"OUTSIDE_6_MONTH_WINDOW": 1}
        # These replacement rows have no matching supplemental evidence. A missing
        # lookup does not prove a USP miss, and negative dates prove no cause.
        assert result["unresolved_count"] == 102
    finally:
        queries._clear_csv_cache()


def test_live_mode_never_reuses_demo_investigation_evidence(monkeypatch):
    from backend.db.investigation_evidence import investigate

    monkeypatch.setattr(config, "USE_SAMPLE_DATA", False)
    result = investigate("296065", ["202606"])

    assert result["status"] == "unavailable"
    assert result["records"] == []
    assert result["causes"] == []


@pytest.mark.parametrize("kwargs", [{"limit": 101}, {"limit": 0}, {"offset": -1}])
def test_investigation_rejects_unbounded_or_invalid_pages(kwargs):
    from backend.db.investigation_evidence import investigate

    with pytest.raises(ValueError):
        investigate("296065", ["202606"], **kwargs)


def test_complete_demo_supports_recorded_causes_without_runtime_invention():
    from backend.db.investigation_evidence import investigate
    result = investigate('296065', ['202606'])
    assert {c['cause']: c['count'] for c in result['causes']} == {
        'USP_SNAPSHOT_MISS': 48, 'OUTSIDE_6_MONTH_WINDOW': 2}
    assert result['unresolved_count'] == 0
    assert all(r['evidence_ref'] for r in result['records'])


@pytest.mark.parametrize('corruption', ['missing', 'stale', 'duplicate', 'wrong_month'])
def test_failed_support_does_not_turn_into_snapshot_misses(monkeypatch, corruption):
    from backend.db.investigation_evidence import investigate
    original = queries.investigation_support
    def broken(*args, **kwargs):
        frame = original(*args, **kwargs)
        if corruption == 'missing':
            return frame.iloc[:0]
        if corruption == 'duplicate':
            return pd.concat([frame, frame])
        frame.loc[:, 'source_fingerprint' if corruption == 'stale' else 'usp_snapshot_period'] = 'invalid'
        return frame
    monkeypatch.setattr(queries, 'investigation_support', broken)
    result = investigate('296065', ['202606'])
    assert result['unresolved_count'] == 48
    assert {c['cause'] for c in result['causes']} == {'OUTSIDE_6_MONTH_WINDOW'}


def test_variance_reconciles_products_and_compares_zero_causes():
    from backend.db.investigation_evidence import investigate
    result = investigate('296065', ['202605', '202606'], 'commission_variance')
    assert result['status'] == 'available'
    variance = result['variance']
    assert round(sum(p['change_ngn'] for p in variance['products']), 2) == variance['totals']['change_ngn']
    assert [z['total_records'] for z in result['zero_investigations']] == [47, 50]
    assert len(result['records']) <= 20


def test_payment_process_evidence_reconciles_to_recorded_balance():
    from backend.db.investigation_evidence import investigate
    result = investigate('296065', ['202606'], 'payment')
    assert result['status'] == 'available'
    p = result['payment']
    assert round(p['owed'] - p['paid'], 2) == p['balance']
    assert p['process']['remaining_amount'] == p['balance']
    assert p['process']['evidence_ref']


def test_missing_account_is_unavailable_not_verified_zero():
    from backend.db.investigation_evidence import investigate
    assert investigate('not-a-dealer', ['202606'])['status'] == 'unavailable'
