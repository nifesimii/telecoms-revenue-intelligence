# Define evidence, freshness and incomplete-data treatment

Type: grilling
Labels: wayfinder:grilling
Status: superseded
Assignee: unassigned
Parent: ../map.md
Blocked by: none

## Question

How should Finance distinguish observed transactions, dealer-supplied periodic
records, derived figures and unavailable information? Agree source and review
labels, reporting-period versus receipt-time versus refresh-time semantics,
and treatment of incomplete account coverage, stale records and missing balances.
Decide how synthetic payment feeds and periodic inputs are represented in the
demo, including whether prepared records suffice or an upload interaction is
needed. Keep monthly versus quarterly input cadence open until its purpose is
clear. Treat "UDP" as an unverified future source, without live integration.


## Execution handoff — 2026-09-16

The user requested implementation with synthetic data throughout. This planning
interview is superseded by [the implemented demo specification](../../../docs/DEALER_FINANCIAL_HEALTH.md).
Remaining demo choices use the documented implementation defaults, not an
assertion of further user interview answers. Real-data questions remain pilot work.
