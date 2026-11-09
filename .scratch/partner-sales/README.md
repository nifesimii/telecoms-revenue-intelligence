# Partner Sales GitHub ticket drafts

Publication status: pending approval of granularity and blocking edges.
Repository: nifesimii/telecoms-revenue-intelligence
Publish label: ready-for-agent (must be created; currently absent).
Source: the accepted conversation scope and local Partner Sales specification.
No parent issue exists; omit Parent from published tickets. Do not create or modify a parent as part of this breakdown.

Testing boundary: rendered-workspace acceptance tests plus existing public API regressions. Approval of this breakdown includes this proposed boundary.
All tickets include implementation and observable acceptance checks. No standalone prefactor is needed based on the current shell and exact-account navigation seams.
Publish in numbered order, replacing draft blocker references with real GitHub issue links and adding native blocking relationships.

- [01: Create and preview a simulated partner invoice](issues/01-draft-invoices.md) — blocked by: none.
- [02: Issue simulated invoices and inspect partner obligations](issues/02-issue-and-browse.md) — blocked by: 1.
- [03: Record partial and full simulated invoice collections](issues/03-invoice-collections.md) — blocked by: 2.
- [04: Explain commission buildup and link to existing evidence](issues/04-commission-account.md) — blocked by: 1.
- [05: Reset and replay the complete Partner Sales presentation](issues/05-repeatable-presentation.md) — blocked by: 2, 3, 4.
