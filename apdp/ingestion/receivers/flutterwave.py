"""
Flutterwave webhook receiver.
Verifies the webhook signature and publishes raw events to Kafka.

Flutterwave sends a POST to this endpoint for every transaction event.
Docs: https://developer.flutterwave.com/docs/integration-guides/webhooks
"""
import structlog
from fastapi import APIRouter, Request, HTTPException, Header
from typing import Annotated

from ingestion.kafka_client import publish_event
from ingestion.config import settings

log = structlog.get_logger()
router = APIRouter()

TOPIC = "raw.flutterwave.transactions"


def verify_signature(verif_hash: str | None) -> bool:
    """
    Flutterwave uses a simple secret hash verification.
    The hash you set in your FLW dashboard must match the header.
    """
    if not settings.FLUTTERWAVE_WEBHOOK_HASH:
        # Never accept an unauthenticated payment event. Local testing uses
        # the explicit /test route instead of weakening the real receiver.
        log.error("FLUTTERWAVE_WEBHOOK_HASH not set — rejecting webhook")
        return False
    return verif_hash == settings.FLUTTERWAVE_WEBHOOK_HASH


@router.post("")
async def receive_flutterwave_webhook(
    request: Request,
    verif_hash: Annotated[str | None, Header(alias="verif-hash")] = None,
):
    """
    Receives all Flutterwave webhook events.
    
    Event types we handle:
    - charge.completed    → successful payment
    - transfer.completed  → successful payout
    - charge.failed       → failed payment
    """
    # 1. Verify webhook authenticity
    if not verify_signature(verif_hash):
        log.warning("Flutterwave webhook signature mismatch", received_hash=verif_hash)
        raise HTTPException(status_code=401, detail="Invalid webhook signature")

    # 2. Parse body
    try:
        payload = await request.json()
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid JSON body")

    event_type = payload.get("event", "unknown")
    transaction_id = payload.get("data", {}).get("id", "unknown")

    log.info(
        "Flutterwave webhook received",
        event_type=event_type,
        transaction_id=transaction_id,
    )

    # 3. Wrap with ingestion metadata and publish
    envelope = {
        "provider": "flutterwave",
        "event_type": event_type,
        "raw": payload,
    }

    success = publish_event(
        topic=TOPIC,
        payload=envelope,
        provider="flutterwave",
        key=str(transaction_id),   # Use txn ID as partition key
    )

    if not success:
        # Return 500 so Flutterwave retries
        raise HTTPException(status_code=500, detail="Failed to queue event")

    return {"status": "received", "event": event_type, "id": transaction_id}


@router.get("/test")
async def test_flutterwave():
    """
    Simulate a Flutterwave charge.completed event.
    Used during development to test the pipeline without real transactions.
    """
    mock_event = {
        "event": "charge.completed",
        "data": {
            "id": 99999,
            "tx_ref": "TEST-001",
            "flw_ref": "FLW-MOCK-001",
            "amount": 50000,
            "currency": "NGN",
            "status": "successful",
            "customer": {
                "name": "Test User",
                "email": "test@example.com",
                "phone_number": "+2348012345678"
            },
            "created_at": "2024-01-15T14:10:00.000Z"
        }
    }

    envelope = {
        "provider": "flutterwave",
        "event_type": "charge.completed",
        "raw": mock_event,
    }

    publish_event(topic=TOPIC, payload=envelope, provider="flutterwave", key="99999")
    return {"status": "test event published", "topic": TOPIC}
