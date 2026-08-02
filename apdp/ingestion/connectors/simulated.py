"""SimulatedConnector — deterministic fake dealer source.

Needs no credentials, no network, no external grant. Its job is to prove
the whole path works end to end *today*: runner → connector → raw envelope
→ (Kafka) → normalizer → Postgres → FBB. When you demo "here is a dealer's
data flowing through the pipeline" before any real access is granted, this
is what produces the data.

Emits mtn_momo-shaped `collection.completed` envelopes so the existing
normalizer handles them with no changes.
"""
from __future__ import annotations

import random
from datetime import datetime, timedelta, timezone

from ingestion.connectors.base import (
    DealerConnection,
    FetchResult,
    register,
)


class SimulatedConnector:
    connector_type = "simulated"

    def fetch(self, conn: DealerConnection, since: datetime | None) -> FetchResult:
        now = datetime.now(timezone.utc)
        start = since or (now - timedelta(days=1))
        # Deterministic per (dealer, day) so re-runs are reproducible.
        seed = f"{conn.dealer_code}:{start.date().isoformat()}"
        rng = random.Random(seed)

        n = rng.randint(3, 8)
        envelopes = []
        for i in range(n):
            ts = start + timedelta(minutes=rng.randint(0, 23 * 60))
            amount = rng.choice([1000, 2500, 5000, 8500, 25000])
            txn_id = f"SIM_{conn.dealer_code}_{start.date().isoformat()}_{i:03d}"
            envelopes.append({
                "provider": "mtn_momo",
                "event_type": "collection.completed",
                "raw": {
                    "financialTransactionId": txn_id,
                    "externalId": txn_id,
                    "amount": str(amount),
                    "currency": "NGN",
                    "payer": {"partyIdType": "MSISDN", "partyId": conn.account_ref},
                    "payerMessage": "Simulated dealer collection",
                    "payeeNote": f"dealer={conn.dealer_code}",
                    "status": "SUCCESSFUL",
                    "created": ts.isoformat(),
                    "updated": ts.isoformat(),
                },
                # Carry the dealer link so the normalizer/sink can attribute it.
                "_dealer_code": conn.dealer_code,
            })

        return FetchResult(
            dealer_code=conn.dealer_code,
            connector_type=self.connector_type,
            envelopes=envelopes,
            ok=True,
            fetched_through=now,
        )


register(SimulatedConnector())
