# FBB Trade Partner Intelligence Platform
## Codex Instructions

> See ARCHITECTURE.md for codebase structure and design decisions (onboarding
> reference). See PROGRESS.md for current status and what's next.

### Mission
Build a finance intelligence platform that explains, validates,
and investigates FBB trade partner commissions — so Finance and
Revenue Assurance can clearly show each dealer what MTN owes them,
explain the variance between the dealer's expected figure and
MTN's calculated figure, and make commission dispute resolution
a fast and evidence-based process.

### MVP Scope
1. Activation commission explanation and validation
2. ORSC revenue explanation and validation
3. Dealer-level variance investigation
4. Zero-commission root cause classification

### Out of Scope (MVP)
- Commission recalculation (platform validates existing
  calculations, does not replace fbb_commission.py)
- Partner self-service / IMEI-level dealer portal
- MoMo, VTU, Bonus programs
- OCR, Contract extraction
- Multi-agent systems
- Notifications and alerts
- Write-back to any production table

### Architecture
```
Data Layer (Presto — development schema, read-only)
        ↓
Query Tool Layer (4 parameterized tools, SELECT only)
        ↓
Knowledge Base (fbb_commission_kb.md — loaded into system prompt)
        ↓
Finance Agent (Codex Codex-sonnet-4-20250514 with tool use)
        ↓
Finance API (FastAPI — POST /chat endpoint)
        ↓
Finance UI (React + Tailwind — chat + dealer summary table)
```

### Primary Users
- Finance (dealer aggregate view, monthly summaries)
- Revenue Assurance (anomaly investigation)
- FBB Operations (partner performance overview)

### Success Criteria
Agent correctly answers these four question types:
1. "Summarise dealer commissions for [month]"
   → Returns ranked dealer table with totals
2. "Why did [dealer]'s commission change vs last month?"
   → Explains delta by denomination using KB root causes
3. "Which dealers have zero-commission records and why?"
   → Classifies each by one of four documented failure modes
4. "What is the ORSC summary for [month]?"
   → Returns dealer ORSC totals with zero-amount flags

---

### Project Structure Rules

**db/queries.py is the single source of truth for all SQL.**
No SQL anywhere else in the codebase. Ever.

**agent.py owns the Codex conversation loop only.**
It does not know about SQL or Presto.

**tool_executor.py owns the translation layer only.**
It receives a tool call from Codex and routes to queries.py.
It does not know about Codex's API format.

**prompts.py builds the system prompt.**
It reads fbb_commission_kb.md at startup and injects it in full.
It does not contain hardcoded business rules — those live in the KB.

---

### The Four Agent Tools

**Tool 1: get_dealer_summary**
- Input: mon_period (string, YYYYMM), distributor_code
  (string, optional) — input parameter naming follows the raw
  SQL column (see ARCHITECTURE.md "Naming conventions")
- Returns: dealer_id, dealer_name, account_profile_class,
  total_activations, total_commission_ngn,
  zero_commission_count, commission_by_denomination
- SQL target: development.fbb_comm_dev_act
- Answers: "What do we owe each partner this month?"

**Tool 2: get_zero_commission_records**
- Input: mon_period (string, YYYYMM),
  distributor_code (string)
- Returns: imei, product_name, product_code,
  invoice_date, first_activation_date,
  unit_selling_price, commission_rate
- SQL target: development.fbb_comm_dev_act
  WHERE commission_rate = 0
- Answers: "Why is Dealer X's commission lower than expected?"
- Note: Codex classifies root cause from KB knowledge.
  SQL returns raw records only.

**Tool 3: get_month_on_month_variance**
- Input: distributor_code (string),
  current_period (string, YYYYMM),
  prior_period (string, YYYYMM)
- Returns: period, product_denomination,
  activation_count, total_commission_ngn,
  delta_ngn, delta_pct
- SQL target: development.fbb_comm_dev_act
  grouped across two periods
- Answers: "Why has Dealer X's commission changed?"

**Tool 4: get_orsc_summary**
- Input: mon_period (string, YYYYMM),
  distributor_code (string, optional)
- Returns: dealer_id, dealer_name, account_profile_class,
  device_count, total_subscription_amount_ngn,
  zero_amount_count
- SQL target: development.fbb_comm_orsc
- Answers: "Which dealers are earning ORSC and how much?"

---

### SQL Rules — Non-Negotiable

- All SQL in db/queries.py only — nowhere else
- Parameterized queries only — no string interpolation in SQL
- SELECT only — no INSERT, UPDATE, DELETE, DROP, CREATE
- Always filter by mon_period — never full table scans
- Read from development schema only:
  - development.fbb_comm_dev_act
  - development.fbb_comm_orsc
  - development.fbb_comm_inv_sales
  - development.usp_dimension
- Never query dataops_prod.* or flare_8.* directly

---

### Knowledge Base Rules

- fbb_commission_kb.md is loaded once at startup in prompts.py
- It is passed whole into every system prompt — do not chunk
- Codex must use KB knowledge to explain query results
- Codex must never invent rules not documented in the KB
- When explaining zero-commission records, Codex must use
  only these four root causes from the KB:
  1. USP snapshot miss
  2. Outside 6-month eligibility window
  3. NULL account_profile_class
  4. Known denomination split (Hynex/Hynex_1)

---

### Agent Behaviour Rules

1. Always state which tool was called and for which period
2. Lead response with the headline number
3. Explain variances using KB root causes only
4. Never speculate beyond what data and KB support
5. Format all monetary amounts as NGN X,XXX,XXX.XX
6. If a question cannot be answered from the four tools + KB,
   say so explicitly and state what additional data is needed
7. Never generate or execute dynamic SQL
8. Never expose raw SQL to the user in responses

---

### Local Development Mode

USE_SAMPLE_DATA=true in .env switches the data layer from
live Presto to pandas reads against data/samples/ CSVs.

This allows full agent loop testing without Presto access.

All four tools must work correctly in sample data mode.
Tests must pass in sample data mode with no Presto connection.

---

### Environment Variables

ANTHROPIC_API_KEY=
PRESTO_HOST=
PRESTO_PORT=8080
PRESTO_USER=
PRESTO_PASSWORD=
PRESTO_CATALOG=hive
PRESTO_SCHEMA=development
USE_SAMPLE_DATA=true
CORS_ORIGINS=http://localhost:5173

---

### Build Order — Follow This Sequence

Do not skip ahead. Complete and verify each step before
moving to the next.

1. config.py + .env.example
2. db/connection.py + db/queries.py
3. tests/test_queries.py (must pass against sample CSVs)
4. agent/tools.py + agent/prompts.py
5. agent/tool_executor.py + agent/agent.py
6. tests/test_agent.py (must pass with mocked tools)
7. api/routes.py + api/schemas.py + main.py
8. tests/test_api.py
9. Frontend — only after all backend tests pass

---

### What Not to Build

- Do not build a vector store or embedding pipeline
- Do not build dynamic SQL generation
- Do not build any write endpoints
- Do not build partner authentication or multi-tenant isolation
- Do not build ORSC continuity monitoring
- Do not connect to UDDM platform
- Do not build notification or alerting systems
