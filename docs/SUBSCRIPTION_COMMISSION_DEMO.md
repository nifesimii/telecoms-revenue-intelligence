# Synthetic subscription commission demonstration

Approved implementation spec, 2026-09-28. Baseline: `10bc4d548b58100def297fc9e5686cbf5ebbbe1f`.

## Truth boundary

ORSC `data_subscription_amount` records subscription revenue. Verified MTN
subscription commission terms/calculations are unavailable. Live mode stays
revenue-only and commission is unavailable. Every demo screen, export and
assistant answer carrying illustrative figures must retain synthetic provenance
and the exact label:

**Illustrative subscription commission policy—not confirmed MTN terms.**

The platform consumes supplied recorded calculations; only the offline synthetic
generator may calculate this illustrative policy. No production recalculation,
live churn monitoring, production writes, notifications or authentication.

## Illustrative policy and evidence

- Attribute a device to its original selling dealer.
- Eligibility lasts 12 months from first activation; purchases/renewals never
  restart it. The generator must document the precise boundary convention.
- A successful PAID subscription purchase/renewal in the reporting month and
  qualifying monthly revenue of at least NGN 5,000.00 **per device** are required.
- Eligible devices earn 5% of **all** qualifying revenue, not only the excess.
- Commission is due on the final day of the following month.
- Payment states need supplied evidence: not yet due, paid, overdue, or unknown.
  Missing evidence and amounts remain null/unknown, never fabricated zeroes.
- No paid subscription this month is separate from churn. Three consecutive
  months without paid subscriptions supports a contextual churn indicator only
  when history is sufficient; insufficient history stays unknown. Churn is not
  an exclusion reason.
- Persist the chain selling dealer → device → reporting month → paid activity →
  eligibility → eligible revenue → recorded simulated commission → due/payment
  evidence → dealer expectation and variance explanation.

## Product acceptance

Provide dealer aggregates distinguishing recorded subscription revenue, eligible
revenue, simulated commission, dealer expectation, variance, and payment status.
Device evidence expands on demand. Cover eligible commission, below minimum,
no renewal, expired eligibility, and earned commission overdue, plus paid,
not-yet-due, unknown payment evidence and missing-history controls.

Keep activation settlements and subscription fixture settlements separate.
Do not introduce duplicate settlement reads into Payment views. Inventory and
Payments keep their bounded contracts, server filtering/sorting/counts/whole-
filter aggregates, maximum page size 100, TanStack caching and lazy evidence.
Use the same bounded design for subscription dealer/device collections.

Correct the KB assertion equating revenue to payable, after reading its source;
preserve the distinction between unverified production terms and this demo.
Provenance must survive assistant context, responses, exports and investigation.

## Implementation and validation contract

Work on current `main`; no branch/worktree and no push. Preserve existing
untracked `.scratch/`, `.tmp/`, `docs/DEMO_UX_REVIEW_2026-09-27.md`,
`docs/FBB_Product_Demo_Executive_Review.pptx` and its `.inspect.ndjson`.

Approved behavioral seams for focused red/green tests: generated fixture policy
examples and evidence invariants; public read/query and API collection/detail/
export contracts; assistant provenance; UI presentation and interaction. Backend
tests must pass before frontend edits begin. Full suite runs at completion,
repeated only for relevant fixes. Fresh independent Standards and Spec reviewers
run in parallel; a distinct validator runs tests and real-browser demo QA.
The lead integrates fixes, updates architecture/progress and commits changes.

## API and demo walkthrough

The Commission Intelligence **Subscription commission** tab uses `/subscriptions`.
Collection filters are `mon_period`, `search`, `payment_status`, `sort_by` and
`direction`, with `limit`/`offset` (maximum 100). `/subscriptions/export` exports
the complete filtered dealer set. `/{dealer_id}/detail` anchors the investigation
and `/{dealer_id}/devices` loads bounded device evidence only when requested.
Device evidence includes strict-null `filtered_summary` amounts for the entire
matching device set, computed before pagination and shown beside the evidence.
The original `/commissions?stream=orsc` and ORSC tools continue to report revenue.

