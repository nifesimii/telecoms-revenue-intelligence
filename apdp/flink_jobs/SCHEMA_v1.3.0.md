# Canonical schema v1.3.0 — telecom trade partner extension

Additive over v1.2.0. All existing PSP events keep the v1.2.0 shape unchanged;
the new fields are nullable and only populated for telecom events.

## Three new event types

| `event_type` | Source file | Kafka topic | Money direction |
|---|---|---|---|
| `telecom.dealer_sale` | `dealer_sales.csv` | `raw.telecom.dealer_sales` | Consumer → Dealer |
| `telecom.commission_statement` | `commission_statements.csv` | `raw.telecom.commission_statements` | MTN ledger entry (no money yet) |
| `telecom.settlement` | `settlement_records.csv` | `raw.telecom.settlement_records` | MTN → Dealer |

All three share `provider: "telecom_batch"` and `ingestion_mode: "BATCH_EOD"`.

## v1.3.0 canonical envelope additions

Added to the canonical event shape. Nullable for non-telecom events.

| Field | Type | Populated for | Notes |
|---|---|---|---|
| `partner_id` | string \| null | All telecom | Umbrella aggregator code |
| `dealer_id` | string \| null | All telecom | Distributor/dealer code — joins to FBB `distributor_code` |
| `product_type` | string \| null | dealer_sale, commission_statement | e.g. `FBB_DEVICE`, `AIRTIME`, `BUNDLE` |
| `gross_revenue` | numeric \| null | dealer_sale, commission_statement | Underlying revenue (NGN) |
| `commission_amount` | numeric \| null | commission_statement, settlement | NGN |
| `commission_rate` | numeric \| null | commission_statement | Decimal, e.g. `0.05` for 5% |
| `settlement_period` | string \| null | All telecom | `YYYYMM` — joins to FBB `mon_period` |
| `linked_statement_ref` | string \| null | settlement | Back-reference to a `commission_statement` event's `transaction_id` |

## Field mapping per event type

### `telecom.dealer_sale`
| Canonical field | Source |
|---|---|
| `transaction_id` | `tel_sale_{transaction_ref}` |
| `event_type` | `telecom.dealer_sale` |
| `transaction_type` | `PAYMENT` |
| `amount` / `amount_ngn` | `total_amount_ngn` |
| `gross_revenue` | same as `amount` |
| `status` | `SUCCESS` (sales rows imply settled) |
| `payment_source` | `source_system` (e.g. `DEALER_MGMT_X`) |
| `sender.phone` | `consumer_msisdn` (often null) |
| `receiver.name` | dealer name (joined later) |
| `metadata.imei` | `imei` |
| `metadata.payment_method` | `CASH` \| `MOMO` \| `CARD` |
| `metadata.product_code` | `product_code` |

### `telecom.commission_statement`
| Canonical field | Source |
|---|---|
| `transaction_id` | `tel_stmt_{statement_ref}` |
| `event_type` | `telecom.commission_statement` |
| `transaction_type` | `STATEMENT` *(new type — ledger entry, not a money movement)* |
| `amount` / `amount_ngn` | `commission_amount_ngn` |
| `commission_amount` | same as `amount` |
| `commission_rate` | `commission_rate` |
| `gross_revenue` | `gross_revenue_ngn` |
| `status` | normalized from `status` (DRAFT/FINAL/DISPUTED → `PENDING`/`SUCCESS`/`FAILED`) |
| `metadata.activation_count` | `activation_count` |
| `metadata.statement_status` | raw `status` |

### `telecom.settlement`
| Canonical field | Source |
|---|---|
| `transaction_id` | `tel_pay_{settlement_ref}` |
| `event_type` | `telecom.settlement` |
| `transaction_type` | `TRANSFER` |
| `amount` / `amount_ngn` | `amount_ngn` |
| `commission_amount` | same as `amount` |
| `linked_statement_ref` | `tel_stmt_{linked_statement_ref}` |
| `status` | normalized from `status` (PAID → `SUCCESS`, PARTIAL → `PENDING`, FAILED → `FAILED`) |
| `metadata.payout_method` | `MOMO` \| `BANK` |
| `metadata.momo_transaction_id` | `momo_transaction_id` |
| `metadata.dealer_msisdn` | `dealer_msisdn` |

## Input file column specs

### `dealer_sales.csv`
| Column | Required | Type | Notes |
|---|---|---|---|
| `transaction_ref` | yes | string | Unique within source system |
| `sale_date` | yes | ISO 8601 timestamp | |
| `dealer_code` | yes | string | |
| `partner_code` | no | string | |
| `product_type` | yes | string | `FBB_DEVICE` \| `AIRTIME` \| `BUNDLE` \| other |
| `product_code` | no | string | |
| `imei` | no | string | Required for `FBB_DEVICE` |
| `total_amount_ngn` | yes | numeric | |
| `payment_method` | yes | string | `CASH` \| `MOMO` \| `CARD` \| `OTHER` |
| `consumer_msisdn` | no | string | |
| `source_system` | yes | string | |

### `commission_statements.csv`
| Column | Required | Type | Notes |
|---|---|---|---|
| `statement_ref` | yes | string | |
| `statement_date` | yes | ISO 8601 timestamp | |
| `settlement_period` | yes | string | `YYYYMM` |
| `dealer_code` | yes | string | |
| `partner_code` | no | string | |
| `product_type` | yes | string | |
| `activation_count` | yes | integer | |
| `gross_revenue_ngn` | yes | numeric | |
| `commission_rate` | yes | numeric | Decimal |
| `commission_amount_ngn` | yes | numeric | |
| `status` | yes | string | `DRAFT` \| `FINAL` \| `DISPUTED` |
| `source_system` | yes | string | |

### `settlement_records.csv`
| Column | Required | Type | Notes |
|---|---|---|---|
| `settlement_ref` | yes | string | |
| `linked_statement_ref` | yes | string | FK → `commission_statements.statement_ref` |
| `settlement_date` | yes | ISO 8601 timestamp | |
| `settlement_period` | yes | string | `YYYYMM` |
| `dealer_code` | yes | string | |
| `amount_ngn` | yes | numeric | |
| `payout_method` | yes | string | `MOMO` \| `BANK` |
| `momo_transaction_id` | no | string | Required when `payout_method=MOMO` |
| `dealer_msisdn` | no | string | Required when `payout_method=MOMO` |
| `status` | yes | string | `PAID` \| `PARTIAL` \| `FAILED` \| `PENDING` |
| `source_system` | yes | string | |

## Envelope wrapper

The batch ingestor wraps each CSV row in the standard APDP envelope before
publishing to the appropriate `raw.telecom.*` topic:

```json
{
  "provider": "telecom_batch",
  "event_type": "telecom.dealer_sale",
  "_source_topic": "raw.telecom.dealer_sales",
  "_ingested_at": "2026-06-20T10:00:00+00:00",
  "_source_file": "dealer_sales_2024_10.csv",
  "_row_index": 42,
  "raw": { /* one CSV row as JSON */ }
}
```

The `_row_index` + `_source_file` pair makes idempotency easy — re-ingesting
the same file is a no-op if `transaction_id` is already present.

## Pipeline version

`_pipeline_version: "1.3.0"` on every normalized event.

## Postgres schema additions

See `migrate_v1_3_0.sql` for the corresponding column additions to
`normalized.transactions` and the new helper view
`normalized.partner_settlements` that unions the three event types into a
single dealer-period reconciliation surface.
