"""
Mono Open-Banking Batch Poller
==============================
Runs nightly at 23:00 (11pm WAT) via cron in the mono-batch Docker service.

Workflow:
  1. Query Postgres for all merchants with a connected Mono account_id
  2. For each account, call Mono API to fetch the past 24 hours of transactions
  3. Normalize each transaction into a canonical payment event (ingestion_mode: BATCH_EOD)
  4. Publish to raw.mono.transactions Kafka topic
  5. Log sync result to mono_sync_log table

Environment variables (from .env / Docker):
  MONO_SECRET_KEY          — Mono API secret key
  KAFKA_BOOTSTRAP_SERVERS  — e.g. kafka:29092
  DATABASE_URL             — PostgreSQL DSN
"""
import json
import logging
import os
import sys
from datetime import datetime, timezone, timedelta
from typing import Optional

import httpx
import psycopg2
from confluent_kafka import Producer

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s — %(message)s",
)
log = logging.getLogger("mono_batch")

# ── Configuration ─────────────────────────────────────────────────────────────

MONO_BASE_URL       = "https://api.withmono.com"
MONO_SECRET_KEY     = os.getenv("MONO_SECRET_KEY", "")
KAFKA_BOOTSTRAP     = os.getenv("KAFKA_BOOTSTRAP_SERVERS", "localhost:9092")
DATABASE_URL        = os.getenv("DATABASE_URL", "postgresql://platform_user:platform_pass@postgres:5432/payment_platform")
KAFKA_TOPIC         = "raw.mono.transactions"

# How far back to look for transactions (slightly over 24h to avoid gaps)
LOOKBACK_HOURS      = 25


# ── Mono API client ───────────────────────────────────────────────────────────

def get_mono_headers() -> dict:
    """Mono uses the secret key directly as a Bearer token."""
    return {
        "mono-sec-key": MONO_SECRET_KEY,
        "Content-Type": "application/json",
    }


def fetch_mono_transactions(
    account_id: str,
    start: datetime,
    end: datetime,
) -> list[dict]:
    """
    Fetch transactions for a Mono-connected account within the given window.
    Returns a list of raw Mono transaction objects.

    Mono API: GET /v2/accounts/{account_id}/transactions
    Params:
      start  — ISO date string (YYYY-MM-DD)
      end    — ISO date string (YYYY-MM-DD)
      paginate — false to get all results in one call (up to 100)
    """
    url = f"{MONO_BASE_URL}/v2/accounts/{account_id}/transactions"
    params = {
        "start": start.strftime("%Y-%m-%d"),
        "end":   end.strftime("%Y-%m-%d"),
        "paginate": "false",
    }
    try:
        with httpx.Client(timeout=30) as client:
            resp = client.get(url, headers=get_mono_headers(), params=params)
            resp.raise_for_status()
            data = resp.json()
            # Mono response: {"status": "successful", "data": {"paging": {...}, "data": [...]}}
            return data.get("data", {}).get("data", [])
    except httpx.HTTPStatusError as e:
        log.error(f"Mono API error for account {account_id}: {e.response.status_code} — {e.response.text}")
        return []
    except Exception as e:
        log.error(f"Failed to fetch Mono transactions for account {account_id}: {e}")
        return []


def fetch_account_meta(account_id: str) -> dict:
    """
    Fetch Mono account metadata to get bank name/code and account holder name.
    GET /v2/accounts/{account_id}
    """
    url = f"{MONO_BASE_URL}/v2/accounts/{account_id}"
    try:
        with httpx.Client(timeout=15) as client:
            resp = client.get(url, headers=get_mono_headers())
            resp.raise_for_status()
            return resp.json().get("data", {})
    except Exception as e:
        log.warning(f"Could not fetch account meta for {account_id}: {e}")
        return {}


# ── Bank code mapping ─────────────────────────────────────────────────────────

# Mono returns bank names as strings — map common Nigerian banks to our codes
BANK_NAME_TO_CODE = {
    "guaranty trust bank":  "GTB",
    "gtbank":               "GTB",
    "gt bank":              "GTB",
    "access bank":          "ACCESS",
    "access bank nigeria":  "ACCESS",
    "zenith bank":          "ZENITH",
    "zenith":               "ZENITH",
    "united bank for africa": "UBA",
    "uba":                  "UBA",
}


def resolve_bank_code(bank_name: Optional[str]) -> str:
    if not bank_name:
        return "OTHER"
    return BANK_NAME_TO_CODE.get(bank_name.strip().lower(), "OTHER")


# ── Kafka producer ────────────────────────────────────────────────────────────

def build_kafka_producer() -> Producer:
    return Producer({
        "bootstrap.servers": KAFKA_BOOTSTRAP,
        "client.id": "mono-batch-poller",
        "acks": "all",
        "retries": 3,
    })


