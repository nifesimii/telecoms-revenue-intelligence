# Payment investigation workspace

Implements `/private/tmp/hands-off.md` (September 13). Review baseline:
`0d0ff43a1bfceb916ac3717983247e282ac9baf4`. Existing staged Inventory work is
outside this change.

Payment follows summary → accounts → evidence. Full-period outstanding is the
headline, alongside commission owed, amount settled, coverage and disputed-account
count. Available earlier periods drive explicit outstanding and coverage changes.
Missing source records, unavailable data and zero balances remain distinct.
One source notice distinguishes simulated settlement data from APDP selection;
retrieval time does not establish source freshness or production provenance.

Exceptions and All Payments use the same bounded `/payments` read. Backend search,
status filtering, deterministic sorting and 25/50/100 pagination remain authoritative.
`record_count` and `generated_at` extend the page contract. Financial totals remain
**full-period**, independent of filtering. No filtered financial totals are claimed.

`GET /payments/export` accepts the same period, search, status and sorting filters
as `/payments`, without pagination. It reads one snapshot and exports the complete
matching account set with period, source and retrieval timestamp; spreadsheet
formula prefixes are escaped. Export is disabled while list scope is changing or
unavailable. It does not concatenate browser pages.

`GET /payments/accounts/{dealer_id}?mon_period=YYYYMM` resolves an exact account,
returning period, source, retrieval timestamp and account; missing accounts return
404. Opening detail fetches the existing exact-account activation verification.
Saved `payment_reconciliation` trails load only on request, with recorded date,
source, confidence and caveats. No audit is initiated. Aggregate payment/activation
differences are factual observations and never establish payment on zero records.

`GET /payments/analytics` accepts mon_period, optional earlier prior_period,
view=comparison|health, search, limit≤100 and offset. It returns a bounded page,
whole-view account_count, matching pagination metadata and period/source context.
Comparison uses only shared accounts, ordered by absolute paid change then dealer
code. Health uses the existing calculation ordered by score then dealer code.
Legacy analytics endpoints remain compatible. Query work still runs over the
existing period snapshots before paging; native database pagination remains future
work requiring measured query plans.

The Health explanation discloses its existing missing-evidence and over-settlement
limitations. No scores, classifications, commission calculations or SQL change.
AI threads use exact account, reporting period, comparison and payment scope, using
the shared Atlas conversation lifecycle. **Ask Atlas about this payment** reveals Atlas,
prefills the payment question, scrolls the composer into view and focuses it.
Select **Send question** to request an answer; opening never sends automatically.
Repeated activation preserves an unsent draft and the existing thread, including
keyboard activation. While a request is pending, focus moves to the composer form.
Cross-module navigation preserves
account code and comparison. Returning from detail retains list filters, page and
keyboard focus. Period changes reset all selected evidence; the obsolete lazy hook is replaced by query
state keyed by dealer **and** period.

Verification results are recorded below when the implementation review completes.

## Verification and review

- Full sample-mode backend suite: 232 passed, 28 skipped. Focused payment suites:
  17 passed. Frontend production build passes; the existing bundle-size warning
  remains. This JavaScript project has no separate typecheck script.
- Public HTTP checks: complete four-account CCA Links export with a one-row page;
  status/search intersection; invalid sort/status and page limit 101 rejected;
  exact 296065 detail and substring 296 rejected; shared-account comparison 799,
  Health 922, both paged; invalid comparison order rejected; no-source period;
  APDP failures return 503 for list/export/detail. These are direct checks, not new
  automated regression tests. Proposed new HTTP test seams remained unconfirmed.
- Browser: explicit not-checked records, exact detail and Activation navigation,
  43 zero records for 296065, missing saved trail, dispute-dialog Escape and focus,
  search/status/sort controls, pagination, filtered empty state, period-bound Health
  summary, list-return focus, and activation/summary request failure and successful retry recovery.
  List and detail widths checked at 320, 768, 1024 and 1440 pixels; wide tables
  scroll within their own regions.
- Standards review: placeholder-summary retrieval timestamps corrected; no hard violations; one minor repeated-stream-configuration
  observation retained in the existing shared assistant.
- Spec review: exact Activation navigation, secondary-view focus and navigation
  replay on period changes were corrected and cleared on follow-up review.
- Live Presto, live AI generation and production deployment were not exercised.
  No audits were run and no production data was changed.
