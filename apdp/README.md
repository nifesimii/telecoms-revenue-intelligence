# 🌍 African Payment Data Platform

A real-time + batch data engineering platform that ingests, normalizes, reconciles,
and reports on payment transactions across MTN MoMo, Flutterwave, Paystack, Monnify,
and direct bank accounts via Mono open banking.

---

## Build Status

| Phase | Description | Status |
|---|---|---|
| **Phase 1** | Infrastructure + Ingestion | ✅ Complete |
| **Phase 2** | Flink Normalization + Schema v1.1.0 | ✅ Complete |
| **Phase 3** | Currency Exchange Rate Service | 🔜 Next |
| **Phase 4** | Cross-Provider Reconciliation | ⏳ Pending |
| **Phase 5** | dbt Models + CBN Regulatory Reports | ⏳ Pending |
| **Phase 6** | Grafana Dashboards + Load Testing | ⏳ Pending |

---

## What Has Been Built (Phases 1 & 2)

### Phase 1 — Infrastructure & Ingestion Layer

The foundation of the platform. Everything needed to receive payment events
from Nigerian providers and get them into Kafka reliably.

**Kafka (KRaft mode — no Zookeeper)**
Single-node Kafka cluster running in KRaft mode. No Zookeeper dependency,
which simplifies operations. 9 topics pre-created covering raw ingestion,
normalized output, reconciliation, CBN reporting, and a dead letter queue.

**FastAPI Ingestion Service**
Runs at `localhost:8000`. Four webhook receivers and one background poller:

| Provider | Type | How it works |
|---|---|---|
| Flutterwave | Webhook | `POST /webhooks/flutterwave` — receives charge events, verifies hash signature |
| Paystack | Webhook | `POST /webhooks/paystack` — receives charge events, verifies HMAC-SHA512 |
| Monnify | Webhook | `POST /webhooks/monnify` — receives transaction events, verifies HMAC-SHA512 |
| MTN MoMo | Poller | Background asyncio task, polls Collections API every 30 seconds, auto-refreshes OAuth2 token |

Each receiver wraps the raw provider payload in a standard envelope and
publishes it to its raw Kafka topic. All four have `/test` GET endpoints
that fire a realistic mock event — no real money, no webhook needed.

**Supporting infrastructure**
- Redis (7.2) — session cache, will serve FX rates in Phase 3
- PostgreSQL (15) — analytical store, dbt target, Mono sync tables
- Prometheus + Grafana — metrics and dashboards (dashboards built in Phase 6)
- Schema Registry — Confluent Schema Registry for future Avro schema enforcement
- Kafka UI — browser UI at `localhost:8080` for inspecting topics and messages

---

### Phase 2 — Flink Normalization + Canonical Schema v1.1.0

The core stream processing layer. A PyFlink job reads from all 6 raw Kafka
topics simultaneously and normalizes every event into a single canonical schema,
regardless of which provider it came from.

**What the Flink job does**

The job runs continuously as a Docker service (`app_flink_normalizer`). It:
1. Subscribes to all 6 raw topics from the earliest available offset
2. For each message, detects the provider from the envelope and routes to the correct normalizer function
3. Outputs a normalized canonical event to `normalized.transactions`
4. Any event that fails parsing or has an unknown provider is dropped with a log warning (dead letter handling is Phase 4)

**Provider normalizers — what each one does**

`normalize_flutterwave()` — extracts from Flutterwave's `data` object. Amount is already in naira. Customer info comes from `data.customer`. Transaction type is inferred from `tx_type` field.

`normalize_paystack()` — Paystack amounts are in **kobo**, so every amount is divided by 100 to get naira. Sender name is assembled from `first_name` + `last_name`. Bank comes from `authorization.bank`.

`normalize_mtn()` — MTN MoMo has no concept of a card or bank — it's mobile money. Sender is identified by MSISDN (phone number) from the `payer.partyId` field. All MTN transactions are typed as `TRANSFER`.

`normalize_monnify()` — Monnify is the most complex normalizer. In addition to the standard fields it handles:
- **Virtual account type**: inferred from webhook payload structure. If `reservedAccountDetails` is present → `STATIC` (permanent merchant VA). If `destinationAccountDetails` is present → `DYNAMIC` (per-transaction VA that expires). If neither → `null`.
- **Settlement mode**: read from `eventData.settlementMode` and normalised to `INSTANT | DAILY | BI_DAILY`.
- **Expected settlement time**: computed from `completed_at` + `settlement_mode`. INSTANT = same timestamp. DAILY = next day at 09:00 UTC. BI_DAILY = next window (15:00 same day or 09:00 next day).

