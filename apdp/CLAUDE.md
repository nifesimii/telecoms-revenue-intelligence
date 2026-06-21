                  # CLAUDE.md

This file provides guidance to Claude Code when working with this repository.

---

## Strategic context

### Layer 1 — APDP (this repo)
Real-time payment ingestion and normalisation platform. It is the
ground-truth payment ledger that everything above it reads from.

### Layer 2 — Revenue Intelligence Platform (builds on top of APDP)
AI-powered telecom trade partner revenue assurance platform. Detects
commission leakage, settlement discrepancies, dealer payout mismatches.
This is the primary business goal. APDP is its foundation.

**Current focus: telecom trade partner data first.**
We are not building generic payment reconciliation. We are building
reconciliation for telecom dealer/aggregator/commission flows specifically.

---

## Architecture

```
Webhooks / Pollers → Kafka raw topics → Flink normalizer → normalized.transactions (Kafka)
                                                                        ↓
                                                               Postgres sink
                                                                        ↓
                                              reconciliation engine → dbt → CBN reports
```

**Ingestion layer** (`ingestion/`) — FastAPI app at `localhost:8000`. Webhook receivers
for Flutterwave, Paystack, and Monnify each verify provider-specific signatures before
publishing. MTN MoMo runs as an asyncio background poller (30s interval, OAuth2
auto-refresh). Mono runs as a separate `mono-batch` service on a daily cron (23:00 UTC)
via `supercronic`.

**Normalization layer** (`flink_jobs/`) — PyFlink 1.18 job that reads all `raw.*` Kafka
topics. Normalization logic lives entirely in `normalizer_core.py` (pure Python, no Flink
dependency) — imported by both the Flink job and the test suite. Flink pipeline wiring is
in `normalizer.py`.

**Canonical schema v1.2.0** — every event on `normalized.transactions` has the same shape
regardless of provider. Key fields: `amount_ngn` (always NGN, FX-converted via Redis or
fallback), `ingestion_mode` (`STREAMING` | `BATCH_EOD`), `fx_rate`, `fx_source`
(`live` | `fallback` | null), `_pipeline_version: "1.2.0"`.

**FX enrichment** (`flink_jobs/fx_service.py`) — converts non-NGN amounts to NGN. Redis
is the primary source; `FALLBACK_RATES` are used when Redis is unavailable.

---

## Key files

| File | Purpose |
|---|---|
| `flink_jobs/normalizer_core.py` | All normalization logic — pure Python, no Flink |
| `flink_jobs/normalizer.py` | Flink job wiring (Kafka source + sink) |
| `flink_jobs/fx_service.py` | Redis FX rate reads/writes |
| `flink_jobs/fx_refresher.py` | Hourly rate refresh loop |
| `flink_jobs/Dockerfile` | Broken build — apache-flink pip timeout |
| `flink_jobs/test_normalizer.py` | Unit tests, run without Kafka/Flink |
| `ingestion/main.py` | FastAPI app entry point |
| `ingestion/receivers/` | Flutterwave, Paystack, Monnify, MTN MoMo |
| `ingestion/pollers/mtn_momo.py` | Background OAuth2 poller |
| `infra/postgres/init.sql` | DB schema (v1.1.0 — needs migration to v1.2.0) |
| `docker-compose.yml` | Full stack declaration |

---

## Provider-specific notes

- **Paystack & Mono**: amounts are in **kobo** — divide by 100 to get naira.
- **MTN MoMo**: no card/bank concept; sender identified by MSISDN; all transactions are `TRANSFER`.
- **Monnify**: most complex normalizer — virtual account type inferred from payload structure,
  settlement time computed from `settlement_mode`.
- **Mono**: only batch provider; `ingestion_mode: BATCH_EOD`; transaction direction
  (`credit`/`debit`) determines sender vs receiver.

---

## Key infrastructure

- Kafka runs in **KRaft mode** (no Zookeeper). Topics pre-created by `kafka-init` container
  via `infra/kafka/create-topics.sh`. `KAFKA_AUTO_CREATE_TOPICS_ENABLE` is `false`.
- Postgres schema initialized by `infra/postgres/init.sql`. Migration for v1.1.0 fields is
  in `migrate_v1_1_0.sql`.
