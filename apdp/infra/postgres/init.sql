CREATE SCHEMA IF NOT EXISTS raw;
CREATE SCHEMA IF NOT EXISTS normalized;
CREATE SCHEMA IF NOT EXISTS regulatory;

-- ── Raw event store ───────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS raw.payment_events (
    id              BIGSERIAL PRIMARY KEY,
    provider        VARCHAR(50) NOT NULL,
    event_type      VARCHAR(100),
    raw_payload     JSONB NOT NULL,
    received_at     TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- ── Normalized transactions (canonical schema v1.3.0) ─────────────────────────
CREATE TABLE IF NOT EXISTS normalized.transactions (
    transaction_id          VARCHAR(100) PRIMARY KEY,
    provider                VARCHAR(50)  NOT NULL,
    event_type              VARCHAR(100),                -- v1.3.0
    amount                  NUMERIC(20, 4),
    currency                CHAR(3),
    amount_ngn              NUMERIC(20, 2),
    amount_usd              NUMERIC(20, 4),
    fx_rate                 NUMERIC(20, 8),              -- v1.2.0
    fx_source               VARCHAR(20),                 -- v1.2.0 — live | fallback | null
    status                  VARCHAR(50),
    transaction_type        VARCHAR(50),

    -- v1.1.0 fields ────────────────────────────────────────────────────────────
    -- Which PSP or bank originated this transaction
    payment_source          VARCHAR(50),
    -- STREAMING = real-time webhook/poll | BATCH_EOD = Mono nightly bank pull
    ingestion_mode          VARCHAR(20),
    -- Monnify only: STATIC (reserved VA) | DYNAMIC (per-transaction VA) | null
    virtual_account_type    VARCHAR(20),
    -- Monnify only: INSTANT | DAILY | BI_DAILY | null
    settlement_mode         VARCHAR(20),
    -- Computed settlement timestamp for Monnify events
    expected_settlement_at  TIMESTAMPTZ,

    -- v1.3.0 telecom trade partner fields (nullable for non-telecom events) ──
    partner_id              VARCHAR(100),
    dealer_id               VARCHAR(100),
    product_type            VARCHAR(50),
    gross_revenue           NUMERIC(20, 2),
    commission_amount       NUMERIC(20, 2),
    commission_rate         NUMERIC(8, 6),
    settlement_period       VARCHAR(6),                  -- YYYYMM
    linked_statement_ref    VARCHAR(150),

    sender_name             VARCHAR(200),
    sender_phone            VARCHAR(30),
    sender_email            VARCHAR(200),
    receiver_name           VARCHAR(200),
    receiver_phone          VARCHAR(30),
    initiated_at            TIMESTAMPTZ,
    completed_at            TIMESTAMPTZ,
    normalized_at           TIMESTAMPTZ DEFAULT NOW(),
    metadata                JSONB
);

-- ── Reconciliation ────────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS normalized.reconciliation_events (
    reconciliation_id        VARCHAR(100) PRIMARY KEY,
    match_type               VARCHAR(50),
    confidence_score         NUMERIC(5, 3),
    action                   VARCHAR(50),
    canonical_transaction_id VARCHAR(100),
    matched_transactions     JSONB,
    reconciled_at            TIMESTAMPTZ DEFAULT NOW()
);

-- ── CBN regulatory staging ────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS regulatory.cbn_ctr_staging (
    id               BIGSERIAL PRIMARY KEY,
    report_date      DATE NOT NULL,
    transaction_id   VARCHAR(100),
    provider         VARCHAR(50),
    amount_ngn       NUMERIC(20, 2),
    sender_name      VARCHAR(200),
    sender_bvn       VARCHAR(20),
    receiver_name    VARCHAR(200),
    receiver_bvn     VARCHAR(20),
    initiated_at     TIMESTAMPTZ,
    structuring_flag BOOLEAN DEFAULT FALSE
);

-- ── Mono open-banking tables ──────────────────────────────────────────────────

-- Merchants who have connected a bank account via Mono Connect OAuth flow.
-- account_id is the Mono-issued ID returned after the Connect flow completes.
-- The mono-batch service queries this table nightly to know which accounts to pull.
CREATE TABLE IF NOT EXISTS public.merchant_mono_accounts (
    id           SERIAL PRIMARY KEY,
    merchant_id  UUID         NOT NULL,
    account_id   VARCHAR(255) NOT NULL UNIQUE,  -- Mono account ID
    bank_name    VARCHAR(255),                   -- e.g. "Guaranty Trust Bank"
    account_name VARCHAR(255),                   -- e.g. "Acme Logistics Ltd"
    created_at   TIMESTAMPTZ  NOT NULL DEFAULT NOW(),
    is_active    BOOLEAN      NOT NULL DEFAULT TRUE
);

-- Audit log written by mono_batch.py after each nightly sync.
-- One row per account per run — used for monitoring and alerting.
CREATE TABLE IF NOT EXISTS public.mono_sync_log (
    id                SERIAL PRIMARY KEY,
    account_id        VARCHAR(255) NOT NULL,
    bank_name         VARCHAR(255),
    synced_at         TIMESTAMPTZ  NOT NULL DEFAULT NOW(),
    transaction_count INT          NOT NULL DEFAULT 0,
    status            VARCHAR(50)  NOT NULL,  -- SUCCESS | PARTIAL | FAILED
    error_message     TEXT
);

-- ── Indexes ───────────────────────────────────────────────────────────────────
CREATE INDEX IF NOT EXISTS idx_txn_provider         ON normalized.transactions(provider);
CREATE INDEX IF NOT EXISTS idx_txn_initiated        ON normalized.transactions(initiated_at);
CREATE INDEX IF NOT EXISTS idx_txn_status           ON normalized.transactions(status);
CREATE INDEX IF NOT EXISTS idx_txn_payment_source   ON normalized.transactions(payment_source);
CREATE INDEX IF NOT EXISTS idx_txn_ingestion_mode   ON normalized.transactions(ingestion_mode);
-- v1.3.0 indexes
CREATE INDEX IF NOT EXISTS idx_txn_event_type       ON normalized.transactions(event_type);
CREATE INDEX IF NOT EXISTS idx_txn_dealer_period    ON normalized.transactions(dealer_id, settlement_period);
CREATE INDEX IF NOT EXISTS idx_txn_partner_period   ON normalized.transactions(partner_id, settlement_period);
CREATE INDEX IF NOT EXISTS idx_txn_linked_stmt      ON normalized.transactions(linked_statement_ref)
  WHERE linked_statement_ref IS NOT NULL;
CREATE INDEX IF NOT EXISTS idx_ctr_report_date      ON regulatory.cbn_ctr_staging(report_date);
CREATE INDEX IF NOT EXISTS idx_mono_sync_account    ON public.mono_sync_log(account_id);
CREATE INDEX IF NOT EXISTS idx_mono_accounts_active ON public.merchant_mono_accounts(is_active);

-- ── v1.3.0 reconciliation view ───────────────────────────────────────────────
-- Per (dealer, settlement_period) aggregation that unions the three telecom
-- event types into one row. Consumed by the FBB Revenue Intelligence platform.
-- Definition mirrors migrate_v1_3_0.sql — keep them in sync.

CREATE OR REPLACE VIEW normalized.partner_settlements AS
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