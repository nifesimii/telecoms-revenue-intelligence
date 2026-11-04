# Issue simulated invoices and inspect partner obligations

## What to build

A presenter explicitly issues a valid draft, then locates and opens the unpaid invoice from a bounded invoice list and partner detail. The presenter can explain exactly what the partner owes for purchases without treating it as commission.

## Acceptance criteria

- [ ] Issuance happens once per draft and freezes buyer, commercial lines and total. Issued invoices begin unpaid; repeated issuance does not duplicate an obligation.
- [ ] Invoice listing supports partner/code search, status filtering, deterministic ordering and pages of at most 100 records. Matching-set summaries do not change merely because the page changes.
- [ ] Lists use issue month, drafts use intended issue month, and invoices retain their original dates and amounts when reporting month changes.
- [ ] Partner detail shows invoice purchase obligations with explicit balance-as-of meaning, separately labelled from any commission account. Drafts remain excluded from outstanding totals.
- [ ] Opening detail and returning restores list filters, page and focus. Empty results and unavailable simulation state are understandable.
- [ ] Acceptance coverage proves draft-to-unpaid transition, immutable issued details, duplicate-issuance safety, account isolation, bounded filtering and complete matching totals.
- [ ] Existing Inventory and Payments backend-owned pagination, aggregates, shared reads, cache behavior and inactive-subtab rules remain unchanged.
- [ ] Simulation is visibly fictional and remains isolated from actual financial evidence, even in live-read mode; no operational write endpoints, production mutations, or new commission calculations are introduced.
- [ ] User-visible acceptance tests cover this slice with deterministic fixtures and no live Presto or paid model calls; use the rendered workspace boundary and reuse existing public API regression coverage where applicable.
- [ ] Keyboard operation, validation, empty/unavailable states, narrow layouts, and NGN formatting work for the behavior introduced in this ticket.

## Blocked by

- Draft ticket 01: Create and preview a simulated partner invoice
