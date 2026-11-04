# Partner Sales and Partner Commission Account

Status: specification draft; agreed product scope captured. Testing boundaries
await confirmation. Issue-tracker setup is not recorded; publication is pending.

## Problem Statement

MTN Finance and channel leadership need to see a coherent partner relationship:
what MTN sells to a trade partner, what the partner owes on those purchases, and
what MTN owes the partner in commission. The current intelligence application
explains commissions and settlements and compares recorded purchases with
activations, but cannot demonstrate creating an invoice or receiving payment
against it. Monthly commission totals alone do not show how an outstanding
commission balance builds up over time.

For the MVP presentation, disconnected sales and commission screens would make
this relationship difficult to explain. Treating both obligations as one net
balance would also imply an offsetting policy that has not been established.

## Solution

Add an internal **Partner Sales** workspace. Using explicitly fictional data,
a presenter selects a trade partner, creates and previews an MTN sales invoice
for FBB devices and physical recharge cards, simulates issuance, and records
partial or full payment. The workspace shows invoice status and remaining
purchase obligations.

Partner detail also presents a **Partner Commission Account** with opening
outstanding commission, recorded earnings, settlements, closing outstanding
commission, and dated activity. Links into existing commission explanations
retain exact partner identity and reporting period. Invoice balances and
commission balances remain separate. Sales actions never generate commission
entitlement or change the existing financial evidence.

This is an interactive presentation simulation, not operational invoice issuance,
a partner portal, or a replacement commission engine.

## User Stories

1. As an MTN Finance presenter, I want to open Partner Sales from the existing application navigation, so that the demonstration feels like one product.
2. As a channel leader, I want to see that MTN sells to trade partners, so that the commercial relationship is unambiguous.
3. As a presenter, I want every simulated screen and invoice preview to identify its fictional nature, so that viewers do not mistake the demo for actual obligations.
4. As a presenter, I want to find a partner by exact account code or displayed name, so that I can select the intended account.
5. As a Finance user, I want similar partner names to remain separate accounts, so that one partner's activity is never attributed to another.
6. As a presenter, I want to retain my reporting month when entering the workspace, so that the sales and commission story has a consistent context.
7. As a presenter, I want a catalogue containing FBB devices and physical recharge cards, so that I can demonstrate the agreed product range.
8. As a presenter, I want to see each product's code, description, unit, and fictional unit price, so that invoice lines are understandable.
9. As a presenter, I want to create an invoice draft for one selected partner, so that the buyer is explicit before issuance.
10. As a presenter, I want to add multiple products and quantities to a draft, so that a mixed purchase can be demonstrated.
11. As a presenter, I want to edit or remove draft lines, so that mistakes can be corrected before issuance.
12. As a presenter, I want invalid quantities or incomplete drafts to produce clear validation messages, so that I can correct the input.
13. As a Finance user, I want line totals and invoice totals to reconcile exactly, so that the displayed purchase obligation is credible.
14. As a presenter, I want to preview the draft with seller, buyer, reference, dates, lines, and total, so that I can explain it before issuance.
15. As a presenter, I want to simulate issuance explicitly, so that saving a draft does not create an outstanding invoice balance.
16. As a Finance user, I want an issued invoice's commercial details to remain fixed, so that later payments refer to a stable obligation.
17. As a presenter, I want to distinguish draft, unpaid, partially paid, and paid invoices, so that each example is easy to explain.
18. As a presenter, I want to record a fictional payment against an issued invoice, so that I can demonstrate collection.
19. As a presenter, I want to record a partial payment, so that the remaining balance is visible.
20. As a presenter, I want to record the remaining payment, so that an invoice can reach a paid state.
21. As a Finance user, I want invalid or excessive payments to be rejected, so that the simulation cannot silently overpay an invoice.
22. As a Finance user, I want repeated submission of the same payment action to have only one effect, so that accidental double clicks do not duplicate collections.
23. As a presenter, I want to inspect payment amounts, dates, and references, so that the outstanding balance is explainable.
24. As a presenter, I want to search and filter invoices by partner and status, so that I can find the relevant example quickly.
25. As a Finance user, I want list totals to describe their whole matching set, so that changing pages does not change the meaning of the summary.
26. As a presenter, I want partner detail to show invoice obligations separately from commission owed by MTN, so that opposite obligations are not conflated.
27. As a Finance user, I want to see opening outstanding commission, period earnings, settlements, and closing outstanding commission, so that buildup is explained.
28. As a Finance user, I want dated commission activity and source references, so that I can trace a balance change.
29. As a Finance user, I want activation and evidenced subscription commission identified separately, so that different earning streams remain understandable.
30. As a Finance user, I want subscription revenue distinguished from subscription commission, so that revenue is not presented as entitlement.
31. As a presenter, I want invoice issuance and invoice payments to leave the commission account unchanged, so that the demo does not invent commission rules.
32. As a Finance user, I want unavailable evidence distinguished from recorded zero amounts, so that missing information is not misrepresented.
33. As a presenter, I want links to existing commission and payment explanations to preserve partner and month, so that the audience can investigate the same account.
34. As a presenter, I want an explicit explanation when no matching account or period evidence exists, so that navigation does not substitute an unrelated partner.
35. As a presenter, I want to return from an explanation to my sales context, so that the presentation can continue smoothly.
36. As a presenter, I want predictable demo state and an explicit reset, so that rehearsals and repeat presentations start consistently.
37. As a presenter, I want clear empty, loading, and recoverable failure states, so that interruptions are understandable.
38. As a keyboard user, I want usable forms, validation, dialogs, and focus restoration, so that I can complete the demonstration without a pointer.
39. As a presenter, I want the workspace and invoice preview to fit laptop and narrow screens, so that key information remains accessible.
40. As an MTN stakeholder, I want fictional sales transactions isolated from real commission and inventory evidence, so that a demonstration cannot change operational conclusions.

