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

**APDP — African Payment Data Platform** (`apdp/`) is the payment-data
pipeline. The full production path is Kafka → Flink → Postgres, but
because the Flink Docker build is broken and the Kafka→Postgres sink was
never wired (see `apdp/CLAUDE.md`), the demo takes a shortcut: fixture
CSVs → pure-Python `normalizer_core` → direct psycopg2 INSERT into
`normalized.transactions`. Everything downstream of the normaliser
(the `normalized.partner_settlements` view, and FBB reading from it)
works exactly the same as the eventual live path.

The two layers meet at one seam: `normalized.partner_settlements`. FBB
reads that view when `PAYMENT_SOURCE=apdp` is set. APDP is an opt-in
integration mode. **Localhost and the Render GM preview both use
`PAYMENT_SOURCE=simulated`** so they return the same deterministic
`payment_simulation.csv` records, totals, dealer names, and exception
flags. A dedicated APDP environment can enable the Postgres path without
changing the preview contract.

The APDP fixture generator now samples from the FBB dealer roster
(`data/samples/fbb_comm_dev_act_<period>.csv`) rather than 5 hardcoded
synthetic codes, so the same dealer IDs appear on both sides of the
reconciliation. Without that patch, the same partner could never
appear in both commission (FBB) and settlement (APDP) data, and the
statement + audit modules had nothing to join.

For the Render deploy specifically, APDP data is packaged as a
`pg_dump` at `infra/postgres/apdp_seed.sql` (~23 MB, ~23k transaction
rows across two periods) that the FBB backend applies on startup via
its lifespan hook — idempotent (COUNT-and-skip on subsequent boots),
non-fatal (a seed failure logs and lets the app boot with an empty
Payment tab rather than a 500).

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
- **TanStack Query 5** — bounded page cache, in-flight request deduplication,
  cancellation signals, retry policy, and short-lived reuse on tab returns.
- **react-markdown** + **remark-gfm** — render the agent's markdown answers.

No TypeScript, no global state-management library (React context + focused
hooks are enough at this size), no test runner on the frontend yet. Large
collection state is deliberately bounded by the API rather than stored as a
complete browser-side dataset.

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
│   ├── dealer_statement.py  Per-period Finance/RA internal statement composer.
│   │                        Joins commission + ORSC + payment (respects
│   │                        PAYMENT_SOURCE) + linked audit trails into one dict —
│   │                        powers GET /dealers/{id}/statement.
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
│   ├── base.py             Generic AuditModule + registry — new audit domains plug
│                            in with one file + one register(...) call.
│   ├── payment_data.py     Shared payment lookup / adjacency / coverage helpers
│                            (extracted from zero_commission so multiple modules
│                            can consume without a leaky import chain).
│   ├── product_aliases.py  Known SKU-alias groups (Hynex / Hynex_1). One source
│                            of truth for both zero_commission and inventory_mismatch.
│   ├── zero_commission_audit.py     "Was partner X paid for zero-comm records?"
│                            6-step chain, PAID / NOT_PAID / INSUFFICIENT_DATA.
│   ├── inventory_mismatch_audit.py  "Do activations exceed invoiced purchases?"
│                            Per (dealer, product) — composite partner_code.
│                            RECONCILED / EXCESS_ACTIVATION / INSUFFICIENT_DATA.
│   ├── payment_reconciliation_audit.py  "Was partner X paid the correct amount?"
│                            Broader net than zero_commission — every partner with
│                            activation activity. PAID_IN_FULL / DISPUTED_ROUNDING /
│                            UNDERPAID / OVERPAID / INSUFFICIENT_DATA.
│   └── eligibility_window_audit.py  "Are zero-comm records genuinely outside the
│                            6-month invoice→activation window?" Per-partner
│                            rollup, per-IMEI evidence in step details.
│                            POLICY_MET / POLICY_VIOLATED / MIXED_ATTRIBUTION.
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
│   ├── useDebouncedValue.js       Debounces server-side table search.
│   └── useLazyDealerVerification.js  Fetches/caches evidence only for rows opened.
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

### Flow B — a bounded data panel (e.g. Payment Intelligence)
```
Browser panel → api/client.js GET /payments?mon_period=YYYYMM&limit=50&offset=0
  → routes.py validates bounded pagination/filter/sort parameters
  → db/connection.execute_query("get_payment_summary", ...)
    → if PAYMENT_SOURCE=simulated: pandas over payment_simulation.csv
    → if PAYMENT_SOURCE=apdp:      db/apdp.py reads normalized.partner_settlements
  ← {items (max 100), pagination, whole-filter-set summary} → panel table
```
This is a plain data endpoint — no LLM involved. Inventory follows the same
contract at `/inventory/comparison-page`. Search is debounced and stale HTTP
requests are aborted. Payment Exceptions and All Payments share the single
`/payments` collection with a status filter, so the APDP settlement dataset is
not fetched twice. Only the active Payment sub-tab is mounted.

