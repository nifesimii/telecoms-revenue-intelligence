"""
MTN MoMo — test/simulation endpoint.

MTN MoMo is poll-based (see pollers/mtn_momo.py for the real poller).
This receiver provides a /test endpoint to simulate MoMo collection
events during development without needing real transactions.
"""
import structlog
from fastapi import APIRouter
from datetime import datetime, timezone

from ingestion.kafka_client import publish_event

log = structlog.get_logger()
router = APIRouter()

TOPIC = "raw.mtn.transactions"


@router.get("/test")
async def test_mtn_momo():
    """
    Simulate an MTN MoMo collection.completed event.
    Mirrors the structure returned by the real MoMo Collections API.
    """
    mock_event = {
        "financialTransactionId": "MTN-TEST-001",
        "externalId": "EXT-TEST-001",
        "amount": "50000",
        "currency": "NGN",
        "payer": {
            "partyIdType": "MSISDN",
            "partyId": "2348012345678"     # MTN uses MSISDN (phone number)
        },
        "payerMessage": "Payment for goods",
        "payeeNote": "Thank you for your payment",
        "status": "SUCCESSFUL",
        "reason": None,
        "created": datetime.now(timezone.utc).isoformat(),
        "updated": datetime.now(timezone.utc).isoformat(),
    }

    envelope = {
        "provider": "mtn_momo",
        "event_type": "collection.completed",
        "raw": mock_event,
    }

    publish_event(
        topic=TOPIC,
        payload=envelope,
        provider="mtn_momo",
        key="MTN-TEST-001"
    )
    return {"status": "test event published", "topic": TOPIC}


@router.get("/poller/status")
async def poller_status():
    """
    Returns info about the MTN MoMo polling configuration.
    The actual poller runs as a background asyncio task.
    """
    from ingestion.config import settings
    return {
        "provider": "mtn_momo",
        "mode": "polling",
        "poll_interval_seconds": 30,
        "target_environment": settings.MTN_TARGET_ENVIRONMENT,
        "base_url": settings.MTN_BASE_URL,
        "api_user_configured": bool(settings.MTN_API_USER_ID),
        "subscription_key_configured": bool(settings.MTN_COLLECTIONS_SUBSCRIPTION_KEY),
    }