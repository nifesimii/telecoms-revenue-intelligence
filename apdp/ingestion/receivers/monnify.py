"""
Monnify webhook receiver.

Monnify (by Interswitch) is widely used in Nigerian fintech for:
- Bank transfer collections
- USSD payments
- Card payments
- Virtual account funding

Monnify signs webhooks with HMAC-SHA512.
Docs: https://developers.monnify.com/docs/webhooks
"""
import hmac
import hashlib
import json
import structlog
from fastapi import APIRouter, Request, HTTPException, Header
from typing import Annotated

from ingestion.kafka_client import publish_event
from ingestion.config import settings

log = structlog.get_logger()
router = APIRouter()

TOPIC = "raw.monnify.transactions"


def verify_monnify_signature(payload_bytes: bytes, signature: str | None) -> bool:
    """
    Monnify signs webhook payloads with HMAC-SHA512.
    The signature is in the 'monnify-signature' header.
    """
    if not signature:
        return False
    if not settings.MONNIFY_SECRET_KEY:
        log.warning("MONNIFY_SECRET_KEY not set — skipping signature check")
        return True

    secret = settings.MONNIFY_SECRET_KEY.encode("utf-8")
    expected = hmac.new(secret, payload_bytes, hashlib.sha512).hexdigest()
    return hmac.compare_digest(expected, signature)


@router.post("")
async def receive_monnify_webhook(
    request: Request,
    monnify_signature: Annotated[str | None, Header(alias="monnify-signature")] = None,
):
    """
    Receives all Monnify webhook events.

    Key event types:
    - SUCCESSFUL_TRANSACTION     → payment successful (card/transfer/USSD)
    - FAILED_TRANSACTION         → payment failed
    - REVERSED_TRANSACTION       → payment reversed
    - DISBURSEMENT_COMPLETED     → payout completed
    - VIRTUAL_ACCOUNT_FUNDED     → virtual account received funds
    """
    # 1. Read raw bytes for signature verification
    body_bytes = await request.body()

    # 2. Verify signature
    if not verify_monnify_signature(body_bytes, monnify_signature):
        log.warning("Monnify webhook signature verification failed")
        raise HTTPException(status_code=401, detail="Invalid webhook signature")

    # 3. Parse JSON
    try:
        payload = json.loads(body_bytes)
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid JSON body")

    event_type = payload.get("eventType", "unknown")
    
    # Monnify nests transaction data under eventData
    event_data = payload.get("eventData", {})
    transaction_ref = event_data.get("transactionReference", "unknown")
    payment_ref = event_data.get("paymentReference", transaction_ref)

    log.info(
        "Monnify webhook received",
        event_type=event_type,
        transaction_ref=transaction_ref,
    )

    # 4. Publish to Kafka
    envelope = {
        "provider": "monnify",
        "event_type": event_type,
        "raw": payload,
    }

    success = publish_event(
        topic=TOPIC,
        payload=envelope,
        provider="monnify",
        key=transaction_ref,
    )

    if not success:
        raise HTTPException(status_code=500, detail="Failed to queue event")

    return {"status": "received", "event": event_type, "reference": transaction_ref}


@router.get("/test")
async def test_monnify():
    """Simulate a Monnify SUCCESSFUL_TRANSACTION event for dev testing."""
    mock_event = {
        "eventType": "SUCCESSFUL_TRANSACTION",
        "eventData": {
            "transactionReference": "MNFY-TEST-001",
            "paymentReference": "MNFY-PAY-001",
            "amountPaid": 50000.00,
            "totalPayable": 50000.00,
            "settlementAmount": 49250.00,   # after Monnify fee
            "currencyCode": "NGN",
            "paymentStatus": "PAID",
            "paymentDescription": "Payment for goods",
            "paymentMethod": "ACCOUNT_TRANSFER",
            "customer": {
                "name": "Test User",
                "email": "test@example.com",
            },
            "product": {
                "reference": "PROD-001",
                "name": "Test Product"
            },
            "metaData": {},
            "createdOn": "2024-01-15T14:10:00.000+0000",
            "completedOn": "2024-01-15T14:10:45.000+0000",
        }
    }

    envelope = {
        "provider": "monnify",
        "event_type": "SUCCESSFUL_TRANSACTION",
        "raw": mock_event,
    }

    publish_event(
        topic=TOPIC,
        payload=envelope,
        provider="monnify",
        key="MNFY-TEST-001"
    )
    return {"status": "test event published", "topic": TOPIC}