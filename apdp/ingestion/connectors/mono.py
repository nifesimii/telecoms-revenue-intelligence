"""MonoConsentConnector — open-banking consent-aggregation access model.

This is the production target for reading a dealer's OWN account: the dealer
authorizes Mono (via the Mono Connect widget) to share their account; Mono
returns an account_id; we poll that account's transactions. No merchant
relationship required, and it reads the dealer's actual wallet/bank — which
the merchant MoMo API cannot.

Builds on the existing mono_batch.py logic (same Mono API, same normalized
event shape) but behind the unified DealerDataConnector interface, so a Mono
dealer is just a `DealerConnection(connector_type="consent", account_ref=
<mono_account_id>, consent_status="granted")` row.

Requires: MONO_SECRET_KEY (shared aggregator key; the dealer-specific part is
the account_ref, obtained at consent time).
"""
from __future__ import annotations

import os
from datetime import datetime, timezone

from ingestion.connectors.base import (
    DealerConnection,
    FetchResult,
    register,
)

MONO_BASE_URL = "https://api.withmono.com"


class MonoConsentConnector:
    connector_type = "consent"

    def fetch(self, conn: DealerConnection, since: datetime | None) -> FetchResult:
        now = datetime.now(timezone.utc)

        # Consent must be granted before we may read this dealer's account.
        if conn.consent_status != "granted":
            return FetchResult(
                dealer_code=conn.dealer_code,
                connector_type=self.connector_type,
                envelopes=[],
                ok=False,
                error=f"consent not granted (status={conn.consent_status}).",
            )

        secret = os.getenv(conn.credentials_ref or "MONO_SECRET_KEY", "")
        if not secret:
            return FetchResult(
                dealer_code=conn.dealer_code,
                connector_type=self.connector_type,
                envelopes=[],
                ok=False,
                error="Mono secret key not configured.",
            )

        import httpx  # lazy — connector registers without the HTTP dep present
        try:
            with httpx.Client(timeout=30) as client:
                resp = client.get(
                    f"{MONO_BASE_URL}/accounts/{conn.account_ref}/transactions",
                    headers={"mono-sec-key": secret},
                    params={"paginate": "false"},
                )
                resp.raise_for_status()
                payload = resp.json()
        except Exception as e:  # noqa: BLE001
            return FetchResult(
                dealer_code=conn.dealer_code,
                connector_type=self.connector_type,
                envelopes=[],
                ok=False,
                error=f"Mono fetch failed: {type(e).__name__}: {e}",
            )

        txns = payload.get("data", payload if isinstance(payload, list) else [])
        envelopes = []
        for t in txns:
            tx_type = str(t.get("type", "credit")).lower()
            envelopes.append({
                "provider": "mono",
                "event_type": f"bank.{tx_type}",
                "raw": {
                    "id": t.get("_id") or t.get("id"),
                    "amount": t.get("amount", 0),        # Mono amounts are in kobo
                    "currency": t.get("currency", "NGN"),
                    "narration": t.get("narration"),
                    "type": tx_type,
                    "balance": t.get("balance"),
                    "date": t.get("date"),
                },
                "bank_code": (conn.metadata or {}).get("bank_code", "OTHER"),
                "account_id": conn.account_ref,
                "account_name": conn.display_name,
                "_dealer_code": conn.dealer_code,
            })

        return FetchResult(
            dealer_code=conn.dealer_code,
            connector_type=self.connector_type,
            envelopes=envelopes,
            ok=True,
            fetched_through=now,
        )


register(MonoConsentConnector())
