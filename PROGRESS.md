# PROGRESS

Rolling status file — "pick up where I left off." Update a few bullets at the
end of each work session. Newest session on top.

---

## Current phase
**Audit trail — Phase 1 (zero-commission) complete + generalized.** The
verification-trail pattern is now reusable across audit domains, with a
browsable UI. Next natural step is validating the *judgment* on real trails
before adding a second domain (inventory).

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
