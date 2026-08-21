# PROGRESS

Rolling status file — "pick up where I left off." Update a few bullets at the
end of each work session. Newest session on top.

---

## Session — 2026-08-10  (manager-review sprint)

Long session — the senior manager received the preview link and started
reviewing before it reaches the GM. Everything below was in response to
observations from that review, plus onboarding prep for incoming team
members. Order is roughly chronological.

**Onboarding materials shipped (for team members joining Monday)**
- `docs/FBB_Onboarding.pptx` — 18-slide deck: MTN/FBB business context
  (no prior knowledge assumed), architecture, 4 audit modules,
  contribution guide, short-term + long-term goals. Two revisions
  incorporated feedback ("assume no MTN knowledge" and "add
  ARCHITECTURE.md-update rule").
- Onboarding note (5-step walkthrough, sent to team on WhatsApp — not
  committed to repo per user preference).
- Deck + note explicitly limit team members to **1–3 chat questions/day**
  because each call bills to the Anthropic account. Access model: GitHub
  repo access + preview URL + local dev tooling; no personal Anthropic
  key initially.

**Search filters shipped across every intelligence tab**
- Activation (previous session), Inventory, Payment, Audit Trails all
  now have client-side substring search. Persists across sub-tabs.
- Inventory searches product code + name too (e.g. `hynex` isolates the
  SKU-alias split).

**Performance hotfix (audit run timing out on Render)**
- Manager saw "timeout of 120000ms exceeded" clicking the Run button in
  Audit Trails. Root cause: `adjacent_period_payments` was called inside
  the per-partner loop, and `_load_csv` had no in-process cache — so
  487 partners × 2 adjacent periods = 974 redundant full CSV parses per
  audit run.
- Fixed both: in-process CSV cache with defensive `.copy()`, plus
  `prefetch_adjacent_frames()` at the orchestrator level threaded
  through gather_inputs. Timings on my box: zero_commission
  120s+ → 8.9s, payment_reconciliation ~15s → 0.9s. On Render (~3-5×
  slower) safely under the 120s client ceiling.
- Also bumped axios client timeout 60s → 120s so a slow first request
  after quiet time doesn't fire the client-side abort before the server
  is done.

**Anthropic API-key rotation guidance**
- Chat returned "I encountered an error retrieving that data" — Render
  logs showed `401 invalid x-api-key`. Not a code bug. Rotate + repaste
  in Render env. Documented the diagnostic path for the team so they
  know to check Render logs → API keys → Anthropic billing in that
  order for chat failures.

**The dealer-identifier naming standardisation (the big one)**
- Codebase had drifted into two competing names — `distributor_code`
  (Phase 1 handlers) vs `dealer_id` (Phase 2+ handlers). The Payment
  tab search shipped a live zero-results bug from this exact drift
  (filter queried on `dealer_id`, response returned `distributor_code`).
- Convention now documented in ARCHITECTURE.md § 6:
  - Raw SQL/CSV columns keep `distributor_code` (matches Presto — we
    don't own the source).
  - **API response fields uniformly `dealer_id` / `dealer_name`.**
  - Input parameters keep `distributor_code` (matches CLAUDE.md tool
    schema + the SQL column being filtered).
  - Audit trail subject stays `partner_code` (generic; supports
    composite keys like `dealer:product`).
- Enforcement: 29 files touched.
  - `backend/db/queries.py` — 4 handlers (`dealer_summary`, `orsc_summary`,
    `payment_summary`, `payment_exceptions`) rename at the return
    boundary via `df.rename(columns={...})`.
  - Downstream backend: `assurance/*`, `agent/dispute_responder.py`,
    `db/{composite,data_coverage,triage}.py`, 3 `audit/*_audit.py`
    files (`gather_inputs` + `run_period`), `api/{schemas,routes}.py`.
  - Frontend: 6 components + 1 hook migrated. Defensive dual-field
    check in `PaymentIntelligencePanel` dropped — now moot.
  - 5 test files updated; RAW-CSV column reads (`dev_act_df["distributor_code"]`)
    intentionally kept per convention. `test_payment_simulation_file_exists`
    now carries a comment explaining why it stays on the raw name.
  - CLAUDE.md tool return docs updated for Tool 1 + Tool 4.

**Learning to keep** (into ARCHITECTURE.md § 6 as a guardrail)
The naming bug happened because two people (or the same person on two
different days) chose different names for the same thing at different
layers, and the frontend filter that came later trusted the newer name.
The layered rule in ARCHITECTURE.md § 6 is now the guardrail: any new
API handler returning a dealer-scoped record MUST alias at the return
boundary.

**State at end of day**
- 210 tests green (up from 208; the two new tests are indirect coverage
  of the rename).
- Live preview at fbb-preview.onrender.com — all 4 audit modules render;
  Overview shows Audit Coverage band; search filters work on all four
  intelligence tabs; Payment search works with a single-field filter.
- Onboarding materials sent to team; new members joining Monday.

**Next — before GM demo**
1. Verify the Render redeploy after commit `13d6b75` shows the rename
   fix live. Smoke-test Payment tab search end-to-end.
2. Wait for the manager's remaining feedback and address any punch-list
   items they surface.
3. Send GM the URL + creds + `docs/GM_DEMO.md` as the read-along.
4. If time permits before GM: prove `PAYMENT_SOURCE=apdp` end-to-end
   with the APDP fixture generator. Not blocking — the demo is fine on
   simulated data.

**Deferred (post-GM feedback)**
- `test_kb_inventory_rules_grounded` live-LLM flake (untouched; low
  priority — model occasionally emits "fraud" in a KB-forbidden
  negation).
- APDP end-to-end continuous run.
- Fifth audit module — waiting on GM feedback about which domain to
  audit next.
- Real dealer data via Mono consent or an MTN internal feed — waiting
  on finance/MTN access approval.

---

## Current phase
**GM preview is LIVE at https://fbb-preview.onrender.com** (Basic-Auth
gated, sample data). Audit-module coverage complete for the demo scope —
FOUR modules registered: `zero_commission`, `inventory_mismatch`,
`payment_reconciliation`, `eligibility_window`. Overview landing page now
surfaces per-module trail counts + top conclusions in an "Audit coverage"
band. Audit table renamed from `zero_commission_trail` → `verification_trail`
(self-migrating). Every intelligence tab has a search filter. Immediate
next: **send the GM the URL + creds and collect feedback** — the demo has
no known missing pieces at this scope.

Docs: ARCHITECTURE.md (onboarding), CLAUDE.md (rules; both exist — root + apdp/),
PROGRESS.md (this file), docs/DEPLOY.md, docs/AUDIT_INVENTORY_MISMATCH_DESIGN.md.

---

## Session — 2026-08-07

**Done**
- **Fourth audit module — `eligibility_window`.** Per-partner, per-IMEI
  audit of the KB's most-cited zero-commission root cause (Section 2 /
  Issue 2: the 6-month invoice→activation rule). 6-step chain:
  zero_commission_records_present → fetch_dates → compute_gaps →
  classify_against_window → root_cause_attribution → upstream_completeness.
  Four conclusions: `POLICY_MET` (all zero-comm outside 180d),
  `POLICY_VIOLATED` (inside-window records with no other explaining KB
  root cause — partner may be owed), `MIXED_ATTRIBUTION` (inside-window
  but every one attributable to NULL profile / USP miss / Hynex alias —
  the label is imprecise, not the calculation), `INSUFFICIENT_DATA`.
  Signal on 202602 sample: 487 trails → 465 MIXED_ATTRIBUTION / 22
  POLICY_MET / 0 POLICY_VIOLATED, all HIGH confidence. 24 tests.
