# Telecoms Revenue Intelligence Platform

End-to-end revenue assurance for MTN's FBB (Fixed Broadband) trade partner
network. Two layers, one repo:

```
telecoms-revenue-intelligence/
├── backend/  + frontend/         ← FBB Revenue Intelligence (the product)
│                                     finance-facing chat + dashboard,
│                                     explains commissions, surfaces leakage,
│                                     reconciles dealer activity
└── apdp/                         ← African Payment Data Platform (the spine)
                                      real-time + batch payment ingestion,
                                      normalisation, FX, Postgres sink
```

The FBB layer is what finance/RA users see. APDP is the data infrastructure
that feeds it — once approval lands to read live partner-transaction data,
APDP normalises everything into the canonical v1.3.0 shape and the FBB
Payment Intelligence view consumes it directly. Until then, FBB runs on
sample CSVs.

---

## FBB Revenue Intelligence (`backend/` + `frontend/`)

A finance-facing platform that explains, validates, and investigates Fixed
Broadband trade partner commissions (Device Activation and ORSC), activation
volumes, inventory mismatches, and partner payments.

### Stack
- **Backend:** FastAPI + Anthropic Claude (tool use), Presto (live) or pandas/CSV (sample mode)
- **Frontend:** React + Vite + Tailwind

### Five integrated views
| Phase | View | What it does |
|-------|------|--------------|
| — | **Overview** *(landing)* | Cross-module triage: posture band, dealers appearing in multiple module findings, per-finding Ask-Claude shortcuts, period-delta vs prior month, CSV export. |
| 1 | **Commission Intelligence** | Claude tool-use chat agent + ranked dealer summary sidebar. Answers monthly summaries, month-on-month variance, zero-commission root-cause classification, ORSC summaries. |
| 2 | **Activation Intelligence** | Period selector with summary, variance, and exceptions tabs. |
| 3 | **Inventory Intelligence** | Dealer × product activation-vs-purchase comparison with `CONFIRMED_MISMATCH` / `NO_INVOICE_RECORD` findings. |
| 4 | **Payment Intelligence** | Coverage card + summary, exceptions, variance tabs. *(Simulated until APDP's telecom feed is wired live — clearly labelled.)* |

### Layout
```
backend/
  agent/         Claude conversation loop, tool definitions, prompts
  api/           FastAPI routes + Pydantic schemas (9 endpoints)
  assurance/     Four assurance services + registry
  db/            Connection, parameterised queries, triage, composite views
  knowledge_base/ fbb_commission_kb.md — injected into the system prompt
  data/samples/  CSV fixtures for USE_SAMPLE_DATA=true mode
  tests/         pytest suite covering queries, agent, API, assurance

frontend/src/
  App.jsx                  Shell + global period selector + data-mode badge
  context/PeriodContext    App-wide period state
  lib/format.js            Shared NGN / period formatters
  api/client.js            Axios wrapper for the 9 backend endpoints
  hooks/useChat.js         Chat state + message threading
  components/
    ChatInterface, MessageBubble, DealerSummaryTable, VarianceCard
    activation/  Phase 2 panel + Summary / Variance / Exceptions tables
    assurance/   Overview panel (cross-module triage)
    inventory/   Phase 3 panel + ComparisonTable
    payment/     Phase 4 panel + Coverage / Summary / Exceptions tables
```

### Quick start
```bash
# 1. Copy sample env, default to sample-data mode (no Presto needed)
cp .env.example .env
echo "USE_SAMPLE_DATA=true" >> .env

# 2. Backend
uvicorn backend.main:app --reload          # http://localhost:8000

# 3. Frontend
cd frontend && npm install && npm run dev  # http://localhost:5173

# 4. Tests
pytest backend/tests
```

See [`CLAUDE.md`](CLAUDE.md) for FBB architecture rules, SQL boundaries, tool
definitions, and build order.

---

## APDP — African Payment Data Platform (`apdp/`)

The data spine. Real-time payment ingestion + normalisation, Postgres sink,
canonical schema. APDP currently ships:

| Phase | Status | What |
|-------|--------|------|
| 1 | ✅ | Ingestion for 5 PSPs (Flutterwave, Paystack, Monnify, MTN MoMo, Mono) |
| 2 | ✅ | Flink normalizer, canonical schema v1.1.0 |
| 3 | ✅ | FX enrichment (Redis-backed), schema v1.2.0 |
| 4 | ✅ | **Telecom trade partner extension (v1.3.0)** — `normalize_telecom_*` for `dealer_sale`, `commission_statement`, `settlement`. See [`apdp/flink_jobs/SCHEMA_v1.3.0.md`](apdp/flink_jobs/SCHEMA_v1.3.0.md). |
| 4 | ✅ | Synthetic telecom data generator ([`apdp/tools/generate_telecom_fixtures.py`](apdp/tools/generate_telecom_fixtures.py)) — emits correlated dealer_sales / commission_statements / settlement_records CSVs with seeded reconciliation discrepancies |
| 4 | ✅ | Postgres migration v1.3.0 + `normalized.partner_settlements` reconciliation view |
| 4 | ✅ | Kafka → Postgres sink service ([`apdp/services/postgres_sink/`](apdp/services/postgres_sink/)) — closes the pipeline loop |
| 4 | ⏳ | Telecom batch file ingestor — *next* |
| 5 | ⏳ | dbt models + CBN CTR staging |

### Stack
- Kafka KRaft + Flink 1.18 (PyFlink) + Postgres 15 + Redis + Prometheus + Grafana
- All orchestrated via `apdp/docker-compose.yml`

### How FBB consumes APDP
Once the telecom batch ingestor is live and Finance has approved partner-
transaction data sharing:

```
dealer mgmt / commission engine / Oracle AP CSV drops
    ↓  apdp/ingestion/pollers/telecom_batch.py (TODO)
raw.telecom.* (Kafka)
    ↓  apdp/flink_jobs/normalizer.py — normalize_telecom_*
normalized.transactions (Kafka)
    ↓  apdp/services/postgres_sink
Postgres: normalized.transactions + normalized.partner_settlements view
    ↓  backend/db/queries.py reads view behind PAYMENT_SOURCE=apdp flag (TODO)
FBB Payment Intelligence — [SIMULATED] banner flips off
```

### Quick start
```bash
cd apdp
docker compose up -d
docker compose ps                                  # all healthy
python flink_jobs/test_normalizer.py               # 14 cases + 170 round-trip rows
python tools/generate_telecom_fixtures.py --period 202410   # synthetic CSVs
```

See [`apdp/CLAUDE.md`](apdp/CLAUDE.md) for APDP architecture rules,
canonical schema, and pipeline conventions.

---

## Security note

`.env` files are git-ignored at both layers. Never commit real
`ANTHROPIC_API_KEY`, Presto credentials, MoMo OAuth secrets, or PSP webhook
signing keys. If a key is accidentally committed, rotate it immediately
in the relevant console.
