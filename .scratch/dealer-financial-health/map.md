# Dealer Financial Health — pilot demonstration map

Status: superseded by implementation
Labels: wayfinder:map

## Destination

An implementation-ready specification and agreed demonstration approach for a
Dealer Financial Health workspace that helps MTN Finance assess dealers' whole
businesses when considering funding, supporting a proposal to enter the pilot stage.
The map is complete when the decision tickets are resolved; building the demo is
a separate execution phase.

## Notes

- On 2026-09-16 the user explicitly requested implementation using synthetic
  data throughout. Continue from [the execution spec](../../docs/DEALER_FINANCIAL_HEALTH.md)
  and [implementation checklist](implementation.md). This supersedes this map's
  planning-only boundary and outstanding demo interviews; it does not claim
  that those historical tickets were resolved through further user interviews.

- Users: MTN Finance. Subject: the dealer's whole business, beyond its MTN
  commission account.
- Confirmed with the user: first deliverable is a demonstration with clearly
  labelled synthetic businesses, followed by a plan for real evidence in a pilot.
- Confirmed with the user: statements and explainable health observations;
  dealer ranking and funding-amount recommendations are excluded.
- The user reports an existing internal platform where dealers upload information,
  tentatively named "UDP". Its identity, contents, export options and access are
  unverified. Do not equate it with UDDM. It is a possible future source, with
  no integration during the demo. Repo instructions prohibit UDDM integration.
- Prepared synthetic periodic records are a proposed demo input. Whether any
  upload interaction belongs in the demo remains a decision, not a commitment.
- A recent payment does not establish freshness of a whole financial statement.
  APDP production account coverage and end-to-end freshness are not proven.
- Existing context: [payment workspace](../../docs/PAYMENT_WORKSPACE.md),
  [APDP connector plan](../../apdp/docs/DEALER_CONNECTORS.md),
  [architecture](../../ARCHITECTURE.md), [domain glossary](../../CONTEXT.md).
- Each session consults wayfinder, grilling and domain-modeling. The prototype
  ticket additionally uses prototype and relevant UI skills.
- Tracker: local Markdown. Child tickets live in `issues/`. Scan open, unassigned
  children by number; a child is unblocked when all `Blocked by` tickets are
  resolved. Claim by setting `Status: claimed` and `Assignee:` before work.
  Resolve by appending `## Answer`, setting `Status: resolved`, and linking the
  answer here. Map decisions live in child tickets, not duplicated in this index.
- Charting session only: no child ticket is claimed or resolved during creation.

## Decisions so far

<!-- Closed-ticket index only. Initial user-agreed scope is recorded in Notes. -->

## Not yet specified

- Implementation boundaries and delivery sequence once statement scope and the
  demonstration experience are agreed.
- Further source-specific investigations that may emerge from the agreed evidence
  requirements, including whether the reported internal platform holds usable
  records. Do not speculate about its schema or promise access.

## Out of scope

- Building, deploying or integrating the feature during this planning map.
- Live dealer data, production banking connections, and internal upload-platform
  integration during the demonstration.
- Automated funding decisions, dealer rankings or recommended funding amounts.
- A dealer self-service portal, production write-back, and commission recalculation.
- Presenting synthetic or incomplete records as verified full-business statements,
  or promising real-time freshness for periodic records.
