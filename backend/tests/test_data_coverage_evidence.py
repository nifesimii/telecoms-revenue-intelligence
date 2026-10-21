"""Atlas data-coverage evidence is the two coverage collectors, projected.

The oracle uses sample data with no mocks of the collectors: figures match
``collect_ifs_missing`` / ``collect_profile_class_missing`` for 202606.
Failure cases monkeypatch a collector or the dealer activity read.
"""
import os

os.environ["USE_SAMPLE_DATA"] = "true"

import pytest

from backend import config
from backend.db import connection, data_coverage, queries
from backend.db.data_coverage_evidence import (
    DATA_COVERAGE_SOURCE,
    DATA_COVERAGE_TOOL,
    MAX_LISTED_DEALERS,
    data_coverage_evidence,
)

PERIOD_KEYS = {"period", "status", "source", "tool", "total", "truncated",
               "total_rows", "note", "rows", "coverage"}


@pytest.fixture(autouse=True)
def sample_mode(monkeypatch):
    monkeypatch.setattr(config, "USE_SAMPLE_DATA", True)


def fail(*_args, **_kwargs):
    raise RuntimeError("source down")


def assert_unavailable(evidence, period, note):
    assert evidence == {"period": period, "status": "unavailable",
                        "source": DATA_COVERAGE_SOURCE, "tool": DATA_COVERAGE_TOOL,
                        "total": None, "truncated": False, "total_rows": 0, "note": note,
                        "rows": [], "coverage": None}


# ── Oracle: real sample data ────────────────────────────────────────────────

def test_whole_month_evidence_matches_the_collectors():
    ifs = data_coverage.collect_ifs_missing("202606")
    profile = data_coverage.collect_profile_class_missing("202606")
    assert len(ifs) == 919 and profile == []

    evidence = data_coverage_evidence("202606", None)

    assert set(evidence) == PERIOD_KEYS
    assert evidence["status"] == "available"
    assert evidence["source"] == DATA_COVERAGE_SOURCE
    assert evidence["tool"] == DATA_COVERAGE_TOOL
    assert evidence["total"] is None and evidence["note"] == ""
    coverage = evidence["coverage"]
    assert coverage["dealer_scoped"] is False and coverage["found"] is True
    assert coverage["sample_data"] is True
    assert list(coverage["gaps"]) == ["profile_class", "invoice"]
    assert coverage["gaps"]["profile_class"] == {"status": "checked", "dealer_count": 0, "dealers": []}
    invoice = coverage["gaps"]["invoice"]
    assert invoice["status"] == "checked"
    assert invoice["dealer_count"] == 919
    assert invoice["dealers"] == ifs[:MAX_LISTED_DEALERS]
    assert evidence["truncated"] is True
    assert evidence["total_rows"] == MAX_LISTED_DEALERS == len(evidence["rows"])
    first = ifs[0]
    assert first["dealer_id"] == "74050" and first["dealer_name"] == "Stone Light Networks"
    assert evidence["rows"][0] == {
        "dealer_id": "74050", "dealer_name": "Stone Light Networks",
        "dimension": "No IFS invoice record",
        "value": f"{first['activation_count']:,} activations across {first['affected_products']:,} products",
    }


def test_dealer_scoped_evidence_lists_only_that_dealer():
    ifs = [d for d in data_coverage.collect_ifs_missing("202606") if d["dealer_id"] == "74050"]

    evidence = data_coverage_evidence("202606", "74050")

    assert evidence["status"] == "available"
    coverage = evidence["coverage"]
    assert coverage["dealer_scoped"] is True and coverage["found"] is True
    assert coverage["gaps"]["profile_class"] == {"status": "checked", "dealer_count": 0, "dealers": []}
    assert coverage["gaps"]["invoice"] == {"status": "checked", "dealer_count": 1, "dealers": ifs}
    assert evidence["truncated"] is False
    assert evidence["total_rows"] == 1
    assert [row["dealer_id"] for row in evidence["rows"]] == ["74050"]


def test_dealer_with_no_activity_is_not_found_rather_than_gap_free():
    evidence = data_coverage_evidence("202606", "NO_SUCH_DEALER")

    assert evidence["status"] == "available"
    assert evidence["rows"] == [] and evidence["total_rows"] == 0
    assert evidence["truncated"] is False
    assert evidence["coverage"] == {"dealer_scoped": True, "found": False,
                                    "sample_data": True, "gaps": None}


def test_unknown_month_is_unavailable():
    assert_unavailable(data_coverage_evidence("209901", None), "209901",
                       "no data is recorded for this month.")


def test_unreadable_periods_are_unavailable(monkeypatch):
    monkeypatch.setattr(queries, "get_available_periods", fail)
    assert_unavailable(data_coverage_evidence("202606", None), "202606",
                       "the recorded months could not be read.")


# ── Failure cases ───────────────────────────────────────────────────────────

def test_one_failed_collector_is_unavailable_not_zero(monkeypatch):
    monkeypatch.setattr(data_coverage, "collect_ifs_missing", fail)

    evidence = data_coverage_evidence("202606", None)

    assert evidence["status"] == "available"
    gaps = evidence["coverage"]["gaps"]
    assert gaps["invoice"] == {"status": "unavailable", "dealer_count": None, "dealers": []}
    assert gaps["profile_class"] == {"status": "checked", "dealer_count": 0, "dealers": []}
    assert evidence["truncated"] is False
    assert evidence["rows"] == [] and evidence["total_rows"] == 0


def test_both_failed_collectors_make_the_month_unavailable(monkeypatch):
    monkeypatch.setattr(data_coverage, "collect_ifs_missing", fail)
    monkeypatch.setattr(data_coverage, "collect_profile_class_missing", fail)
    assert_unavailable(data_coverage_evidence("202606", None), "202606",
                       "the coverage sources could not be read.")


def test_unreadable_dealer_activity_is_unavailable(monkeypatch):
    monkeypatch.setattr(connection, "execute_query", fail)
    assert_unavailable(data_coverage_evidence("202606", "74050"), "202606",
                       "the dealer's activation records could not be read.")


def test_profile_class_rows_come_first_and_copy_collector_figures(monkeypatch):
    missing = [{"dealer_id": "1", "dealer_name": "Alpha", "total_activations": 1234,
                "zero_commission_count": 56, "commission_ngn": 0.0}]
    monkeypatch.setattr(data_coverage, "collect_profile_class_missing", lambda _p: missing)
    monkeypatch.setattr(data_coverage, "collect_ifs_missing", lambda _p: [
        {"dealer_id": "2", "dealer_name": "Beta", "affected_products": 3, "activation_count": 7}])

    evidence = data_coverage_evidence("202606", None)

    assert evidence["coverage"]["gaps"]["profile_class"]["dealers"] == missing
    assert evidence["rows"] == [
        {"dealer_id": "1", "dealer_name": "Alpha",
         "dimension": "Account profile class not recorded",
         "value": "1,234 activations, 56 zero-commission"},
        {"dealer_id": "2", "dealer_name": "Beta", "dimension": "No IFS invoice record",
         "value": "7 activations across 3 products"},
    ]
    assert evidence["total_rows"] == 2 and evidence["truncated"] is False
