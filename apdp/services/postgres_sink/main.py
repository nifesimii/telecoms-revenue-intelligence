"""
Kafka → Postgres sink.

Consumes normalized payment events from the `normalized.transactions` topic
and UPSERTs them into Postgres `normalized.transactions` table.

  * Idempotent: ON CONFLICT (transaction_id) DO UPDATE — re-processing the
    same offset is safe. Useful for Kafka replays and at-least-once delivery.
  * Manual commit: offsets only committed after successful DB write. A crash
    mid-batch will reprocess the unwritten messages on restart.
  * v1.3.0-aware: writes all telecom fields (dealer_id, partner_id,
    commission_*, settlement_period, linked_statement_ref) when present.
  * Resilient: bad messages are logged and skipped (dead-letter strategy is
    a follow-up — for now, a Prometheus counter tracks them).

Env vars (all optional, sensible compose defaults):
    KAFKA_BOOTSTRAP_SERVERS   default kafka:29092
    KAFKA_TOPIC               default normalized.transactions
    KAFKA_GROUP_ID            default postgres-sink
    POSTGRES_HOST             default postgres
    POSTGRES_PORT             default 5432
    POSTGRES_DB               default payment_platform
    POSTGRES_USER             default platform_user
    POSTGRES_PASSWORD         default platform_pass
"""
from __future__ import annotations

import json
import os
import signal
import sys
from typing import Any

import psycopg2
import psycopg2.extras
import structlog
from confluent_kafka import Consumer, KafkaError, KafkaException
from prometheus_client import Counter, start_http_server

log = structlog.get_logger("postgres_sink")

# ── Prometheus metrics ───────────────────────────────────────────────────────
events_written = Counter(
    "sink_events_written_total",
    "Events successfully UPSERTed into Postgres",
    ["event_type"],
)
events_failed = Counter(
    "sink_events_failed_total",
    "Events skipped due to parse/validation/DB error",
    ["reason"],
)


# ── Field mapping: normalized JSON → Postgres columns ────────────────────────
# Sender/receiver are nested dicts in the JSON; flattened into the table.

INSERT_SQL = """
INSERT INTO normalized.transactions (
    transaction_id, provider, event_type,
    amount, currency, amount_ngn, fx_rate, fx_source,
    status, transaction_type,
    payment_source, ingestion_mode, virtual_account_type,
    settlement_mode, expected_settlement_at,
    partner_id, dealer_id, product_type, gross_revenue,
    commission_amount, commission_rate, settlement_period,
    linked_statement_ref,
    sender_name, sender_phone, sender_email,
    receiver_name, receiver_phone,
    initiated_at, completed_at, normalized_at, metadata
) VALUES (
    %(transaction_id)s, %(provider)s, %(event_type)s,
    %(amount)s, %(currency)s, %(amount_ngn)s, %(fx_rate)s, %(fx_source)s,
    %(status)s, %(transaction_type)s,
    %(payment_source)s, %(ingestion_mode)s, %(virtual_account_type)s,
    %(settlement_mode)s, %(expected_settlement_at)s,
    %(partner_id)s, %(dealer_id)s, %(product_type)s, %(gross_revenue)s,
    %(commission_amount)s, %(commission_rate)s, %(settlement_period)s,
    %(linked_statement_ref)s,
    %(sender_name)s, %(sender_phone)s, %(sender_email)s,
    %(receiver_name)s, %(receiver_phone)s,
    %(initiated_at)s, %(completed_at)s, %(normalized_at)s, %(metadata)s
)
ON CONFLICT (transaction_id) DO UPDATE SET
    provider = EXCLUDED.provider,
    event_type = EXCLUDED.event_type,
    amount = EXCLUDED.amount,
    currency = EXCLUDED.currency,
    amount_ngn = EXCLUDED.amount_ngn,
    fx_rate = EXCLUDED.fx_rate,
    fx_source = EXCLUDED.fx_source,
    status = EXCLUDED.status,
    transaction_type = EXCLUDED.transaction_type,
    payment_source = EXCLUDED.payment_source,
    ingestion_mode = EXCLUDED.ingestion_mode,
    virtual_account_type = EXCLUDED.virtual_account_type,
    settlement_mode = EXCLUDED.settlement_mode,
    expected_settlement_at = EXCLUDED.expected_settlement_at,
    partner_id = EXCLUDED.partner_id,
    dealer_id = EXCLUDED.dealer_id,
    product_type = EXCLUDED.product_type,
    gross_revenue = EXCLUDED.gross_revenue,
    commission_amount = EXCLUDED.commission_amount,
    commission_rate = EXCLUDED.commission_rate,
    settlement_period = EXCLUDED.settlement_period,
    linked_statement_ref = EXCLUDED.linked_statement_ref,
    sender_name = EXCLUDED.sender_name,
    sender_phone = EXCLUDED.sender_phone,
    sender_email = EXCLUDED.sender_email,
    receiver_name = EXCLUDED.receiver_name,
    receiver_phone = EXCLUDED.receiver_phone,
    initiated_at = EXCLUDED.initiated_at,
    completed_at = EXCLUDED.completed_at,
    normalized_at = EXCLUDED.normalized_at,
    metadata = EXCLUDED.metadata
"""


