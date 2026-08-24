"""Regression coverage for the agent-facing dealer dossier."""
from __future__ import annotations

import pandas as pd

from backend import config
from backend.db.composite import assemble_dealer_full_context
from backend.db.queries import _sample_get_health_scorecard


def test_dossier_uses_apdp_payment_source(monkeypatch) -> None:
    """The agent dossier must not silently fall back to simulated payments."""
    apdp_rows = [
        {
            "dealer_id": "19472",
            "settlement_period": "202602",
            "expected_commission_ngn": 12_345.0,
            "total_settled_ngn": 10_000.0,
            "reconciliation_status": "PARTIALLY_PAID",
        }
    ]
    monkeypatch.setattr(config, "PAYMENT_SOURCE", "apdp")
    monkeypatch.setattr(
        "backend.db.composite.payment_lookup",
        lambda period, source: pd.DataFrame(apdp_rows),
    )

    dossier = assemble_dealer_full_context("19472", "202602")

    assert dossier["found"] is True
    assert dossier["payment"] == {
        "commission_owed_ngn": 12_345.0,
        "amount_paid_ngn": 10_000.0,
        "amount_unpaid_ngn": 2_345.0,
        "payment_status": "PARTIALLY_PAID",
        "exception_flag": "PARTIALLY_PAID",
        "payment_channel": "",
        "payment_date": None,
        "data_source": "APDP",
    }


def test_dossier_allows_an_empty_apdp_payment_view(monkeypatch) -> None:
    monkeypatch.setattr(config, "PAYMENT_SOURCE", "apdp")
    monkeypatch.setattr(
        "backend.db.composite.payment_lookup",
        lambda period, source: pd.DataFrame(),
    )

    dossier = assemble_dealer_full_context("19472", "202602")

    assert dossier["found"] is True
    assert dossier["payment"] == {}


def test_health_scorecard_uses_apdp_payment_source(monkeypatch) -> None:
    """The health tab must use and identify APDP settlements when enabled."""
    frames = {
        "202603": pd.DataFrame([
            {
                "dealer_id": "19969",
                "expected_commission_ngn": 10_000.0,
                "total_settled_ngn": 7_500.0,
                "reconciliation_status": "PARTIALLY_PAID",
            }
        ]),
        "202602": pd.DataFrame([
            {
                "dealer_id": "19969",
                "expected_commission_ngn": 10_000.0,
                "total_settled_ngn": 5_000.0,
                "reconciliation_status": "PARTIALLY_PAID",
            }
        ]),
    }
    calls = []

    def fake_lookup(period, source):
        calls.append((period, source))
        return frames[period].copy()

    monkeypatch.setattr(config, "PAYMENT_SOURCE", "apdp")
    monkeypatch.setattr("backend.audit.payment_data.payment_lookup", fake_lookup)

    result = _sample_get_health_scorecard(
        {"current_period": "202603", "prior_period": "202602"}
    )

    assert calls == [("202603", "apdp"), ("202602", "apdp")]
    row = result.loc[result["dealer_id"] == "19969"].iloc[0]
    assert row["settlement_rate_pct"] == 75.0
    assert row["settlement_rate_delta"] == 25.0
    assert row["outstanding_ngn"] == 2_500.0
    assert row["data_source"] == "APDP"


def test_health_scorecard_allows_empty_apdp_view(monkeypatch) -> None:
    monkeypatch.setattr(config, "PAYMENT_SOURCE", "apdp")
    monkeypatch.setattr(
        "backend.audit.payment_data.payment_lookup",
        lambda period, source: pd.DataFrame(),
    )

    result = _sample_get_health_scorecard(
        {"current_period": "202603", "prior_period": "202602"}
    )

    assert result.empty
    assert "data_source" in result.columns
