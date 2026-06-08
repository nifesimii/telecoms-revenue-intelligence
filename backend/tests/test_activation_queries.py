"""Phase 2 — query & API tests for Activation Intelligence.

Seven tests, all running in sample-data mode. Existing tests in
``test_queries.py`` and ``test_api.py`` are untouched.
"""
from __future__ import annotations

import os

os.environ["USE_SAMPLE_DATA"] = "true"

import pandas as pd  # noqa: E402
import pytest  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

from backend.db.connection import execute_query  # noqa: E402
from backend.main import app  # noqa: E402


@pytest.fixture(scope="module")
def client() -> TestClient:
    with TestClient(app) as c:
        yield c


# ---------------------------------------------------------------------------
# Test 1 — totals
# ---------------------------------------------------------------------------


def test_activation_summary_202603_totals() -> None:
    df = execute_query("get_activation_summary", {"mon_period": "202603"})

    assert int(df["activation_count"].sum()) == 30_892
    assert int(df["qualified_activation_count"].sum()) == 24_887
    assert int(df["non_qualified_activation_count"].sum()) == 6_005
    assert len(df) == 922

    # The qualified + non-qualified split must always reconcile to the total.
    reconciled = (
        df["qualified_activation_count"] + df["non_qualified_activation_count"]
    )
    assert (reconciled == df["activation_count"]).all()


# ---------------------------------------------------------------------------
# Test 2 — qualification_rate_pct calculation
# ---------------------------------------------------------------------------


def test_activation_summary_qualification_rate() -> None:
    df = execute_query("get_activation_summary", {"mon_period": "202603"})
    # The frame is already sorted by activation_count desc — the top dealer
    # is the highest-volume one.
    top = df.iloc[0]
    total = int(top["activation_count"])
    qualified = int(top["qualified_activation_count"])
    expected_rate = round(qualified / total * 100.0, 2)
    assert float(top["qualification_rate_pct"]) == pytest.approx(expected_rate, abs=0.01)
    # And it must be in the valid percentage band.
    assert 0.0 <= float(top["qualification_rate_pct"]) <= 100.0


# ---------------------------------------------------------------------------
# Test 3 — variance: dealers present in both periods, deltas in both directions
# ---------------------------------------------------------------------------


def test_activation_variance_two_periods() -> None:
    df = execute_query(
        "get_activation_variance",
        {"period_a": "202602", "period_b": "202603"},
    )
    assert len(df) > 0

    # All rows must carry both periods, and the delta must equal b - a.
    assert (df["period_a"] == "202602").all()
    assert (df["period_b"] == "202603").all()
    assert (
        df["delta_activations"]
        == df["activation_count_b"] - df["activation_count_a"]
    ).all()

    # Must contain both winners and losers (production data has plenty of each).
    assert (df["delta_activations"] > 0).any()
    assert (df["delta_activations"] < 0).any()

    # Inner-join only: every dealer here was present in BOTH periods, so
    # neither side may be zero unless that dealer genuinely had 0 in one
    # period (rare — pandas merge inner has dropped the absent ones already).
    # Sanity: row count <= min(unique dealers in a, b).
    a = execute_query("get_activation_summary", {"mon_period": "202602"})
    b = execute_query("get_activation_summary", {"mon_period": "202603"})
    assert len(df) <= min(len(a), len(b))


# ---------------------------------------------------------------------------
# Test 4 — all three exception types are present in 202603
# ---------------------------------------------------------------------------


def test_activation_exceptions_all_types_present() -> None:
    df = execute_query("get_activation_exceptions", {"mon_period": "202603"})
    assert len(df) > 0

    present = set(df["exception_type"].astype(str).unique())
    expected = {"ALL_UNQUALIFIED", "HIGH_UNQUALIFIED_RATE", "UNUSUAL_VOLUME"}
    assert expected.issubset(present), (
        f"Missing exception types: {expected - present}"
    )


# ---------------------------------------------------------------------------
# Test 5 — UNUSUAL_VOLUME threshold = mean + 2*std
# ---------------------------------------------------------------------------


def test_unusual_volume_threshold() -> None:
    summary = execute_query("get_activation_summary", {"mon_period": "202603"})
    counts = summary["activation_count"].astype(float)
    threshold = float(counts.mean()) + 2.0 * float(counts.std(ddof=1))

    exceptions = execute_query("get_activation_exceptions", {"mon_period": "202603"})
    unusual = exceptions[exceptions["exception_type"] == "UNUSUAL_VOLUME"]
    assert len(unusual) > 0

    # Every flagged dealer must clear the threshold.
    assert (unusual["activation_count"].astype(float) >= threshold).all(), (
        f"Some UNUSUAL_VOLUME rows below threshold {threshold:.2f}"
    )

    # And no dealer above the threshold should be missing from the flag set.
    flagged_ids = set(unusual["dealer_id"].astype(str))
    above_threshold = summary[summary["activation_count"].astype(float) >= threshold]
    expected_ids = set(above_threshold["dealer_id"].astype(str))
    assert expected_ids == flagged_ids, (
        f"Threshold mismatch — expected {len(expected_ids)} dealers flagged, "
        f"got {len(flagged_ids)}"
    )


# ---------------------------------------------------------------------------
# Test 6 — GET /activations/summary endpoint
# ---------------------------------------------------------------------------


def test_activation_api_summary_endpoint(client: TestClient) -> None:
    r = client.get("/activations/summary", params={"mon_period": "202603"})
    assert r.status_code == 200, r.text

    body = r.json()
    assert isinstance(body, list)
    assert len(body) == 922  # one row per dealer in 202603

    required = {
        "dealer_id",
        "dealer_name",
        "account_profile_class",
        "report_month",
        "activation_count",
        "qualified_activation_count",
        "non_qualified_activation_count",
        "activation_commission_amount",
        "qualification_rate_pct",
    }
    assert required.issubset(set(body[0].keys()))

    # Sorted by activation_count descending — first item has the highest count.
    counts = [row["activation_count"] for row in body]
    assert counts == sorted(counts, reverse=True)


# ---------------------------------------------------------------------------
# Test 7 — GET /activations/exceptions endpoint
# ---------------------------------------------------------------------------


def test_activation_api_exceptions_endpoint(client: TestClient) -> None:
    r = client.get("/activations/exceptions", params={"mon_period": "202603"})
    assert r.status_code == 200, r.text

    body = r.json()
    assert isinstance(body, list)
    assert len(body) > 0

    valid_types = {"ALL_UNQUALIFIED", "HIGH_UNQUALIFIED_RATE", "UNUSUAL_VOLUME"}
    for row in body:
        assert row["exception_type"] in valid_types, (
            f"Unexpected exception_type: {row['exception_type']!r}"
        )