Expandable Verify rows use
`GET /dealers/{dealer_id}/verification?mon_period=YYYYMM`. The compact response
is fetched only when the row is first opened and cached by dealer-period; tab
mounting no longer downloads verification evidence for every dealer.

**Current storage-engine boundary:** sample mode still has to aggregate the
period CSV in-process before applying the bounded page, and the APDP summary
adapter currently reads the period reconciliation rows before slicing. The
wire contract is already bounded, so these internals can move to native
Presto/Postgres page/count/aggregate queries without changing the frontend.
Live Presto remains unimplemented; do not claim database-level page efficiency
until that path is wired and measured.

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

### Flow D — APDP ingestion, production path (Kafka → Flink → Postgres)
```
Dealer CSV drop → ingestion/pollers/telecom_batch.py → Kafka raw topic
  → flink_jobs/normalizer (Flink) → canonical event → Kafka normalized topic
    → services/postgres_sink → Postgres normalized.transactions
      → migrate_v1_3_0.sql's partner_settlements view
        → FBB db/apdp.py reads it when PAYMENT_SOURCE=apdp
```
**Status:** the normaliser logic is complete + tested, but the Flink
Docker build is broken (`apache-flink==1.18.1` pip timeout) and the
Kafka→Postgres sink was never wired. This is the eventual production
path; not what runs today.

### Flow D′ — APDP demo path (bypass Kafka + Flink)
```
apdp/tools/generate_telecom_fixtures.py         (samples FBB dealer IDs)
  → dealer_sales.csv + commission_statements.csv + settlement_records.csv
    → apdp/tools/ingest_fixtures_to_postgres.py (uses normalizer_core directly)
      → Postgres normalized.transactions
        → normalized.partner_settlements view
          → FBB db/apdp.py reads it when PAYMENT_SOURCE=apdp
```
This is what actually runs in the demo. Same normaliser code as Flow D
(pure-Python `normalizer_core.py` is the shared brain), just skipping
the streaming plumbing. On Render, the seeded Postgres state is
packaged as `infra/postgres/apdp_seed.sql` and applied on backend boot
by `main.py`'s lifespan hook — see the "APDP seed loading" abstraction
in §5.

### Flow E — a Dealer Statement (per-period, Finance-internal)
```
Statement button in Payment Intelligence dealer row
  → api/client.js GET /dealers/{dealer_id}/statement?mon_period=YYYYMM
    → routes.py → db/dealer_statement.compose_dealer_statement()
      → execute_query("get_dealer_summary", ...)         (commission side)
      → execute_query("get_orsc_summary", ...)           (informational)
      → payment_data.payment_lookup(period, source)      (settlement side,
                                                          respects PAYMENT_SOURCE)
      → audit_store.get_partner_trail(...) per module    (linked evidence)
    ← DealerStatementResponse (Position headline + all four sections)
← DealerStatementModal renders. Copy-as-markdown / download-as-.md.
```
This is a formatter, not a new data source — every underlying number
comes from an existing query or audit trail. The Position headline
(PAID_IN_FULL / UNDERPAID / OVERPAID) is computed from the same
tolerance rules as the payment_reconciliation audit module, so the
statement and the audit trail never contradict each other on the same
(dealer, period).

### Flow F — Current Position card on Overview
```
Overview panel → api/client.js GET /payments/summary?mon_period=…
  → returns PaymentCoverageResponse with owed/paid/unpaid/coverage
    + disputed/partial/pending counts + data_source ("APDP" | "SIMULATED")
← CurrentPositionBand renders 4 tiles + a Live·APDP or Simulated badge.
```
Same endpoint that powers Payment Intelligence's coverage card, wired
into a compact 4-tile summary on the landing page. The Exceptions tile
is clickable → deep-links into the Payment tab.

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

**Bounded intelligence collections (`PaginationMeta` + page response models).**
Inventory and Payment never return an unbounded array to their main tables.
The server owns search, filters, deterministic sorting, total counts, and
whole-filter-set aggregates; the browser renders at most 100 records and uses
shared pagination controls. *Why:* virtualization alone reduces DOM work but
does not reduce payload, JSON parsing, or browser memory. The bounded wire
contract is the stable seam that lets the future data engine evolve safely.

