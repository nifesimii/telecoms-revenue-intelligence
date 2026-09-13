# Activation investigation workspace

Implementation scope agreed from the September 13 design review: adopt Overview
and Commission's visual hierarchy, preserving Activation's focus on volume and
qualification. No commission recalculation, new business rules, production writes,
or automatic audits. Existing legacy activation endpoints remain compatible.

## Acceptance contract

- Full-period summary: total activation records, qualified and zero-commission
  records, weighted qualification rate, accounts with zero records, entirely zero
  accounts, recorded commission. Search must not change these headline totals.
- Three views: Dealer accounts, Period comparison, Exceptions. One bounded active
  collection, backend search/class/finding filters and deterministic sorting,
  25/50/100 rows, full-filter matching aggregates and CSV export.
- Exceptions grouped per dealer; readable finding labels, existing severity and
  next action; distinguish findings from distinct accounts and avoid causal claims.
- Comparison uses accounts present in both periods, explicitly labelled; actual
  month headings and qualification deltas in percentage points. No comparison and
  missing prior records remain distinct from zero.
- Account detail shows activation totals, comparison and findings, with on-demand
  existing zero-commission evidence and navigation to Commission scoped to account.
- Preserve list filters/page/focus on return; refresh, retry, skeleton, no-source,
  no-matches and no-exceptions states; errors never become empty successful data.
- Reuse existing neutral/yellow design tokens, readable tables, keyboard controls,
  associated labels and responsive layouts at 320, 768, 1024 and 1440 pixels.

## API contract

GET /activations/accounts, /activations/accounts/export,
/activations/accounts/{dealer_id}/detail. Required mon_period, optional earlier
prior_period. Collection filters: view=accounts|comparison|exceptions,
search, partner_class, finding=all|with_zero|all_zero|ALL_UNQUALIFIED|
HIGH_UNQUALIFIED_RATE|UNUSUAL_VOLUME. sort_by=activation_count|dealer_name|
non_qualified_activation_count|qualification_rate_pct|activation_commission_amount|
delta_activations|severity; direction=asc|desc; limit <=100, offset >=0.

Page: mon_period, prior_period, view, source, generated_at, summary,
filtered_summary, comparison_account_count, partner_classes, items, total, limit,
offset. Each item retains existing activation summary field names, plus findings
(objects: type, label, severity, recommended_action), prior_activation_count,
prior_qualification_rate_pct, prior_commission_amount, delta_activations,
delta_qualification_rate (percentage points), delta_commission_ngn. Missing prior
fields and deltas are null. summary and filtered_summary: account_count,
activation_count, qualified_activation_count, non_qualified_activation_count,
qualification_rate_pct (null for no records), activation_commission_amount,
accounts_with_zero, all_zero_accounts, finding_count, flagged_accounts.

Detail: mon_period, prior_period, source, generated_at, account (same item shape).
Export matches complete filtered collection, includes period/comparison provenance,
readable findings and spreadsheet-formula escaping. Source failure returns 503.

## Implementation and verification

Baseline: 0ff1324bb799ac2ea3c55fa219b2f2213ea16bd2.
Public HTTP endpoint test boundaries were proposed to the user; confirmation
remained pending, so no new automated test files were authored. Existing full
backend suite: **232 passed, 28 skipped**. Frontend production build passed; this
JavaScript project has no separate typecheck command. Existing bundle-size warning
remains. Live Presto and AI generation were not exercised.

Independent read-only HTTP checks covered 25/100-page bounds and 101 rejection,
stable ties, search/class/finding intersections, full vs matching totals, exact
detail/404, earlier-period validation, grouped findings, CSV scope/provenance and
formula escaping. Process-local source failure and empty-data checks returned 503
and successful empty data respectively. March matches independent fixture totals:
922 accounts; 30,892 activations; 24,887 qualified; 6,005 zero; 190 findings across
155 distinct accounts. Comparison contains 799 shared accounts. Dealer 74050 has
+254 activations, +4.04 percentage points and +NGN 387,738.54 recorded commission.

Browser checks: stable full summary during search, retained search focus, account
detail and 25-row on-demand evidence, return focus, grouped exceptions, no matches,
no comparison, exact Commission navigation preserving No comparison, responsive
account/detail layouts at 320/768/1024/1440 pixels. Wide tables scroll inside their
own regions. Controlled local API interruption shows a stale-data error and disables
export; retry recovers. No automatic audit or AI calls are introduced.

## Independent review

Fresh-context backend, frontend and validation agents worked from this contract.
Separate Standards and Spec reviewers both identified exact Commission navigation
depending on the first substring-search page. The fix loads exact detail directly
and supplies a list-heading focus fallback if the account row is absent on return.
Both reviewers cleared the exact-navigation fix. A nonblocking duplicated CSV
escaping heuristic was retained to avoid an unrelated shared exporter refactor.