- All env vars flow through `ingestion/config.py` (Pydantic Settings). See `.env.example`.

---

## Build status

### ✅ Complete
- **Phase 1** — Ingestion layer: all 5 PSP sources (Flutterwave, Paystack, Monnify,
  MTN MoMo, Mono)
- **Phase 2** — Flink normalizer: canonical schema v1.1.0, all providers
- **Phase 3** — FX enrichment: Redis-backed rates, `fx_refresher.py`, schema v1.2.0
  (`fx_rate` / `fx_source` fields)

### ❌ Not built — immediate blocker
- **Flink Docker build broken**: `pip install apache-flink==1.18.1` (~800MB) times out
  during `docker build`. Normalizer logic is complete and tests pass — it cannot deploy.
  Fix before anything else.

### ❌ Not built — pipeline gap
- **Kafka → Postgres sink**: normalized events land in the Kafka `normalized.transactions`
  topic but nothing writes them to the Postgres table. DB schema exists but stays empty.
- **Postgres schema migration**: `init.sql` is v1.1.0 — missing `fx_rate` and `fx_source`
  columns that the v1.2.0 normalizer outputs.

### ❌ Not built — telecom extension (Phase 4, priority)
APDP currently normalises consumer PSP flows only. Telecom trade partner data arrives as
batch files (CSV/Excel/JSON exports from dealer management systems, aggregator platforms,
MTN BSS/OSS), not webhooks. Required additions:
- New Kafka topics: `raw.telecom.dealer_sales`, `raw.telecom.commission_statements`,
  `raw.telecom.settlement_records`
- New batch ingestors in `ingestion/pollers/` for telecom file sources
- Extended canonical schema with trade partner fields: `partner_id`, `dealer_id`,
  `commission_amount`, `commission_rate`, `product_type`, `gross_revenue`,
  `settlement_period`
- New `normalize_telecom()` function in `normalizer_core.py`

### ❌ Not built — reconciliation and reporting (Phase 5–6)
- **Reconciliation engine**: reads normalized trade partner events, matches against
  commission schedules, detects discrepancies. Writes to
  `normalized.reconciliation_events`.
- **dbt models**: analytics layer on Postgres — daily volumes, provider breakdowns,
  settlement analysis, CBN CTR staging logic.
- **Grafana dashboards**: `infra/grafana/dashboards/` is empty. Prometheus is not
  scraping anything from the ingestion service.

---

## Build priorities (in order)

1. Fix Flink Docker build timeout
2. Postgres schema migration (add `fx_rate`, `fx_source` columns)
3. Kafka → Postgres consumer (closes the end-to-end pipeline loop)
4. Telecom trade partner adapter (batch ingestors + schema extension + telecom normalizer)
5. Reconciliation engine
6. dbt models + CBN CTR staging
7. Prometheus metrics on ingestion service + Grafana dashboards

---

## Commands

**Start all services:**
```bash
docker compose up -d
docker compose ps   # verify all containers are healthy
```

**Run normalizer unit tests (no Kafka/Flink required):**
```bash
python flink_jobs/test_normalizer.py
# Expected: ✅ ALL TESTS PASSED (8/8)
```

**Run pytest suite:**
```bash
pytest tests/
```

**Fire test events against the running ingestion service:**
```bash
curl http://localhost:8000/webhooks/flutterwave/test
curl http://localhost:8000/webhooks/paystack/test
curl http://localhost:8000/webhooks/mtn/test
curl http://localhost:8000/webhooks/monnify/test
```

**Trigger Mono batch manually:**
```bash
docker compose exec mono-batch python /app/ingestion/pollers/mono_batch.py
```

**Rebuild a single service after code change:**
```bash
docker compose up -d --build ingestion
docker compose up -d --build flink-normalizer
```

---

## Coding constraints

- Prefer minimal, surgical changes — no speculative abstractions.
- Match existing code style exactly.
- New normalizers go in `normalizer_core.py` following the existing pattern.
- Run `flink_jobs/test_normalizer.py` after any change to `normalizer_core.py`.
- Telecom data is batch (file drops), not webhook — don't design it as a receiver.
- Check existing patterns before introducing new ones.
