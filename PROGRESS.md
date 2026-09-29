# PROGRESS

Rolling status file — "pick up where I left off." Update a few bullets at the
end of each work session. Newest session on top.

---

## Session — 2026-09-29 (Live inference validation follow-up)

- Resumed from the clean committed implementation and ran three bounded provider
  requests using a synthetic June commission finding: one original buffered path
  and two current structured requests. No production data or deployment.
- Original buffered return: 59.992s and three model calls; final call used its
  full 2,048-token output budget and completeness was not established by this
  probe. Current path completed successfully in 22.179s and 21.817s, with first
  backend-streamed text at 2.033s and 1.597s, one model call each and no retries.
- Provider caching verified: first request created an 8,425-token prefix; repeat
  read all 8,425 tokens from cache. This confirms reuse, not an isolated caching
  speedup or production latency guarantee. Recorded metrics contain no prompts,
  financial text or credentials. Full results and measurement limits are in
  `docs/INFERENCE_LATENCY.md`.
- Documentation-only follow-up; existing implementation QA remains 323 backend
  passes/28 skips, 14 frontend passes, browser regressions and build passing.

---

## Session — 2026-09-29 (Explain Findings latency)

- Overview Explain Findings now carries exact dealer/month/finding/product scope
  into a deterministic evidence read and one streamed explanation generation.
  Full core KB, source provenance, synthetic-data qualifications, missing-evidence
  caveats and bounded zero-record samples are preserved. Edited questions and
  follow-ups keep the general agent loop.
- Shared inference policy disables SDK retry amplification, permits one bounded
  application retry, respects provider retry guidance and applies a 90-second
  overall deadline with explicit HTTP timeouts. Stable prefixes request provider
  prompt caching; payload-free logs record evidence/model/retry/token timings.
- Browser renders progressive text with Stop/Retry, marks partial answers
  incomplete, preserves final metadata and keeps dealer/month/product threads
  isolated through navigation and reload. Local performance entries separate
  first rendered text, network completion and rendered completion.
- Delegated implementation and review used subagents and visible Herdr workers.
  Review fixes require an actual provider completion event, validate inventory
  product identity, stop further evidence operations after cancellation, retain
  synthetic activation provenance, and separate buffered answer-readiness logs.
- Final sample-mode backend suite: 323 passed, 28 skipped. All 14 frontend Node
  tests and the production build pass (existing bundle-size
  warning remains). Isolated Chrome checks pass for streaming, scope isolation,
  cancellation, retry, reload, narrow layout and existing Payment/Commission chat.
  No standalone typecheck is configured; changed Python modules compile.
- Mocked persistent 429 comparison: 12 HTTP attempts / 65.019 seconds of intended
  waits before, 2 attempts / 1 second after. This verifies failure recovery only.
  No live-model, warm-cache or production speedup is claimed. No deployment,
  Presto access, billed model requests, dependency changes or source writes.
  Measurements, contract and remaining operational checks:
  `docs/INFERENCE_LATENCY.md`.

---

## Session — 2026-09-28 (Subscription layout consistency)

- Inspected rendered Commission, Subscriptions and Payments views in isolated
  Chrome. Subscriptions now uses a compact shared summary, seven-column dealer
  table and the same View breakdown action as Activation Commission.
- Revenue changes sit below current revenue; prior amounts and percentage
  changes remain in dealer detail. Revenue, recorded commission, settled and
  outstanding amounts retain their separate meanings and missing-evidence states.
- Consolidated subscription evidence into one expandable section, added an
  Explain figures prompt action, and made zero-revenue labels explicit.
- Fixed page overflow from the table's absolutely positioned screen-reader
  heading by containing it within the horizontal scroll region.
- Browser checks covered 320/768/1024/1440px, evidence expansion, focus return,
  prompt prefilling, empty search, filters, no comparison, stream switching,
  unavailable commission evidence and failed-refresh messaging. No document
  overflow in the verified layouts. Build and five frontend tests passed;
  full backend suite: 287 passed, 28 skipped. Existing bundle warning remains.
- Local frontend changes only; no deployment or financial calculation changes.

---

## Session — 2026-09-28 (Subscription commission demo)

