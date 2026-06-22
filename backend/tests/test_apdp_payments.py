"""Tests for the PAYMENT_SOURCE=apdp branch of the /payments/* routes.

These tests do NOT require a running APDP Postgres — psycopg2's connection
is monkeypatched to a fake that yields canned rows mimicking the
normalized.partner_settlements view shape.

Run:
    python -m pytest backend/tests/test_apdp_payments.py -v
"""
from __future__ import annotations

import os
from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient

# Sample mode for the other (Presto-less) endpoints. The PAYMENT_SOURCE
# flag is patched per-test via the autouse fixture below — env-var-only
# wouldn't work if another test module imported backend.config first.
os.environ["USE_SAMPLE_DATA"] = "true"

from backend.main import app  # noqa: E402


# One row per dealer covering each reconciliation_status state so the
# mapping logic gets full coverage in one fixture.
APDP_ROWS_202410 = [
    {
        "dealer_id":                  "FBB_D00001",
        "settlement_period":          "202410",
        "sale_count":                 21,
        "total_sales_ngn":            920_000.0,
        "statement_count":            1,
        "expected_commission_ngn":    73_600.0,
        "statement_gross_revenue_ngn": 920_000.0,
        "settlement_count":           1,
        "total_settled_ngn":          73_600.0,
        "paid_count":                 1,
        "partial_count":              0,
        "disputed_count":             0,
        "payment_variance_ngn":       0.0,
        "reconciliation_status":      "RECONCILED",
    },
    {
        "dealer_id":                  "FBB_D00002",
        "settlement_period":          "202410",
        "sale_count":                 14,
        "total_sales_ngn":            560_000.0,
        "statement_count":            1,
        "expected_commission_ngn":    44_800.0,
        "statement_gross_revenue_ngn": 560_000.0,
        "settlement_count":           1,
        "total_settled_ngn":          18_500.0,
        "paid_count":                 0,
        "partial_count":              1,
        "disputed_count":             0,
        "payment_variance_ngn":       -26_300.0,
        "reconciliation_status":      "PARTIALLY_PAID",
    },
    {
        "dealer_id":                  "FBB_D00003",
        "settlement_period":          "202410",
        "sale_count":                 9,
        "total_sales_ngn":            225_000.0,
        "statement_count":            1,
        "expected_commission_ngn":    15_750.0,
        "statement_gross_revenue_ngn": 225_000.0,
        "settlement_count":           1,
        "total_settled_ngn":          0.0,
        "paid_count":                 0,
        "partial_count":              0,
        "disputed_count":             1,
        "payment_variance_ngn":       -15_750.0,
        "reconciliation_status":      "DISPUTED",
    },
    {
        "dealer_id":                  "FBB_D00005",
        "settlement_period":          "202410",
        "sale_count":                 30,
        "total_sales_ngn":            1_200_000.0,
        "statement_count":            0,
        "expected_commission_ngn":    0.0,
        "statement_gross_revenue_ngn": 0.0,
        "settlement_count":           0,
        "total_settled_ngn":          0.0,
        "paid_count":                 0,
        "partial_count":              0,
        "disputed_count":             0,
        "payment_variance_ngn":       0.0,
        "reconciliation_status":      "SALES_WITHOUT_STATEMENT",
    },
]

APDP_ROWS_202409 = [
    # Same dealers, prior period — paid state.
    {
        "dealer_id":                  "FBB_D00001",
        "settlement_period":          "202409",
        "sale_count":                 19,
        "total_sales_ngn":            850_000.0,
        "statement_count":            1,
        "expected_commission_ngn":    68_000.0,
        "statement_gross_revenue_ngn": 850_000.0,
        "settlement_count":           1,
        "total_settled_ngn":          68_000.0,
        "paid_count":                 1,
        "partial_count":              0,
        "disputed_count":             0,
        "payment_variance_ngn":       0.0,
        "reconciliation_status":      "RECONCILED",
    },
    {
        "dealer_id":                  "FBB_D00002",
        "settlement_period":          "202409",
        "sale_count":                 12,
        "total_sales_ngn":            480_000.0,
        "statement_count":            1,
        "expected_commission_ngn":    38_400.0,
        "statement_gross_revenue_ngn": 480_000.0,
        "settlement_count":           1,
        "total_settled_ngn":          38_400.0,
        "paid_count":                 1,
        "partial_count":              0,
        "disputed_count":             0,
        "payment_variance_ngn":       0.0,
        "reconciliation_status":      "RECONCILED",
    },
]


def _fake_get_partner_settlements(period: str):
    if period == "202410":
        return list(APDP_ROWS_202410)
    if period == "202409":
        return list(APDP_ROWS_202409)
    return []


def _fake_get_partner_settlements_two_periods(period_a: str, period_b: str):
    return _fake_get_partner_settlements(period_a), _fake_get_partner_settlements(period_b)


@pytest.fixture(scope="module")
def client():
    with TestClient(app) as c:
        yield c


@pytest.fixture(autouse=True)
def patch_apdp_reader():
    """Force PAYMENT_SOURCE=apdp at the module attribute level (env vars are
    read-once at import time) and monkeypatch the APDP reader so no real
    Postgres is needed.
    """
    with patch("backend.config.PAYMENT_SOURCE", "apdp"), patch(
        "backend.db.apdp.get_partner_settlements",
        side_effect=_fake_get_partner_settlements,
    ), patch(
        "backend.db.apdp.get_partner_settlements_two_periods",
        side_effect=_fake_get_partner_settlements_two_periods,
    ):
        yield


