-- FBB Revenue Intelligence — audit database schema.
--
-- Runs once at container init (mounted into docker-entrypoint-initdb.d) OR
-- re-executed idempotently by audit_store.ensure_schema() on first write
-- against a managed DB (e.g. Render Postgres). All statements are
-- CREATE ... IF NOT EXISTS, so re-runs are safe.
--
-- The table is `audit.verification_trail` — generic across audit modules,
-- with the domain named per row in the `module` column. Historically named
-- `zero_commission_trail`; the rename to `verification_trail` is handled
-- by audit_store.ensure_schema() before this file is executed, so a legacy
-- DB self-migrates without operator intervention.

CREATE SCHEMA IF NOT EXISTS audit;

-- One row per (partner, period, run). A "run" is one explicit
-- "run assurance for period X" invocation; re-running a period replaces
-- that period's rows (see audit_store.replace_period_trails).
CREATE TABLE IF NOT EXISTS audit.verification_trail (
    trail_id            BIGSERIAL PRIMARY KEY,

    -- ── Identity of the claim ────────────────────────────────────────────
    -- For per-record audit modules (e.g. inventory_mismatch), partner_code
    -- may be a composite like "{dealer_id}:{product_code}" — see the
    -- module docstring for the shape it uses.
    partner_code        VARCHAR(50)  NOT NULL,
    partner_name        VARCHAR(200),
    mon_period          VARCHAR(6)   NOT NULL,          -- YYYYMM

    -- ── Run lifecycle ────────────────────────────────────────────────────
    run_id              UUID         NOT NULL,          -- groups one period run
    generated_at        TIMESTAMPTZ  NOT NULL DEFAULT NOW(),
    -- Which audit domain produced this trail. Values today:
    -- zero_commission | inventory_mismatch | payment_reconciliation |
    -- eligibility_window. Free-form string — no CHECK constraint so new
    -- modules can register without a migration.
    module              VARCHAR(50)  NOT NULL DEFAULT 'zero_commission',
    -- The data source the chain checked against. Semantics per module:
    -- 'simulated'/'apdp' for payment-backed audits; 'ifs' for inventory;
    -- 'fbb_comm_dev_act' for the eligibility-window audit. Recorded, not
    -- gated — the reader decides how much to trust each.
    payment_source      VARCHAR(20)  NOT NULL,
    pipeline_version    VARCHAR(20)  NOT NULL DEFAULT '1.0.0',

    -- ── Final conclusion (step 7) ────────────────────────────────────────
    -- Vocabulary is per-module; enumerated in backend/audit/trail.py.
    conclusion          VARCHAR(30)  NOT NULL,
    confidence          VARCHAR(10)  NOT NULL,          -- HIGH | MEDIUM | LOW
    -- Fast filter: how many of steps 1-6 raised a caveat. 0 = fully clean.
    caveat_count        INT          NOT NULL DEFAULT 0,
    -- Names of the steps that raised a caveat, e.g. {'upstream_completeness'}.
    -- GIN-indexed so "all trails where step 6 raised a caveat" is a cheap
    -- `WHERE 'upstream_completeness' = ANY(caveat_steps)`.
    caveat_steps        TEXT[]       NOT NULL DEFAULT '{}',

    -- ── Denormalized per-step results (fast aggregate queries) ───────────
    -- Full detail lives in `steps` JSONB below; these mirror the key result
    -- of each zero_commission step. Kept for backward compatibility with
    -- the earliest analytics queries; newer modules populate what fits and
    -- leave the rest NULL.
    step1_activity_ok        BOOLEAN,
    step1_record_count       INT,
    step2_rate_ok            BOOLEAN,
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
CREATE INDEX IF NOT EXISTS idx_vt_module         ON audit.verification_trail(module);
CREATE INDEX IF NOT EXISTS idx_vt_period         ON audit.verification_trail(mon_period);
CREATE INDEX IF NOT EXISTS idx_vt_partner_period ON audit.verification_trail(partner_code, mon_period);
CREATE INDEX IF NOT EXISTS idx_vt_run            ON audit.verification_trail(run_id);
CREATE INDEX IF NOT EXISTS idx_vt_conclusion     ON audit.verification_trail(conclusion);
CREATE INDEX IF NOT EXISTS idx_vt_confidence     ON audit.verification_trail(confidence);
CREATE INDEX IF NOT EXISTS idx_vt_caveat_steps   ON audit.verification_trail USING GIN (caveat_steps);
CREATE INDEX IF NOT EXISTS idx_vt_steps          ON audit.verification_trail USING GIN (steps);

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

COMMENT ON TABLE audit.verification_trail IS
    'Generic verification-chain store, one row per (partner, period, run) '
    'across every registered audit module. See backend/audit/base.py for '
    'the module registry and audit_init.sql for the schema.';
