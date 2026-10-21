# Dealer Financial Health — synthetic demonstration

## Objective and authorization

MTN Finance and Operations can review synthetic whole-business balance sheet, income
statement, cash flow statement and six basic KPIs to understand the proposed
funding-review capability. The user authorized implementation on 2026-09-16;
all data is synthetic. This execution spec supersedes the planning-only boundary
of `.scratch/dealer-financial-health/map.md`. No further planning approval is
needed for the demo defaults below.

## Demo defaults

- Twenty existing sample dealer identities from `data/samples/financial_health_dealers.json`. These exact codes and names also occur in the commission workspace. Financial figures and assigned scenarios remain entirely fictional. Scenarios:
  cash-generating operations, profitable but working-capital constrained,
  operating losses/debt pressure, and a missing repayment schedule.
- One whole business per dealer, including non-MTN activity; no outlet drill-down.
- Monthly January–June 2026, current versus previous month. Balance sheets are
  month-end snapshots; income and cash flow are monthly movements, not YTD.
  The app selector exposes all six months. January has no prior-month report.
- Prepared synthetic accounting records, simulated payment activity and a
  synthetic debt schedule. No uploads, real accounts, UDP/UDDM or APDP connection.
- Deterministic figures reconcile: assets = liabilities + equity; profit carries
  into retained earnings; cash movement links consecutive balance sheets.
- Income statement: sales and commission income, cost of sales, gross profit,
  operating expenses, depreciation, operating profit, interest, tax, net profit.
- Balance sheet: cash, receivables, inventory, net fixed assets, payables,
  current debt, long-term debt, contributed capital, retained earnings and totals.
- Cash flow: indirect operating cash flow, investing (capital expenditure),
  financing (borrowing and principal paid), opening and closing cash. Interest
  and tax are operating cash flows in this demo; no dividends or owner movements.
- KPIs: gross/net margin, operating cash flow, current ratio, total-liabilities
  to equity, EBITDA-based DSCR. DSCR uses scheduled principal plus interest in
  the same month. Missing schedule => unavailable, not zero. Zero denominators
  and non-positive equity have explicit reasons, never misleading multiples.
- No lending thresholds, fundability ranking, credit score, or recommended amount.
  Observations explain statement facts and evidence limitations deterministically.

## Capability order and implementation

1. Financial records and read API: deterministic Python demo model with explicit
   provenance, accounting tests, bounded list and exact dealer-period detail.
2. Finance workspace: React + existing TanStack Query and Tailwind; navigation,
   dealer search/sort, statement views, six KPIs, evidence and CSV report.
3. Verification: backend regression suite, frontend build, browser journeys and
   responsive checks. No new dependencies or database schema changes.

All financial logic lives in the backend demo module; no SQL is introduced.
Existing payment reads and commissions retain their behavior. Atlas reads the same financial service through two direct, read-only tools.
The synthetic endpoints stay synthetic regardless of the application's data mode.

## API contract

- `GET /financial-health?mon_period=YYYYMM&search=&sort_by=dealer_name&direction=asc&limit=25&offset=0`:
  bounded summaries, matching total, pagination, supported demo periods and source.
  Whitelisted sort keys: dealer_name, revenue, net_profit. Maximum limit 100.
- `GET /financial-health/{dealer_id}?mon_period=YYYYMM`: statements, previous-month
  comparisons, KPI definitions/inputs/status, observations, source evidence.
- Unknown month: empty collection; unknown dealer-period: 404. Invalid periods,
  sorts or pagination: 422. No write endpoints. No reads from production services.

## Design contract

Extend the existing MTN yellow/neutral workspace shell and shared period selector.
Use a compact dealer table, readable accounting statements with aligned monetary
columns, and six compact metrics with expandable calculation evidence. Synthetic
provenance is visible on list, detail, and export. Report dates are source dates,
not a fabricated live-refresh timestamp. Source details distinguish modeled feed
records from prepared monthly records. Support loading, retry, no matches,
unsupported period and unavailable ratios. All actions keyboard accessible;
tables scroll locally at narrow widths with no page overflow. Returning to the
dealer list restores focus. Navigation supports the existing `?view=` history.

## Acceptance and commands

- All three statements and six KPIs are reachable for every supported dealer/month.
- Statement identities reconcile over every month; tests independently verify
  headline amounts, ratio edge cases, missing schedules, isolation and API bounds.