## Implementation Decisions

### Agreed product and architecture boundaries

- Add Partner Sales as a distinct workspace in the existing internal application.
  Reuse its navigation, reporting-period context, formatting, and exact-account
  handoff conventions.
- MTN is the seller and the trade partner is the buyer. This is not downstream
  trade-partner-to-retailer invoicing.
- The catalogue covers FBB devices and physical recharge cards. Recharge-card
  commission policies and calculations are excluded.
- Support draft creation and editing, preview, simulated issuance, partial/full
  payment recording, invoice balances, and a dated Partner Commission Account.
- Sales obligations and commission outstanding are separately labelled. There
  is no combined net balance, commission wallet, or commission-funded payment.
- Commission entries are recorded evidence or explicit fictional demonstration
  entries. Invoice creation, issuance, and collection do not trigger earnings.
- Preserve activation and subscription commission distinctions. Subscription
  revenue alone cannot establish entitlement; missing settlements are not zero.
- Do not infer saleable stock, stock reservation, or fulfilment from the existing
  inventory purchase-versus-activation evidence.
- Preserve the existing bounded Inventory and Payments contracts, maximum page
  size of 100, backend-owned filtering/counts/aggregates, shared Payments reads,
  on-demand evidence, and bounded query caching. This feature must not add an
  alternative unbounded path or mount inactive Payment sub-tabs.
- No operational write API, production writeback, new commission calculations,
  production schema migration, or additional agent tools are required.

### Proposed implementation defaults for ticketing

These details close unspecified implementation choices; they were not separately
approved business policies. They apply only to this presentation simulation.

- Keep synthetic invoice drafts, issued invoices, and collections in a dedicated
  browser simulation store. Use session-scoped persistence across refresh and
  workspace navigation, with explicit reset to versioned seed data. Do not share
  records between users or write them to backend financial sources. If storage
  is unavailable or incompatible, show a clear recovery/reset state.
- Use a small, explicitly bounded fictional catalogue and partner cohort. New
  invoice and activity lists use bounded views (at most 100 rows per page),
  deterministic ordering, and summaries over the complete matching simulation
  set. Browser-owned simulation state is not a replacement for backend-owned
  Inventory or Payments collection processing.
- Represent money with exact minor-unit arithmetic and display NGN X,XXX,XXX.XX.
  Catalogue prices are fixed demo values; quantities are positive whole units.
  Invoice totals are the sum of line totals. Taxes and discounts are not modeled;
  the preview must say this is a simplified demonstration, not a tax invoice.
- An invoice includes a stable simulation identifier/reference, exact dealer
  account, seller label, issue date, optional due date, currency, product lines,
  quantities, unit prices, total, and synthetic provenance. Use date-only values
  consistently and do not change amounts when the reporting month changes.
- Drafts do not contribute to invoice obligations. On simulated issuance,
  freeze partner, lines, and total. Status derives from issuance and collections:
  unpaid when none, partially paid when below total, paid when equal to total.
  Issuance must not occur twice for the same draft.
- Payments apply to one issued invoice and contain a unique action identifier,
  date, reference, and positive amount no greater than its outstanding balance.
  Duplicate submission of the same action is idempotent. Reject draft payments,
  payments dated before issuance, and payments on fully paid invoices.
- Invoice lists are scoped by invoice issue month (drafts by intended issue month).
  Detail shows all recorded collections and an explicit balance-as-of date;
  later collections must not be silently presented as a historical month-end
  balance. Commission statements are scoped to the selected calendar month.
- Commission opening balances and dated activity come from a coherent fictional
  statement fixture. Closing outstanding equals opening outstanding plus recorded
  earnings minus settlements when all inputs are available. Never manufacture
  transaction dates or opening balances from existing monthly totals.
- Reuse existing read-only account/statement interfaces for explanation links.
  Any fixture account connected to them must use an exact sample account and
  reconcile the same period and commission basis. Show the opening carry-forward
  separately from the existing period-only statement; do not imply those totals
  are interchangeable. Where no coherent fixture exists, show the unavailable
  handoff rather than inventing or relabelling evidence.
- Keep simulation provenance visible even when the application is configured for
  live reads. Do not pass synthetic sales activity into live Atlas context or
  merge it into existing payments, inventory, or Financial Health evidence.