- Added separate fictional recorded upstream subscription commission and
  settlement evidence linked to existing dealer/device/month records in sample
  mode. Revenue retains its existing meaning; live unsupported commission fields
  stay unavailable. Shared evidence supports the workspace and contextual chat.
- Subscription account figures, totals and exports distinguish revenue,
  commission, settled and outstanding amounts; bounded device evidence loads on
  demand. Existing activation settlement remains separately scoped.
- Corrected the KB's unsupported claim that subscription revenue equals payable
  commission. Actual rate and eligibility remain unconfirmed. Assumptions and
  the live-data path are recorded in `docs/SUBSCRIPTION_COMMISSION_DEMO.md`.
- Validation: full backend suite 287 passed, 28 skipped, including 13 new
  subscription API/tool regression tests. Frontend build and five existing Node
  tests passed; isolated browser checks passed at 320/768/1024/1440px without
  page errors or document overflow. Existing bundle-size warning remains.
- Standards and spec reviews have no unresolved findings. CSV reads remain in
  queries.py, and the internal fixture query is excluded from agent tools.
  Live Presto and billed LLM calls were not exercised. No deployment performed.

---

## Session — 2026-09-27 (Keep selected dealer across reporting periods)

- Commission, Activation and Payment investigations retain the selected dealer
  when the reporting month changes, matching existing comparison continuity.
  Period-specific workspaces still reload figures/evidence and reset comparison
  defaults. Explicit Back to accounts and dealer reselection remain available.
- Commission navigation is consumed once so a month change cannot reopen an
  earlier navigation target. Commission/Activation classifications come from
  the fresh detail response, including a current null classification.
- Verified in isolated Chrome: comparison changes, May/January reporting changes,
  fresh dealer detail requests, Back to accounts, reselection and null-class
  responses. No application runtime errors in the three-workspace check.
- Full suite: 274 backend passed, 28 existing skips; all five frontend tests
  passed; production build passed with the existing bundle-size warning. No
  standalone typecheck is configured. Standards and Spec reviews have no
  unresolved findings. No deployment.

---

## Session — 2026-09-27 (Pre-demo evidence and investigation fixes)

- Implemented the priorities in `docs/DEMO_UX_REVIEW_2026-09-27.md` using three
  visible Herdr workers, followed by fresh Standards and Spec reviews.
- Payment drafts use exact source owed/paid amounts, keep activation earnings
  separate, preserve source qualifications and require Finance review. Removed
  unsupported final decisions/turnaround promises; fixed modal labels and focus.
  APDP missing statements/settlements retain evidence qualifications; normalized
  zero amounts cannot support a closed/aligned conclusion without evidence.
- Saved Commission conclusions show confidence. Activation source labels include
  reporting/comparison synthetic provenance, including CSV exports. Coverage
  tickets request source confirmation before conditional remediation; Inventory
  assistant handoffs carry dealer/product scope with explicit exit and resets.
- Commission/Activation comparisons retain selected dealer and filters; Financial
  Health retains dealer across months and names total liabilities-to-equity.
- Audit eligibility wording is conditional. Replacement scope/outcome survives
  period/navigation remounts, duplicate runs are blocked, and collection shrink
  resets to a freshly fetched first page.
- Verification: full backend suite 274 passed, 28 existing skips; five frontend
  tests passed; production build passed (existing bundle-size warning). No
  standalone typecheck is configured; changed Python modules compile. After
  review fixes, 29 focused payment/APDP checks passed again. Existing
  regression tests were updated; new test seams were not confirmed.
- Chrome verified six workspaces, comparison/month continuity, Inventory handoff
  and scope exit, dispute composition/focus/download, and saved March evidence.
  Mocked audit responses verified pending/outcome retention and shrinking-page
  recovery without live replacement runs. Rehearsal and evidence caveats:
  `docs/DEMO_UX_REHEARSAL_2026-09-27.md`.
- Review: all Spec findings and the Standards scope violation resolved. A
  non-blocking source-field mapping duplication heuristic remains; broader
  normalization refactoring was deliberately kept outside this demo fix.
- No deployment, source fixture changes, live AI or Presto calls. Deployed build
  parity/projector rehearsal remains an environment-specific pre-demo check.

---

## Session — 2026-09-27 (Richer synthetic Inventory scenarios)

- Used two Codex agents in Herdr sibling panes for fixture generation and
  downstream provenance, followed by independent Standards and Spec reviews.
