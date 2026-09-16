# Inventory investigation workspace

## First-release contract

Implement the September 13 Inventory review on the existing bounded API.
Baseline: `0d0ff43a1bfceb916ac3717983247e282ac9baf4`.

- Dealer-product comparison is the main grain. Preserve API enums; display
  invoice coverage gaps, observed excess requiring investigation, and within
  recorded purchases separately from saved verification conclusions.
- Current-filter summaries come from the server, never the visible page:
  observed excess units and dealer-product counts by comparison status.
- Expose server finding filters, search, supported deterministic sorts and
  25/50/100 pagination. Retain TanStack Query bounded caching.
- Show dealer and product names/codes, recorded purchases, activation records,
  excess units/percentage and one explicit evidence action. Null is unknown.
- Selected dealer-product detail preserves list state and return focus. Load
  saved `inventory_mismatch` evidence only on demand, keyed by exact
  `dealer_id:product_code` and reporting period. No audits run on navigation.
- Show saved source/time/confidence and caveats. Distinguish absent, failed,
  loading, refreshed and stale evidence. Never infer excess-unit commission
  from dealer-wide commission or zero-commission counts.
- Show product qualification as context only. Inventory explanations concern
  carryover, confirmed SKU aliases, ingestion coverage and excess activation.
- Coverage ticket defaults to IFS, explicitly covers the whole reporting
  period rather than current filters, and remains copyable with no submission.
- Follow existing neutral/MTN workspace styling. Associated labels, semantic
  headings, keyboard/focus handling, accessible dialog, readable tables and
  responsive layouts at 320/768/1024/1440px are required.

## Explicit data limitations and later work

This release corrects the ticket compiler's unsupported six-month invoice-window
wording; it does not redefine purchase-window calculations. Current sample
comparison reads the complete IFS fixture without filtering invoice dates to
the reporting period. Its completion dates span March 5–28, 2026. The UI must
not claim six months of coverage, period-matched purchases, a stock balance,
or attributable commission exposure. Actual window/completeness metadata
and agreed period-aware purchase semantics need a separate backend contract.

Saved trail carryover/alias checks omit purchase-only combinations; upstream
completeness currently checks for a nonempty IFS file. Show these limitations
alongside saved results, including HIGH confidence. Later improvements:
purchase-only history, bounded invoice evidence, authoritative source freshness,
distinct-dealer/full-period aggregates, filtered exports and scoped tickets.

## Verification

New regression-test boundaries were proposed for agreement: Inventory UI/API
filtering, pagination, exact-subject evidence, period switching, and missing/error
states. Existing backend checks and production build run regardless. This is
a JavaScript frontend without a separate typechecking command.

Final checks: **232 backend tests passed, 28 skipped**; focused Inventory/API
checks passed (15 passed, 1 skipped), and coverage-compiler checks passed (18).
The production frontend build passed with the pre-existing bundle-size warning.
No new automated test files were added while boundary confirmation was pending.

Browser verification used the real sample-data API and a separate temporary,
read-only local proxy for controlled failures; no running development API was
interrupted. March current-filter totals: 24 mismatches, 224 excess units and
4,150 missing-invoice combinations. Tivos 409091/product 1283279 shows 60
purchased, 118 activated, +58; its saved HIGH excess conclusion includes the
August 5 saved timestamp and current limitations. Nestobar 74050/product 1283279
has unknown purchases/gap and an inconclusive saved conclusion.

Checked: observed-only/coverage/within views, no-match search, 100-row pages and
next-page offset, exact-subject selection, list return focus, period reset,
404 versus 503 evidence, successful evidence recovery, stale comparison error
and disabled evidence actions, ticket failure/retry and whole-period scope,
native dialog initial focus/keyboard containment/Escape return. List/detail
layouts were inspected across 320/768/1024/1440px; wide tables scroll inside
their own regions. The normal application browser console had no errors/warnings.
Live AI generation, live Presto and ServiceNow submission were not exercised.

Independent Standards review found no hard violations; optional readability,
structured-detail expansion and numeric-defense suggestions were recorded.
Numeric display guards were tightened. Spec review found a lost sticky header;
it was restored inside a bounded scroll region and the reviewer cleared the fix.
Backend purchase-window semantics and completeness remain deferred, as above.
