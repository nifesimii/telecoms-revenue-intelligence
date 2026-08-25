"""Phase 3 — query, assurance service, and API tests for Inventory Assurance.

Existing tests are not modified. Tests 9 and 10 (agent-level) live in
``test_inventory_agent.py``.
"""
from __future__ import annotations

import asyncio
import os

os.environ["USE_SAMPLE_DATA"] = "true"

import pytest  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

from backend.assurance.inventory_assurance import (  # noqa: E402
    InventoryAssuranceService,
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
# Test 1 — comparison returns records with the documented fields
# ---------------------------------------------------------------------------


def test_inventory_comparison_returns_records() -> None:
    df = execute_query("get_inventory_comparison", {"mon_period": "202603"})
    assert len(df) > 0

    required = {
        "dealer_id",
        "dealer_name",
        "product_code",
        "product_name",
        "activation_count",
        "qualified_count",
        "total_units_purchased",
        "inventory_gap",
        "gap_pct",
        "finding_type",
        "data_coverage_note",
    }
    assert required.issubset(set(df.columns))


# ---------------------------------------------------------------------------
# Test 2 — CONFIRMED_MISMATCH rows always have a positive inventory_gap
# ---------------------------------------------------------------------------


def test_confirmed_mismatches_present() -> None:
    df = execute_query("get_inventory_comparison", {"mon_period": "202603"})
    confirmed = df[df["finding_type"] == "CONFIRMED_MISMATCH"]
    assert len(confirmed) > 0
    assert (confirmed["inventory_gap"].astype(float) > 0).all()


# ---------------------------------------------------------------------------
# Test 3 — NO_INVOICE_RECORD rows carry None gap and gap_pct
# ---------------------------------------------------------------------------


def test_no_invoice_record_has_null_gap() -> None:
    df = execute_query("get_inventory_comparison", {"mon_period": "202603"})
    no_invoice = df[df["finding_type"] == "NO_INVOICE_RECORD"]
    assert len(no_invoice) > 0
    assert no_invoice["inventory_gap"].isna().all()
    assert no_invoice["gap_pct"].isna().all()
    assert no_invoice["total_units_purchased"].isna().all()


# ---------------------------------------------------------------------------
# Test 4 — WITHIN_ALLOCATION rows have activations <= purchased
# ---------------------------------------------------------------------------


def test_within_allocation_has_zero_or_negative_gap() -> None:
    df = execute_query("get_inventory_comparison", {"mon_period": "202603"})
    within = df[df["finding_type"] == "WITHIN_ALLOCATION"]
    if within.empty:
        pytest.skip("No WITHIN_ALLOCATION rows in current sample")
    # activation_count <= total_units_purchased.
    assert (
        within["activation_count"].astype(int)
        <= within["total_units_purchased"].astype(float)
    ).all()


# ---------------------------------------------------------------------------
# Test 5 — deduplication: Tivos Technology Ltd on product 1283279 = 60 units
# ---------------------------------------------------------------------------


def test_deduplication_applied() -> None:
    df = execute_query("get_inventory_comparison", {"mon_period": "202603"})
    tivos = df[
        (df["dealer_name"].str.contains("Tivos", case=False, na=False))
        & (df["product_code"].astype(str) == "1283279")
        & (df["total_units_purchased"].notna())
    ]
    assert len(tivos) >= 1, "Tivos dedup baseline row not found"
    assert int(tivos.iloc[0]["total_units_purchased"]) == 60


# ---------------------------------------------------------------------------
# Test 6 — InventoryAssuranceService produces FLAG with severity counts
# ---------------------------------------------------------------------------


def test_inventory_assurance_service() -> None:
    svc = InventoryAssuranceService()
    result = _run(svc.run("202603"))

    from backend.assurance.base import AssuranceResult

    assert isinstance(result, AssuranceResult)
    assert result.status == "FLAG"
    assert len(result.findings) > 0

    # HIGH findings must clear the gap_pct >= 200 threshold (the description
    # carries the percentage label).
    high = [f for f in result.findings if f["severity"] == "HIGH"]
    for f in high:
        # parse "XX.X%" from the recommended_action / description
        import re

        m = re.search(r"([0-9]+\.?[0-9]*)% excess", f["recommended_action"])
        assert m is not None, f"No gap_pct in HIGH finding: {f}"
        assert float(m.group(1)) >= 200.0

    # Metadata exposes the NO_INVOICE_RECORD count.
    assert "no_invoice_record_count" in result.metadata
    assert isinstance(result.metadata["no_invoice_record_count"], int)
    assert result.metadata["no_invoice_record_count"] > 0


# ---------------------------------------------------------------------------
# Test 7 — GET /inventory/comparison endpoint
# ---------------------------------------------------------------------------


def test_inventory_api_endpoint(client: TestClient) -> None:
    r = client.get("/inventory/comparison", params={"mon_period": "202603"})
    assert r.status_code == 200, r.text

    body = r.json()
    assert isinstance(body, list)
    assert len(body) > 0

    types = {row["finding_type"] for row in body}
    # CONFIRMED_MISMATCH must be present; WITHIN_ALLOCATION must NOT be
    # (default include_within_allocation=False).
    assert "CONFIRMED_MISMATCH" in types
    assert "WITHIN_ALLOCATION" not in types

    # NO_INVOICE_RECORD rows carry null gap/gap_pct.
    no_invoice = [r for r in body if r["finding_type"] == "NO_INVOICE_RECORD"]
    for row in no_invoice:
        assert row["inventory_gap"] is None
        assert row["gap_pct"] is None


def test_inventory_page_is_bounded_and_filterable(client: TestClient) -> None:
    r = client.get("/inventory/comparison-page", params={
        "mon_period": "202603", "limit": 25, "offset": 0,
        "finding_type": "CONFIRMED_MISMATCH",
    })
    assert r.status_code == 200, r.text
    body = r.json()
    assert len(body["items"]) <= 25
    assert body["pagination"]["returned"] == len(body["items"])
    assert body["pagination"]["total"] >= len(body["items"])
    assert all(row["finding_type"] == "CONFIRMED_MISMATCH" for row in body["items"])
    assert body["summary"]["confirmed_mismatch_count"] == body["pagination"]["total"]


def test_inventory_page_rejects_unbounded_limit(client: TestClient) -> None:
    r = client.get("/inventory/comparison-page", params={"mon_period": "202603", "limit": 1000})
    assert r.status_code == 422


# ---------------------------------------------------------------------------
# Test 8 — query results never use fraud language; agent question check
# ---------------------------------------------------------------------------


def test_inventory_assurance_never_uses_fraud_language() -> None:
    """The query layer must not emit fraud / theft / criminal language.

    (The agent-side language check lives in test 10 — that one is live.)
    """
    df = execute_query("get_inventory_comparison", {"mon_period": "202603"})
    forbidden = ("fraud", "theft", "grey market", "criminal")
    for col in ("data_coverage_note",):
        for txt in df[col].dropna().astype(str):
            lower = txt.lower()
            for word in forbidden:
                assert word not in lower, (
                    f"Forbidden word {word!r} in column {col}: {txt!r}"
                )

    svc = InventoryAssuranceService()
    result = _run(svc.run("202603"))
    blob = (
        result.summary
        + " "
        + result.metadata.get("coverage_note", "")
        + " "
        + " ".join(
            f["description"] + " " + f["recommended_action"] for f in result.findings
        )
    ).lower()
    for word in forbidden:
        assert word not in blob, f"Forbidden word {word!r} in service output"
