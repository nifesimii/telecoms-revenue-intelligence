# Explain commission buildup and link to existing evidence

## What to build

A presenter selects a partner in Partner Sales and opens a dated Partner Commission Account, explains opening outstanding, earnings, settlements and closing outstanding, and follows exact-account/month links into existing commission or payment explanations. This slice can proceed after draft creation; it does not require invoice issuance or collections.

## Acceptance criteria

- [ ] Use coherent, clearly fictional statement fixtures with stable partner identities, dated activity and source references. Do not fabricate opening balances or dates from existing monthly totals.
- [ ] When all evidence is available, closing outstanding equals opening outstanding plus period earnings minus settlements. An independent acceptance fixture of NGN 20,000.00 + NGN 15,000.00 - NGN 10,000.00 closes at NGN 25,000.00.
- [ ] Activation commission and separately evidenced subscription commission remain distinct; subscription revenue is not commission entitlement. Recharge-card commissions are excluded.
- [ ] Missing opening balances, earnings or settlements remain unavailable rather than zero or a misleading partial total. Recorded zero entries remain distinguishable.
- [ ] Activity lists are bounded to at most 100 rows per page, have deterministic ordering, and reconcile to complete statement totals.
- [ ] Existing explanation links preserve exact partner and reporting month. Fixture-linked sample statements reconcile on the same period basis; opening carry-forward is separately disclosed from period-only totals.
- [ ] Unavailable or incompatible account evidence shows an unavailable handoff, not a substitute dealer. Synthetic activity is never injected into live Atlas context or financial source records.
- [ ] Returning from an explanation restores sales context. Existing read-only statement/API contracts are reused, with existing sample-mode regression coverage retained.
- [ ] Browser acceptance tests cover the statement reconciliation, unavailable-versus-zero cases, stream distinctions, exact navigation and provenance. Draft activity leaves commissions unchanged.
- [ ] Simulation is visibly fictional and remains isolated from actual financial evidence, even in live-read mode; no operational write endpoints, production mutations, or new commission calculations are introduced.
- [ ] User-visible acceptance tests cover this slice with deterministic fixtures and no live Presto or paid model calls; use the rendered workspace boundary and reuse existing public API regression coverage where applicable.
- [ ] Keyboard operation, validation, empty/unavailable states, narrow layouts, and NGN formatting work for the behavior introduced in this ticket.

## Blocked by

- Draft ticket 01: Create and preview a simulated partner invoice