# ---------------------------------------------------------------------------
# /health surfaces the source flag
# ---------------------------------------------------------------------------

def test_health_advertises_apdp_source(client: TestClient) -> None:
    # /health reads config at request time, so the autouse patch flips it
    data = client.get("/health").json()
    assert data["payment_source"] == "apdp"


# ---------------------------------------------------------------------------
# /payments/summary
# ---------------------------------------------------------------------------

def test_summary_returns_apdp_source_and_mapped_records(client: TestClient) -> None:
    r = client.get("/payments/summary?mon_period=202410")
    assert r.status_code == 200, r.text
    data = r.json()
    assert data["data_source"] == "APDP"
    assert data["period"] == "202410"
    # Aggregate totals: 73,600 + 44,800 + 15,750 + 0 = 134,150 owed
    assert data["total_commission_owed"] == pytest.approx(134_150.0)
    # Paid: 73,600 + 18,500 + 0 + 0 = 92,100
    assert data["total_amount_paid"] == pytest.approx(92_100.0)
    # Status counts: 1 RECONCILED→FULLY_PAID, 1 PARTIALLY_PAID, 1 DISPUTED, 1 SALES_WITHOUT_STATEMENT→PENDING
    assert data["fully_paid_count"] == 1
    assert data["partially_paid_count"] == 1
    assert data["disputed_count"] == 1
    assert data["pending_count"] == 1
    # Records carry the v1.3.0 enrichment fields
    by_dealer = {r["distributor_code"]: r for r in data["records"]}
    assert by_dealer["FBB_D00001"]["reconciliation_status"] == "RECONCILED"
    assert by_dealer["FBB_D00001"]["data_source"] == "APDP"
    assert by_dealer["FBB_D00002"]["payment_variance_ngn"] == pytest.approx(-26_300.0)
    assert by_dealer["FBB_D00005"]["sale_count"] == 30
    # Sales-without-statement is a PENDING in payment_status but flagged in exception_flag
    assert by_dealer["FBB_D00005"]["payment_status"] == "PENDING"
    assert by_dealer["FBB_D00005"]["exception_flag"] == "SALES_WITHOUT_STATEMENT"


def test_summary_reconciled_row_has_no_exception_flag(client: TestClient) -> None:
    r = client.get("/payments/summary?mon_period=202410")
    rec = next(x for x in r.json()["records"] if x["distributor_code"] == "FBB_D00001")
    assert rec["exception_flag"] is None


def test_summary_postgres_error_returns_503(client: TestClient) -> None:
    with patch(
        "backend.db.apdp.get_partner_settlements",
        side_effect=Exception("connection refused"),
    ):
        r = client.get("/payments/summary?mon_period=202410")
    assert r.status_code == 503
    assert "APDP unreachable" in r.json()["detail"]


# ---------------------------------------------------------------------------
# /payments/exceptions
# ---------------------------------------------------------------------------

def test_exceptions_excludes_fully_paid_and_sorts_by_severity(client: TestClient) -> None:
    r = client.get("/payments/exceptions?mon_period=202410")
    assert r.status_code == 200
    rows = r.json()
    statuses = [row["payment_status"] for row in rows]
    # No FULLY_PAID, three remaining, DISPUTED first
    assert "FULLY_PAID" not in statuses
    assert len(rows) == 3
    assert statuses[0] == "DISPUTED"
    # PARTIALLY_PAID comes before PENDING
    assert statuses.index("PARTIALLY_PAID") < statuses.index("PENDING")


# ---------------------------------------------------------------------------
# /payments/variance
# ---------------------------------------------------------------------------

def test_variance_returns_dealers_in_both_periods_only(client: TestClient) -> None:
    r = client.get("/payments/variance?period_a=202409&period_b=202410")
    assert r.status_code == 200
    rows = r.json()
    dealer_ids = {row["dealer_id"] for row in rows}
    # Only dealers present in BOTH periods (D00001, D00002). D00003/D00005 only in 202410.
    assert dealer_ids == {"FBB_D00001", "FBB_D00002"}


def test_variance_computes_signed_delta_and_status_change(client: TestClient) -> None:
    rows = client.get("/payments/variance?period_a=202409&period_b=202410").json()
    by_dealer = {row["dealer_id"]: row for row in rows}
    # D00001: 68,000 (Sep) → 73,600 (Oct) paid
    assert by_dealer["FBB_D00001"]["delta_paid"] == pytest.approx(73_600.0 - 68_000.0)
    assert by_dealer["FBB_D00001"]["status_changed"] is False  # both FULLY_PAID
    # D00002: 38,400 → 18,500, status flipped RECONCILED → PARTIALLY_PAID
    assert by_dealer["FBB_D00002"]["delta_paid"] == pytest.approx(18_500.0 - 38_400.0)
    assert by_dealer["FBB_D00002"]["status_changed"] is True
    assert by_dealer["FBB_D00002"]["payment_status_a"] == "FULLY_PAID"
    assert by_dealer["FBB_D00002"]["payment_status_b"] == "PARTIALLY_PAID"
