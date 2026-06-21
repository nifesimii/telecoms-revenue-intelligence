-- Migration: canonical schema v1.1.0 → v1.3.0
--
-- Run against the running Postgres container:
--   docker cp migrate_v1_3_0.sql app_postgres:/tmp/migrate.sql
--   docker exec app_postgres psql -U platform_user -d payment_platform -f /tmp/migrate.sql
--
-- Idempotent — uses IF NOT EXISTS everywhere. Safe to re-run.
-- Bundles v1.2.0 (fx_rate, fx_source) AND v1.3.0 (telecom extension) since
-- v1.2.0 was never migrated to Postgres.

-- ── v1.2.0 catch-up: FX enrichment columns ────────────────────────────────────
ALTER TABLE normalized.transactions
  ADD COLUMN IF NOT EXISTS fx_rate    NUMERIC(20, 8),
  ADD COLUMN IF NOT EXISTS fx_source  VARCHAR(20);

-- ── v1.3.0: event_type promoted to column ────────────────────────────────────
-- The normalizer has always emitted event_type in JSON; v1.3.0 needs it as a
-- column because the telecom variants (sale/statement/settlement) all share
-- provider="telecom_batch" and event_type is the only way to tell them apart.
ALTER TABLE normalized.transactions
  ADD COLUMN IF NOT EXISTS event_type VARCHAR(100);

-- ── v1.3.0: telecom trade partner fields ─────────────────────────────────────
-- All nullable — only populated for telecom events.
-- See flink_jobs/SCHEMA_v1.3.0.md for the full spec.
ALTER TABLE normalized.transactions
  ADD COLUMN IF NOT EXISTS partner_id            VARCHAR(100),
  ADD COLUMN IF NOT EXISTS dealer_id             VARCHAR(100),
  ADD COLUMN IF NOT EXISTS product_type          VARCHAR(50),
  ADD COLUMN IF NOT EXISTS gross_revenue         NUMERIC(20, 2),
  ADD COLUMN IF NOT EXISTS commission_amount     NUMERIC(20, 2),
  ADD COLUMN IF NOT EXISTS commission_rate       NUMERIC(8, 6),
  ADD COLUMN IF NOT EXISTS settlement_period     VARCHAR(6),       -- YYYYMM
  ADD COLUMN IF NOT EXISTS linked_statement_ref  VARCHAR(150);

-- ── v1.3.0 indexes ───────────────────────────────────────────────────────────
CREATE INDEX IF NOT EXISTS idx_txn_event_type        ON normalized.transactions(event_type);
CREATE INDEX IF NOT EXISTS idx_txn_dealer_period     ON normalized.transactions(dealer_id, settlement_period);
CREATE INDEX IF NOT EXISTS idx_txn_partner_period    ON normalized.transactions(partner_id, settlement_period);
CREATE INDEX IF NOT EXISTS idx_txn_linked_stmt       ON normalized.transactions(linked_statement_ref)
  WHERE linked_statement_ref IS NOT NULL;

-- ── v1.3.0 reconciliation view ───────────────────────────────────────────────
-- Per (dealer, settlement_period) aggregation that unions the three telecom
-- event types into one row. The FBB Revenue Intelligence platform queries
-- this view directly. Drop + recreate so column additions take effect.

DROP VIEW IF EXISTS normalized.partner_settlements;

CREATE VIEW normalized.partner_settlements AS
WITH sales_agg AS (
    SELECT dealer_id,
           settlement_period,
           COUNT(*)         AS sale_count,
           SUM(amount_ngn)  AS total_sales_ngn
    FROM normalized.transactions
    WHERE event_type = 'telecom.dealer_sale'
      AND dealer_id IS NOT NULL
      AND settlement_period IS NOT NULL
    GROUP BY dealer_id, settlement_period
),
statements_agg AS (
    SELECT dealer_id,
           settlement_period,
           COUNT(*)                 AS statement_count,
           SUM(commission_amount)   AS expected_commission_ngn,
           SUM(gross_revenue)       AS statement_gross_revenue_ngn
    FROM normalized.transactions
    WHERE event_type = 'telecom.commission_statement'
      AND dealer_id IS NOT NULL
      AND settlement_period IS NOT NULL
    GROUP BY dealer_id, settlement_period
),
settlements_agg AS (
    SELECT dealer_id,
           settlement_period,
           COUNT(*)                                        AS settlement_count,
           SUM(amount_ngn)                                 AS total_settled_ngn,
           COUNT(*) FILTER (WHERE status = 'SUCCESS')      AS paid_count,
           COUNT(*) FILTER (WHERE status = 'PENDING')      AS partial_count,
           COUNT(*) FILTER (WHERE status = 'FAILED')       AS disputed_count
    FROM normalized.transactions
    WHERE event_type = 'telecom.settlement'
      AND dealer_id IS NOT NULL
      AND settlement_period IS NOT NULL
    GROUP BY dealer_id, settlement_period
)
SELECT
    dealer_id,
    settlement_period,
    sale_count,
    total_sales_ngn,
    statement_count,
    expected_commission_ngn,
    statement_gross_revenue_ngn,
    settlement_count,
    total_settled_ngn,
    paid_count,
    partial_count,
    disputed_count,
    COALESCE(total_settled_ngn, 0) - COALESCE(expected_commission_ngn, 0)
        AS payment_variance_ngn,
    CASE
        WHEN expected_commission_ngn IS NULL
             AND COALESCE(sale_count, 0) > 0
            THEN 'SALES_WITHOUT_STATEMENT'
        WHEN total_settled_ngn IS NULL
             AND expected_commission_ngn IS NOT NULL
            THEN 'STATEMENT_WITHOUT_PAYMENT'
        WHEN COALESCE(disputed_count, 0) > 0
            THEN 'DISPUTED'
        WHEN COALESCE(partial_count, 0) > 0
            THEN 'PARTIALLY_PAID'
        WHEN ABS(COALESCE(total_settled_ngn, 0)
                 - COALESCE(expected_commission_ngn, 0)) > 0.01
            THEN 'AMOUNT_MISMATCH'
        ELSE 'RECONCILED'
    END AS reconciliation_status
FROM sales_agg
FULL OUTER JOIN statements_agg   USING (dealer_id, settlement_period)
FULL OUTER JOIN settlements_agg  USING (dealer_id, settlement_period);

COMMENT ON VIEW normalized.partner_settlements IS
    'v1.3.0 — per-dealer per-period reconciliation surface. Unions '
    'telecom.dealer_sale + telecom.commission_statement + telecom.settlement '
    'events. Consumed by the FBB Revenue Intelligence platform.';