- Added a reproducible 16-comparison cohort across 13 dealers/six products:
  12 positive fictional purchase quantities and four retained missing-evidence
  controls. Existing source CSVs and all commission/payment amounts are preserved.
- Shared fixed quantities retain existing purchase semantics. June anchor cases
  cover exact matches, purchase cushions, one-unit excesses and larger excesses;
  all six months and baseline/enriched outcomes appear in the generated manifest.
- Search `Synthetic` in Inventory to explore the cohort across tabs. Labels and
  disclosures survive API, agent result compression, assurance and ticket drafts.
  Synthetic trails are inconclusive/LOW; synthetic evidence cannot establish
  carryover/aliases, and prior saved trails are not presented as scenario proof.
- June totals are now 35 observed mismatches, 377 excess units, 4,138 invoice
  gaps and 63 within-purchase combinations. Walkthrough, monthly distribution and
  regeneration: `docs/INVENTORY_DEMO_SCENARIOS.md` and `data/samples/README.md`.
- Updated the existing sample-audit assertion to distinguish the four known
  synthetic holdout trails from authentic IFS trails without weakening either
  provenance check. New test boundaries were proposed but not confirmed; no new
  scenario test files were introduced.
- Verification: focused inventory query/audit checks passed (33), composite checks
  passed (4), and generator output is byte-for-byte deterministic with unchanged
  source hashes. Final full backend suite: 274 passed, 28 existing skips; all five
  frontend tests and production build passed (existing bundle-size warning).
  No standalone typecheck is configured; Python compilation passed. Updated
  Overview expectations for three additional March findings; its export check
  now requires synthetic disclosure. Standards and Spec reviews: no unresolved
  findings after follow-up review.
- Browser checked three scenario views, month switching, detail disclosure,
  suppressed stale audit requests, ticket disclosure and 320/768/1024/1440px
  layouts. Fixed the mobile search field squeezing. No deployment.

---

## Session — 2026-09-27 (Inventory summaries and data assessment)

- Each Inventory view now shows relevant summaries: investigation excess and
  gaps; coverage combinations/distinct dealers/activations; within-purchase
  combinations/purchased units/activations. API aggregates cover the entire
  filtered result before pagination; absent purchased quantities remain null.
- Inspected January–June fixtures without changes. All three classifications
  already exist each month; 97.96–98.50% of combinations lack matched invoices.
  Distribution and proposed scenarios: `docs/INVENTORY_DATA_ASSESSMENT.md`.
  Shared March-only IFS evidence and purchase-window semantics should be addressed
  before generating monthly replenishment/carryover stories.
- Validation: 274 backend tests passed, 28 existing skips; all 5 frontend tests
  and production build passed (existing bundle-size warning). Headless Chrome
  verified tab totals, pagination, empty search/reset, reporting-period reset,
  and card layouts at 320/768/1024/1440px. No application runtime errors;
  existing missing `/favicon.ico` produces a browser console 404.
- Sample fixtures unchanged. No deployment.

---

## Session — 2026-09-20 (January–June demo coverage)

- Populated January, April, May and June 2026 using February/March dealer
  identities and recorded product commissions. Existing February/March activation,
  ORSC and payment records are preserved. New months are explicitly synthetic.
- Added 118,754 activation records, 800 ORSC records and 3,705 derived simulated
  payment rows. All six months are discovered by the existing period selector;
  June is the latest default. Shared IFS/USP evidence remains unchanged.
- Extended the separate four-business Financial Health demo through June.
  Regeneration and assumptions: `backend/data/generate_half_year_demo.py` and
  `data/samples/README.md`. Fixed stale payment-generator dealer field names.
- Six-month API/query checks validate populated streams, stable dealer identities,
  inventory availability and payment reconciliation. Standards and Spec review:
  no findings. Full backend suite: 268 passed, 28 skipped. All 5 frontend tests
  and build passed; existing bundle-size warning remains. Regeneration is
  byte-for-byte deterministic. No standalone typecheck is configured.
- Restart any running backend after updating cached fixtures. No deployment.

---

## Session — 2026-09-16 (Dealer Financial Health wayfinding)

