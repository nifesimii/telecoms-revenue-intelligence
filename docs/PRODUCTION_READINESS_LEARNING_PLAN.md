# Production Readiness — What to Learn to Excel with This Platform

A prioritized learning plan for taking the FBB Trade Partner Revenue
Intelligence Platform (and its APDP foundation) from "demo I built" to
"system MTN finance can responsibly trust in production."

Framed against *this specific codebase* — not generic advice.

> **Meta-point that beats every item below:** ship this to one real MTN
> finance user within ~6 weeks. The ship → break → fix → redeploy loop
> teaches you which of these items actually matter for your users, in
> what order. Reading everything without that loop produces a
> well-studied engineer who built something nobody uses.

---

## Tier 1 — Non-negotiable to get this into finance's hands

### 0. Preserve the bounded collection contract

The MVP now has the correct browser/API boundary for large Inventory and
Payment tables: capped pages, server-owned filtering/sorting/aggregates,
on-demand verification, request deduplication, and timing visibility. Do not
regress to returning bare unbounded arrays.

When moving from MVP to the platform, finish the storage-engine side using
measurements from real data:

- Implement native parameterized Presto/Postgres page, count, and aggregate
  queries behind the existing response envelopes.
- Validate partition pruning, deterministic ordering, deep-page cost, exact
  count cost, and response-size/latency percentiles.
- Add database indexes or materialized/pre-aggregated views only after query
  plans show they are needed.
- Keep offset pagination for finance page-number workflows until deep offsets
  become a measured problem; introduce cursors endpoint-by-endpoint if needed.
- Add Redis only when multiple backend instances or repeated database load
  require a shared cache, with explicit open-period and closed-period freshness
  policies.
- Add frontend integration tests for request deduplication, stale-request
  cancellation, inactive-tab non-rendering, and URL-restorable investigation
  state.

This is production hardening, not an invitation to create a universal table
framework or cache financial data indefinitely.

### 1. LLM evals + observability as a continuous practice
The eval harness exists (`backend/tests/evals/`). What matters is *using*
it weekly, growing the golden set as regressions surface, and mining real
conversations for patterns.

- **Langfuse** or **Phoenix (Arize)** — open-source LLM observability.
  A few hours of wiring buys per-request traces, latency percentiles,
  cost per conversation, and prompt-version regression diffs.
- Anthropic *Building Effective Agents* essay.
- The practice of **trace mining** — every conversation is training data
  for the next prompt iteration.

This separates "we have an AI feature" from "we run an AI product."

### 2. Authentication + authorization + audit logging
Today anyone with the URL queries any dealer. For MTN finance this blocks
pilot outright.

- **OIDC** flow (FastAPI + `fastapi-users` or Authlib). Wire to MTN's
  AD/Okta — never roll your own.
- **Audit log** every `/chat`: user ID, question, tools called, dealers
  touched. Compliance will ask.
- Role-based scoping: Finance → aggregates, RA → IMEIs, Ops → performance.

### 3. Secrets management — move off `.env`
AWS Secrets Manager, HashiCorp Vault, or K8s sealed secrets. The Anthropic
key sitting in `.env` is a production smell.

### 4. Real Kubernetes deployment (not docker-compose)
You have Rancher/K3s locally — use it.

- Deployments, Services, Ingress, ConfigMaps/Secrets, HPA.
- **Helm** for packaging (or Kustomize).
- Resource limits + requests (LLM workloads spike memory).
- Health/readiness probes.
- MTN ops will not deploy your docker-compose. Kubernetes is the language.

### 5. Prompt caching (Anthropic feature)
Your system prompt + KB never change between turns — cache them and cut
per-`/chat` token cost by ~90%. Two header changes. Read the Anthropic
prompt-caching docs; this is the single highest ROI change available.

---

## Tier 2 — Makes you the *senior* engineer on this

### 6. SRE fundamentals
- **SLOs not SLAs** — Google SRE book ch. 3-4. Internalize error budgets.
- **Four golden signals** — latency, traffic, errors, saturation. Wire
  them into the Grafana already running in the APDP stack.
- Promote the current `Server-Timing` and structured HTTP duration logs into
  endpoint/query latency histograms, response-size dashboards, and performance
  budgets for Inventory and Payment.
- **Runbooks** — every alert needs a documented response. Start with the
  top 5: APDP Postgres down, Anthropic rate limit, Flink killed, Kafka
  lag, sink consumer stalled.

### 7. Data quality + backfills (APDP side)
- **dbt tests** — `dbt test` + custom data tests on the normalized layer.
- **Great Expectations** or **Soda Core** — schema drift, row-count alerts.
- **Backfill patterns** — reprocess months of history without
  double-counting (idempotent keys + topic replay).
- **CDC vs batch** — if source tables get updates not just inserts, you
  need Debezium.

### 8. Production Postgres
- Connection pooling (`pgbouncer`) — connection-per-request dies at load.
- Read replicas for the reconciliation view.
- Index strategy for `partner_settlements` queries.
- VACUUM/ANALYZE behaviour.

---

## Tier 3 — Career multipliers (data/AI engineering market)

### 9. Finish the Karpathy + Ed Donner LLM track
Custom evals, fine-tuning, RAG, agentic patterns — translate directly to
the portfolio and the founder thesis.

### 10. Production LLM patterns not yet in this codebase
- **Streaming responses** (`/chat` is single-shot today).
- **Tool-result caching** within a conversation.
- **Self-consistency / N-best sampling** for high-stakes answers.
- **Eval-driven prompt iteration** as a standing loop.

### 11. One adjacent specialty, deeply (12-month horizon)
Ranked by current market value:
1. **Production LLM ops** — Langfuse, evals, fine-tuning, observability.
   Hottest market right now.
2. **Streaming data architecture** — Flink, Kafka, Debezium, Iceberg.
   You're already here; go one level deeper.
3. **Cloud platform engineering** — Terraform + K8s + service mesh.
   Durable, less hot, always paying.

---

## Tier 4 — If this becomes a startup

### 12. Multi-tenancy + isolation
- Postgres row-level security or schema-per-tenant.
- Tenant ID propagation through every query and every log.
- Data-leak risk is existential for a finance product.

### 13. SOC 2 Type II
The real gate for selling to anything bigger than a fintech. **Drata** or
**Vanta** automate most of it (~$10k/yr). Start at first paying customer;
6-month minimum.

### 14. Enterprise B2B sales motion
Long cycles, RFPs, security questionnaires, procurement slower than the
build. Read: *The Mom Test*, *Predictable Revenue*.

---

## One-line recommendation
If you do one thing beyond shipping: stand up **Langfuse + auth + audit
logging** this week. Those three convert this from "demo I built" to
"system MTN finance can responsibly trust with their data." Everything
else compounds from that base.