- Switching dealer/period never shows another account's stale result as current.
- CSV includes all statement rows and KPIs, dealer, month, synthetic label, prior
  values and evidence; no live claim. Export is from the loaded exact report.
- `USE_SAMPLE_DATA=true PAYMENT_SOURCE=simulated .venv/bin/python -m pytest -q`
- `cd frontend && npm run build`
- Browser: list/detail, all statement views, formulas, export, period changes,
  missing-schedule example, no matches/error recovery, 320/768/1024/1440px.

## Later pilot work

Validate real source coverage, Finance's metric definitions and lending policies,
identify the reported internal upload platform, and agree consent/access and
reporting cadence. These do not block the synthetic demonstration.

## Implemented and verified — 2026-09-16

- Model: `backend/db/financial_health.py`; read API:
  `backend/api/financial_health_routes.py`; workspace and report export:
  `frontend/src/components/financial/`. Mounted as `?view=financial-health`.
- Backend suite: 260 passed, 28 skipped. New accounting/API cases: 12 passed.
  Frontend report tests: 2 new passed; 3 existing audit-report tests passed.
  Production build passed with the existing bundle-size warning; no dependencies
  were added. Existing unrelated work was preserved, with no commit/deployment.
- Browser verified dealer selection, all three statement views, KPI inputs,
  missing schedule, negative equity, profit-versus-cash explanation, source labels,
  search/no matches/recovery, sorting, period reset and keyboard operation.
- List failure/retry verified by stopping and restarting the local API; an error
  did not become an empty report. Local sample API and Vite preview restored.
- No page/main horizontal overflow at 320/768/1024/1440px. Accounting tables use
  local horizontal scrolling on narrow screens. Return restores dealer-row focus.
- Browser-downloaded CSV checked: 55 rows covering all statements, six KPIs,
  source evidence and assumptions; synthetic provenance retained on every row.

Demo limitations are deliberate: prepared month-end records, 20 shared sample dealer identities, no real-time ingestion, live source integration or funding decisions.


## Shared dealer cohort and Atlas — 2026-10-01

User-authorized extension: Finance and Operations can browse 20 existing sample
dealers and ask Atlas about their statements or compare the cohort. The frozen
cohort samples evenly spaced March activation-volume ranks among codes present
in all six months. Selection volume does not determine financial condition.
Names are not legal-entity identifiers; each scenario stays attached to one
exact dealer code and does not imply consolidation of similarly named accounts.
The modeled scope is whole-business for demonstration only, not verified scope.

Four accounting scenarios recur at five scales, scaling opening balances and
all monetary movements together. Financial Health is always synthetic, including
when the rest of the application is configured for live data. Commission income
is independently modeled and does not claim to equal recorded MTN commissions.
No data feeds, financial uploads, new SQL, or production writes are introduced.

- `get_financial_health_report(mon_period, distributor_code)` returns the exact
  workspace report, or an explicit unavailable result for unsupported accounts
  or months. It includes source, assumptions, prior month, and evidence.
- `get_financial_health_summary(mon_period, search?, sort_by?, direction?, limit?,
  offset?)` shares the bounded workspace collection (maximum 100), including
  six KPIs with inputs, statuses, and prior values for the returned page.
- Atlas is available at cohort and dealer level in Financial Health, loaded on
  demand through the existing assistant. Every request carries the exact dealer
  and period, and conversation threads are isolated by workspace/dealer/month.
- Explanations are grounded in the returned statements and the Financial Health
  KB section. Missing schedules, missing reports and invalid ratios retain their
  explicit statuses. No credit scores, lending thresholds or recommendations.

Acceptance: all 120 dealer-month reports reconcile; the frozen identities match
existing fixtures every month; API and Atlas reports agree exactly; comparisons
are bounded; follow-ups and dealer/month switches preserve correct context;
provenance is visible in the workspace, tool evidence and exported report.


Verification of this extension: backend full suite **393 passed, 28 skipped**;
frontend unit tests **5 passed**; production build passed. Isolated Chrome
verified the actual local workspace/API with only AI replies mocked: all three
statements, CSV export, cohort and dealer conversations, plain visible questions,
context on follow-ups, dealer/month isolation, missing evidence, and narrow
layout. Standards and Spec reviews reported no findings. No live model-quality
evaluation was run. The JavaScript frontend has no configured typecheck script;
Vite compilation and the runtime browser journeys provide frontend validation.

Browser check (with local sample API and Vite running):
`PLAYWRIGHT_MODULE=/path/to/playwright/index.mjs node frontend/tests/financial-health.mjs`.