- User subsequently authorized implementation with synthetic data throughout.
  Implemented Financial Health workspace at `?view=financial-health`, four
  fictional businesses, three reconciled statements, prior-month comparisons,
  six explainable KPIs, source evidence and complete CSV report. Spec and
  verification: `docs/DEALER_FINANCIAL_HEALTH.md`. Planning map superseded.
- Read-only synthetic API is isolated from Presto/APDP and remains explicitly
  synthetic in either data mode. Monthly fixtures cover Jan–Mar 2026; the app's
  Feb/Mar selector uses January for the February comparison. No integrations,
  lending thresholds, dealer scores, funding decisions or production writes.
- Validation: 260 backend tests passed, 28 skipped; 2 new frontend export tests
  and 3 existing report tests passed; build passed (existing bundle warning).
  Browser verified statements, metrics, search/sort, periods, download, error/retry,
  keyboard/focus and 320/768/1024/1440px overflow. No deployment or commit.
- Follow-up: claimed "Define the dealer financial statements and business
  boundary." User selected balance sheet, income statement and cash flow
  statement, then requested minimum profitability/lending KPIs. Recorded six
  proposed demo metrics with definitions, evidence requirements and no lending
  thresholds; reporting scope and detailed statement contents remain open.
- Charted `.scratch/dealer-financial-health/map.md` with five open decision
  tickets and dependency links. No tickets resolved; no application changes.
- User confirmed whole-business health for MTN Finance funding consideration,
  a synthetic demonstration to support pilot entry, and statements/explainable
  observations without dealer ranking or funding-amount recommendations.
- Recorded the user-reported internal upload platform (tentatively "UDP") as
  an unverified future data source; demo integration is excluded. Do not assume
  it is UDDM or that account feeds supply complete financial statements.
- Added the agreed dealer-financial-health term to `CONTEXT.md`. Next decision:
  "Define the dealer financial statements and business boundary."

---

## Session — 2026-09-15 (March ORSC demo coverage)

- Fixed the demo coverage mismatch: the default March period had activation
  records but ORSC was configured only for February.
- Added a reproducible, explicitly synthetic March ORSC fixture: 200 device
  records, 157 accounts, NGN 2,050,990.17 subscription revenue and 69 zero amounts.
  February remains NGN 1,964,280.90; demo change is NGN 86,709.27.
- Commission workspace source labels, account detail and export identify March
  ORSC as synthetic. No changes to live queries or commission-payable semantics.
- Generator and assumptions: `backend/data/generate_orsc_demo.py` and
  `data/samples/README.md`. Added the domain glossary in `CONTEXT.md`.
- Regression reproduced before the fix; backend suite: 248 passed, 28 skipped.
  Restarted the local sample API on port 8000 and verified March ORSC totals,
  February comparison, populated accounts and synthetic source label in-browser.
  Changes are local; no hosted deployment was performed.

---

## Session — 2026-09-14 (shared header and workspace history)

- Aligned both header rows with the existing six-workspace content gutters;
  shortened navigation labels and added bold active text with a yellow underline.
  Reporting period and data mode remain visible at phone widths, with stable
  control sizing and explicit loading, unavailable and empty period labels.
- Workspace switches now create browser history entries. Back/Forward restores
  view, linked month and contextual investigation revision; Audit remains mounted
  on ordinary navigation to preserve filters. Existing evidence return focus is
  retained. Period changes retain the existing period-scoped reset behavior.
- Verified all six workspaces at 320/768/1024/1440px with no page overflow;
  direct links, filters, period continuity, detail navigation, Audit return focus,
  history context, delayed periods and reload/Forward context restoration checked.
  Status failure/empty/live states used browser response overrides. Live saved
  Audit reads currently fail locally; no audit was run or evidence replaced.
- Validation: 246 backend tests passed, 28 skipped; 3 existing frontend report
  tests passed; production build passed with the existing chunk-size warning.
  No TypeScript check is configured. Standards/spec findings were corrected.
  New automated navigation tests remain pending test-seam confirmation; runtime
  inspection found no page exceptions or non-GET requests in the main journeys.
  No deployment. Existing unrelated workspace work was preserved.

---

## Session — 2026-09-14 (Audit Trails saved-evidence workspace)

- Implemented bounded saved-assessment API and UI: backend filters, deterministic
  sorting, full-module versus whole-filter scope, 25/50/100 rows and on-demand steps.
