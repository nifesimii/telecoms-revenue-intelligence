# Partner Sales rehearsal

A repeatable presenter script for the invoice, collection and commission
explanation story. Everything on the Partner Sales screens is fictional and stays
in one browser tab. See the [specification](PARTNER_SALES_SPEC.md) and
[scope decision](adr/0001-partner-sales-presentation-boundary.md).

## Setup

Install dependencies and create `.env` as in the README's setup section, with
`USE_SAMPLE_DATA=true`. Then start both servers from the repository root:

```sh
uvicorn backend.main:app        # http://localhost:8000
npm --prefix frontend run dev   # http://localhost:5173
```

Open `http://localhost:5173/?view=partner-sales&period=202605`. The header should
show **Synthetic demonstration** and the reporting period **May 2026**.

No other setup is needed. In live-read mode the invoice story still runs, but the
commission account offers no explanation links and says why.

## Sequence

If the tab has been used before, start at step 1. On a new tab, step 1 is optional.

| # | Do | Expect |
| --- | --- | --- |
| 1 | **Reset simulation**, then **Reset to starting point** | Notice says 3 example invoices in May 2026 and the next draft will be SIM-INV-0004. No partner selected. 3 matching records: Paid, Partially paid and Unpaid, with NGN 180,000.00 outstanding. |
| 2 | Select **River Isle Ventures · Account 296065**, then **Create draft** | Draft SIM-INV-0004, May 2026, intended issue date 31 May 2026. |
| 3 | Add **FBB-5G-ROUTER**, quantity 2. Add **RCC-0100**, quantity 100 | Lines NGN 100,000.00 and NGN 10,000.00. Draft total NGN 110,000.00. |
| 4 | **Preview invoice** | MTN as seller, the exact account as buyer, total NGN 110,000.00, and a statement that this is not a tax invoice. |
| 5 | **Issue simulated invoice** | Status Unpaid. Outstanding NGN 110,000.00. |
| 6 | Record a collection of **40000** | Recorded SIM-PAY-0003. Status Partially paid. Outstanding NGN 70,000.00. |
| 7 | Optional: refresh the page, then open SIM-INV-0004 from the list | The invoice and collection are still there. A refresh returns to the list and clears list filters. |
| 8 | Record a collection of **70000** | Recorded SIM-PAY-0004. Status Paid. Collected NGN 110,000.00. Outstanding NGN 0.00. History shows NGN 70,000.00 then NGN 0.00 outstanding after each collection. |
| 9 | **View purchase obligations**, then **View commission account** | Obligations list only SIM-INV-0004. Opening NGN 250,000.00, earnings NGN 954,922.38, settlements NGN 382,339.85, closing NGN 822,582.53. The invoice did not change them. |
| 10 | **Explain activation commission** | Commission opens on account 296065, May 2026, with a banner saying it was opened from the simulation and shows existing evidence. |
| 11 | **Return to Partner Sales** | Same statement and figures, with focus back on the link. Repeat for **Explain subscription commission** and **Explain settlement**. |
| 12 | **Reset simulation**, then **Reset to starting point** | Back to the state after step 1, with the example invoices restored. The next run gives the same references and amounts. |

## Points to say

- The purchase obligation is what the partner would owe MTN. Commission is what MTN
  would owe the partner. They are separate balances and are never netted.
- Invoices and collections never create, reduce or fund commission.
- Existing explanations show period-only recorded totals. The statement's opening
  carry-forward of NGN 250,000.00 is fictional and is not part of them.
- There is no stock reservation, real invoice issuance or production write.
- The three example invoices are fictional too. The partner names come from the sample
  data, but those partners owe nothing. They exist only in May 2026, on other accounts,
  so they never touch account 296065.

## If something goes wrong

| You see | Meaning | Do |
| --- | --- | --- |
| "could not be restored" | The saved simulation is from another version or is damaged | **Start a new simulation** |
| "could not be saved" | Session storage is unavailable, so a refresh loses the work | Avoid refreshing, or **Try saving again** |
| "this reset could not be saved" | The earlier simulation may return on refresh | **Try saving again**, or use a new tab |
| "could not be checked" on Existing explanations | Recorded evidence could not be read. Statement figures are still shown | Check the API, then **Retry evidence check** |
| "does not reconcile" or "No recorded statement" | No explanation stands behind this statement, so no link is offered | Use account 296065 in May 2026 |
| "Requested account unavailable" in Commission | The explanation's evidence failed to load | **Retry account**, or **Return to Partner Sales** |
| "Payment position unavailable" in Payments | The settlement explanation's evidence failed to load | **Retry payment**, or **Return to Partner Sales** |
| "Reporting periods unavailable" | The API cannot be reached. The simulation is kept | Start the API, then reload |

A reset affects only this tab's simulation. It leaves recorded evidence, other
workspaces, other session data and the reporting month as they were. An explanation
already open keeps its **Return to Partner Sales** banner, which reopens the same
fictional statement: statements hold no invoice or collection data, so nothing is restored.

## Automated check

```sh
npm --prefix frontend run test:acceptance
```

`frontend/tests/acceptance/partner-sales.spec.js` runs this sequence through a reset
and again by keyboard at 320px, using fixtures: no backend, Presto or model calls.