def _row_from_event(evt: dict[str, Any]) -> dict[str, Any]:
    """Flatten the normalized JSON event into a row dict for psycopg2."""
    sender   = evt.get("sender")   or {}
    receiver = evt.get("receiver") or {}
    metadata = evt.get("metadata") or {}
    return {
        "transaction_id":        evt.get("transaction_id"),
        "provider":              evt.get("provider"),
        "event_type":            evt.get("event_type"),
        "amount":                evt.get("amount"),
        "currency":              evt.get("currency"),
        "amount_ngn":            evt.get("amount_ngn"),
        "fx_rate":               evt.get("fx_rate"),
        "fx_source":             evt.get("fx_source"),
        "status":                evt.get("status"),
        "transaction_type":      evt.get("transaction_type"),
        "payment_source":        evt.get("payment_source"),
        "ingestion_mode":        evt.get("ingestion_mode"),
        "virtual_account_type":  evt.get("virtual_account_type"),
        "settlement_mode":       evt.get("settlement_mode"),
        "expected_settlement_at": evt.get("expected_settlement_at"),
        # v1.3.0 telecom fields (nullable)
        "partner_id":            evt.get("partner_id"),
        "dealer_id":             evt.get("dealer_id"),
        "product_type":          evt.get("product_type"),
        "gross_revenue":         evt.get("gross_revenue"),
        "commission_amount":     evt.get("commission_amount"),
        "commission_rate":       evt.get("commission_rate"),
        "settlement_period":     evt.get("settlement_period"),
        "linked_statement_ref":  evt.get("linked_statement_ref"),
        "sender_name":           sender.get("name"),
        "sender_phone":          sender.get("phone"),
        "sender_email":          sender.get("email"),
        "receiver_name":         receiver.get("name"),
        "receiver_phone":        receiver.get("phone"),
        "initiated_at":          evt.get("initiated_at"),
        "completed_at":          evt.get("completed_at"),
        "normalized_at":         evt.get("_normalized_at"),
        "metadata":              psycopg2.extras.Json(metadata),
    }


def _build_consumer() -> Consumer:
    return Consumer(
        {
            "bootstrap.servers": os.getenv("KAFKA_BOOTSTRAP_SERVERS", "kafka:29092"),
            "group.id":          os.getenv("KAFKA_GROUP_ID", "postgres-sink"),
            "enable.auto.commit": False,                # commit only after DB write
            "auto.offset.reset": "earliest",            # replay backlog on first run
            "session.timeout.ms": 30_000,
            "max.poll.interval.ms": 300_000,
        }
    )


def _build_db_conn():
    conn = psycopg2.connect(
        host     = os.getenv("POSTGRES_HOST", "postgres"),
        port     = int(os.getenv("POSTGRES_PORT", "5432")),
        dbname   = os.getenv("POSTGRES_DB", "payment_platform"),
        user     = os.getenv("POSTGRES_USER", "platform_user"),
        password = os.getenv("POSTGRES_PASSWORD", "platform_pass"),
    )
    conn.autocommit = False
    return conn


# Global shutdown flag toggled by signal handlers.
_shutdown = False


def _on_sigterm(_signum, _frame):
    global _shutdown
    log.info("Shutdown signal received — finishing current batch")
    _shutdown = True


def main() -> int:
    signal.signal(signal.SIGTERM, _on_sigterm)
    signal.signal(signal.SIGINT,  _on_sigterm)

    metrics_port = int(os.getenv("METRICS_PORT", "9100"))
    start_http_server(metrics_port)
    log.info("Prometheus metrics server started", port=metrics_port)

    topic = os.getenv("KAFKA_TOPIC", "normalized.transactions")
    consumer = _build_consumer()
    consumer.subscribe([topic])
    log.info("Subscribed to Kafka topic", topic=topic)

    conn = _build_db_conn()
    log.info("Postgres connection established")

    try:
        while not _shutdown:
            msg = consumer.poll(timeout=1.0)
            if msg is None:
                continue
            if msg.error():
                if msg.error().code() == KafkaError._PARTITION_EOF:
                    continue
                log.error("Kafka error", error=str(msg.error()))
                events_failed.labels(reason="kafka_error").inc()
                continue

            raw_value = msg.value()
            try:
                evt = json.loads(raw_value)
            except (json.JSONDecodeError, TypeError) as e:
                log.error("Bad JSON, skipping", error=str(e),
                          offset=msg.offset(), partition=msg.partition())
                events_failed.labels(reason="bad_json").inc()
                consumer.commit(message=msg, asynchronous=False)
                continue

            if not evt.get("transaction_id"):
                log.error("Missing transaction_id, skipping",
                          offset=msg.offset(), partition=msg.partition())
                events_failed.labels(reason="missing_id").inc()
                consumer.commit(message=msg, asynchronous=False)
                continue

            row = _row_from_event(evt)
            try:
                with conn.cursor() as cur:
                    cur.execute(INSERT_SQL, row)
                conn.commit()
            except psycopg2.Error as e:
                log.error("DB write failed", error=str(e),
                          transaction_id=row.get("transaction_id"))
                conn.rollback()
                events_failed.labels(reason="db_error").inc()
                # Do NOT commit Kafka offset — message will be retried.
                continue

            events_written.labels(event_type=evt.get("event_type") or "unknown").inc()
            consumer.commit(message=msg, asynchronous=False)
    finally:
        log.info("Closing consumer and DB connection")
        try:
            consumer.close()
        except Exception:
            pass
        try:
            conn.close()
        except Exception:
            pass
    return 0


if __name__ == "__main__":
    sys.exit(main())