**On-demand verification (`useLazyDealerVerification`).** Expandable evidence
is keyed and cached by `(period, dealer_id)`, with concurrent requests
deduplicated. *Why:* verification is a detail workflow, not a prerequisite for
showing a table page.

**TanStack Query client (`frontend/src/main.jsx`).** Collection pages are keyed
by period + pagination + search + filters, stay fresh for 60 seconds, and are
garbage-collected after five minutes. This is intentionally a browser cache,
not a source of truth; the backend remains authoritative.

**HTTP performance observability (`backend/main.py`).** Every response includes
a `Server-Timing` duration and emits a payload-free structured timing log. The
middleware intentionally logs no SQL or financial record contents.

**Optional APDP seed loading (`backend/main.py::_seed_apdp_if_empty` +
`infra/postgres/apdp_seed.sql`).** On backend startup, when
`PAYMENT_SOURCE=apdp` and `normalized.transactions` is empty (or the
table is missing entirely), the FBB backend applies the packaged seed
via psycopg2. Idempotent (COUNT-and-skip on subsequent boots), non-fatal
(a failure logs and lets the app boot — Payment tab shows an empty
state with the Live·APDP badge rather than a 500). *Why:* Render's
managed Postgres has no way to inject fixture data at provision time;
this hook is how the demo gets ~23k transaction rows into the DB on
first boot without an operator running `psql` by hand. This path is disabled
in the localhost-aligned Render preview. An APDP-enabled environment's first boot pays
~30-60s for the load; every boot after is ~50ms.

**Dealer-statement composer (`backend/db/dealer_statement.py`).** A
formatter, not a new data source. Reads commission-side (`get_dealer_summary`)
+ ORSC + payment-side (`payment_data.payment_lookup` — respects
`PAYMENT_SOURCE`) + linked audit trails (`audit_store.get_partner_trail`
per registered module) and shapes them into one per-period statement
dict. The Position headline (PAID_IN_FULL / UNDERPAID / OVERPAID) uses
the same tolerance rules as `payment_reconciliation_audit`, so a
dealer's Statement and their audit trail never contradict each other
on the same (dealer, period).

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
- **Naming conventions — dealer identifier.** The FBB source data uses one word
  for "dealer" and the platform uses another; keeping them separate is deliberate,
  not sloppy. The rule is layer-by-layer:

  | Layer | Column / field | Why |
  |---|---|---|
  | **Raw SQL / CSV** (`fbb_comm_dev_act`, `fbb_comm_orsc`, `payment_simulation.csv`, `usp_dimension`) | `distributor_code` / `distributor_name` | Matches the Presto/Hive schema. Cannot be changed — we don't own the source system. |
  | **Query-layer INPUT parameters** (`execute_query("get_dealer_summary", {"distributor_code": ...})`) | `distributor_code` | The parameter maps to the raw column being filtered on. Keeping the name aligned makes the SQL trivial to read. |
  | **Agent tool INPUT parameters** (`get_dealer_summary`, `get_zero_commission_records`, etc.) | `distributor_code` | Documented in CLAUDE.md and grounded into the KB. Renaming would invalidate the model's tool schema. |
  | **API response fields** (`GET /dealers`, `GET /payments/summary`, everything the frontend consumes) | `dealer_id` / `dealer_name` | User-facing vocabulary — Finance/RA talk about "dealers", not "distributors". Uniform across every endpoint. |
  | **Audit-trail subject** (`audit.verification_trail.partner_code`) | `partner_code` / `partner_name` | Generic — supports composite keys like `"{dealer}:{product}"` for the `inventory_mismatch` module. |

  **How to remember this in code.**
  - If you're writing SQL or reading from a raw DataFrame → `distributor_code`.
  - If you're building an API response dict → `dealer_id` / `dealer_name`. Alias at the return boundary (`df.rename(columns={"distributor_code": "dealer_id"})`).
  - If you're calling a tool or endpoint that takes a dealer parameter → `distributor_code` (input side keeps the SQL name).
  - If you're touching the audit layer → `partner_code`.

  The most common bug this convention prevents: a frontend filter reading `row.distributor_code` from what is now a `dealer_id` payload, silently returning zero matches. The Payment tab search shipped with exactly this bug — fixed by standardising every handler to alias at the return boundary. See [PROGRESS.md](PROGRESS.md) for the retro.
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
- **APDP demo path bypasses Kafka + Flink.** Production would ingest via
  Kafka topics → Flink normaliser → Postgres sink. Today the Flink Docker
  build fails on the `apache-flink==1.18.1` pip timeout and the Kafka→Postgres
  sink was never wired (see `apdp/CLAUDE.md`). We work around it: fixture
  CSVs → `apdp/tools/ingest_fixtures_to_postgres.py` runs the same
  `normalizer_core.py` code directly + INSERTs via psycopg2. The
  view (`normalized.partner_settlements`) and everything downstream is
  identical to the eventual live path — the shortcut is only at ingestion.
