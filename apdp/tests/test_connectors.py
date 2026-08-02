"""Tests for the dealer data-connector layer.

All run with zero infra and zero credentials — the simulated connector +
per-dealer error isolation are what make this possible. The MoMo/Mono
connectors are exercised only for their no-credentials / no-consent guard
paths (their live behaviour needs real sandbox creds).

Run:  PYTHONPATH=apdp python -m pytest apdp/tests/test_connectors.py -q
"""
from __future__ import annotations

import json
import os
import sys
from pathlib import Path

import pytest

# Make `ingestion` and the flink normalizer importable.
APDP = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(APDP))
sys.path.insert(0, str(APDP / "flink_jobs"))

from ingestion.connectors import base  # noqa: E402
from ingestion.connectors.base import DealerConnection  # noqa: E402
from ingestion.connectors.onboarding import load_connections  # noqa: E402
from ingestion.connectors.runner import run  # noqa: E402


# ── Abstraction / registry ──────────────────────────────────────────────

def test_registry_lists_all_connectors():
    got = base.list_connectors()
    assert set(got) == {"simulated", "momo", "consent"}


def test_get_connector_resolves_and_unknown_is_none():
    assert base.get_connector("simulated") is not None
    assert base.get_connector("does_not_exist") is None


def test_connection_validates_connector_type():
    with pytest.raises(ValueError):
        DealerConnection(dealer_code="X", connector_type="bogus", account_ref="1")


def test_connection_readiness_rules():
    # simulated / momo / internal / file are ready when active
    assert DealerConnection("X", "simulated", "1").ready is True
    assert DealerConnection("X", "momo", "1").ready is True
    # inactive is never ready
    assert DealerConnection("X", "simulated", "1", is_active=False).ready is False
    # consent is ready ONLY when granted
    assert DealerConnection("X", "consent", "acc", consent_status="pending").ready is False
    assert DealerConnection("X", "consent", "acc", consent_status="granted").ready is True


# ── Onboarding registry ─────────────────────────────────────────────────

def test_onboarding_loads_sample_dealers():
    conns = load_connections()
    codes = {c.dealer_code for c in conns}
    # From dealer_connections.sample.json
    assert {"FBB_D00001", "FBB_D00002", "FBB_D00003", "FBB_D00004"} <= codes
    # The pending-consent dealer is present but not ready.
    d3 = next(c for c in conns if c.dealer_code == "FBB_D00003")
    assert d3.connector_type == "consent"
    assert d3.ready is False


# ── Simulated connector ─────────────────────────────────────────────────

def test_simulated_connector_is_deterministic():
    conn = DealerConnection("FBB_D00001", "simulated", "2348031000001")
    c = base.get_connector("simulated")
    a = c.fetch(conn, None)
    b = c.fetch(conn, None)
    assert a.ok and b.ok
    # Same seed (dealer + day) → identical transaction ids.
    assert [e["raw"]["financialTransactionId"] for e in a.envelopes] == \
           [e["raw"]["financialTransactionId"] for e in b.envelopes]


def test_simulated_envelopes_normalize():
    """The whole point: a connector envelope flows through the EXISTING
    normalizer with no changes."""
    from normalizer_core import normalize_event
    conn = DealerConnection("FBB_D00001", "simulated", "2348031000001")
    result = base.get_connector("simulated").fetch(conn, None)
    for env in result.envelopes:
        normalized = normalize_event(json.dumps(env))
        assert normalized is not None
        n = json.loads(normalized)
        assert n["provider"] == "mtn_momo"
        assert n["_pipeline_version"] == "1.3.0"
        assert n["amount_ngn"] >= 0


# ── MoMo / Mono guard paths (no creds / no consent) ─────────────────────

def test_momo_without_credentials_fails_cleanly(monkeypatch):
    for k in ("MTN_COLLECTIONS_SUBSCRIPTION_KEY", "MTN_API_USER_ID", "MTN_API_KEY"):
        monkeypatch.delenv(k, raising=False)
    # Also neutralise ingestion.config settings if present.
    import ingestion.connectors.momo as momo_mod
    monkeypatch.setattr(momo_mod.MoMoConnector, "_cfg",
                        lambda self: {"sub_key": "", "api_user": "", "api_key": "", "base_url": ""})
    conn = DealerConnection("FBB_D00004", "momo", "2348031000004")
    res = momo_mod.MoMoConnector().fetch(conn, None)
    assert res.ok is False
    assert "credentials not configured" in res.error


def test_consent_without_grant_fails_cleanly():
    conn = DealerConnection("FBB_D00003", "consent", "acc", consent_status="pending")
    res = base.get_connector("consent").fetch(conn, None)
    assert res.ok is False
    assert "consent not granted" in res.error


# ── Runner: per-dealer isolation + dry run ──────────────────────────────

def test_runner_dry_run_isolates_failures(monkeypatch):
    # Ensure MoMo has no creds so that dealer fails while simulated succeed.
    import ingestion.connectors.momo as momo_mod
    monkeypatch.setattr(momo_mod.MoMoConnector, "_cfg",
                        lambda self: {"sub_key": "", "api_user": "", "api_key": "", "base_url": ""})
    report = run(dry_run=True)
    # From the sample registry: 2 simulated ready + 1 momo ready (fails) +
    # 1 consent pending (not ready, so not attempted).
    assert report.dealers_attempted == 3
    assert report.dealers_ok == 2
    assert report.dealers_failed == 1
    assert report.events_published >= 6   # 2 simulated dealers, 3-8 events each
    # The failure is captured, not raised.
    failed = [d for d in report.details if not d["ok"]]
    assert len(failed) == 1
    assert failed[0]["dealer"] == "FBB_D00004"


def test_runner_named_dealer_probes_even_when_not_ready():
    # Naming a specific dealer ignores readiness so you can see the error.
    report = run(dry_run=True, only_dealer="FBB_D00003")
    assert report.dealers_attempted == 1
    assert report.dealers_failed == 1   # consent pending → clean failure
