# Reset and replay the complete Partner Sales presentation

## What to build

A presenter can reset a rehearsal to known seed data and run the complete invoice, collection and commission explanation story reliably, including refresh, navigation and recoverable failures. Earlier tickets already include their own validation and accessibility; this slice adds reset/recovery behavior and verifies their integration.

## Acceptance criteria

- [ ] An explicit reset restores versioned simulation seeds and clears drafts, issued invoices and collections consistently without touching existing commission/payment/inventory sources or unrelated user state.
- [ ] Unavailable or incompatible session storage produces a clear recovery/reset path rather than silently corrupting data or implying persistence.
- [ ] The complete presentation creates and issues the mixed NGN 110,000.00 invoice, records NGN 40,000.00 then NGN 70,000.00, explains its status/history, and opens a commission account that remains unchanged throughout.
- [ ] Exact dealer and month survive explanation handoffs; return navigation, focus, refresh, filters and session state remain coherent. A missing evidence source supports an understandable retry or unavailable state.
- [ ] Synthetic provenance remains visible throughout, including live-read configuration. No net balance, commission-funded payment, stock reservation, real invoice issuance, new agent tools or production writes appear.
- [ ] Run reproducible browser acceptance coverage for the integrated scenario, keyboard and narrow-screen checks, relevant existing frontend/sample-mode backend regressions and the frontend production build.
- [ ] Record a concise rehearsal sequence and expected results so the presenter can repeat the story without undocumented setup.
- [ ] Simulation is visibly fictional and remains isolated from actual financial evidence, even in live-read mode; no operational write endpoints, production mutations, or new commission calculations are introduced.
- [ ] User-visible acceptance tests cover this slice with deterministic fixtures and no live Presto or paid model calls; use the rendered workspace boundary and reuse existing public API regression coverage where applicable.
- [ ] Keyboard operation, validation, empty/unavailable states, narrow layouts, and NGN formatting work for the behavior introduced in this ticket.

## Blocked by

- Draft ticket 02: Issue simulated invoices and inspect partner obligations
- Draft ticket 03: Record partial and full simulated invoice collections
- Draft ticket 04: Explain commission buildup and link to existing evidence
