# fbb-trade-intel

FBB Trade Partner Revenue Intelligence Platform — a finance-facing
chat + dashboard interface that explains, validates, and investigates
Fixed Broadband trade partner commissions (Device Activation and ORSC),
activation volumes, inventory mismatches, and partner payments.

## Stack

- **Backend:** FastAPI + Anthropic Claude (tool use)
- **Data:** Presto (live) or pandas/CSV (sample mode)
- **Frontend:** React + Vite + Tailwind

## Current capabilities

The platform ships with five integrated intelligence views, all backed
by real query and assurance services:

| Phase | View | What it does |
|-------|------|--------------|
| 1 | **Commission Intelligence** | Chat agent (Claude tool-use) + ranked dealer summary sidebar. Answers the four MVP question types: monthly summaries, month-on-month variance, zero-commission classification, ORSC summaries. |
| 2 | **Activation Intelligence** | Period selector with three tabs — dealer activation summary, period-to-period variance, and flagged exceptions. |
| 2 | **Assurance Status** | Aggregated PASS / FLAG status across all four assurance modules (commission, activation, inventory, payment) with severity counts. |
| 3 | **Inventory Intelligence** | Dealer × product activation-vs-purchase comparison with `CONFIRMED_MISMATCH` and `NO_INVOICE_RECORD` finding types. |
| 4 | **Payment Intelligence** | Payment coverage card + summary, exceptions, and variance tabs. *(Simulated data — clearly labelled in the UI.)* |

Backend layout:

```
backend/
  agent/         Claude conversation loop, tool definitions, prompts
  api/           FastAPI routes + Pydantic schemas (9 endpoints)
  assurance/     Four assurance services + registry
  db/            Connection, parameterised queries, triage, composite views
  knowledge_base/ fbb_commission_kb.md — injected into the system prompt
  data/samples/  CSV fixtures for USE_SAMPLE_DATA=true mode
  tests/         pytest suite covering queries, agent, API, assurance
```

Frontend layout:

```
frontend/src/
  App.jsx                  Top-level view switcher
  api/client.js            Axios wrapper for all 9 backend endpoints
  hooks/useChat.js         Chat state + message threading
  components/
    ChatInterface.jsx, MessageBubble.jsx, DealerSummaryTable.jsx, VarianceCard.jsx
    activation/   ActivationIntelligencePanel + Summary / Variance / Exceptions tables
    assurance/    AssuranceStatusPanel (status cards across all four modules)
    inventory/    InventoryIntelligencePanel + ComparisonTable
    payment/      PaymentIntelligencePanel + Coverage / Summary / Exceptions tables
```

## Quick start

1. Copy `.env.example` to `.env` and fill in values (or use the sample-data shortcut below).
2. Set `USE_SAMPLE_DATA=true` to run the full agent loop against `data/samples/` CSVs — no Presto required.
3. Backend: `uvicorn backend.main:app --reload` (defaults to `http://localhost:8000`).
4. Frontend: `cd frontend && npm install && npm run dev` (defaults to `http://localhost:5173`).
5. Run tests: `pytest backend/tests`.

See `CLAUDE.md` for the architecture rules, SQL boundaries, tool definitions,
and build order.

## Security note

`.env` is git-ignored. Never commit a real `ANTHROPIC_API_KEY` or Presto
credentials. If a key is accidentally committed, rotate it immediately
in the Anthropic console.
