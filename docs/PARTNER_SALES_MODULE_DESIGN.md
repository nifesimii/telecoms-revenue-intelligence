# Partner Sales & Account — design interview

Status: both interview rounds accepted; synthesized in
[the specification](PARTNER_SALES_SPEC.md). Specification testing boundaries and
issue-tracker setup await confirmation; implementation has not started.

## Agreed direction

- MTN is the seller; trade partners are the buyers.
- Primary presentation audience: MTN Finance and channel leadership.
- Present one partner's purchases, invoices, and commission account together.
- Demonstrate interactive simulated invoicing using fictional data.
- Partner Commission Account means recorded earnings, settlements, and
  outstanding commission owed by MTN; invoice balances are separately visible.
- Capture resolved domain terms in CONTEXT.md and the presentation scope
  boundary in docs/adr/0001-partner-sales-presentation-boundary.md.

## Accepted second-round decisions

- Product coverage: FBB devices and physical recharge cards; no recharge-card
  commission policy or calculation is added.
- Invoice demonstration: draft creation, preview, simulated issuance, partial/full
  payment recording, and outstanding balances; no reservation or fulfilment.
- Commission account: opening outstanding, recorded earnings, settlements, closing
  outstanding, and dated fictional activity. Invoicing does not generate earnings.
- No commission offsetting against invoice obligations.
- A distinct Partner Sales workspace with partner detail linking to existing
  commission account evidence and explanations.

## Specification defaults

The specification supplies explicitly identified implementation defaults for
invoice fields, fixed fictional pricing, dates, simulation persistence/reset,
missing evidence, navigation, acceptance examples, and ticket boundaries.
These defaults are not assertions about actual MTN commercial or tax policy.

Existing inventory is purchase-versus-activation evidence, not available stock.
Existing payment statements are a useful account foundation, but period totals
alone do not provide a transaction-level running ledger.