- **Overview "Audit coverage" band.** New tile grid on the landing page
  showing all four audit modules with trail counts + top two conclusion
  badges colour-coded to match the Audit Trails tab. Best-effort loading
  so a Postgres blip doesn't blank the whole Overview; every tile and
  the section header link back to the Audit Trails tab. Demo flow is
  now: land on Overview → see audit coverage → click tile → inspect
  trails.
- **Audit table renamed** `audit.zero_commission_trail` →
  `audit.verification_trail` (the table was already generic across
  modules; the phase-1 name was a lie). `ensure_schema()` self-migrates
  legacy DBs BEFORE running the init script — renames the table AND all
  `idx_zct_*` indexes to `idx_vt_*` so CREATE INDEX IF NOT EXISTS in
  the init script no-ops instead of creating duplicates. Verified on the
  live local Postgres: 8,679 pre-existing trails preserved end-to-end.
  Two Postgres-auto-named constraints (`zero_commission_trail_pkey`,
  `..._key`) keep their old names on migrated DBs — cosmetic, not
  referenced anywhere.
- **Search filters** on every intelligence tab now (this session added
  Inventory + Payment; previous session added Activation + Audit Trails).
  Every tab has a consistent shape: client-side substring, "N of M"
  count when active, search persists across sub-tabs.

