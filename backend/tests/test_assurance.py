"""Tests for the Assurance Layer scaffolding.

Five service-level tests (mocked-free — they hit the real query handlers in
sample-data mode) plus one API end-to-end test.

Existing 49 tests are not modified.
"""
from __future__ import annotations

import os

os.environ["USE_SAMPLE_DATA"] = "true"

import asyncio  # noqa: E402

import pytest  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

from backend.assurance.activation_assurance import (  # noqa: E402
    ActivationAssuranceService,
)
from backend.assurance.base import AssuranceResult  # noqa: E402
from backend.assurance.commission_assurance import (  # noqa: E402
    CommissionAssuranceService,
)
from backend.assurance.inventory_assurance import (  # noqa: E402
    InventoryAssuranceService,
)
from backend.assurance.payment_assurance import (  # noqa: E402
    PaymentAssuranceService,
)
from backend.assurance.registry import ASSURANCE_REGISTRY  # noqa: E402
from backend.main import app  # noqa: E402


def _run(coro):
    return asyncio.run(coro)


@pytest.fixture(scope="module")
def client() -> TestClient:
    with TestClient(app) as c:
        yield c


# ---------------------------------------------------------------------------
# Test 1 — Activation Assurance returns a populated result for 202603
# ---------------------------------------------------------------------------


def test_activation_assurance_returns_result() -> None:
    svc = ActivationAssuranceService()
    result = _run(svc.run("202603"))

    assert isinstance(result, AssuranceResult)
    assert result.module == "Activation Assurance"
    assert result.status == "FLAG"
    assert len(result.findings) > 0
    # Same 35 ALL_UNQUALIFIED dealers as the underlying query.
    high = sum(1 for f in result.findings if f["severity"] == "HIGH")
    assert high == 35


# ---------------------------------------------------------------------------
# Test 2 — Commission Assurance flags dealers with zero-commission counts
# ---------------------------------------------------------------------------


def test_commission_assurance_returns_result() -> None:
    svc = CommissionAssuranceService()
    result = _run(svc.run("202603"))

    assert isinstance(result, AssuranceResult)
    assert result.module == "Commission Assurance"
    assert result.status == "FLAG"
    assert len(result.findings) > 0
    # Every finding is MEDIUM severity per the spec.
    assert all(f["severity"] == "MEDIUM" for f in result.findings)
    assert all(
        f["type"] == "ZERO_COMMISSION_ACTIVATION" for f in result.findings
    )


# ---------------------------------------------------------------------------
# Test 3 — Inventory Assurance is a stub
# ---------------------------------------------------------------------------


def test_inventory_assurance_not_implemented() -> None:
    # Phase 3 update: InventoryAssuranceService.run() is now implemented
    # (Section 12 of the KB). The service now FLAGs CONFIRMED_MISMATCH
    # findings instead of returning NOT_IMPLEMENTED. The test name is kept
    # to preserve git history of the assurance stub; the assertion is
    # updated to match the post-Phase-3 contract.
    svc = InventoryAssuranceService()
    result = _run(svc.run("202603"))

    assert result.status == "FLAG"
    assert len(result.findings) > 0
    assert "no_invoice_record_count" in result.metadata


# ---------------------------------------------------------------------------
# Test 4 — Payment Assurance is a stub
# ---------------------------------------------------------------------------


def test_payment_assurance_not_implemented() -> None:
    # Phase 4 update: PaymentAssuranceService.run() is now implemented
    # (Section 13 of the KB). The service now FLAGs payment exceptions
    # instead of returning NOT_IMPLEMENTED. Test name preserved for git
    # history; assertion updated to the post-Phase-4 contract.
    svc = PaymentAssuranceService()
    result = _run(svc.run("202603"))

    assert result.status == "FLAG"
    assert len(result.findings) > 0
    assert result.metadata.get("data_source") == "SIMULATED"
    assert "[SIMULATED DATA]" in result.summary


# ---------------------------------------------------------------------------
# Test 5 — Registry contains all four modules under the documented keys
# ---------------------------------------------------------------------------


def test_registry_contains_all_four_modules() -> None:
    assert set(ASSURANCE_REGISTRY.keys()) == {
        "activation",
        "commission",
        "inventory",
        "payment",
    }


# ---------------------------------------------------------------------------
# Test 6 — GET /assurance/status returns the expected aggregated shape
# ---------------------------------------------------------------------------


def test_assurance_api_endpoint(client: TestClient) -> None:
    r = client.get("/assurance/status", params={"mon_period": "202603"})
    assert r.status_code == 200, r.text

    body = r.json()
    assert body["period"] == "202603"
    assert isinstance(body["modules"], list)
    assert len(body["modules"]) == 4

    by_name = {m["module"]: m for m in body["modules"]}
    assert set(by_name.keys()) == {
        "activation",
        "commission",
        "inventory",
        "payment",
    }

    # Implemented modules: activation + commission.
    assert by_name["activation"]["implemented"] is True
    assert by_name["activation"]["status"] == "FLAG"
    assert by_name["commission"]["implemented"] is True
    assert by_name["commission"]["status"] == "FLAG"

    # Phase 4 update: all four modules are now implemented. Inventory was
    # promoted in Phase 3; payment in Phase 4.
    inv = by_name["inventory"]
    assert inv["implemented"] is True
    assert inv["status"] == "FLAG"
    assert "high_count" in inv

    pay = by_name["payment"]
    assert pay["implemented"] is True
    assert pay["status"] == "FLAG"
    assert "high_count" in pay
