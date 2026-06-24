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


# ---------------------------------------------------------------------------
# Agent tool — compile_data_coverage_ticket through tool_executor
# ---------------------------------------------------------------------------

import json  # noqa: E402

from backend.agent.tool_executor import execute_tool  # noqa: E402


def test_agent_tool_happy_path() -> None:
    """The tool envelope returned to Claude carries the right shape."""
    result = execute_tool({
        "id": "toolu_test_001",
        "name": "compile_data_coverage_ticket",
        "input": {"mon_period": "202603", "source": "both"},
    })
    assert result["type"] == "tool_result"
    assert result["tool_use_id"] == "toolu_test_001"
    assert "is_error" not in result or not result["is_error"]

    envelope = json.loads(result["content"])
    assert envelope["tool"] == "compile_data_coverage_ticket"
    assert envelope["parameters"] == {"mon_period": "202603", "source": "both"}
    # The data_coverage helper's payload fields are spread into the envelope
    for key in (
        "mon_period", "source", "severity", "severity_action",
        "affected_dealers", "ifs_missing", "usp_missing", "ticket_body",
    ):
        assert key in envelope, f"missing key in envelope: {key}"
    assert envelope["drill_down_hint"]
    # ticket_body should be markdown, not empty
    assert envelope["ticket_body"].startswith("# FBB")


def test_agent_tool_rejects_missing_period() -> None:
    result = execute_tool({
        "id": "toolu_test_002",
        "name": "compile_data_coverage_ticket",
        "input": {"source": "both"},
    })
    assert result.get("is_error") is True
    assert "mon_period" in result["content"]


def test_agent_tool_rejects_invalid_source() -> None:
    result = execute_tool({
        "id": "toolu_test_003",
        "name": "compile_data_coverage_ticket",
        "input": {"mon_period": "202603", "source": "email"},
    })
    assert result.get("is_error") is True
    assert "invalid source" in result["content"].lower()


def test_agent_tool_source_ifs_excludes_usp_section() -> None:
    result = execute_tool({
        "id": "toolu_test_004",
        "name": "compile_data_coverage_ticket",
        "input": {"mon_period": "202603", "source": "ifs"},
    })
    envelope = json.loads(result["content"])
    assert envelope["source"] == "ifs"
    assert envelope["usp_missing"] == []