- Render partner/product input as text, preserve keyboard interaction and focus,
  and provide validation, empty, unavailable, retry, and reset states. Invalid
  actions leave previously valid balances unchanged.

## Testing Decisions

Proposed boundaries await user confirmation before issue publication.

- **Primary new boundary: the rendered application workspace.** Exercise the
  invoice lifecycle, collections, commission display, persistence/reset, and
  cross-workspace navigation through user-visible controls. Assert observable
  amounts, statuses, labels, and account/month context, not component state,
  private helpers, snapshots of markup, or storage implementation details.
- **Reuse existing public API boundaries for commission regression.** Existing
  FastAPI TestClient coverage checks subscription commission evidence, missing
  settlements, exact-account statements, bounded results, and separation of
  sample versus live data. Extend those tests only if those contracts change;
  do not create a second statement calculation merely to test this feature.
- Prior art includes existing browser verification of Payment navigation and
  account/month continuity, Node presentation tests for missing values and
  synthetic provenance, subscription workspace HTTP contract tests, and dealer
  statement evidence tests. Browser checks are documented, but the frontend
  package currently has no configured browser-test runner. The implementation
  must establish a reproducible browser acceptance harness for this boundary.
- Cover draft editing and validation; exact invoice totals; one-time issuance;
  partial and full payments; invalid and duplicate payment actions; isolation
  between partners; deterministic paging/filter summaries; and unchanged
  commission balances after all sales actions.
- Cover opening-plus-earnings-minus-settlements reconciliation, independent
  commission streams, missing versus zero evidence, no fabricated dates, and
  no implication that invoice activity earns commission.
- Cover exact account/month handoffs, unavailable links, return context,
  refresh/reset, keyboard operation, responsive layouts, and synthetic labels.
- Assert that sales actions issue no financial mutation requests and do not alter
  existing evidence responses. Run acceptance checks with fictional fixtures,
  sample data, and mocked unavailable dependencies; no live Presto or paid model
  calls are needed.
- Run relevant existing sample-mode backend regressions, frontend tests, and
  the production frontend build when implementing. Tests must not simply mirror
  helper implementations; expected balances should be independently specified.

## Out of Scope

- Real invoice issuance, legal/tax invoice compliance, tax determination,
  discounts, credit notes, cancellations after issuance, refunds, or reversals.
- Invoice PDF/export generation, invoice emailing, notifications, and reminders.
- Payment gateways, bank reconciliation, real collections, commission offsetting,
  approval chains, credit limits, or shared accounting ledgers.
- Partner authentication, partner self-service, downstream retailer accounts,
  multi-tenant isolation, or concurrent multi-user transaction processing.
- Stock availability, reservations, warehouse operations, fulfilment, device
  serial allocation, procurement, and stock valuation.
- Recharge-card commissions, MoMo, VTU, bonuses, new commission policies,
  commission recalculation, or inferring ORSC entitlement from revenue.
- Production writes, live sales ingestion, new agent tools, and changes to the
  existing Financial Health whole-business financial model.

## Further Notes

### Presentation acceptance example

Use fictional demo prices and values, never represent them as MTN price lists.
Create an invoice for two FBB devices at NGN 50,000.00 each and 100 physical
recharge cards at NGN 100.00 each. The invoice total is NGN 110,000.00.
Recording NGN 40,000.00 produces a partially paid invoice with NGN 70,000.00
outstanding; recording the remaining NGN 70,000.00 produces a paid invoice.

Separately, a fictional commission statement with NGN 20,000.00 opening
outstanding, NGN 15,000.00 earnings, and NGN 10,000.00 settlements closes at
NGN 25,000.00. All invoice actions leave that balance unchanged. These numbers
are acceptance-example values, not asserted values for an existing sample dealer.
A fixture used for existing explanation links must reconcile with that dealer's
sample evidence instead.

### Suggested ticket boundaries and ordering

1. Simulation foundation: bounded seed catalogue/cohort, invoice and collection
   behavior, provenance, exact money, session persistence/reset, and browser
   acceptance harness. Establish a minimal observable workspace entry point.
2. Partner Sales invoice journey: partner selection, drafts, validation, preview,
   one-time issuance, invoice list, filtering/paging, and partner detail.
3. Collections: partial/full payments, history, duplicate-action protection,
   outstanding summaries, and invalid-action behavior.
4. Partner Commission Account: coherent opening/activity/closing fixtures,
   independent sales/commission balances, stream distinctions, missing evidence,
   and exact-account links to existing explanations.
5. Presentation completion: navigation continuity, recovery states, accessibility,
   responsive verification, deterministic reset, and the full acceptance scenario.

Each ticket includes its own observable acceptance checks; testing is not deferred
to the last ticket. The foundation precedes the invoice journey; collections
build on issued invoices; final presentation acceptance covers all slices.

The design interview's product recommendations have been accepted. Publication
as a parent specification issue with the ready-for-agent label is pending the
required testing-boundary check and project issue-tracker configuration. Child
ticket creation can use the boundaries above after the specification is published.