- Preserved exact saved trail identity for duplicate subjects, historical conclusions
  and provenance. Exposed partial-payment qualifications, HIGH-confidence Inventory
  limitations and corrected/qualified Eligibility entitlement wording.
- Added all-match formula-safe CSV and individual readable evidence reports;
  accessible evidence controls, return focus/context, friendly failure/missing states,
  explicit refresh versus replacement-run controls. No saved audit run or deployment.
- Verification: 246 backend tests passed, 28 skipped; 3 report tests passed;
  production build passed with existing bundle warning. Read-only actual-store API
  and browser journeys covered all modules, exports, paging, errors/retry, identity,
  period changes and 320/768/1024/1440px widths. Browser log: zero non-GET attempts.
- Native database projection/paging and historical retention remain deferred;
  current server shaping reuses period-wide saved-store reads. See
  `docs/AUDIT_WORKSPACE.md` for exact contracts, evidence and limits.

---

## Session — 2026-09-13 (Inventory investigation workspace)

- Inventory now separates observed excess, invoice coverage gaps and within-
  purchase comparisons from saved verification conclusions. Removed unsupported
  dealer-total commission verdicts and six-month invoice-window wording.
- Existing bounded API powers current-filter summaries, finding views, search,
  supported sorting and 25/50/100 pagination. Dealer/product identities are
  readable; column headers remain sticky inside an accessible scroll region.
- Exact dealer-product/period saved trails load only when evidence is opened.
  Period changes reset selection; returning preserves list state and focus.
  Source time, recorded confidence and carryover/completeness limits are visible.
- Coverage-ticket dialog defaults to IFS, states whole-period scope, supports
  keyboard/Escape focus return and copy recovery. Compiler wording corrected;
  purchase calculations and data contracts remain unchanged.
- Verification: 232 backend tests passed, 28 skipped; 18 focused coverage tests
  passed; frontend build passed with the existing bundle-size warning. Browser
  checks covered responsive layouts, filters/paging, saved/missing/failed evidence,
  period changes, stale refresh and retry, modal focus and ticket error recovery.
- Independent standards/spec reviews completed; sticky-header regression fixed
  and cleared. No new regression tests were authored while proposed test-boundary
  confirmation remained pending. No deployment or audits initiated.
- Scope, evidence and deferred data work: `docs/INVENTORY_WORKSPACE.md`.

---

## Session — 2026-09-13 (Activation investigation workspace)

- Activation now shares Overview/Commission hierarchy: full-period activation
  summary, readable bounded accounts, explicit comparison scope and grouped findings.
- Additive `/activations/accounts` supports max100 paging, backend filters/stable
  sorting, matching totals/export and exact detail. Legacy agent reads are unchanged.
- Account detail loads zero-commission evidence only on request; Commission
  navigation preserves exact account/comparison and list return restores focus.
- Source errors never become empty data. Failure/retry, search, comparison,
  evidence and responsive 320–1440px browser checks passed.
- Full backend suite: 232 passed, 28 skipped. Production build passed (existing
  chunk warning). Independent standards/spec navigation finding fixed and cleared.
  No new automated tests while proposed TDD boundary confirmation remains pending.
  See `docs/ACTIVATION_WORKSPACE.md` for scope and verification details.

---

## Session — 2026-09-13 (Commission investigation workspace)

- Commission Intelligence now leads with recorded commission, prior-period
  change, account counts and zero-record counts, followed by a bounded table.
- New additive `/commissions` API supports backend search, partner-class and
  zero-amount filters, stable sorting, full matching CSV export and max100 pages.
- Exact-code account detail shows denomination comparisons and bounded raw
  evidence independently of payment availability. Saved audits load on demand.
- ORSC is a separate subscription-revenue view. No source records, missing
  comparison accounts and recorded zero balances remain distinct.
- Contextual AI is account/period/comparison/stream scoped; conversations
  persist even when a response finishes after navigating away.
- Existing backend suite: 232 passed, 28 skipped; frontend build passed;
  API/browser checks and independent standards/spec reviews completed.
  New automated regression tests await confirmation of the proposed TDD seams;
  live AI generation and Presto were not tested. See `docs/COMMISSION_WORKSPACE.md`.

---

## Session — 2026-09-13 (finance Overview)