def publish_to_kafka(producer: Producer, envelope: dict, key: str) -> bool:
    try:
        producer.produce(
            topic=KAFKA_TOPIC,
            key=key.encode("utf-8"),
            value=json.dumps(envelope).encode("utf-8"),
        )
        return True
    except Exception as e:
        log.error(f"Kafka publish failed for {key}: {e}")
        return False


# ── Postgres helpers ──────────────────────────────────────────────────────────

def get_db_connection():
    return psycopg2.connect(DATABASE_URL)


def fetch_mono_accounts(conn) -> list[dict]:
    """
    Returns all merchants with a connected Mono account.
    Expected table schema (created in infra/postgres/init.sql):

      CREATE TABLE merchant_mono_accounts (
        id           SERIAL PRIMARY KEY,
        merchant_id  UUID NOT NULL,
        account_id   VARCHAR(255) NOT NULL UNIQUE,  -- Mono account ID
        bank_name    VARCHAR(255),
        account_name VARCHAR(255),
        created_at   TIMESTAMPTZ DEFAULT NOW(),
        is_active    BOOLEAN DEFAULT TRUE
      );
    """
    with conn.cursor() as cur:
        cur.execute("""
            SELECT merchant_id, account_id, bank_name, account_name
            FROM merchant_mono_accounts
            WHERE is_active = TRUE
        """)
        cols = [desc[0] for desc in cur.description]
        return [dict(zip(cols, row)) for row in cur.fetchall()]


def log_sync_result(
    conn,
    account_id: str,
    bank_name: str,
    transaction_count: int,
    status: str,
    error_message: Optional[str] = None,
) -> None:
    """
    Write a sync log row to mono_sync_log.
    Expected table schema:

      CREATE TABLE mono_sync_log (
        id                SERIAL PRIMARY KEY,
        account_id        VARCHAR(255) NOT NULL,
        bank_name         VARCHAR(255),
        synced_at         TIMESTAMPTZ DEFAULT NOW(),
        transaction_count INT DEFAULT 0,
        status            VARCHAR(50),   -- 'SUCCESS' | 'PARTIAL' | 'FAILED'
        error_message     TEXT
      );
    """
    with conn.cursor() as cur:
        cur.execute("""
            INSERT INTO mono_sync_log
              (account_id, bank_name, synced_at, transaction_count, status, error_message)
            VALUES (%s, %s, NOW(), %s, %s, %s)
        """, (account_id, bank_name, transaction_count, status, error_message))
    conn.commit()


# ── Main batch logic ──────────────────────────────────────────────────────────

def run_batch():
    now       = datetime.now(timezone.utc)
    window_end   = now
    window_start = now - timedelta(hours=LOOKBACK_HOURS)
    batch_date   = now.strftime("%Y-%m-%d")

    log.info(f"Starting Mono EOD batch | window: {window_start.date()} → {window_end.date()}")

    if not MONO_SECRET_KEY:
        log.error("MONO_SECRET_KEY is not set — aborting batch")
        sys.exit(1)

    try:
        conn = get_db_connection()
    except Exception as e:
        log.error(f"Failed to connect to Postgres: {e}")
        sys.exit(1)

    accounts = fetch_mono_accounts(conn)
    if not accounts:
        log.info("No active Mono-connected accounts found — nothing to sync")
        conn.close()
        return

    log.info(f"Found {len(accounts)} connected merchant account(s)")
    producer = build_kafka_producer()

    total_published = 0

    for account in accounts:
        account_id   = account["account_id"]
        bank_name    = account.get("bank_name") or ""
        account_name = account.get("account_name") or ""
        bank_code    = resolve_bank_code(bank_name)

        log.info(f"Syncing account {account_id} ({account_name} — {bank_name})")

        # Fetch transactions from Mono
        transactions = fetch_mono_transactions(account_id, window_start, window_end)
        log.info(f"  → Fetched {len(transactions)} transaction(s)")

        published = 0
        failed    = 0
        ingested_at = now.isoformat()

        for txn in transactions:
            txn_id = txn.get("id", "unknown")

            envelope = {
                "provider":     "mono",
                "event_type":   f"bank.{txn.get('type', 'credit').lower()}",
                "bank_code":    bank_code,
                "account_id":   account_id,
                "account_name": account_name,
                "batch_date":   batch_date,
                "raw":          txn,
                "_ingested_at": ingested_at,
                "_source_topic": KAFKA_TOPIC,
            }

            if publish_to_kafka(producer, envelope, key=f"mono_{txn_id}"):
                published += 1
            else:
                failed += 1

        # Flush after each account to bound memory usage
        producer.flush(timeout=10)

        status = "SUCCESS" if failed == 0 else ("PARTIAL" if published > 0 else "FAILED")
        error_msg = f"{failed} events failed to publish" if failed > 0 else None

        log_sync_result(conn, account_id, bank_name, published, status, error_msg)
        log.info(f"  → Published {published}/{len(transactions)} | status: {status}")
        total_published += published

    conn.close()
    log.info(f"Mono EOD batch complete — {total_published} total events published to {KAFKA_TOPIC}")


if __name__ == "__main__":
    run_batch()