Start with June 2026, then use May to demonstrate overdue timing. Subscription
evidence is supplied as of **15 July 2026**: unpaid June earnings are not yet due
until 31 July; unpaid May earnings were due 30 June. This date is a fixture
snapshot, not the current clock or a live monitoring service.

The eight distinctly synthetic dealer accounts cover these investigations:

| Account | Investigation |
| --- | --- |
| SYN-SUB-001 | Eligible paid revenue with recorded commission matching expectation |
| SYN-SUB-002 | One device exactly at the minimum and one below it; dealer revenue pooling is invalid |
| SYN-SUB-003 | Current month without a paid renewal, separate from churn |
| SYN-SUB-004 | Paid revenue after the original eligibility window expired |
| SYN-SUB-005 | Earned commission with unpaid settlement evidence; June not yet due, May overdue |
| SYN-SUB-006 | Earned commission but missing settlement evidence, payment unknown |
| SYN-SUB-007 | Churn/history investigation: complete and incomplete history controls |
| SYN-SUB-008 | Missing activity and expectation evidence; monetary results unknown |

Eligibility uses the paid purchase date in the interval from first activation
(inclusive) to its 12-calendar-month anniversary (exclusive). A February 29
anniversary clamps to February 28. The generator rounds illustrative commission
half-up to kobo; request-time code never applies the rate. Portfolio totals with
missing contributions remain unknown; explicitly named known subtotals are
partial and must not be represented as complete balances.

## Implementation boundaries and operational limits

`backend/data/generate_subscription_demo.py` writes the separate JSON fixtures;
named scenarios carry stable dealer/device/evidence identities. The shared
provenance label lives in `backend/models/subscription.py`. Runtime reads validate
fixture labels and preserve them through the API, UI, exports and assistant.
`backend/db/subscription_workspace.py` only groups, sums, filters and pages
supplied records; it does not calculate policy earnings or monitor churn.

The existing Presto adapter is still a stub. Live-mode revenue-only contracts
are tested at the external adapter boundary, but a real Presto read cannot yet
be demonstrated. No actual MTN commission terms or settlement were verified.
No paid external LLM call was made; assistant tool/response behavior is covered
with a substituted SDK, and UI assistant scope is covered by presentation tests.
The JavaScript frontend has no standalone typecheck script; its production
build retains the existing bundle-size warning.

## Verification and independent review

- Final independent suite: **290 backend tests passed, 28 skipped**; all **9
  frontend tests passed** and production build passed. Focused tests used
  red/green at the generator, public API, tool/response and presentation seams.
- Isolated Chrome and API checks: **111 assertions** across the five narratives
  and all eight dealers; paid/not-yet-due/overdue/unknown; January/June history;
  exact provenance, expectations/variance, lazy bounded evidence and caching;
  dealer/month continuity and focus return; filters/sort/CSV, empty/error/retry,
  live-source substitutes, and whole-filter device totals before pagination.
- Screenshots inspected at 320, 768, 1024 and 1440 pixels. Tables scroll within
  their containers; device chains remain readable and keyboard focus visible.
  Normal runtime console output was clean; injected HTTP 500s tested failures.
- All six fixture files reproduce exactly, including after stable-identity
  refactoring. Existing source CSVs and protected user artifacts match their
  pre-implementation hashes. Browser artifacts/logs are under
  `/tmp/subscription-validation` for this local session.
- **Standards:** no documented-standard violations. Both maintenance findings
  (positional scenario identities, duplicated label sources) resolved; follow-up
  found no new actionable issues.
- **Spec:** both gaps (device-filter totals, reachable reconciliation KB
  ambiguity) resolved; follow-up found no new actionable issues or scope creep.
