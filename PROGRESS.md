# PROGRESS

Rolling status file — "pick up where I left off." Update a few bullets at the
end of each work session. Newest session on top.

---

## Current phase
**Preparing a GM preview / finance presentation.** The FBB app (5 intelligence
views + Overview + Audit Trails) runs end-to-end on sample data. Dealer
data-connector layer is built and proven in APDP. Immediate next step:
**deploy for a shareable link (Option 2 — real hosting: frontend + backend +
Postgres on a cloud host).** No deployment config written yet.

Recent milestones behind this: audit trail (zero-commission) Phase 1 complete
and generalized into a reusable module registry with a browsable UI; dealer
connector abstraction + sandbox proof done.

Docs: ARCHITECTURE.md (onboarding), CLAUDE.md (rules; both exist — root + apdp/),
PROGRESS.md (this file). CLAUDE.md points at ARCHITECTURE.md.

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
