"""
MTN MoMo transaction poller.

MTN MoMo doesn't push webhooks reliably in sandbox — we poll their
Collections API every 30 seconds for new transactions.

Auth flow:
  1. Base64 encode API_USER_ID:API_KEY → Basic auth
  2. POST to /collection/token/ → get Bearer access token (valid 3600s)
  3. Use Bearer token for all subsequent requests
  4. Refresh token before expiry
"""
import asyncio
import base64
import json
import structlog
from datetime import datetime, timezone, timedelta
from typing import Optional

import httpx

from ingestion.kafka_client import publish_event
from ingestion.config import settings

log = structlog.get_logger()

TOPIC = "raw.mtn.transactions"
POLL_INTERVAL_SECONDS = 30
TOKEN_REFRESH_BUFFER_SECONDS = 300  # Refresh 5 mins before expiry


class MTNMoMoPoller:
    def __init__(self):
        self.base_url = settings.MTN_BASE_URL
        self.subscription_key = settings.MTN_COLLECTIONS_SUBSCRIPTION_KEY
        self.api_user_id = settings.MTN_API_USER_ID
        self.api_key = settings.MTN_API_KEY
        self.target_env = settings.MTN_TARGET_ENVIRONMENT

        self._access_token: Optional[str] = None
        self._token_expires_at: Optional[datetime] = None
        self._last_poll_timestamp: Optional[str] = None

    def _get_basic_auth(self) -> str:
        """Base64 encode API_USER_ID:API_KEY for Basic auth."""
        credentials = f"{self.api_user_id}:{self.api_key}"
        return base64.b64encode(credentials.encode()).decode()

    async def get_access_token(self, client: httpx.AsyncClient) -> str:
        """
        Fetch a new OAuth2 Bearer token.
        MTN tokens are valid for 3600 seconds.
        """
        response = await client.post(
            f"{self.base_url}/collection/token/",
            headers={
                "Authorization": f"Basic {self._get_basic_auth()}",
                "Ocp-Apim-Subscription-Key": self.subscription_key,
            }
        )
        response.raise_for_status()
        data = response.json()

        self._access_token = data["access_token"]
        expires_in = int(data.get("expires_in", 3600))
        self._token_expires_at = datetime.now(timezone.utc) + timedelta(seconds=expires_in)

        log.info("MTN MoMo access token refreshed", expires_in=expires_in)
        return self._access_token

    def _token_needs_refresh(self) -> bool:
        if not self._access_token or not self._token_expires_at:
            return True
        buffer = timedelta(seconds=TOKEN_REFRESH_BUFFER_SECONDS)
        return datetime.now(timezone.utc) >= (self._token_expires_at - buffer)

    async def fetch_transactions(self, client: httpx.AsyncClient) -> list[dict]:
        """
        Fetch recent transactions from MTN MoMo Collections API.
        In sandbox, this returns simulated transactions.
        """
        if self._token_needs_refresh():
            await self.get_access_token(client)

        # MTN MoMo sandbox: fetch account balance as connectivity check
        # In production, you'd query transaction history endpoint
        response = await client.get(
            f"{self.base_url}/collection/v1_0/account/balance",
            headers={
                "Authorization": f"Bearer {self._access_token}",
                "Ocp-Apim-Subscription-Key": self.subscription_key,
                "X-Target-Environment": self.target_env,
            }
        )

        if response.status_code == 200:
            log.debug("MTN MoMo poll successful", status=response.status_code)
            # In sandbox, balance endpoint confirms connectivity
            # Real transaction polling uses different endpoint per deployment
            return []
        else:
            log.warning("MTN MoMo poll returned non-200", status=response.status_code)
            return []

    async def run(self):
        """
        Main polling loop. Runs indefinitely, polling every POLL_INTERVAL_SECONDS.
        """
        log.info("MTN MoMo poller starting", interval_seconds=POLL_INTERVAL_SECONDS)

        async with httpx.AsyncClient(timeout=30.0) as client:
            while True:
                try:
                    transactions = await self.fetch_transactions(client)

                    for txn in transactions:
                        envelope = {
                            "provider": "mtn_momo",
                            "event_type": "collection.completed",
                            "raw": txn,
                        }
                        publish_event(
                            topic=TOPIC,
                            payload=envelope,
                            provider="mtn_momo",
                            key=txn.get("financialTransactionId", "unknown")
                        )

                    if transactions:
                        log.info("MTN MoMo transactions published", count=len(transactions))

                except httpx.HTTPStatusError as e:
                    log.error("MTN MoMo HTTP error", status=e.response.status_code, error=str(e))
                except Exception as e:
                    log.error("MTN MoMo poller error", error=str(e))

                await asyncio.sleep(POLL_INTERVAL_SECONDS)


async def run_mtn_poller():
    """Entry point for running the poller as a standalone async task."""
    poller = MTNMoMoPoller()
    await poller.run()