- Overview leads with outstanding, owed, settled and an explicit comparison
  against an earlier available period. Missing sources never become zero balances.
- `GET /assurance/overview` computes full-period findings and distinct dealer
  overlap before a ranked bounded queue (maximum 100). The UI displays five
  accounts per page with backend search and severity/module filters.
- `GET /assurance/overview/export` exports every finding, rejects incomplete
  assessments, and escapes formula-leading text. Legacy previews expose total
  counts and truncation. `GET /payments/position` is aggregate-only.
- Queue amounts and financial totals share one source-aware payment snapshot.
  Overview no longer fetches whole-period dealer verification collections.
- Evidence navigation preserves dealer/module context and resets the payment
  destination tab. Inactive Audit Trails releases its large table DOM. Mobile
  has a workspace selector and visible period control.
- Missing invoice evidence, findings and saved audit trails are separate;
  audit errors are distinct from not-run states. No audits run on navigation.
- Scope/design and review baseline: `docs/OVERVIEW_REDESIGN.md`.
- Independent standards/spec review findings resolved. Final verification:
  232 backend tests passed, 28 skipped; production frontend build passed;
  browser journeys and responsive checks passed at 320–1440 pixels.

---

## Session — 2026-08-25  (bounded intelligence-table foundation)

Inventory and Payment tab latency was traced to unbounded payloads, thousands
of DOM rows, duplicate Payment reads, hidden sub-tabs being rendered, and eager
whole-period verification fetches. The data-table boundary is now bounded:

- `GET /inventory/comparison-page` supports a hard maximum of 100 rows,
  offset pagination, server-side text/finding filters, whitelisted stable
  sorting, total count, and full-filter-set summary cards.
- `GET /payments` replaces the Payment UI's summary + exceptions double read
  with one filterable, bounded collection. Exceptions are a status-filtered
  view of the same collection; legacy endpoints remain for internal/backward
  compatibility.
- Inventory and Payment use 25/50/100-row pagination, 300ms debounced search,
  TanStack Query cancellation/deduplication with a bounded five-minute page
  cache, and render only the active Payment sub-tab.
- `GET /dealers/{id}/verification` plus `useLazyDealerVerification` loads and
  deduplicates compact dealer evidence only after a Verify row is opened.
- HTTP responses expose `Server-Timing`; structured request logs record path,
  status, duration, and content length without payload/SQL data.
- Compatibility and new bounded-contract tests pass in sample mode; the Vite
  production build passes.

Known boundary: sample pandas and the current APDP adapter still assemble a
period result before applying the page. The browser/API contract is bounded,
but native Presto/Postgres page/count/aggregate execution remains follow-up
work once live Presto is implemented and production query plans can be
measured. Redis and cursor pagination remain deliberately deferred.

**CI follow-up:** GitHub Actions previously supplied a fake non-empty
`ANTHROPIC_API_KEY`, which accidentally activated five live-agent tests and
failed with Anthropic 401 responses. Live tests now carry the `live_agent`
marker and require `RUN_LIVE_AGENT_TESTS=1`; the normal sample-data workflow
runs without any Anthropic key. CI-equivalent result: 215 passed, 28 skipped.

**Render follow-up:** the TanStack Query install regenerated
`package-lock.json` under local npm 11, while Render's `node:22-alpine` image
uses npm 10.9.8. npm 10 rejected the peer/dependency layout (`picomatch` and
React types) before the Vite build. The lockfile was regenerated inside the
exact Render image, `packageManager` now pins npm 10.9.8, and CI now runs
`npm ci` + `npm run build` under Node 22 so lockfile drift fails before deploy.

**Render audit connection follow-up:** an Audit Trails screenshot showed the
deployed backend attempting local Docker's `localhost:5544`, proving that the
service lacked `FBB_AUDIT_PG_*` bindings. The demo config now safely falls back
to explicitly configured `APDP_PG_*` credentials (the Render design already
shares one managed DB for `audit` + `normalized` schemas), while local dev with
no APDP binding retains `localhost:5544`. Deployment docs now call out the
dashboard configuration check explicitly.

---

## Session — 2026-08-21  (APDP live-data sprint)

The demo story added a new twist during manager review — "can you actually
show live payment data from APDP turning into a real financial statement
for a dealer?" This session ships the whole end-to-end. Chronological.