**Where the ORSC "next module" plan pivoted**
Investigation surfaced a real blocker for an ORSC-flavoured payment
audit: the ORSC sample data carries `data_subscription_amount` (revenue
collected from the end customer, not what MTN owes the dealer), no
ORSC-specific payment stream exists in `payment_simulation.csv` (that
file is activation-commission-focused), and CLAUDE.md forbids ORSC
continuity monitoring. Substituted **Eligibility Window** as a
per-record policy audit that cleanly works on the current sample data
and turns one of the KB's four documented zero-commission root causes
into a verifiable per-IMEI verdict.

**Signal quality summary — how the four modules see the same sample data**
`zero_commission` → narrow claim, all-LOW on ambiguous sample data.
`payment_reconciliation` → 939 trails, dominant UNDERPAID/MEDIUM+HIGH.
`inventory_mismatch` → 4,018 trails, 12 real EXCESS_ACTIVATION/HIGH.
`eligibility_window` → 487 trails, 465 MIXED_ATTRIBUTION/HIGH.
Four different framings of the same underlying data, each pointing
Finance at a different actionable pile.

**Next (immediate)**
- **Send the link.** GM demo has no known missing pieces. Waiting on
  code is now the wrong bottleneck.

**Next (later — driven by GM feedback)**
- If GM asks for finer per-record inspection, the audit-trail expand
  panels are the natural place to add drill-down (IMEI list is already
  in step details but not surfaced in the UI).
- If GM validates the "UNDERPAID / OVERPAID" vocabulary, keep it; if
  they want "SHORTFALL / OVERPAYMENT" (or a Finance-specific term),
  it's a one-line rename per module.
- Real dealer data (Mono consent aggregation → APDP connector layer)
  remains the biggest downstream unlock — no action needed until
  finance/MTN grants access.

**Open issues (unchanged from last session)**
- Live-LLM flake `test_kb_inventory_rules_grounded` — model
  occasionally emits "fraud" in a KB-forbidden negation. Non-blocking.
- `payment_reconciliation` and `zero_commission` still share
  payment-data helpers via a leaky import; natural refactor when a
  fifth payment-aware module lands is to lift them into
  `backend/audit/payment_data.py`.

---

## Session — 2026-08-03

**Done**
- **Render deploy shipped.** Blueprint (`render.yaml`), multi-stage Dockerfile
  (Node builds SPA → Python serves both on one origin), Basic-Auth middleware
  gated by `DEMO_USERNAME` / `DEMO_PASSWORD`, and `audit_store.ensure_schema()`
  now executes `audit_init.sql` on first write so Render-managed Postgres
  bootstraps without an init hook. Live at
  https://fbb-preview.onrender.com — `/health` green, Audit Trails tab works
  end-to-end on the managed DB.
- **Second audit module — inventory_mismatch.** Mirrors zero_commission's
  shape via the generic `AuditModule` registry; one trail per (dealer,
  product) with composite `partner_code` (`{dealer}:{product}`) so per-product
  granularity holds without a schema migration. 6-step chain: mismatch_signal
  → purchase_record_lookup → allocation_calculation → prior_period_stock →
  product_alias_reconciliation → upstream_completeness. Extended trail
  vocabulary with `RECONCILED` / `EXCESS_ACTIVATION`. New `product_aliases.py`
  is the shared source-of-truth for Hynex/Hynex_1-style groups. KB gains
  "Inventory mismatch root causes" section. 17 tests.
- **Third audit module — payment_reconciliation.** Coexists with
  zero_commission (no behaviour change to that module — they answer different
  questions). Audits the general "paid the correct amount for period Y"
  claim for every partner with commission activity. Five conclusions via an
  amount-comparison bucket: `PAID_IN_FULL` / `DISPUTED_ROUNDING` (rounding /
  FX / fees inside ±100 NGN or <1%) / `UNDERPAID` / `OVERPAID` /
  `INSUFFICIENT_DATA`. Confidence rule excludes the step-4 non-full-match
  caveat so a clean UNDERPAID reads HIGH. 27 tests.
- **Signal quality on sample data (202602):**
  zero_commission → 487 trails, ALL LOW confidence (unhelpful demo signal).
  payment_reconciliation → 939 trails: 912 UNDERPAID, 27 PAID_IN_FULL;
  confidence spread 777 MEDIUM / 148 HIGH / 14 LOW. Dramatically better
  demo signal — this alone justifies keeping the two modules side by side.
