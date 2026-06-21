"""
Kafka producer singleton for the ingestion service.
All receivers share one producer instance for efficiency.
"""
import json
import structlog
from datetime import datetime, timezone
from confluent_kafka import Producer, KafkaException
from prometheus_client import Counter

log = structlog.get_logger()

# Prometheus metrics
messages_published = Counter(
    "kafka_messages_published_total",
    "Total messages published to Kafka",
    ["topic", "provider"]
)
messages_failed = Counter(
    "kafka_messages_failed_total",
    "Total Kafka publish failures",
    ["topic", "provider"]
)

_producer: Producer | None = None

def get_producer() -> Producer:
    global _producer
    if _producer is None:
        from ingestion.config import settings
        _producer = Producer({
            "bootstrap.servers": settings.KAFKA_BOOTSTRAP_SERVERS,
            "client.id": "african-payment-ingestion",
            "acks": "all",               # Wait for all replicas
            "retries": 3,
            "retry.backoff.ms": 500,
        })
        log.info("Kafka producer initialized", servers=settings.KAFKA_BOOTSTRAP_SERVERS)
    return _producer


def delivery_callback(err, msg):
    """Called by Kafka after each message is delivered (or fails)."""
    if err:
        log.error("Kafka delivery failed", error=str(err), topic=msg.topic())
    else:
        log.debug("Message delivered", topic=msg.topic(), partition=msg.partition(), offset=msg.offset())


def publish_event(topic: str, payload: dict, provider: str, key: str | None = None) -> bool:
    """
    Publish a payment event to a Kafka topic.
    
    Args:
        topic:    Target Kafka topic
        payload:  Event dict (will be JSON-serialized)
        provider: Provider name for metrics labeling
        key:      Optional message key for partition routing
    
    Returns:
        True if enqueued successfully, False on error
    """
    producer = get_producer()
    
    # Stamp every event with ingestion metadata
    payload["_ingested_at"] = datetime.now(timezone.utc).isoformat()
    payload["_source_topic"] = topic
    
    try:
        producer.produce(
            topic=topic,
            key=key.encode("utf-8") if key else None,
            value=json.dumps(payload).encode("utf-8"),
            callback=delivery_callback
        )
        producer.poll(0)  # Trigger delivery callbacks without blocking
        messages_published.labels(topic=topic, provider=provider).inc()
        return True
    except KafkaException as e:
        log.error("Failed to publish event", topic=topic, provider=provider, error=str(e))
        messages_failed.labels(topic=topic, provider=provider).inc()
        return False