**The blocker that shaped everything**
The APDP fixture generator hardcoded 5 synthetic dealers (`FBB_D00001`…5)
with no relationship to the ~900 FBB sample dealers (`19472`, `74050`…).
Flipping `PAYMENT_SOURCE=apdp` without fixing this meant: 5 unrelated
dealers in the Payment tab, every FBB partner INSUFFICIENT_DATA in the
payment_reconciliation audit, and a Dealer Statement that could never
join both sides for the same partner. Fixture generator now loads every
distinct `distributor_code` from the FBB CSV for the target period —
939 dealers in 202602, 922 in 202603, all real FBB IDs.

**Kafka/Flink bypass**
`apdp/CLAUDE.md` documents that the Flink Docker build is broken and the
Kafka→Postgres sink was never wired. For the demo we only need
`normalized.transactions` populated so `normalized.partner_settlements`
returns rows. New `apdp/tools/ingest_fixtures_to_postgres.py` reads the
fixture CSVs → runs `normalize_telecom_*` from `flink_jobs/normalizer_core.py`
directly → INSERTs via psycopg2. One command, ~5 seconds, no Kafka.

**APDP schemas applied to the shared Postgres**
Local + Render both use the existing `fbb-audit-pg` Postgres for
everything — the `audit` schema and the `raw` + `normalized` schemas
coexist in one DB for the demo. Production separation is a later
concern. This means one Render Postgres instance, one connection
string, one place to reason about.

**Packaged seed for Render**
`infra/postgres/apdp_seed.sql` is a `pg_dump` (schema + data) of the
raw + normalized schemas post-ingest — 23 MB, ~23k transaction rows
across two periods, producing 939 + 922 dealer-settlement rows.
`backend/main.py` lifespan hook runs a one-shot loader on backend boot:
if `PAYMENT_SOURCE=apdp` and `normalized.transactions` is empty (or
missing), apply the seed. Idempotent (COUNT-and-skip on later boots).
Non-fatal (a failure logs and returns — Payment tab shows empty state
with the Live·APDP badge, not a 500). First Render boot pays ~30-60s
for the seed; every boot after is ~50ms.

**Payment reconciliation signal on APDP data**
Before this session, running `payment_reconciliation` gave 912 UNDERPAID
/ 27 PAID_IN_FULL on simulated data — dominated by one bucket. On APDP
data with real dealer IDs, the picture is much richer: 580 UNDERPAID /
351 OVERPAID / 4 DISPUTED_ROUNDING / 4 PAID_IN_FULL. All four amount
buckets show up, spread realistically. That's the demo signal we needed
to prove the module actually reconciles rather than always says the
same thing.

**Dealer Statement — Finance/RA internal per-period view**
Answers "for dealer X in period Y, what did we owe, what did we pay,
what's outstanding, and which audit trails support that verdict?" all
in one call.

- `backend/db/dealer_statement.py` composes commission-side (dealer
  summary) + ORSC + payment-side (respects `PAYMENT_SOURCE`) + linked
  audit trail refs into one dict. A formatter, not a new data source.
- `GET /dealers/{dealer_id}/statement?mon_period=…` new endpoint,
  Pydantic-validated response.
- `DealerStatementModal.jsx` renders it with a Position headline
  (PAID_IN_FULL / UNDERPAID / OVERPAID), Commission-side card,
  Payment-side card with a Live·APDP or Simulated badge, ORSC
  informational, Linked audit trails list. Copy-as-markdown and
  download-as-`.md` buttons in the footer, matching DisputeDraftModal.
- Launched from a "Statement" button on each row in the All Payments
  sub-tab. Adding the same button to Activation and Commission
  dealer rows is a small follow-up.
- Fixed two lingering `distributor_name` references in
  PaymentSummaryTable that the earlier rename standardisation
  missed — noticed while adding the Statement column.

**Current Position card on Overview**
New band on the landing page, placed above Audit Coverage. Four tiles:
Total commission owed / Amount settled / Outstanding / Exceptions
(disputed + partial + pending). Data-source badge flips Live·APDP or
Simulated. The Exceptions tile is clickable and deep-links into the
Payment tab. Best-effort load — a missing payment source degrades to
"nothing rendered" rather than blanking the whole Overview.

