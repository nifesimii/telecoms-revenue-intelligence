# Create and preview a simulated partner invoice

## What to build

An internal presenter opens Partner Sales, selects an exact trade partner, creates a mixed FBB-device and physical-recharge-card invoice draft, edits it, and previews the amount MTN would invoice. This is the first complete presentation slice, including its small fictional catalogue, session state, and reproducible browser acceptance harness.

## Acceptance criteria

- [ ] Partner Sales appears in the existing navigation and retains the reporting month. Partner selection exposes exact account codes and never merges similar names.
- [ ] The bounded fictional catalogue shows product code, description, unit and fixed price. Drafts support multiple lines, positive whole quantities, edits and removals; invalid or empty drafts cannot proceed.
- [ ] Totals use exact minor-unit arithmetic. Two devices at NGN 50,000.00 and 100 cards at NGN 100.00 yield NGN 110,000.00.
- [ ] Preview identifies MTN as seller, the selected partner as buyer, a stable simulation reference, dates, lines and total. It states that taxes and discounts are not modeled and this is not an operational tax invoice.
- [ ] Drafts survive workspace navigation and same-tab refresh in session-scoped simulation storage. Storage failure is visible. Drafts do not create invoice obligations or commission.
- [ ] A repeatable browser acceptance test completes draft creation, correction and preview, and verifies no financial mutation requests. Include basic accessible controls and responsive preview from this slice onward.
- [ ] Simulation is visibly fictional and remains isolated from actual financial evidence, even in live-read mode; no operational write endpoints, production mutations, or new commission calculations are introduced.
- [ ] User-visible acceptance tests cover this slice with deterministic fixtures and no live Presto or paid model calls; use the rendered workspace boundary and reuse existing public API regression coverage where applicable.
- [ ] Keyboard operation, validation, empty/unavailable states, narrow layouts, and NGN formatting work for the behavior introduced in this ticket.

## Blocked by

None (can start immediately).
