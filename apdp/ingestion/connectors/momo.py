"""MoMoConnector — MTN MoMo API access model.

The live-mechanism proof. Authenticates against MTN MoMo (sandbox by
default: sandbox.momodeveloper.mtn.com), pulls transaction activity, and
emits mtn_momo envelopes for the normalizer.

Honest scope note (read before trusting this for production):
  * The MoMo Collections/Disbursements API authenticates as a MERCHANT.
    It exposes transactions on accounts *you hold keys for* — not an
    arbitrary dealer's personal wallet. To read a dealer's own account you
    need either the `consent` model (dealer authorizes) or the `internal`
    model (MTN's own ledger). See docs/DEALER_CONNECTORS.md.
  * MTN's sandbox does not expose a rich transaction-history endpoint; it
    exposes account/balance + single-transaction status. So against sandbox
    this connector proves AUTH + CONNECTIVITY + envelope emission (the hard,
    provider-specific parts). Point `MTN_BASE_URL` at production and swap the
    fetch endpoint for the real statement/history API when credentials and
    the production access grant land.

Requires (per dealer or shared, via credentials_ref → env):
    MTN_COLLECTIONS_SUBSCRIPTION_KEY, MTN_API_USER_ID, MTN_API_KEY,
    MTN_BASE_URL, MTN_TARGET_ENVIRONMENT
"""
from __future__ import annotations

import base64
import os
from datetime import datetime, timezone

from ingestion.connectors.base import (
    DealerConnection,
    FetchResult,
    register,
)


class MoMoConnector:
    connector_type = "momo"

    def _cfg(self) -> dict[str, str]:
        # Read from ingestion.config if available, else env. Kept lazy so the
        # connector imports cleanly even when MoMo isn't configured.
        try:
            from ingestion.config import settings
            return {
                "sub_key": settings.MTN_COLLECTIONS_SUBSCRIPTION_KEY,
                "api_user": settings.MTN_API_USER_ID,
                "api_key": settings.MTN_API_KEY,
                "base_url": settings.MTN_BASE_URL,
            }
        except Exception:
            return {
                "sub_key": os.getenv("MTN_COLLECTIONS_SUBSCRIPTION_KEY", ""),
                "api_user": os.getenv("MTN_API_USER_ID", ""),
                "api_key": os.getenv("MTN_API_KEY", ""),
                "base_url": os.getenv("MTN_BASE_URL", "https://sandbox.momodeveloper.mtn.com"),
            }

    def fetch(self, conn: DealerConnection, since: datetime | None) -> FetchResult:
        cfg = self._cfg()
        now = datetime.now(timezone.utc)

        if not (cfg["sub_key"] and cfg["api_user"] and cfg["api_key"]):
            return FetchResult(
                dealer_code=conn.dealer_code,
                connector_type=self.connector_type,
                envelopes=[],
                ok=False,
                error="MoMo credentials not configured (MTN_* env not set).",
            )

        import httpx  # lazy — connector registers without the HTTP dep present
        try:
            with httpx.Client(timeout=20) as client:
                token = self._get_token(client, cfg)
                # Sandbox: balance call proves auth + connectivity. Production:
                # replace with the statement/transaction-history endpoint.
                resp = client.get(
                    f"{cfg['base_url']}/collection/v1_0/account/balance",
                    headers={
                        "Authorization": f"Bearer {token}",
                        "X-Target-Environment": os.getenv("MTN_TARGET_ENVIRONMENT", "sandbox"),
                        "Ocp-Apim-Subscription-Key": cfg["sub_key"],
                    },
                )
                resp.raise_for_status()
                balance = resp.json()
        except Exception as e:  # noqa: BLE001 — capture, don't sink the batch
            return FetchResult(
                dealer_code=conn.dealer_code,
                connector_type=self.connector_type,
                envelopes=[],
                ok=False,
                error=f"MoMo fetch failed: {type(e).__name__}: {e}",
            )

        # Emit a connectivity-proof envelope carrying the live balance. In
        # production this loop iterates the real transaction history instead.
        envelope = {
            "provider": "mtn_momo",
            "event_type": "collection.completed",
            "raw": {
                "financialTransactionId": f"MOMO_PROBE_{conn.dealer_code}_{int(now.timestamp())}",
                "externalId": conn.account_ref,
                "amount": str(balance.get("availableBalance", "0")),
                "currency": balance.get("currency", "EUR"),  # sandbox returns EUR
                "payer": {"partyIdType": "MSISDN", "partyId": conn.account_ref},
                "payerMessage": "MoMo connectivity probe",
                "payeeNote": f"dealer={conn.dealer_code}",
                "status": "SUCCESSFUL",
                "created": now.isoformat(),
                "updated": now.isoformat(),
            },
            "_dealer_code": conn.dealer_code,
            "_probe": True,   # marks this as a connectivity proof, not real txn
        }

        return FetchResult(
            dealer_code=conn.dealer_code,
            connector_type=self.connector_type,
            envelopes=[envelope],
            ok=True,
            fetched_through=now,
        )

    def _get_token(self, client, cfg: dict[str, str]) -> str:
        creds = base64.b64encode(f"{cfg['api_user']}:{cfg['api_key']}".encode()).decode()
        resp = client.post(
            f"{cfg['base_url']}/collection/token/",
            headers={
                "Authorization": f"Basic {creds}",
                "Ocp-Apim-Subscription-Key": cfg["sub_key"],
            },
        )
        resp.raise_for_status()
        return resp.json()["access_token"]


register(MoMoConnector())
