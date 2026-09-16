# Audit Trails saved-evidence workspace

Implement the accepted September 14 handoff. Saved assessments are evidence,
not independently verified financial outcomes. No audit executes on reads,
refresh, navigation or export. Existing explicit runs replace module/period
trails; older versions are not retained.

## Contract

- Add GET `/assurance/audit/records` and `/records/export`. Keep legacy trails
  and exact-subject endpoints compatible. Required period and module; search,
  conclusion, confidence, caveat presence/step and exact subject filters;
  deterministic whitelisted sorting; limit 25/50/100 (hard maximum 100).
- Return compact items without steps, full-module summary, whole-filter summary,
  pagination and retrieval timestamp. Counts distinguish trails, subjects and
  dealers; Inventory subjects are dealer-products. No cross-module money sums.
- Reuse existing saved-store reads. Server-side collection shaping follows the
  existing workspace foundation; native database projection/filter/aggregation
  is deferred pending measured plans. No additive SQL or storage writes.
- Exact detail preserves recorded fields and explicitly qualifies historical
  Eligibility entitlement wording. Show partial payment beside NOT_PAID and
  structured limitations irrespective of caveat count or confidence.
- Provide module measures, readable identity, saved source/time/run/version,
  full matching CSV and individual readable evidence download. Formula-safe CSV.
- Separate loading, failed read, empty collection, filtered miss and missing
  exact evidence. Friendly retry/reset states; TanStack Query cancellation/cache.
- Reuse Overview surfaces and MTN styles, accessible controls, return focus and
  retained originating investigation context. Responsive at 320/768/1024/1440.

## Verification plan

Public API tests with saved-store boundary fixtures cover pagination, filters,
summary scope, exports, source failure, exact subject and preserved evidence.
Existing sample-data backend suite before frontend; production build and browser
journeys across modules, limitations, error/missing states and navigation.

## Delivered behavior and verification — September 14

`backend/api/audit_workspace_routes.py` validates the bounded read/export contract;
`backend/db/audit_workspace.py` shapes existing persisted reads. Exact evidence
accepts optional `trail_id`: list selection opens that saved row, including when
multiple saved trails share a subject. Direct contextual navigation selects the
existing latest-subject read. A missing selected row returns 404 rather than
silently substituting another assessment. The original recorded text, conclusions,
IDs, timestamps and pipeline versions remain intact.

The React workspace uses one active bounded collection and separate exact-evidence
queries with cancellation. It shows full-module and whole-filter counts, module
measures, readable products and per-row provenance. Errors hide unrefreshed results;
404, 503, no matches and no saved collection have distinct copy. Module selection
survives period changes; filters and row focus survive evidence return. Overview
navigation preserves the exact subject and returns focus to the originating control.

Downloads include complete matching CSV with explicit filters and formula escaping,
and a plain-text evidence report with measures, checks, recorded caveats, limitations,
qualified historical wording plus original text, and provenance. No external sharing.
Run remains a separate explicit operation with replacement-scope acknowledgement.
It was not exercised against the saved datastore during implementation.

Actual checks:
- Full sample-data backend suite: **246 passed, 28 skipped**. Fourteen new public
  API regression cases; legacy error assertions updated to require friendly copy.
- Node built-in report tests: **3 passed**. No dependency or test framework added.
- Production frontend build passed; existing bundle-size warning remains.
- Read-only actual-store checks covered all four modules, limits, compact payloads,
  exact evidence and all-match CSV counts. March Inventory: 4,174 trails, 920
  dealers; 25-row response 21,709 bytes (the earlier all-step response was ~13 MB).
- March zero commission: 620 trails across 575 subjects/dealers. Duplicate-subject
  identity regression verifies exact selected trail IDs rather than latest-row
  substitution. Eligibility: 575 saved trails; Payment Reconciliation: zero.
- Browser checks: no-match/reset; 100-row page and next offset; missing detail,
  failed detail/list, retry recovery; all module views and period changes; real
  NOT_PAID/positive partial payment; HIGH Inventory with no recorded caveats but
  visible purchase-only limitation; historical Eligibility qualification.
- Downloaded CSV verified at **575 matching Eligibility rows** while viewing a
  100-row page. Downloaded individual report checked for payment and run provenance.
- Keyboard evidence opening, row-focus return and Overview exact-subject return
  verified. List/detail width checks at 320/768/1024/1440px found no page overflow;
  wide tables scroll within their region. Mobile detail and desktop list visually
  inspected. Browser console returned no errors/warnings.
- Isolated browser verification server blocked non-GET requests and logged **zero
  non-GET attempts** across browsing, refresh, selection, navigation and export.

Commands: `USE_SAMPLE_DATA=true .venv/bin/python -m pytest backend/tests -q`,
`node --test frontend/src/components/audit/auditPresentation.test.js`,
`npm --prefix frontend run build` (same-origin API override used for isolated
browser checks). Existing staged Inventory work and unrelated artifacts preserved.

## Remaining boundaries

Backend reads still load the saved module/period through existing audit_store
helpers before shaping/filtering. Selecting a specific trail ID uses the same
period-scoped reader for identity isolation. This bounds browser payload/cache,
not database materialization. Native compact projections and database page/count/
aggregate queries remain follow-up work under the existing query-plan guidance;
no SQL/storage migration was added. Earlier replaced trail versions are not retained.
Live Presto, production deployment, source freshness, commission recalculation and
actual audit execution were not tested or changed.

### Review polish — filter spacing

Replaced the tightly wrapped filter toolbar with aligned groups: module and a
wide search field; a separate evidence-filter grid; sorting/reset below a divider.
Controls are full-width in their columns with consistent 44px minimum height and
20–24px gaps. Mobile stacks fields; tablet uses two evidence-filter columns;
desktop uses four. Build passed and browser checks at 320/768/1024/1440px showed
no page overflow or console errors. This is a layout-only change.