- **APDP + audit share one Postgres.** Locally and on Render, the FBB
  `audit` schema and the APDP `raw` + `normalized` schemas live in the
  same managed Postgres (`fbb-audit-pg`). One connection, one bill, one
  place to reason about. Production would put APDP behind its own DB
  and network boundary; the demo doesn't need that separation.
- **APDP data on Render is seeded from `infra/postgres/apdp_seed.sql`.**
  ~23 MB SQL file baked into the Docker image, applied on backend
  startup via `main.py`'s lifespan hook when
  `PAYMENT_SOURCE=apdp` AND `normalized.transactions` is empty.
  Idempotent — skips instantly on subsequent boots.
- **Fixture-generator dealer roster** in `apdp/tools/generate_telecom_fixtures.py`
  loads dealer IDs from `data/samples/fbb_comm_dev_act_<period>.csv` so
  the same partner appears on both sides of the reconciliation. Falls
  back to a legacy 5-dealer hardcoded list if the FBB CSVs aren't
  reachable (isolated APDP checkouts, testing).
- **Audit trail confidence on the `zero_commission` module reads LOW
  everywhere on sample data.** This is the module being honest about
  ambiguous data: sample USP codes don't overlap activation codes
  (trips step 2), simulated payments carry adjacent-period partials
  (trips step 5). Use `payment_reconciliation` for the broader signal
  — on APDP data it produces a rich UNDERPAID / OVERPAID /
  DISPUTED_ROUNDING / PAID_IN_FULL spread.
- **`ensure_schema()` self-heal.** `audit_store.py` runs idempotent
  ALTERs on first write to add the `module` column and rename the
  legacy `zero_commission_trail` table to `verification_trail` on
  older audit DBs. Intentional convenience so a pre-existing DB
  doesn't need an operator migration.
- **No auth.** Any caller can hit any endpoint and query any dealer.
  Fine for the pilot; a real deployment needs authn/authz (flagged in
  `docs/PRODUCTION_READINESS_LEARNING_PLAN.md`). The GM preview is
  gated by HTTP Basic Auth at the FastAPI layer — not a real user
  system.
- **No CI linter; one known-flaky test.**
  `test_inventory_agent.py::test_kb_inventory_rules_grounded` is a
  live-LLM test that occasionally emits "fraud" in a KB-forbidden
  negation. GitHub Actions runs the non-eval suite only.
- **`uv.lock` vs `requirements.txt`.** Both exist at the root/backend.
  The pinned `backend/requirements.txt` is the source of truth for
  installs; `uv.lock` is not currently the managed lockfile.
- **Two separate docker-compose files.** Root `docker-compose.yml` is
  *only* the FBB audit Postgres + backup. APDP's full stack is
  `apdp/docker-compose.yml`. They are independent; don't expect one
  to bring up the other. Because the demo bypasses Kafka/Flink, you
  only need the root compose to run locally.

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

# 6. (Optional) APDP live-data path — generate + load fixtures into the
#     same Postgres from step 2, then flip PAYMENT_SOURCE=apdp on the backend.
python apdp/tools/generate_telecom_fixtures.py --period 202602 --out /tmp/apdp-fixtures
python apdp/tools/generate_telecom_fixtures.py --period 202603 --out /tmp/apdp-fixtures
PGPASSWORD=fbb_audit_pass psql -h localhost -p 5544 -U fbb_audit -d fbb_audit \
  -f apdp/infra/postgres/init.sql -f apdp/migrate_v1_3_0.sql       # apply APDP schemas
.venv/bin/python apdp/tools/ingest_fixtures_to_postgres.py --fixtures /tmp/apdp-fixtures --period 202602
.venv/bin/python apdp/tools/ingest_fixtures_to_postgres.py --fixtures /tmp/apdp-fixtures --period 202603
# Now re-run step 3 with PAYMENT_SOURCE=apdp APDP_PG_HOST=localhost APDP_PG_PORT=5544
#   APDP_PG_DB=fbb_audit APDP_PG_USER=fbb_audit APDP_PG_PASSWORD=fbb_audit_pass
```

The app runs fully on sample data without Docker or Presto — only the Audit
Trails tab and `PAYMENT_SOURCE=apdp` need Postgres. Step 6 is what the Render
deploy does automatically via the packaged `infra/postgres/apdp_seed.sql`. APDP
has its own setup; see `apdp/README.md` and `apdp/CLAUDE.md`.
