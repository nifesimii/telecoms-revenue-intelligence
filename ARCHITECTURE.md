# Architecture

Onboarding document for engineers joining this project. Read it start to
finish and you should understand how the codebase is built without needing to
ask anyone.

It sits alongside two other root docs:
- `PROGRESS.md` — rolling "what's done / what's next" status.
- `CLAUDE.md` — working instructions and design rules (the authoritative
  rulebook for how the FBB backend is meant to be structured).

Keep this file accurate. When you materially change the architecture — add a
layer, change how data flows, move a major responsibility — update the
relevant section here in the same change.

---

## 1. Overview

This repository is one product built in two stacked layers.

**FBB Revenue Intelligence** (`backend/` + `frontend/`) is a finance-facing
application that explains, validates, and audits MTN Nigeria's Fixed
Broadband (FBB) **trade-partner commissions**. It answers questions like "what
commission do we owe dealer X for this month", "why did their payout change",
"which dealers earned zero commission and why", and — most recently — "can we
prove, step by step, that a partner was or wasn't paid". Its users are Finance,
Revenue Assurance, and FBB Operations.

**APDP — African Payment Data Platform** (`apdp/`) is the payment-data pipeline
that will feed FBB real settlement data (Kafka → Flink → Postgres). Today FBB
runs primarily on sample CSVs; APDP is the path to live data. The two layers
meet at a single seam: APDP normalises payment/settlement events into a Postgres
view (`normalized.partner_settlements`), and FBB reads that view when the
`PAYMENT_SOURCE=apdp` flag is set.

---

## 2. Tech Stack

### FBB backend (Python)
- **FastAPI** + **uvicorn** — HTTP API. Chosen over Django because this is a
  thin API over a data/agent layer with no need for an ORM, admin, templating,
  or migrations framework; FastAPI's Pydantic-based request/response typing and
  async support fit the LLM-tool-use workload directly.
