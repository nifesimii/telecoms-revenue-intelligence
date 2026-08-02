-- FBB Revenue Intelligence — audit database schema.
--
-- Runs once at container init (mounted into docker-entrypoint-initdb.d).
-- This is a DEDICATED FBB Postgres, separate from APDP's payment_platform.
--
-- Phase 1 scope: zero-commission flagging ONLY. Inventory mismatch trails
-- come later once this pattern is validated.
--
-- Design goals:
--   1. Audit — every "Partner X not paid for period Y" claim is backed by a
--      persisted, inspectable verification chain.
--   2. Evaluation — trails are easy to aggregate/query across many records
--      (e.g. "all trails where the upstream-completeness step raised a
--      caveat") so we can review the agent's judgment quality over time.

CREATE SCHEMA IF NOT EXISTS audit;

-- One row per (partner, period, run). A "run" is one explicit
-- "run assurance for period X" invocation; re-running a period replaces
-- that period's rows (see audit_store.replace_period_trails).
CREATE TABLE IF NOT EXISTS audit.zero_commission_trail (
    trail_id            BIGSERIAL PRIMARY KEY,

    -- ── Identity of the claim ────────────────────────────────────────────
    partner_code        VARCHAR(50)  NOT NULL,
    partner_name        VARCHAR(200),
    mon_period          VARCHAR(6)   NOT NULL,          -- YYYYMM

    -- ── Run lifecycle ────────────────────────────────────────────────────
    run_id              UUID         NOT NULL,          -- groups one period run
    generated_at        TIMESTAMPTZ  NOT NULL DEFAULT NOW(),
    -- Which audit domain produced this trail. The table is generic across
    -- audit modules (zero_commission today; inventory/payment later).
    module              VARCHAR(50)  NOT NULL DEFAULT 'zero_commission',
    -- Which payment dataset the chain checked against. Recorded, not gated:
    -- 'simulated' trails are persisted alongside 'apdp' ones; the reader
    -- decides how much to trust each. See DATA SAFETY note in the task brief.
    payment_source      VARCHAR(20)  NOT NULL,          -- 'simulated' | 'apdp'
    pipeline_version    VARCHAR(20)  NOT NULL DEFAULT '1.0.0',

    -- ── Final conclusion (step 7) ────────────────────────────────────────
    conclusion          VARCHAR(20)  NOT NULL,          -- NOT_PAID | PAID | INSUFFICIENT_DATA
    confidence          VARCHAR(10)  NOT NULL,          -- HIGH | MEDIUM | LOW
    -- Fast filter: how many of steps 1-6 raised a caveat. 0 = fully clean.
    caveat_count        INT          NOT NULL DEFAULT 0,
    -- Names of the steps that raised a caveat, e.g. {'upstream_completeness'}.
    -- GIN-indexed so "all trails where step 6 raised a caveat" is a cheap
    -- `WHERE 'upstream_completeness' = ANY(caveat_steps)`.
    caveat_steps        TEXT[]       NOT NULL DEFAULT '{}',

    -- ── Denormalized per-step results (fast aggregate queries) ───────────
    -- Full detail lives in `steps` JSONB below; these mirror the key result
    -- of each step so common analytics don't need JSONB extraction.
    step1_activity_ok        BOOLEAN,   -- had qualifying activity
    step1_record_count       INT,
    step2_rate_ok            BOOLEAN,   -- applicable rate/eligibility found
    step3_expected_ngn       NUMERIC(20, 2),
    step4_payment_found      BOOLEAN,
    step4_amount_paid_ngn    NUMERIC(20, 2),
    step5_near_match_found   BOOLEAN,
    step6_upstream_complete  BOOLEAN,

    -- ── Full inspectable chain ───────────────────────────────────────────
    -- Array of step objects, each: {step, name, checked, result, caveat,
    -- detail{}}. This is the auditor-facing verification chain.
    steps               JSONB        NOT NULL,

    -- One (partner, period) claim per run.
    UNIQUE (partner_code, mon_period, run_id)
);

-- ── Indexes ──────────────────────────────────────────────────────────────
CREATE INDEX IF NOT EXISTS idx_zct_module        ON audit.zero_commission_trail(module);
CREATE INDEX IF NOT EXISTS idx_zct_period        ON audit.zero_commission_trail(mon_period);
CREATE INDEX IF NOT EXISTS idx_zct_partner_period ON audit.zero_commission_trail(partner_code, mon_period);
CREATE INDEX IF NOT EXISTS idx_zct_run           ON audit.zero_commission_trail(run_id);
CREATE INDEX IF NOT EXISTS idx_zct_conclusion    ON audit.zero_commission_trail(conclusion);
CREATE INDEX IF NOT EXISTS idx_zct_confidence    ON audit.zero_commission_trail(confidence);
CREATE INDEX IF NOT EXISTS idx_zct_caveat_steps  ON audit.zero_commission_trail USING GIN (caveat_steps);
CREATE INDEX IF NOT EXISTS idx_zct_steps         ON audit.zero_commission_trail USING GIN (steps);

-- ── Run ledger ───────────────────────────────────────────────────────────
-- One row per "run assurance for period X" invocation, for provenance:
-- who/what triggered it, how many trails it produced, timing.
CREATE TABLE IF NOT EXISTS audit.assurance_run (
    run_id          UUID         PRIMARY KEY,
    module          VARCHAR(50)  NOT NULL DEFAULT 'zero_commission',
    mon_period      VARCHAR(6)   NOT NULL,
    payment_source  VARCHAR(20)  NOT NULL,
    trail_count     INT          NOT NULL DEFAULT 0,
    started_at      TIMESTAMPTZ  NOT NULL DEFAULT NOW(),
    completed_at    TIMESTAMPTZ,
    triggered_by    VARCHAR(100) NOT NULL DEFAULT 'api'
);

CREATE INDEX IF NOT EXISTS idx_run_period ON audit.assurance_run(mon_period);

COMMENT ON TABLE audit.zero_commission_trail IS
    'Phase 1 — persisted verification chain behind every zero-commission '
    '"not paid" claim, per (partner, period, run). Serves both audit '
    '(inspectable evidence) and evaluation (aggregate the agent''s judgment '
    'quality). See infra/postgres/audit_init.sql.';