**Deploy**
`render.yaml` — `PAYMENT_SOURCE=simulated`, matching localhost exactly for
the GM preview. `APDP_PG_*` env vars remain wired to the same managed
fbb-audit-pg Postgres so APDP can still be enabled explicitly. `.dockerignore`
excludes `apdp/` (deliberately — the runtime path doesn't need Flink or
Kafka) but includes `infra/` where the seed lives. Dockerfile already
COPYs `infra/` so the seed lands in the image.

**Next — before GM demo**
1. Watch the Render redeploy. Once Live, `/health` should return
   `payment_source: "simulated"` and the same revision as GitHub.
2. Open localhost and Render for Feb 2026. Both should show the Simulated
   badge, NGN 41,649,665.49 owed, NGN 36,403,291.00 paid,
   NGN 5,246,374.49 outstanding, 12 disputed, and 912 exceptions.
3. Punch-list items after that: Statement button on Activation +
   Commission tab dealer rows, address the pre-existing live-LLM
   flake, second APDP dealer story ("this dealer was Overpaid — here's
   the trail proving it").

**Deferred (post-GM)**
- Split APDP + FBB audit Postgres in production
- APDP end-to-end ingestion via Kafka/Flink (fix the Docker build)
- Fifth audit module — waiting on GM feedback about domain priority
- Real dealer data via Mono consent / MTN internal feed — waiting on
  finance/MTN access approval
- Live-LLM flake in `test_kb_inventory_rules_grounded`

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
gated). The hosted preview and localhost now both use the deterministic
simulated payment dataset (`PAYMENT_SOURCE=simulated`). This deliberately
keeps screenshots, totals, dealer names, statuses, and exception counts
identical across both environments. APDP/Postgres remains implemented and
can be enabled in a dedicated integration environment.

Four audit modules registered (`zero_commission`, `inventory_mismatch`,
`payment_reconciliation`, `eligibility_window`) and the payment audit
now produces a realistic multi-bucket spread (UNDERPAID / OVERPAID /
DISPUTED_ROUNDING / PAID_IN_FULL) against APDP data.

Two new user-facing surfaces landed this session:
1. **Dealer Statement** modal — per-period Finance/RA internal view
   composing commission entitlement + payment settlement + linked
   audit trails, launched from a "Statement" button on each Payment
   Intelligence dealer row. Copy-as-markdown + download-as-`.md`.
2. **Current Position** card on Overview — platform-wide reconciliation
   headline (Owed / Settled / Outstanding / Exceptions) with a
   Live·APDP or Simulated data-source badge.

Immediate next: **watch the Render redeploy land (~3 min), verify
Live·APDP end-to-end, send the URL + creds to the GM.** No blocking
known issues.

Docs: ARCHITECTURE.md (onboarding + design rules), CLAUDE.md (rules;
both exist — root + apdp/), PROGRESS.md (this file), docs/DEPLOY.md,
docs/GM_DEMO.md (GM read-along), docs/AUDIT_INVENTORY_MISMATCH_DESIGN.md.

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


## Session — 2026-09-13 (Payment investigation workspace)

- Implemented the Payment handoff: full-period outstanding summary and explicit
  comparison, bounded account filters/sorting/paging, complete matching CSV export,
  exact dealer detail and scoped commission/activation navigation.
- Verification starts Not checked. Missing/failed evidence and retry are distinct;
  dealer-period queries replace the obsolete lazy hook. Saved reconciliation loads
  only on request; aggregate differences no longer imply undocumented causes.
- Period comparison and Health are bounded and have explicit request states;
  Health formula and limitations are visible. Period changes reset evidence while
  retaining the active view. List return restores filters/page/focus.
- Verification: 232 backend tests passed, 28 skipped; 17 focused payment tests
  passed; production frontend build passed with existing bundle-size warning.
  HTTP checks cover export scope, exact identity, limits/filters and APDP failure.
  Browser checks cover responsive widths 320/768/1024/1440, navigation, missing
  trail, filtered empty state, failed requests and successful retry.
- Standards/spec reviews completed; navigation/focus and cached-summary timestamp
  findings fixed. Proposed new test seams remained unconfirmed; no new regression
  tests were authored. No live AI/Presto, deployment or audit run.
- Contract and verification: `docs/PAYMENT_WORKSPACE.md`.
