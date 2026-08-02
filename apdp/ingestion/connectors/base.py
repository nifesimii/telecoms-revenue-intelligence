"""DealerDataConnector — the model-agnostic contract.

The point of this layer: "connect to a dealer and fetch their account
data" is not one thing. Depending on what MTN/finance grants, the access
model is one of:

  * momo     — MTN MoMo API (merchant-side; sees accounts we hold keys to)
  * consent  — open-banking aggregation (Mono/Okra; dealer authorizes read)
  * internal — MTN's own MoMo/BSS ledger feed (no per-dealer consent)
  * file     — batch CSV/export drop (already handled by telecom_batch)
  * simulated— deterministic fake source (proves the pipeline with no creds)

Every model is wrapped behind ONE interface. A dealer is onboarded by
adding a `DealerConnection` row (connector type + account ref + creds ref);
the runner dispatches each connection to its connector and publishes the
returned raw envelopes to Kafka. Whatever model finance approves, we
implement/activate that one connector — everything downstream (normalizer,
sink, FBB) is unchanged.

A connector returns **raw envelopes** in exactly the shape the Flink
normalizer expects:

    {
        "provider":   "mtn_momo" | "mono" | "telecom_batch" | ...,
        "event_type": "collection.completed" | "bank.credit" | ...,
        "raw":        { ...provider-native transaction fields... },
    }

The runner stamps `_ingested_at` / `_source_topic` via kafka_client on publish.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Protocol, runtime_checkable

# The five access models. `file` and `simulated` need no external grant.
CONNECTOR_TYPES = ("momo", "consent", "internal", "file", "simulated")

# Consent lifecycle for consent-aggregation dealers. Non-consent models
# report "n/a".
CONSENT_STATES = ("pending", "granted", "revoked", "expired", "n/a")


@dataclass
class DealerConnection:
    """One onboarded dealer's data-access config — the 'add a dealer = a row'
    unit. Persisted in the dealer_connections table (or a JSON fallback).

    Attributes:
        dealer_code:    joins to FBB's distributor_code.
        connector_type: one of CONNECTOR_TYPES — which access model.
        account_ref:    provider-native account identifier (MoMo MSISDN /
                        Mono account_id / internal partner id / file glob).
        credentials_ref: name of the env/secret holding this dealer's creds,
                        NOT the secret itself. e.g. "MONO_SECRET_KEY". Lets
                        onboarding stay in config while secrets stay in the
                        secret store.
        consent_status: consent lifecycle (consent model only; else "n/a").
        is_active:      disable a dealer without deleting the row.
        display_name:   human label.
        metadata:       free-form (region, tier, notes).
    """

    dealer_code: str
    connector_type: str
    account_ref: str
    credentials_ref: str | None = None
    consent_status: str = "n/a"
    is_active: bool = True
    display_name: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if self.connector_type not in CONNECTOR_TYPES:
            raise ValueError(
                f"unknown connector_type {self.connector_type!r}; "
                f"expected one of {CONNECTOR_TYPES}"
            )
        if self.consent_status not in CONSENT_STATES:
            raise ValueError(f"invalid consent_status {self.consent_status!r}")

    @property
    def ready(self) -> bool:
        """Can we pull from this dealer right now?"""
        if not self.is_active:
            return False
        if self.connector_type == "consent":
            return self.consent_status == "granted"
        return True


@dataclass
class FetchResult:
    """Outcome of one connector.fetch() — envelopes plus provenance so the
    runner can log/monitor per dealer without the connector knowing Kafka."""

    dealer_code: str
    connector_type: str
    envelopes: list[dict[str, Any]]
    ok: bool = True
    error: str | None = None
    fetched_through: datetime | None = None   # high-water mark for next run


@runtime_checkable
class DealerDataConnector(Protocol):
    """One access model. Implementations are stateless; per-dealer config
    arrives via the DealerConnection argument."""

    #: stable connector-type key, one of CONNECTOR_TYPES
    connector_type: str

    def fetch(self, conn: DealerConnection, since: datetime | None) -> FetchResult:
        """Pull `conn`'s account activity since `since` (None = full/default
        window) and return raw envelopes ready for the normalizer. Must not
        raise for expected failures (auth, network) — capture them in
        FetchResult.ok/error so one dealer's failure doesn't sink the batch.
        """
        ...


# ── Registry ─────────────────────────────────────────────────────────────
_REGISTRY: dict[str, DealerDataConnector] = {}


def register(connector: DealerDataConnector) -> DealerDataConnector:
    _REGISTRY[connector.connector_type] = connector
    return connector


def get_connector(connector_type: str) -> DealerDataConnector | None:
    _ensure_loaded()
    return _REGISTRY.get(connector_type)


def list_connectors() -> list[str]:
    _ensure_loaded()
    return sorted(_REGISTRY.keys())


_loaded = False


def _ensure_loaded() -> None:
    """Import concrete connectors so they self-register."""
    global _loaded
    if _loaded:
        return
    _loaded = True
    from ingestion.connectors import simulated, momo, mono  # noqa: F401