`normalize_mono()` — Mono is the only batch provider. Transactions come from Nigerian bank accounts (GTBank, Access, Zenith, UBA) connected via Mono's open banking API. Amount is in **kobo** (divided by 100). Transaction direction (`type: credit | debit`) determines who is sender vs receiver — for a CREDIT, the merchant account is the receiver; for a DEBIT, the merchant account is the sender. `payment_source` is set based on `bank_code` in the envelope (e.g. `GTB` → `DIRECT_BANK_GTB`).

**Mono batch poller (`mono_batch.py`)**

A separate Docker service (`app_mono_batch`) runs `supercronic` with a cron schedule of `0 23 * * *` (23:00 UTC daily). When it fires it:
1. Queries `merchant_mono_accounts` table for all active connected accounts
2. Calls Mono API `GET /v2/accounts/{id}/transactions` with a 25-hour lookback window
3. Wraps each transaction in an envelope with `bank_code`, `account_name`, and `batch_date`
4. Publishes to `raw.mono.transactions`
5. Writes a row to `mono_sync_log` per account with count and status

Despite being batch-sourced, Mono events flow into the same `normalized.transactions`
topic as real-time events. `ingestion_mode: "BATCH_EOD"` distinguishes them downstream.

**Canonical schema (v1.1.0)**

Every event leaving the Flink job — regardless of provider — has this exact shape:

```json
{
  "transaction_id":         "flw_99999 | ps_REF | mtn_TXN | mnfy_REF | mono_ID",
  "provider":               "flutterwave | paystack | mtn_momo | monnify | mono",
  "event_type":             "charge.completed | charge.success | collection.completed | ...",
  "amount":                 50000.0,
  "currency":               "NGN",
  "amount_ngn":             50000.0,
  "status":                 "SUCCESS | FAILED | PENDING | UNKNOWN",
  "transaction_type":       "PAYMENT | TRANSFER",
  "payment_source":         "FLUTTERWAVE | PAYSTACK | MTN_MOMO | MONNIFY | DIRECT_BANK_GTB | DIRECT_BANK_ACCESS | DIRECT_BANK_ZENITH | DIRECT_BANK_UBA | DIRECT_BANK_OTHER",
  "ingestion_mode":         "STREAMING | BATCH_EOD",
  "virtual_account_type":   "STATIC | DYNAMIC | null",
  "settlement_mode":        "INSTANT | DAILY | BI_DAILY | null",
  "expected_settlement_at": "2024-01-16T09:00:00+00:00 | null",
  "sender": {
    "name":  "string | null",
    "email": "string | null",
    "phone": "+2348012345678 | null",
    "bank":  "string | null"
  },
  "receiver": {
    "name":  "string | null",
    "email": "string | null",
    "phone": "string | null",
    "bank":  "string | null"
  },
  "initiated_at":        "2024-01-15T14:10:00.000Z",
  "completed_at":        "2024-01-15T14:10:45.000Z | null",
  "metadata":            {},
  "_normalized_at":      "2026-03-07T10:13:05.057624+00:00",
  "_ingested_at":        "2026-03-07T10:13:04.380317+00:00",
  "_raw_topic":          "raw.flutterwave.transactions",
  "_pipeline_version":   "1.1.0"
}
```

**Test suite**

`flink_jobs/test_normalizer.py` — 8 test cases covering all 5 providers with no
Flink or Kafka dependency. Run with `python flink_jobs/test_normalizer.py`.

| Test case | What it verifies |
|---|---|
| Flutterwave | Standard charge event, `payment_source: FLUTTERWAVE`, phone normalisation |
| Paystack | Kobo → naira conversion, name assembly from first+last |
| MTN MoMo | MSISDN phone normalisation, `transaction_type: TRANSFER` |
| Monnify standard | No VA fields, no settlement mode → all null |
| Monnify static VA + DAILY | `virtual_account_type: STATIC`, `expected_settlement_at` = next day 09:00 |
| Monnify dynamic VA + INSTANT | `virtual_account_type: DYNAMIC`, `expected_settlement_at` = same as `completed_at` |
| Mono CREDIT (GTBank) | Kobo → naira, `ingestion_mode: BATCH_EOD`, merchant as receiver |
| Mono DEBIT (Access Bank) | `payment_source: DIRECT_BANK_ACCESS`, merchant as sender |

