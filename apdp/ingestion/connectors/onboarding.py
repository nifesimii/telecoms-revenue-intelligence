"""Dealer onboarding registry — "add a dealer = a row, not code".

Loads the list of onboarded dealers (their DealerConnection config) from,
in priority order:

  1. Postgres `public.dealer_connections` (the production source), if a
     DATABASE_URL is set and the table exists, else
  2. a JSON file at DEALER_CONNECTIONS_FILE (default
     ingestion/connectors/dealer_connections.sample.json) — the zero-infra
     path so the connector layer is demonstrable with no database.

The point: onboarding a dealer, granting/revoking consent, disabling a
dealer — all data operations, never code changes.
"""
from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

from ingestion.connectors.base import DealerConnection

_DEFAULT_FILE = Path(__file__).parent / "dealer_connections.sample.json"


def load_connections() -> list[DealerConnection]:
    rows = _load_from_postgres()
    if rows is None:
        rows = _load_from_file()
    return [_to_connection(r) for r in rows]


def active_connections() -> list[DealerConnection]:
    """Only dealers we can pull from right now (active + consent-ready)."""
    return [c for c in load_connections() if c.ready]


def _to_connection(r: dict[str, Any]) -> DealerConnection:
    return DealerConnection(
        dealer_code=str(r["dealer_code"]),
        connector_type=str(r["connector_type"]),
        account_ref=str(r["account_ref"]),
        credentials_ref=r.get("credentials_ref"),
        consent_status=r.get("consent_status", "n/a"),
        is_active=bool(r.get("is_active", True)),
        display_name=r.get("display_name"),
        metadata=r.get("metadata") or {},
    )


def _load_from_file() -> list[dict[str, Any]]:
    path = Path(os.getenv("DEALER_CONNECTIONS_FILE", str(_DEFAULT_FILE)))
    if not path.exists():
        return []
    with path.open() as f:
        data = json.load(f)
    return data.get("dealers", data if isinstance(data, list) else [])


def _load_from_postgres() -> list[dict[str, Any]] | None:
    """Return rows from public.dealer_connections, or None if unavailable
    (no DATABASE_URL / no psycopg2 / table missing) so the caller falls back
    to the file source."""
    dsn = os.getenv("DATABASE_URL")
    if not dsn:
        return None
    try:
        import psycopg2
        import psycopg2.extras
    except Exception:
        return None
    try:
        conn = psycopg2.connect(dsn, connect_timeout=5)
        try:
            with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
                cur.execute(
                    "SELECT dealer_code, connector_type, account_ref, "
                    "credentials_ref, consent_status, is_active, display_name, "
                    "metadata FROM public.dealer_connections"
                )
                return [dict(r) for r in cur.fetchall()]
        finally:
            conn.close()
    except Exception:
        # Table missing / connection refused → fall back to file.
        return None
