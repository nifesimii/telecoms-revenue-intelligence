-- Run this manually against the running Postgres container:
-- docker exec app_postgres psql -U platform_user -d payment_platform -f /tmp/migrate.sql
-- (after copying this file in with docker cp)

-- Add v1.1.0 columns to normalized.transactions
ALTER TABLE normalized.transactions
  ADD COLUMN IF NOT EXISTS payment_source         VARCHAR(50),
  ADD COLUMN IF NOT EXISTS ingestion_mode         VARCHAR(20),
  ADD COLUMN IF NOT EXISTS virtual_account_type   VARCHAR(20),
  ADD COLUMN IF NOT EXISTS settlement_mode        VARCHAR(20),
  ADD COLUMN IF NOT EXISTS expected_settlement_at TIMESTAMPTZ;

-- Mono: merchants with connected bank accounts
CREATE TABLE IF NOT EXISTS public.merchant_mono_accounts (
  id           SERIAL PRIMARY KEY,
  merchant_id  UUID         NOT NULL,
  account_id   VARCHAR(255) NOT NULL UNIQUE,
  bank_name    VARCHAR(255),
  account_name VARCHAR(255),
  created_at   TIMESTAMPTZ  NOT NULL DEFAULT NOW(),
  is_active    BOOLEAN      NOT NULL DEFAULT TRUE
);

-- Mono: nightly sync audit log
CREATE TABLE IF NOT EXISTS public.mono_sync_log (
  id                SERIAL PRIMARY KEY,
  account_id        VARCHAR(255) NOT NULL,
  bank_name         VARCHAR(255),
  synced_at         TIMESTAMPTZ  NOT NULL DEFAULT NOW(),
  transaction_count INT          NOT NULL DEFAULT 0,
  status            VARCHAR(50)  NOT NULL,
  error_message     TEXT
);

-- New indexes
CREATE INDEX IF NOT EXISTS idx_txn_payment_source   ON normalized.transactions(payment_source);
CREATE INDEX IF NOT EXISTS idx_txn_ingestion_mode   ON normalized.transactions(ingestion_mode);
CREATE INDEX IF NOT EXISTS idx_mono_sync_account    ON public.mono_sync_log(account_id);
CREATE INDEX IF NOT EXISTS idx_mono_accounts_active ON public.merchant_mono_accounts(is_active);
