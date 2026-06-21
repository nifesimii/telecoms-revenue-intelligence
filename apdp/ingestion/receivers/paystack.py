"""
Paystack webhook receiver.
Paystack uses HMAC-SHA512 signature verification.

Docs: https://paystack.com/docs/payments/webhooks
"""
import hmac
import hashlib
import structlog
from fastapi import APIRouter, Request, HTTPException, Header
from typing import Annotated

from ingestion.kafka_client import publish_event
from ingestion.config import settings

log = structlog.get_logger()
router = APIRouter()

TOPIC = "raw.paystack.transactions"


def verify_paystack_signature(payload_bytes: bytes, signature: str | None) -> bool:
    """
    Paystack signs webhooks with HMAC-SHA512 using your secret key.
    We recompute the hash and compare.
    """
    if not signature:
        return False

    secret = settings.PAYSTACK_SECRET_KEY.encode("utf-8")
    expected = hmac.new(secret, payload_bytes, hashlib.sha512).hexdigest()
    return hmac.compare_digest(expected, signature)


@router.post("")
async def receive_paystack_webhook(
    request: Request,
    x_paystack_signature: Annotated[str | None, Header(alias="x-paystack-signature")] = None,
):
    """
    Receives all Paystack webhook events.

    Key event types:
    - charge.success      → payment successful
    - transfer.success    → payout successful
    - transfer.failed     → payout failed
    """
    # 1. Read raw bytes FIRST (needed for signature verification)
    body_bytes = await request.body()

    # 2. Verify signature
    if not verify_paystack_signature(body_bytes, x_paystack_signature):
        log.warning("Paystack webhook signature verification failed")
        raise HTTPException(status_code=401, detail="Invalid webhook signature")

    # 3. Parse JSON
    import json
    try:
        payload = json.loads(body_bytes)
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid JSON body")

    event_type = payload.get("event", "unknown")
    reference = payload.get("data", {}).get("reference", "unknown")

    log.info(
        "Paystack webhook received",
        event_type=event_type,
        reference=reference,
    )

    # 4. Publish to Kafka
    envelope = {
        "provider": "paystack",
        "event_type": event_type,
        "raw": payload,
    }

    success = publish_event(
        topic=TOPIC,
        payload=envelope,
        provider="paystack",
        key=reference,
    )

    if not success:
        raise HTTPException(status_code=500, detail="Failed to queue event")

    return {"status": "received", "event": event_type, "reference": reference}


@router.get("/test")
async def test_paystack():
    """Simulate a Paystack charge.success event for dev testing."""
    mock_event = {
        "event": "charge.success",
        "data": {
            "id": 88888,
            "reference": "TEST-PS-001",
            "amount": 5000000,   # Paystack uses kobo — this is ₦50,000
            "currency": "NGN",
            "status": "success",
            "customer": {
                "first_name": "Test",
                "last_name": "User",
                "email": "test@example.com",
                "phone": "08012345678"
            },
            "created_at": "2024-01-15T14:10:30.000Z"
        }
    }

    envelope = {
        "provider": "paystack",
        "event_type": "charge.success",
        "raw": mock_event,
    }

    publish_event(topic=TOPIC, payload=envelope, provider="paystack", key="TEST-PS-001")
    return {"status": "test event published", "topic": TOPIC}
