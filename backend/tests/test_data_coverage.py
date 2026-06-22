"""Tests for the data coverage ticket compiler + endpoint."""
from __future__ import annotations

import os

os.environ["USE_SAMPLE_DATA"] = "true"

import pytest
from fastapi.testclient import TestClient

from backend.db.data_coverage import _severity_for, compile_data_coverage_ticket
from backend.main import app


@pytest.fixture(scope="module")
def client():
    with TestClient(app) as c:
        yield c


# ---------------------------------------------------------------------------
# Severity rules
# ---------------------------------------------------------------------------

@pytest.mark.parametrize(
    "count,expected",
    [(0, "LOW"), (1, "LOW"), (3, "LOW"), (4, "MEDIUM"), (10, "MEDIUM"), (11, "HIGH"), (500, "HIGH")],
)
def test_severity_tiers(count: int, expected: str) -> None:
    label, _action = _severity_for(count)
    assert label == expected


# ---------------------------------------------------------------------------
# Compiler shape
# ---------------------------------------------------------------------------

def test_compiler_returns_expected_payload_shape() -> None:
    # 202603 exists in the sample data.
    out = compile_data_coverage_ticket("202603", "both")
    # Required keys present
    for key in (
        "mon_period", "source", "severity", "severity_action",
        "affected_dealers", "ifs_missing", "usp_missing", "ticket_body",
    ):
        assert key in out, f"missing key {key}"
    assert out["mon_period"] == "202603"
    assert out["source"] == "both"
    assert out["severity"] in ("LOW", "MEDIUM", "HIGH")
    assert isinstance(out["ifs_missing"], list)
    assert isinstance(out["usp_missing"], list)
    assert "FBB Commission Data Coverage Issue" in out["ticket_body"]
    assert out["mon_period"] in out["ticket_body"]


def test_compiler_source_filter() -> None:
    """source='ifs' should only populate ifs_missing; same for 'usp'."""
    ifs_only = compile_data_coverage_ticket("202603", "ifs")
    assert ifs_only["usp_missing"] == []
    usp_only = compile_data_coverage_ticket("202603", "usp")
    assert usp_only["ifs_missing"] == []


def test_compiler_affected_dealer_count_dedupes() -> None:
    """affected_dealers is a union — a dealer in both IFS and USP counts once."""
    out = compile_data_coverage_ticket("202603", "both")
    union_size = len(
        {r["dealer_id"] for r in out["ifs_missing"]}
        | {r["dealer_id"] for r in out["usp_missing"]}
    )
    assert out["affected_dealers"] == union_size


# ---------------------------------------------------------------------------
# Endpoint
# ---------------------------------------------------------------------------

def test_endpoint_returns_200_and_ticket_body(client: TestClient) -> None:
    r = client.get("/inventory/data-coverage-issues?mon_period=202603")
    assert r.status_code == 200, r.text
    data = r.json()
    assert data["mon_period"] == "202603"
    assert data["source"] == "both"
    assert "ticket_body" in data and data["ticket_body"].startswith("# FBB")


def test_endpoint_rejects_bad_period(client: TestClient) -> None:
    r = client.get("/inventory/data-coverage-issues?mon_period=BAD")
    assert r.status_code == 422  # pydantic regex pattern rejects


def test_endpoint_rejects_bad_source(client: TestClient) -> None:
    r = client.get("/inventory/data-coverage-issues?mon_period=202603&source=email")
    assert r.status_code == 422


def test_endpoint_source_ifs_only(client: TestClient) -> None:
    r = client.get("/inventory/data-coverage-issues?mon_period=202603&source=ifs")
    assert r.status_code == 200
    data = r.json()
    assert data["source"] == "ifs"
    assert data["usp_missing"] == []
