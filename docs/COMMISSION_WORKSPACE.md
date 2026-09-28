# Commission investigation workspace

Scope: accepted Commission Intelligence recommendations in the September 13
conversation. Review baseline: 43e4ce26aac7b240b906ed6827ab828d1ce434bc.

- Lead with recorded commission, account counts, zero records and explicit
  comparison period. Keep settlement and dealer-claimed expectations separate.
- Make a searchable, class/filter/sort-controlled bounded account table primary.
  Maximum page size 100. Full-period and filtered-set totals precede pagination.
- Show account codes everywhere: duplicate names must never select an account.
- Open denomination breakdown, period comparison and bounded zero-record
  evidence on demand, independently of payment availability.
- Preserve ORSC as a separate subscription-revenue view, not commission payable.
- Provide contextual AI assistance with exact account/period; no automatic sends.
- Keep sources, absent prior records, unavailable data and genuinely empty data
  distinguishable. Never infer a confirmed error from a zero amount.
- Reuse existing named SELECT queries; no recalculation, production writes,
  new audit runs, agent tools or external integrations.
- Match Overview's visual language and support 320/768/1024/1440px layouts,
  labelled controls, keyboard selection and focus return from detail.

Implementation slices: bounded collection and summary; account evidence;
workspace UI and contextual chat; browser verification and independent review.
Proposed test seams: public HTTP API and user-visible browser journeys.

## Verification

- Existing query suite: 27 passed. Existing backend suite: 232 passed,
  28 skipped. No new test files were written while confirmation of the
  proposed TDD seams was pending; this is not new automated regression coverage.
- Production frontend build passes. This JavaScript project has no separate
  typecheck script. The existing bundle-size warning remains.
- Running API checks: March commission NGN 47,642,607.64; prior February
  NGN 41,649,665.49; delta NGN 5,992,942.15. Limit 101 returns 422.
- Name search finds all four CCA Links accounts and matching CSV exports all
  four with codes, periods and financial measures. Account 296065 has
  NGN 920,811.58, 43 zero records, and on-demand denomination evidence.
- Browser: account search/selection, zero records, focus return, period and
  stream switching. Detail/page widths checked at 320, 768, 1024 and 1440px.
- March ORSC has no source accounts and is explicitly empty, not a verified
  zero balance. February has 157 accounts and NGN 1,964,280.90 recorded revenue.
  **September 15 update:** the approved synthetic March demo fixture now supplies
  200 records across 157 accounts, totalling NGN 2,050,990.17. Source labels in
  the workspace, detail and export identify it as synthetic. February is
  unchanged. See `data/samples/README.md` for generation assumptions.
- Live Presto and live AI answer generation were not exercised. The pending
  response lifecycle fix was independently code-reviewed, not runtime tested.

## Review

### Standards

The initial review found a conversation-lifecycle defect and missing architecture
documentation. Both were corrected; follow-up found no substantive defects.

### Spec

The initial review found ambiguous empty-source totals and the same conversation
lifecycle defect. Both were corrected; follow-up found no substantive issues.
Conversation state now survives component unmounts and remains scoped to the
exact account, period, comparison and stream. Source absence is explicit.
