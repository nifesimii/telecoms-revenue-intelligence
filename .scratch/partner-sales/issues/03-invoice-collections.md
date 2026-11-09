# Record partial and full simulated invoice collections

## What to build

A presenter records a fictional collection against an issued invoice, inspects its dated payment history and remaining balance, then completes payment. The invoice changes from unpaid to partially paid to paid without affecting commissions.

## Acceptance criteria

- [ ] A collection has a date, reference, positive exact amount and stable action identifier, and belongs to one issued invoice.
- [ ] For an NGN 110,000.00 invoice, NGN 40,000.00 produces NGN 70,000.00 outstanding and partially paid status; the remaining NGN 70,000.00 produces paid status and zero outstanding.
- [ ] Draft payments, nonpositive payments, overpayments, payments before issuance, and payments on fully paid invoices are rejected without changing valid balances.
- [ ] Repeated submission of the same action has one effect. Payment history, invoice detail and matching-set summaries agree after refresh and navigation.
- [ ] Detail displays all recorded collections and an explicit balance-as-of date. Later collections are not silently represented as a historical month-end balance.
- [ ] Collections neither generate commission nor offset existing commission outstanding. No payment gateway, bank reconciliation, refunds or reversals are added.
- [ ] Acceptance tests exercise the whole payment journey plus duplicate submissions, invalid amounts, date validation and cross-partner isolation.
- [ ] Simulation is visibly fictional and remains isolated from actual financial evidence, even in live-read mode; no operational write endpoints, production mutations, or new commission calculations are introduced.
- [ ] User-visible acceptance tests cover this slice with deterministic fixtures and no live Presto or paid model calls; use the rendered workspace boundary and reuse existing public API regression coverage where applicable.
- [ ] Keyboard operation, validation, empty/unavailable states, narrow layouts, and NGN formatting work for the behavior introduced in this ticket.

## Blocked by

- Draft ticket 02: Issue simulated invoices and inspect partner obligations
