"""Phase 4 — query, assurance service, and API tests for Payment Intelligence.

Existing tests are not modified.
"""
from __future__ import annotations

import asyncio
import os

os.environ["USE_SAMPLE_DATA"] = "true"

import pandas as pd  # noqa: E402
import pytest  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

from backend.assurance.payment_assurance import (  # noqa: E402
    PaymentAssuranceService,
)
from backend.db.connection import execute_query  # noqa: E402
from backend.main import app  # noqa: E402


def _run(coro):
    return asyncio.run(coro)


@pytest.fixture(scope="module")
def client() -> TestClient:
    with TestClient(app) as c:
        yield c


# ---------------------------------------------------------------------------
# Test 1 — simulation file exists and is shaped correctly
# ---------------------------------------------------------------------------


def test_payment_simulation_file_exists() -> None:
    from backend import config

    path = config.SAMPLE_DATA_PATHS["payment_simulation"]
    assert path.exists(), f"payment_simulation.csv not found at {path}"

    df = pd.read_csv(path)
    # RAW CSV column names — these follow the source schema (Presto /
    # Hive), NOT the API-facing dealer_id/dealer_name convention. The
    # rename happens at the handler return boundary. See ARCHITECTURE.md.
    required = {
        "distributor_code",
        "distributor_name",
        "account_profile_class",
        "report_month",
        "commission_owed",
        "amount_paid",
        "amount_unpaid",
        "payment_rate",
        "payment_status",
        "payment_channel",
        "payment_date",
        "exception_flag",
        "data_source",
    }
    assert required.issubset(set(df.columns))

    periods = set(df["report_month"].astype(str))
    assert "202602" in periods
    assert "202603" in periods


# ---------------------------------------------------------------------------
# Test 2 — totals match get_dealer_summary; all four statuses present
# ---------------------------------------------------------------------------


def test_payment_summary_totals_202603() -> None:
    pay = execute_query("get_payment_summary", {"mon_period": "202603"})
    dealer = execute_query("get_dealer_summary", {"mon_period": "202603"})

    pay_total = float(pay["commission_owed"].astype(float).sum())
    dealer_total = float(dealer["total_commission_ngn"].astype(float).sum())

    # 1% tolerance per the spec (rounding can shift sums very slightly).
    assert abs(pay_total - dealer_total) / dealer_total < 0.01

    statuses = set(pay["payment_status"].astype(str))
    assert statuses == {"FULLY_PAID", "PARTIALLY_PAID", "DISPUTED", "PENDING"}


# ---------------------------------------------------------------------------
# Test 3 — DISPUTED records link only to ALL_UNQ / CONFIRMED_MISMATCH
# ---------------------------------------------------------------------------


def test_disputed_linked_to_exceptions() -> None:
    df = execute_query("get_payment_summary", {"mon_period": "202603"})
    disputed = df[df["payment_status"] == "DISPUTED"]
    assert len(disputed) > 0
    # All disputed rows must have a flag.
    flags = disputed["exception_flag"].dropna().astype(str)
    assert len(flags) == len(disputed)
    allowed = {"ALL_UNQUALIFIED", "CONFIRMED_MISMATCH"}
    assert set(flags) <= allowed


# ---------------------------------------------------------------------------
# Test 4 — FULLY_PAID has a payment_date; DISPUTED has none
# ---------------------------------------------------------------------------


def test_fully_paid_has_payment_date() -> None:
    df = execute_query("get_payment_summary", {"mon_period": "202603"})

    fully = df[df["payment_status"] == "FULLY_PAID"]
    assert len(fully) > 0
    assert fully["payment_date"].notna().all(), (
        "Some FULLY_PAID rows have null payment_date"
    )

    disputed = df[df["payment_status"] == "DISPUTED"]
    assert len(disputed) > 0
    # payment_date is None / NaN for all disputed.
    assert disputed["payment_date"].isna().all(), (
        "Some DISPUTED rows have a payment_date set"
    )


# ---------------------------------------------------------------------------
# Test 5 — exceptions endpoint excludes FULLY_PAID
# ---------------------------------------------------------------------------


def test_payment_exceptions_excludes_fully_paid() -> None:
    df = execute_query("get_payment_exceptions", {"mon_period": "202603"})
    assert len(df) > 0
    assert "FULLY_PAID" not in set(df["payment_status"].astype(str))


# ---------------------------------------------------------------------------
# Test 6 — realistic coverage band
# ---------------------------------------------------------------------------


def test_payment_coverage_is_realistic() -> None:
    df = execute_query("get_payment_summary", {"mon_period": "202603"})
    owed = float(df["commission_owed"].astype(float).sum())
    paid = float(df["amount_paid"].astype(float).sum())
    assert owed > 0
    coverage = paid / owed * 100.0
    assert 70.0 <= coverage <= 95.0, (
        f"Coverage {coverage:.2f}% outside 70-95% band"
    )


# ---------------------------------------------------------------------------
# Test 7 — PaymentAssuranceService
# ---------------------------------------------------------------------------


def test_payment_assurance_service() -> None:
    svc = PaymentAssuranceService()
    result = _run(svc.run("202603"))

    from backend.assurance.base import AssuranceResult

    assert isinstance(result, AssuranceResult)
    assert result.status == "FLAG"
    assert "payment_coverage_pct" in result.metadata
    assert result.metadata.get("data_source") == "SIMULATED"
    assert "[SIMULATED DATA]" in result.summary


# ---------------------------------------------------------------------------
# Test 8 — GET /payments/summary
# ---------------------------------------------------------------------------


def test_payment_api_summary_endpoint(client: TestClient) -> None:
    r = client.get("/payments/summary", params={"mon_period": "202603"})
    assert r.status_code == 200, r.text

    body = r.json()
    for field in (
        "period",
        "total_commission_owed",
        "total_amount_paid",
        "total_amount_unpaid",
        "payment_coverage_pct",
        "disputed_count",
        "partially_paid_count",
        "pending_count",
        "fully_paid_count",
        "data_source",
        "records",
    ):
        assert field in body, f"Missing field {field!r}"
    assert body["data_source"] == "SIMULATED"
    assert body["period"] == "202603"
    assert isinstance(body["records"], list)
    assert len(body["records"]) > 0


def test_payment_collection_is_bounded_and_consolidates_exceptions(client: TestClient) -> None:
    r = client.get("/payments", params={
        "mon_period": "202603", "limit": 25,
        "payment_status": "DISPUTED,PARTIALLY_PAID,PENDING",
    })
    assert r.status_code == 200, r.text
    body = r.json()
    assert len(body["items"]) <= 25
    assert body["pagination"]["returned"] == len(body["items"])
    assert all(row["payment_status"] != "FULLY_PAID" for row in body["items"])
    assert "Server-Timing" in r.headers


def test_dealer_verification_is_on_demand(client: TestClient) -> None:
    dealer = client.get("/dealers", params={"mon_period": "202603"}).json()[0]
    r = client.get(
        f"/dealers/{dealer['dealer_id']}/verification",
        params={"mon_period": "202603"},
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["dealer_id"] == dealer["dealer_id"]
    assert body["activation_count"] >= body["qualified_activation_count"]