- **Partner search filter** on the Audit Trails UI — client-side substring
  over `partner_code` + `partner_name`, useful with the 4000+ inventory
  trails.

**Where we are on the PARTIALLY_PAID design question**
Resolved. Under payment_reconciliation, a partial payment is `UNDERPAID`
(HIGH confidence when the payment record itself is clean). No need to add
a `PARTIALLY_PAID` conclusion to zero_commission — the audit that cares
about "how much" is now its own module, and the audit that cares about
"was the specific zero-commission root cause valid" stays scoped to that.

**Next (immediate — where we pick up)**
1. Smoke-test the deployed URL: log in, run all three audit modules on
   Feb 2026, exercise the new partner filter, confirm nothing broke that
   didn't break locally.
2. Send the GM the URL + creds (out of band). Collect feedback on
   whether payment_reconciliation's UNDERPAID/OVERPAID buckets are the
   right vocabulary for Finance (they may want a different label like
   "SHORTFALL" / "OVERPAYMENT").
3. Only after that: pick the next audit module. Candidates on the shortlist
   (see AUDIT_INVENTORY_MISMATCH_DESIGN.md for the pattern):
   - **ORSC payment** — parallel to payment_reconciliation for the other
     revenue stream.
   - **Duplicate payment** — narrow, high fraud/error signal.
   - **Eligibility window compliance** — per-IMEI policy audit.

**Next (later)**
- Confirm with finance/MTN which dealer access model will be granted
  (targeting consent-aggregation + staying model-agnostic).
- When creds land: wire the production MoMo history endpoint and/or the
  Mono consent-capture flow; load the real dealer roster into
  `dealer_connections`.
- Address the pre-existing live-LLM flake in
  `test_kb_inventory_rules_grounded` — model occasionally emits "fraud"
  in a negation, which the KB Rule 4 forbids. Not a regression; noted
  since it now fires against a KB the model has clearly read.

**Open issues**
- Audit table is still named `audit.zero_commission_trail` even though it
  now carries three modules' worth of trails via the `module` column.
  Rename deferred until the abstraction has a fourth module — the migration
  is cheaper once (rename + drop the old CHECK-implicit constraint) than
  every time.
- payment_reconciliation and zero_commission share payment-data helpers via
  a leaky import; natural refactor when a fourth payment-aware module lands
  is to lift them into `backend/audit/payment_data.py`.

---

## Session — 2026-08-02

**Done**
- Built the **dealer data-connector layer** in APDP (`apdp/ingestion/connectors/`)
  so that when finance approves, connecting to dealers + pulling their MoMo/
  account data is fast and model-proof. One `DealerDataConnector` interface;
  swappable backends (simulated / momo / consent-Mono / [internal — later]).
  Onboarding-as-config (`dealer_connections` table + JSON fallback), a runner
  with per-dealer error isolation, and 11 tests (all pass, zero creds/infra).
- Proved end-to-end: a connector envelope flows through the EXISTING normalizer
  unchanged → canonical v1.3.0 event.
- Wrote `apdp/docs/DEALER_CONNECTORS.md` — the access-model decision record
  (3 models, proven-vs-pending, "day approval lands" activation checklist).

**Key reality captured:** the MoMo *merchant* API can't read an arbitrary
dealer's wallet. Real dealer-account access is consent-aggregation (Mono) or
an internal MTN feed. The abstraction means whichever finance grants, it's one
connector to activate — not a rebuild.

