# Partner Sales rehearsal

A repeatable presenter script for the two-login story: a partner orders, MTN Finance
issues and collects, and the partner sees each step and their own commission account. Everything on the Partner Sales screens is fictional and is held in
the API server's memory, shared by everyone signed in until it restarts. See the [specification](PARTNER_SALES_SPEC.md) and
scope decisions ([presentation boundary](adr/0001-partner-sales-presentation-boundary.md),
[two logins](adr/0002-partner-sales-two-logins.md)).

## Setup

Install dependencies and create `.env` as in the README's setup section, with
`USE_SAMPLE_DATA=true`. Then start both servers from the repository root:

```sh
uvicorn backend.main:app        # http://localhost:8000
npm --prefix frontend run dev   # http://localhost:5173
```

The login page and both signed-in views should say the records are fictional.

### Two separate browser contexts

Sign-in cookies are shared by every tab and window in one browser profile, so signing in
as the partner in a second tab replaces Finance's session in the first. The first tab
refuses to act for the new login: on its next action, or when you return to it, it goes
back to sign-in saying the browser is now signed in as a different user. Use two separate
contexts, side by side:

- **Finance window:** a normal window. Open
  `http://localhost:5173/?view=partner-sales&period=202605` and sign in with the internal
  login from `DEMO_LOGINS`. The header shows **Synthetic demonstration** and **May 2026**.
- **Partner window:** a private (incognito) window, or a second browser profile. Sign in as
  **partner-296065**. The header shows **Partner account 296065**.

Neither side sees the other's changes until it refreshes the page; there is no live push.

### Before a hosted presentation

Do not deploy right before presenting. A deploy or restart returns the simulation to its
seed for everyone, and a slow first build can leave the service unavailable. Deploy the day
before, rehearse on the hosted service, then **Reset simulation** shortly before you start.
See [DEPLOY.md](DEPLOY.md) for the hosted logins. In live-read mode the invoice story still runs, but the
commission account offers no explanation links and says why.

## Sequence

Records are shared and outlast the tab, so start at step 1 unless the API server has just started.

Finance works across three tabs: **Orders to review**, **Invoices** and **Partner accounts**. The partner has four: **Order**, **My orders**, **Invoices** and **Commission**. Refreshing returns each side to its first tab. **Reset simulation** is in the page header, which order, invoice and account details hide, so go back to a tab first.

| # | Window | Do | Expect |
| --- | --- | --- | --- |
| 1 | Finance | **Reset simulation**, then **Reset to starting point**. Open **Invoices**, then return to **Orders to review** | Notice says 3 example invoices in May 2026 and the next invoice will be SIM-INV-0004. 3 matching invoices: Paid, Partially paid and Unpaid, with NGN 180,000.00 outstanding. Order SIM-ORD-0001 awaits review. |
| 2 | Partner | Refresh, then **Start a draft order**. Open **My orders**, **Invoices** and **Commission**, then return to **Order** | No orders or invoices yet. An empty draft order for River Isle Ventures · Account 296065. Commission account for June 2026 closes at NGN 1,418,759.61. |
| 3 | Partner | Add **FBB-5G-ROUTER**, quantity 2. Add **RCC-0100**, quantity 100. **Preview order**, then **Submit order**. Open **My orders** | Lines NGN 100,000.00 and NGN 10,000.00, total NGN 110,000.00. The order is listed as SIM-ORD-0002, Submitted. |
| 4 | Finance | Refresh the page, then **Review** SIM-ORD-0002 | The order for River Isle Ventures · Account 296065, total NGN 110,000.00, with issue date 31 May 2026. |
| 5 | Finance | Enter a due date, then **Issue invoice** | Invoice SIM-INV-0004 from partner order SIM-ORD-0002. Status Unpaid. Outstanding NGN 110,000.00. |
| 6 | Partner | Refresh. Open **My orders**, then **Invoices**, then SIM-INV-0004 | SIM-ORD-0002 is Issued. **Invoices** lists SIM-INV-0004, Unpaid, NGN 110,000.00 outstanding. Opening it shows no payment control. |
| 7 | Finance | On the open invoice, record a collection of **40000** | Recorded SIM-PAY-0003. Status Partially paid. Outstanding NGN 70,000.00. |
| 8 | Partner | Refresh, then open **Invoices** | SIM-INV-0004 is Partially paid, NGN 70,000.00 outstanding. |
| 9 | Finance | On the same invoice, record a collection of **70000** | Recorded SIM-PAY-0004. Status Paid. Collected NGN 110,000.00. Outstanding NGN 0.00. |
| 10 | Partner | Refresh, open **Invoices**, then SIM-INV-0004. Open **Commission** and choose **May 2026** | Paid, with both collections. Commission opening NGN 250,000.00, closing NGN 822,582.53, as before the order: invoices never change commission. No explanation links. |
| 11 | Finance | On the open invoice, **View all purchase obligations**, then **View commission account** | Obligations list only SIM-INV-0004. Opening NGN 250,000.00, earnings NGN 954,922.38, settlements NGN 382,339.85, closing NGN 822,582.53. |
| 12 | Finance | **Explain activation commission**, then **Return to Partner Sales** | Commission opens on account 296065, May 2026, with a banner saying it was opened from the simulation. Returning shows the same statement, with focus back on the link. |
| 13 | Optional, new private window | Sign in as **partner-353072**. Open **Invoices**, **My orders** and **Commission** | A same-named account sees no orders or invoices, and only its own May 2026 statement. |
| 14 | Finance | Use the **Back to** buttons until the tabs return, then **Reset simulation** and **Reset to starting point** | Back to the state after step 1. Partners have no reset control. |
| 15 | Partner | Refresh. Open **My orders** and **Invoices**, then return to **Order** | No orders, invoices or draft: the seed, for every partner. The next run gives the same references and amounts. |