All 8 pass ✅.

---

## Current Running Services

```
docker compose ps
```

| Container | Image | Status | Port |
|---|---|---|---|
| app_kafka | confluentinc/cp-kafka:7.5.0 | ✅ Healthy | 9092 |
| app_schema_registry | cp-schema-registry:7.5.0 | ✅ Up | 8081 |
| app_kafka_ui | provectuslabs/kafka-ui | ✅ Up | 8080 |
| app_postgres | postgres:15-alpine | ✅ Healthy | 5432 |
| app_redis | redis:7.2-alpine | ✅ Healthy | 6379 |
| app_ingestion | ingestion (FastAPI) | ✅ Up | 8000 |
| app_flink_normalizer | flink-normalizer (PyFlink) | ✅ Up | — |
| app_mono_batch | mono-batch (supercronic) | ✅ Up | — |
| app_prometheus | prom/prometheus:v2.47.0 | ✅ Up | 9090 |
| app_grafana | grafana/grafana:10.1.0 | ✅ Up | 3000 |

---

## Kafka Topics

| Topic | Partitions | Producer | Consumer |
|---|---|---|---|
| `raw.flutterwave.transactions` | 3 | FastAPI ingestion | Flink normalizer |
| `raw.paystack.transactions` | 3 | FastAPI ingestion | Flink normalizer |
| `raw.mtn.transactions` | 3 | MTN MoMo poller | Flink normalizer |
| `raw.monnify.transactions` | 3 | FastAPI ingestion | Flink normalizer |
| `raw.mono.transactions` | 3 | Mono batch poller | Flink normalizer |
| `normalized.transactions` | 6 | Flink normalizer | Phase 4 reconciler |
| `reconciled.transactions` | 6 | Phase 4 reconciler | Phase 5 dbt |
| `cbn.reports.daily` | 1 | Phase 5 reporter | CBN reporting |
| `dead.letter.queue` | 3 | Future error handler | Monitoring |

---

## Postgres Schema

**`normalized` schema**
- `normalized.transactions` — canonical events written by future dbt sink
- `normalized.reconciliation_events` — matched/unmatched reconciliation results

**`regulatory` schema**
- `regulatory.cbn_ctr_staging` — Currency Transaction Reports (transactions ≥ ₦5M)

**`public` schema (Mono)**
- `merchant_mono_accounts` — merchants with connected bank accounts via Mono Connect
- `mono_sync_log` — audit log for each nightly batch sync

---

## Architecture

```
┌─────────────────────────────────────────────────────────────────┐
│                        INGESTION LAYER                          │
│                                                                 │
│  Flutterwave ──→ POST /webhooks/flutterwave ──→ raw.flw.*       │
│  Paystack    ──→ POST /webhooks/paystack    ──→ raw.ps.*        │
│  Monnify     ──→ POST /webhooks/monnify     ──→ raw.monnify.*   │
│  MTN MoMo    ──→ asyncio poller (30s)       ──→ raw.mtn.*       │
│  Mono        ──→ cron batch (23:00 daily)   ──→ raw.mono.*      │
└──────────────────────────┬──────────────────────────────────────┘
                           │ Kafka (KRaft)
                           ▼
┌─────────────────────────────────────────────────────────────────┐
│                    NORMALIZATION LAYER  ✅                       │
│                                                                 │
│  PyFlink job reads all 6 raw.* topics simultaneously           │
│  Routes each event to provider-specific normalizer             │
│  Outputs canonical schema v1.1.0 events                        │
│                    ▼                                            │
│           normalized.transactions                               │
└──────────────────────────┬──────────────────────────────────────┘
                           │
                           ▼
┌─────────────────────────────────────────────────────────────────┐
│              ENRICHMENT LAYER  🔜 Phase 3                       │
│                                                                 │
│  FX rate service → Redis cache → enrich amount_ngn             │
│  for non-NGN transactions (USD, GHS, KES)                      │
└─────────────────────────────────────────────────────────────────┘
                           │
                           ▼
┌─────────────────────────────────────────────────────────────────┐
│            RECONCILIATION LAYER  ⏳ Phase 4                     │
│                                                                 │
│  Flink windowed matching across providers                       │
│  Outputs to reconciled.transactions                            │
└─────────────────────────────────────────────────────────────────┘
                           │
                           ▼
┌─────────────────────────────────────────────────────────────────┐
│              REPORTING LAYER  ⏳ Phase 5                        │
│                                                                 │
│  dbt models → fact/dim tables                                  │
│  CBN CTR (≥₦5M) + STR (suspicious) regulatory reports         │
└─────────────────────────────────────────────────────────────────┘
```