**Next (immediate — where we're picking up)**
- **Deploy for a GM preview link (Option 2: real hosting).** The app is 2 pieces
  — frontend (Vite/React) + backend (FastAPI). A frontend-only host = dead shell
  ("API unreachable"); need both up + optional Postgres for the Audit Trails tab.
  All demo data is fictional sample data, so a public link leaks nothing real
  (still password-gate it). To write when resumed: backend Dockerfile, hosting
  blueprint (platform TBD — Render/Railway/Vercel+Render), CORS_ORIGINS + the
  frontend's VITE_API_URL wiring, managed Postgres hookup. Frontend reads
  VITE_API_URL (defaults to localhost:8000); CORS defaults to localhost:5173 —
  both need the deployed URLs.

**Next (later)**
- Confirm with finance/MTN which dealer access model will be granted (targeting
  consent-aggregation + staying model-agnostic).
- When creds land: wire the production MoMo history endpoint and/or the Mono
  consent-capture flow; load the real dealer roster into `dealer_connections`.
- Validate audit-trail judgment (the PARTIALLY_PAID question); add inventory as
  a second audit module.

---

## Session — 2026-07-28 (later)

**Done**
- Added **ARCHITECTURE.md** at the repo root — full onboarding doc (overview,
  tech stack + rationale, directory tree, data flows, key abstractions,
  conventions, known rough edges, setup & run). Referenced from CLAUDE.md so
  future sessions read it. Keep it updated when architecture changes materially.

---

## Session — 2026-07-28

**Done**
- Generalized the audit trail into a reusable `AuditModule` base + registry
  (`backend/audit/base.py`); migrated zero-commission onto it with identical
  output (same 487 trails).
- Persistence + endpoints are now module-aware (`module` column, idempotent
  `ensure_schema()` self-heal; new generic `/assurance/audit/*` endpoints;
  old `/assurance/zero-commission/*` still work).
- Built the **Audit Trails** frontend tab — module dropdown, Run button,
  trails table with expandable per-row step checklist, breakdown band, and a
  caveat-step evaluation filter. Renders any module's trails generically.
- Verified live end-to-end (Docker up): run job, module column populated,
  caveat filter (474 near_match), full checklist, backward-compat. 57 tests
  pass; frontend builds.

**Next**
- **(c) Validate the judgment**: eyeball ~20 real trails. Key question — is
  "partial payment in adjacent period → NOT_PAID / LOW" correct, or should
  partial be its own conclusion (`PARTIALLY_PAID`)?
- Then add a **second audit module** (inventory mismatch) to prove the base —
  should be one new `inventory_audit.py` + `register(...)`, no UI/storage change.
- Push the local commits to origin (was 9 ahead before this session's commit).

**Open issues**
- All sample-data trails come back **LOW confidence** — legitimate (sample
  USP product codes don't overlap activation product codes → step 2 caveats;
  adjacent-period partial payments → step 5 caveats). Not a bug, but confirms
  why (c) matters before trusting confidence at face value.
- Docker daemon flapped repeatedly this session; live checks needed restarts.
- `backend/tests/test_inventory_agent.py::test_kb_inventory_rules_grounded`
  is a pre-existing live-LLM flake (unrelated).

---

## Earlier sessions (condensed)

**Zero-commission audit trail (Phase 1) + dedicated FBB Postgres** — 6-step
verification chain per (partner, period); dedicated `fbb_audit` Postgres with
persistent volume + daily `pg_dump` backup sidecar (first backup in the whole
project); run job + query/breakdown endpoints; 19 tests. Verified live: 487
trails, idempotent re-run, GIN-indexed caveat query, backup dump.

**Eval harness + dispute generator + polish pile** — opt-in agent eval suite
(23 golden cases, `RUN_EVALS=1`); finance-ready dispute-response generator
(pure-Python letter + modal); chat persistence, URL state, CSV export, CI,
`requirements.txt`, httpx warning fix, arm64 Flink pin.

**APDP integration** — moved APDP under `apdp/`; telecom canonical schema
v1.3.0 + normalizer + synthetic generator; telecom-batch ingestor (file→Kafka);
Kafka→Postgres sink; Postgres migration + `partner_settlements` view; FBB
Payment Intelligence reads it behind `PAYMENT_SOURCE=apdp`.

**FBB frontend/product** — 5 intelligence views; Overview landing page; verify
expandables (payment/inventory/assurance); data-coverage ServiceNow ticket
(Stage 1); NGN/period formatting; qualified-vs-unqualified glossary tooltips.

---

## Key run commands
```bash
# Audit datastore (dedicated FBB Postgres + backup sidecar)
docker compose up -d

# Backend (sample mode, pointed at audit DB)
FBB_AUDIT_PG_HOST=localhost FBB_AUDIT_PG_PORT=5544 USE_SAMPLE_DATA=true \
  .venv/bin/python -m uvicorn backend.main:app --host 127.0.0.1 --port 8000

# Frontend
cd frontend && npm run dev            # :5173 → talks to backend :8000

# Generate + browse audit trails
curl -X POST "localhost:8000/assurance/audit/run?module=zero_commission&mon_period=202602"
# …or open the "Audit Trails" tab in the UI.

# Tests
.venv/bin/python -m pytest backend/tests -q          # RUN_EVALS=1 to include evals
```