To show a rejection instead, at step 5 enter a reason and **Reject order**. On their next
refresh the partner sees the order under **My orders** as Rejected with that reason, and starts a new draft to
order again.

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
| "Your session has ended" on the login page | The session expired (after 8 hours) or someone signed out in the same browser profile. Whatever was being sent was not applied | Sign in again |
| "This browser is now signed in as a different user" on the login page | The other side signed in within the same browser profile, replacing this window's session. Nothing was applied | Sign the other side in from a private window or second profile, then sign in here again |
| "This order was already decided" | Another Finance session decided it, or the simulation was reset. Nothing was applied | **Load latest orders** |
| The partner does not see Finance's change | Neither side updates on its own | Refresh the partner window |
| "This changed elsewhere or the simulation was reset" | Someone else changed this record or reset the simulation, so nothing was applied | **Load latest**, which discards what was typed on the page |
| "could not be saved" | The API could not be reached, so the latest edits are only on this page | Check the API, then **Try saving again** |
| "could not be reset" | The API could not be reached, so nothing changed | Check the API, then **Reset to starting point** again |
| "could not be checked" on Existing explanations | Recorded evidence could not be read. Statement figures are still shown | Check the API, then **Retry evidence check** |
| "does not reconcile" or "No recorded statement" | No explanation stands behind this statement, so no link is offered | Use account 296065 in May 2026 |
| "Requested account unavailable" in Commission | The explanation's evidence failed to load | **Retry account**, or **Return to Partner Sales** |
| "Payment position unavailable" in Payments | The settlement explanation's evidence failed to load | **Retry payment**, or **Return to Partner Sales** |
| "Reporting periods unavailable" | The API cannot be reached | Start the API, then reload. Restarting it returns the simulation to its seed |

Only an internal login can reset. A reset returns the simulation to its seed for everyone signed in, including every partner's draft; partners see it on their next refresh. It leaves recorded evidence, other
workspaces, other session data and the reporting month as they were. An explanation
already open keeps its **Return to Partner Sales** banner, which reopens the same
fictional statement: statements hold no invoice or collection data, so nothing is restored.

## Automated check

```sh
npm --prefix frontend run test:acceptance
```

`frontend/tests/acceptance/order-review.spec.js` runs the two-login story in separate
browser contexts against the real sample-mode API: the full order-to-paid example, a
rejection, a reset reaching a signed-in partner, an ended session, and the flows by
keyboard at 360px. `frontend/tests/acceptance/partner-sales.spec.js` covers Finance's
invoice and commission screens, through a reset and by keyboard at 320px. Neither makes
Presto or model calls.