---

## Stack

| Layer | Technology |
|---|---|
| Ingestion | FastAPI + Python 3.11 |
| Batch scheduling | supercronic |
| Message queue | Apache Kafka 7.5 (KRaft) |
| Stream processing | Apache Flink 1.18 (PyFlink) |
| Open banking | Mono API |
| Cache | Redis 7.2 |
| Database | PostgreSQL 15 |
| Transformation | dbt (Phase 5) |
| Observability | Prometheus + Grafana |
| Infrastructure | Docker Compose |

---

## Quick Start

### 1. Credentials

```bash
cp .env.example .env
# Required for streaming: FLUTTERWAVE_SECRET_KEY, PAYSTACK_SECRET_KEY,
#   MTN_COLLECTIONS_SUBSCRIPTION_KEY, MTN_API_USER_ID, MTN_API_KEY,
#   MONNIFY_SECRET_KEY
# Required for batch: MONO_SECRET_KEY
```

### 2. Start everything

```bash
docker compose up -d
```

### 3. Verify services

```bash
docker compose ps
```

### 4. Access UIs

| Service | URL | Credentials |
|---|---|---|
| Kafka UI | http://localhost:8080 | — |
| API docs | http://localhost:8000/docs | — |
| Grafana | http://localhost:3000 | admin / admin |
| Prometheus | http://localhost:9090 | — |

### 5. Fire test events

```bash
curl http://localhost:8000/webhooks/flutterwave/test
curl http://localhost:8000/webhooks/paystack/test
curl http://localhost:8000/webhooks/mtn/test
curl http://localhost:8000/webhooks/monnify/test
```

Check Kafka UI → Topics → `normalized.transactions` → Messages to see Flink output.

### 6. Run normalizer unit tests

```bash
python flink_jobs/test_normalizer.py
# Expected: ✅ ALL TESTS PASSED (8/8)
```

### 7. Trigger Mono batch manually

```bash
docker compose exec mono-batch python /app/ingestion/pollers/mono_batch.py
# Expected: "No active Mono-connected accounts found" until a merchant connects
```

---

## Project Structure

```
african-payment-platform/
├── ingestion/
│   ├── receivers/
│   │   ├── flutterwave.py        # Webhook (hash verify) + /test GET
│   │   ├── paystack.py           # Webhook (HMAC-SHA512) + /test GET
│   │   ├── mtn_momo.py           # /test GET + /poller/status
│   │   └── monnify.py            # Webhook (HMAC-SHA512) + /test GET
│   ├── pollers/
│   │   ├── mtn_momo.py           # Asyncio poller, 30s interval, OAuth2 refresh
│   │   ├── mono_batch.py         # EOD bank statement pull (cron 23:00 UTC)
│   │   └── mono_entrypoint.sh    # Entrypoint for mono-batch Docker service
│   ├── kafka_client.py           # Shared Confluent producer + Prometheus metrics
│   ├── config.py                 # Pydantic settings (all env vars)
│   └── main.py                   # FastAPI app, router registration, lifespan
├── flink_jobs/
│   ├── normalizer_core.py        # All 5 normalizer functions — no Flink dependency
│   ├── normalizer.py             # Flink pipeline: KafkaSource → map → KafkaSink
│   ├── test_normalizer.py        # 8 unit tests, runs without Kafka or Flink
│   └── Dockerfile                # PyFlink 1.18 image with Kafka connector JAR
├── infra/
│   ├── kafka/
│   │   └── create-topics.sh      # Creates all 9 Kafka topics on first boot
│   ├── postgres/
│   │   └── init.sql              # Full schema: raw, normalized, regulatory, mono tables
│   ├── prometheus/
│   │   └── prometheus.yml        # Scrape config (ingestion service metrics)
│   └── grafana/
│       └── dashboards/           # Dashboard provisioning (Phase 6)
├── dbt/                          # Phase 5
├── docker-compose.yml
├── requirements.txt
└── .env
```