- **Anthropic SDK** — the Claude agent (`claude-sonnet-4-5`) with tool use.
- **pandas** — the data layer. In sample mode, queries are implemented as pandas
  operations over CSVs (see §7 on why there's no live SQL engine yet).
- **psycopg2-binary** — connects to the two Postgres databases (APDP's payment
  DB and FBB's dedicated audit DB). Only used on the APDP-payment and audit-trail
  paths, not the core sample-data path.
- **pydantic** — API request/response schemas.
- **pytest** — tests.

Runtime + test deps are pinned in `backend/requirements.txt`. `pyproject.toml`
does *not* declare dependencies — it only configures pytest (warning filters,
test path). A `uv.lock` exists at the root but the pinned `requirements.txt` is
the source of truth for what to install.

### FBB frontend (JavaScript)
- **React 18** + **Vite 5** — SPA and dev server/bundler. Vite chosen for fast
  dev startup and simple config over CRA/webpack.
- **Tailwind CSS 3** — styling (utility classes, no component library).
- **axios** — HTTP client; every backend call is centralised in
  `frontend/src/api/client.js`.
- **react-markdown** + **remark-gfm** — render the agent's markdown answers.

No TypeScript, no state-management library (React context + hooks are enough at
this size), no test runner on the frontend yet.

### APDP (Python + infra)
- **Apache Kafka** (KRaft mode, no Zookeeper) — event backbone.
- **Apache Flink / PyFlink 1.18** — the normaliser job. Note the normalisation
  *logic* is pure Python (`normalizer_core.py`) so it can be unit-tested without
  a Flink cluster; Flink is only the runtime wrapper.
- **Postgres 15** — the normalised event store + reconciliation views.
- **Redis** — FX-rate cache for currency conversion.
- **Prometheus + Grafana** — metrics/dashboards (scaffolded).
- Orchestrated via `apdp/docker-compose.yml`.

---

## 3. Directory Structure

```
telecoms-revenue-intelligence/
├── ARCHITECTURE.md          This file.
├── CLAUDE.md                Design rules + AI working instructions (authoritative).
├── PROGRESS.md              Rolling status: what's done, next, open issues.
├── README.md               Public overview of both layers.
├── docker-compose.yml       Dedicated FBB *audit* Postgres + its backup sidecar.
│                            (APDP has its own compose under apdp/.)
├── pyproject.toml           pytest config only (not dependencies).
├── backend/requirements.txt Pinned Python runtime + test deps.
│
├── backend/                 FBB Revenue Intelligence — Python API + agent.
├── frontend/                FBB Revenue Intelligence — React SPA.
├── apdp/                    African Payment Data Platform — ingestion pipeline.
├── data/samples/            CSV fixtures the backend reads in sample mode.
├── infra/postgres/          Audit DB schema (audit_init.sql) + backup.sh.
├── backups/                 Local pg_dump output (gitignored; .gitkeep tracked).
└── docs/                    Design/learning docs (audit trail, production plan).
```

### `backend/` — grouped by responsibility

The backend has four conceptual layers. The design rule (from `CLAUDE.md`):
**all SQL lives in `backend/db/queries.py` and nowhere else.** Everything above
the data layer asks for results; it never writes SQL.

```
backend/
├── main.py                  FastAPI app: CORS, mounts the router, /health.
│                            Lifespan hook fails fast at boot if the KB won't load.
├── config.py                All env vars → module constants. Mode flags, DB creds,
│                            sample-CSV path map. Start here to understand config.
│
├── api/                     ── API LAYER (HTTP surface) ──
│   ├── routes.py            Every endpoint. The only place HTTP meets the layers below.
│   └── schemas.py           Pydantic request/response models.
│
├── db/                      ── DATA LAYER (single source of truth for numbers) ──
│   ├── queries.py           Every SQL string + every sample-CSV pandas handler.
│   │                        SAMPLE_HANDLERS maps query-name → function; QUERY_NAMES
│   │                        is the allow-list. get_available_periods() lives here.
│   ├── connection.py        execute_query(name, params): dispatches to the CSV
│   │                        handler (sample mode) or Presto (not yet wired).
│   ├── composite.py         assemble_dealer_full_context(): bundles commission +
│   │                        activation + inventory + payment for one dealer into a
│   │                        single call (saves the agent 4 round-trips).
│   ├── triage.py            TRIAGE_HANDLERS: shape/trim query results for the agent.
│   ├── data_coverage.py     Compiles the IFS/USP data-gap ServiceNow ticket.
│   ├── apdp.py              Reads APDP's partner_settlements view (PAYMENT_SOURCE=apdp).
│   └── audit_store.py       Persists + queries verification trails in the FBB audit DB.
│
├── assurance/              ── INTELLIGENCE: the "flaggers" ──
│   ├── base.py              BaseAssuranceService contract + shared result shape.
│   ├── registry.py          ASSURANCE_REGISTRY: {activation, commission, inventory,
│   │                        payment} — the API iterates this to run them all.
│   ├── commission_assurance.py    Flags dealers with zero-commission activations.
│   ├── activation_assurance.py    Flags activation-volume/qualification anomalies.
│   ├── inventory_assurance.py     Flags purchase-vs-activation mismatches.
│   └── payment_assurance.py       Flags payment-coverage exceptions.
│
├── audit/                 ── INTELLIGENCE: the "prover" (audit trails) ──
│   ├── trail.py            TrailStep + VerificationTrail dataclasses + JSON sanitiser.
│   ├── zero_commission_audit.py   The 6-step verification chain for "was partner X
│   │                        paid?" (activity → rate → expected → payment search →
│   │                        near-match → upstream completeness → verdict).
│   └── base.py             Generic AuditModule + registry — lets new audit domains
│                            (inventory, payment) plug in later with one file each.
│
├── agent/                 ── AGENT LAYER (Claude chat) ──
│   ├── agent.py            The conversation loop. run_agent(): sends messages to
│   │                        Claude, executes tool-use turns (max 5 iterations),
│   │                        retries on rate limits, returns the answer + tool trace.
│   ├── tools.py            Tool definitions in Anthropic format. ~13 tools: the 4
│   │                        core (dealer summary, zero-commission records, MoM
│   │                        variance, ORSC) + activation/inventory/payment queries +
│   │                        get_kb_section + get_dealer_full_context.
│   ├── tool_executor.py    Routes a Claude tool call → the right db/ function.
│   │                        QUERY tools go through execute_query; DIRECT tools
│   │                        (get_kb_section, dossier) call handlers directly.
│   ├── prompts.py          Builds the system prompt. Injects the tiered KB (see §5).
│   └── dispute_responder.py  Pure-Python (no LLM) generator for a finance-ready
│                            dispute-response letter.
│
├── knowledge_base/        ── The agent's domain knowledge ──
│   ├── fbb_commission_kb.md    L1 core KB, injected into every system prompt.
│   └── addenda/               Reference material (table schemas, calc logic,
│                            reconciliation anchors, …) fetched on demand via the
│                            get_kb_section tool — kept OUT of the base prompt to
│                            save tokens.
│
├── models/                Pydantic domain models (e.g. activation_summary).
├── data/                  generate_payment_simulation.py — builds the simulated
│                          payment CSV from real commission + exception data.
└── tests/                 pytest suite (~130 tests). One file per area. evals/ is
                           the opt-in agent-quality suite (RUN_EVALS=1, real API).
```

### `frontend/src/` — grouped by responsibility

```
frontend/src/
├── main.jsx                React entry point.
├── App.jsx                 Shell: tab bar + global period selector. Six tabs, each
│                           a panel (Overview, Commission, Activation, Inventory,
│                           Payment, Audit Trails).
├── api/client.js           Every backend call in one file (axios). Best map of what
│                           the frontend can do.
├── context/PeriodContext.jsx  Selected reporting month, shared app-wide, URL-synced.
├── hooks/
│   ├── useChat.js          Chat state + localStorage persistence.
│   └── useDealerVerification.js  Shared fetch for the inline "verify" expandables.
├── lib/
│   ├── format.js           NGN + period (YYYYMM → "Feb 2026") formatting.
│   └── csv.js              CSV export helper.
└── components/
    ├── ChatInterface.jsx / MessageBubble.jsx / DealerSummaryTable.jsx / VarianceCard.jsx
    │                       Commission Intelligence tab (the Claude chat + sidebar).
    ├── activation/         Activation Intelligence tab (summary/variance/exceptions).
    ├── inventory/          Inventory Intelligence tab + DataCoverageTicketModal.
    ├── payment/            Payment Intelligence tab + DisputeDraftModal.
    ├── assurance/AssuranceStatusPanel.jsx   Overview (cross-module triage landing).
    ├── audit/AuditTrailPanel.jsx            Audit Trails tab (browse verification chains).
    └── shared/HelpIcon.jsx                  Tooltip + glossary (qualified vs unqualified).
```

### `apdp/` — grouped by responsibility

```
apdp/
├── docker-compose.yml       Full stack: Kafka, Flink, Postgres, Redis, Prometheus, Grafana.
├── CLAUDE.md / README.md    APDP-specific rules + overview.
├── ingestion/
│   ├── main.py              FastAPI app for the webhook receivers.
│   ├── config.py            APDP env/config.
│   ├── kafka_client.py      Kafka producer helpers.
│   ├── receivers/           Webhook handlers: flutterwave, paystack, monnify, mtn_momo.
│   └── pollers/
│       ├── mtn_momo.py      Background poller for MoMo.
│       └── telecom_batch.py Watches a folder for dealer CSV drops → publishes to Kafka.
├── flink_jobs/
│   ├── normalizer_core.py   Pure-Python normalisation → canonical schema v1.3.0
│   │                        (dealer_sale / commission_statement / settlement). Unit-tested.
│   ├── normalizer.py        Flink runtime wrapper around normalizer_core.
│   ├── fx_service.py        Redis-backed FX conversion.
│   └── test_normalizer.py   Normaliser unit tests (no Kafka/Flink needed).
├── services/postgres_sink/  Consumes normalised Kafka events → writes to Postgres.
├── infra/postgres/init.sql  APDP schema.
├── migrate_v1_3_0.sql       Adds telecom tables + the partner_settlements view FBB reads.
└── tools/generate_telecom_fixtures.py   Synthetic dealer/commission/settlement CSVs.
```

---

## 4. Data Flow

### Flow A — a chat question ("why did dealer 74050 earn zero commission?")
```
Browser (ChatInterface) → api/client.js POST /chat
  → routes.py → agent.run_agent()
    → Claude decides to call a tool (e.g. get_zero_commission_records)
      → tool_executor routes it → db/connection.execute_query()
        → db/queries.py SAMPLE_HANDLERS[name] reads data/samples/*.csv (pandas)
      ← tool result returned to Claude
    ← Claude composes the English answer (grounded in the injected KB)
  ← routes.py returns {response, tools_called, ...}
← rendered as markdown in the chat
```
The agent may fetch KB addenda mid-answer via `get_kb_section`, and may call
`get_dealer_full_context` to get commission+activation+inventory+payment in one
shot instead of four calls.

### Flow B — a data panel (e.g. Payment Intelligence)
```
Browser panel → api/client.js GET /payments/summary?mon_period=YYYYMM
  → routes.py → db/connection.execute_query("get_payment_summary", ...)
    → if PAYMENT_SOURCE=simulated: pandas over payment_simulation.csv
    → if PAYMENT_SOURCE=apdp:      db/apdp.py reads normalized.partner_settlements
  ← Pydantic-shaped rows → panel table
```
This is a plain data endpoint — no LLM involved.

### Flow C — the audit trail (generate + inspect verification chains)
```
"Run" in Audit Trails tab → POST /assurance/audit/run?module=zero_commission&mon_period=…
  → routes.py → audit/base.get_module() → module.build_trails()
    → zero_commission_audit.run_period(): for each flagged partner, run the 6-step
      chain, produce a VerificationTrail (conclusion + confidence + caveats)
  → audit_store.replace_period_trails(): atomically writes to the FBB audit Postgres
    (delete-then-insert per module/period; also self-heals the schema)
← run provenance {run_id, trail_count, ...}

Later, GET /assurance/audit/trails[/{partner}] and /breakdown read them back for
inspection and evaluation (e.g. "all trails where step 6 raised a caveat").
```

### Flow D — APDP ingestion (how live data will reach FBB)
```
Dealer CSV drop → ingestion/pollers/telecom_batch.py → Kafka raw topic
  → flink_jobs/normalizer (Flink) → canonical event → Kafka normalized topic
    → services/postgres_sink → Postgres normalized.transactions
      → migrate_v1_3_0.sql's partner_settlements view
        → FBB db/apdp.py reads it when PAYMENT_SOURCE=apdp
```

---

## 5. Key Abstractions

Understand these before making changes.

**`execute_query(name, params)` (`db/connection.py`) + `SAMPLE_HANDLERS` /
`QUERY_NAMES` (`db/queries.py`).** The single choke point for all data access.
A query has a name, a SQL string (for the future Presto path), and a pandas
handler (for the current sample path). `QUERY_NAMES` is the allow-list — the
tool executor refuses any tool whose name isn't a registered query or a DIRECT
handler. *Why:* keeping every data access behind one named, allow-listed
function is what lets the agent call tools safely and lets the whole app run
with no database.

**The tiered knowledge base (`agent/prompts.py` + `knowledge_base/`).** The core
KB (`fbb_commission_kb.md`) is injected into every system prompt. Bulkier
reference material lives in `knowledge_base/addenda/` and is pulled in only when
needed via the `get_kb_section` tool. *Why:* the full KB in every prompt burned
too much of the per-minute token budget on cold runs; the split keeps prompts
small while keeping the detail reachable.

**The agent loop (`agent/agent.py`).** `run_agent()` runs a bounded tool-use
loop (`MAX_TOOL_ITERATIONS = 5`) with rate-limit retries, and returns both the
text answer and the list of tools called. *Why the cap:* protects against
pathological loops and runaway token spend.

**Tool executor's two routing paths (`agent/tool_executor.py`).** QUERY tools go
through `execute_query`; DIRECT tools (`get_kb_section`, dealer dossier) call a
handler directly. *Why:* not everything the agent needs is a SQL/pandas query —
some tools are lookups or compositions.

**`BaseAssuranceService` + `ASSURANCE_REGISTRY` (`assurance/`).** Each analytical
"flagger" implements the same interface and registers by name, so the API can
run all of them for a period without hard-coding the list. *Why:* uniform result
shape means the Overview page and API don't need per-module logic.

**`VerificationTrail` / `TrailStep` + `AuditModule` registry (`audit/`).** A trail
is a *structured, persisted* object (not a text explanation): an ordered list of
steps, each with what-was-checked / result / caveat, plus a conclusion and
confidence. `AuditModule` (`audit/base.py`) makes the whole machinery
domain-agnostic — a new audit domain is one new `*_audit.py` + a `register(...)`
call, with no changes to storage, endpoints, or UI. *Why:* the trail must be
queryable for audit ("prove this claim") and for evaluation ("how often did we
mislabel a data gap as not-paid?"), which a text blob can't support.

**`PeriodContext` (frontend).** The selected reporting month is global app state,
synced to the URL, so all panels stay on the same period and links are shareable.

---

## 6. Conventions

- **All SQL in one file.** `backend/db/queries.py` is the only place SQL strings
  or data-access logic live. Do not query data from routes, the agent, or the
  assurance/audit modules directly — go through `execute_query`. (This is a hard
  rule in `CLAUDE.md`.)
- **Config via `backend/config.py`.** All env vars are read once there into
  module constants. Don't call `os.getenv` elsewhere. `.env.example` documents
  every variable; copy it to `.env` for local runs.
- **Mode flags.** `USE_SAMPLE_DATA` (CSV vs Presto) and `PAYMENT_SOURCE`
  (simulated vs apdp) are the two switches that change where data comes from.
- **Tests** live in `backend/tests/`, one file per area
  (`test_<area>.py`). They run in sample mode with no external services. The
  agent-quality **evals** (`backend/tests/evals/`, `test_evals.py`) are opt-in
  via `RUN_EVALS=1` because each case is a real (billable) Anthropic call; the
  default `pytest` run skips them. pytest config is in `pyproject.toml`.
- **Naming.** Query names, tool names, and audit step names are stable string
  keys (e.g. `get_dealer_summary`, `upstream_completeness`) and are persisted /
  allow-listed — treat renames as migrations, not refactors.
- **Frontend API access** is centralised in `frontend/src/api/client.js`; add
  new endpoints there, not inline in components.
- **No enforced linter/formatter** is wired in CI today (see rough edges). Match
  the surrounding style: the code leans on module docstrings and section-comment
  banners.
- **Money + periods.** Amounts are NGN, formatted `NGN X,XXX,XXX.XX`; periods are
  `YYYYMM` strings. Frontend formatting helpers are in `lib/format.js`.

---

## 7. Known Rough Edges

Things that are deliberately incomplete, temporary, or non-obvious — don't
"fix" them without understanding why they're like this.

- **Live Presto is not wired.** `db/connection.py::_run_presto` raises
  `NotImplementedError`. `USE_SAMPLE_DATA=true` is the permanent mode until a
  Presto service account is provisioned. The SQL strings in `queries.py` exist
  for that future path but are not executed today — the pandas handlers are.
- **Payment data is simulated by default.** `payment_simulation.csv` is generated
  from real commission/exception data (`data/generate_payment_simulation.py`).
  `PAYMENT_SOURCE=apdp` switches to live APDP data, but that requires the APDP
  stack running and its telecom feed populated.
- **APDP is partially deployed.** The normaliser logic, sink, and schema exist and
  are tested, but the end-to-end pipeline is not continuously running; it's
  brought up on demand. See `apdp/CLAUDE.md` / `PROGRESS.md` for current state.
- **Audit trail confidence reads LOW on sample data.** Every zero-commission
  trail comes back LOW confidence because the sample USP product codes don't
  overlap the activation product codes (trips step 2) and sample payments have
  adjacent-period partials (trips step 5). This is the system being honest about
  ambiguous sample data, not a bug. An open design question (in `PROGRESS.md`):
  should a partial payment be its own conclusion (`PARTIALLY_PAID`) rather than
  `NOT_PAID`/LOW? Validate on real trails before trusting confidence at face value.
- **Audit table name vs generality.** The audit table is still called
  `audit.zero_commission_trail` even though the layer is now generic (it has a
  `module` column). Renaming it is a migration deferred until a second module lands.
- **`ensure_schema()` self-heal.** `audit_store.py` runs an idempotent ALTER on
  first write to add the `module` column to older audit DBs. It's a convenience so
  a pre-existing DB doesn't need a manual migration — intentional, not a leak.
- **No auth.** Any caller can hit any endpoint and query any dealer. Fine for the
  current demo/pilot stage; a real deployment needs authn/authz (flagged in
  `docs/PRODUCTION_READINESS_LEARNING_PLAN.md`).
- **No CI linter; one known-flaky test.**
  `test_inventory_agent.py::test_kb_inventory_rules_grounded` is a live-LLM test
  and can flake. GitHub Actions runs the non-eval suite only.
- **`uv.lock` vs `requirements.txt`.** Both exist at the root/backend. The pinned
  `backend/requirements.txt` is the source of truth for installs; `uv.lock` is not
  currently the managed lockfile.
- **Two separate docker-compose files.** Root `docker-compose.yml` is *only* the
  FBB audit Postgres + backup. APDP's full stack is `apdp/docker-compose.yml`.
  They are independent; don't expect one to bring up the other.

---

## 8. Setup & Run

Prerequisites: Python 3.12+, Node 20+/22+ (the frontend's Vite needs a modern
Node — an old Node in PATH will fail to start the dev server), Docker (only for
the audit DB / APDP), and an `ANTHROPIC_API_KEY` if you want the chat agent.

```bash
# 0. Config
cp .env.example .env            # fill ANTHROPIC_API_KEY; defaults are fine otherwise

# 1. Python deps (into a venv)
python -m venv .venv
.venv/bin/pip install -r backend/requirements.txt

# 2. (Optional) Audit datastore — needed only for the Audit Trails feature
docker compose up -d            # dedicated FBB audit Postgres on host port 5544 + backup

# 3. Backend  → http://localhost:8000  (interactive docs at /docs)
FBB_AUDIT_PG_HOST=localhost FBB_AUDIT_PG_PORT=5544 USE_SAMPLE_DATA=true \
  .venv/bin/python -m uvicorn backend.main:app --host 127.0.0.1 --port 8000

# 4. Frontend → http://localhost:5173  (calls the backend at :8000 by default)
cd frontend && npm install && npm run dev

# 5. Tests (sample mode, no external services)
.venv/bin/python -m pytest backend/tests -q
RUN_EVALS=1 .venv/bin/python -m pytest backend/tests/test_evals.py -q   # opt-in, billable
```

The app runs fully on sample data without Docker or Presto — only the Audit
Trails tab and `PAYMENT_SOURCE=apdp` need Postgres. APDP has its own setup; see
`apdp/README.md` and `apdp/CLAUDE.md`.
