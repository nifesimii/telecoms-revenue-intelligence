# FBB Trade Partner Intelligence — Demo Guide

A short read-along for the preview at
[https://fbb-preview.onrender.com](https://fbb-preview.onrender.com). Log
in with the credentials shared separately.

> **Everything you see is fictional sample data.** No real MTN systems are
> connected. Numbers are for shape-testing the platform; treat them as
> illustrative, not indicative.

---

## What this platform does

Explains, validates, and audits FBB trade-partner commissions so Finance
and Revenue Assurance can answer four kinds of questions with evidence,
not with intuition:

1. **What do we owe each partner this month?**
2. **Why did a partner's commission change vs last month?**
3. **Why did a specific partner earn zero commission?**
4. **Can we prove, step-by-step, that we paid a partner the right amount?**

The last one is the newest addition — a persisted *verification chain*
(audit trail) behind every finding, not just a text explanation.

---

## The six tabs

**Overview** — the landing page. Answers "is this month OK, and if not
where do I look first?" Three bands stacked top-down:
- **Posture** — module-level PASS / FLAG counts + severity roll-up
- **Audit coverage** — trail counts per audit module for the period
- **Dealers across multiple modules** — the "look here first" list
Every card links into the deeper tab that owns that data.

**Commission Intelligence** — Ask Claude about any partner. Claude has
access to four data tools + the domain knowledge base and cites the
tools it used in every answer. Good for open-ended investigation.

**Activation Intelligence** — Per-dealer activation totals, qualification
rates, and month-on-month variance. Three sub-tabs (Summary / Variance /
Exceptions) with a search filter that persists across sub-tabs.

**Inventory Intelligence** — Activations vs IFS invoiced purchases,
per (dealer, product). Flags `CONFIRMED_MISMATCH` (activations exceed
purchases), `NO_INVOICE_RECORD` (activations with no matching invoice —
possibly outside the data window), or `WITHIN_ALLOCATION` (fine).

**Payment Intelligence** — Coverage card + per-dealer payment table +
period-over-period variance. Shows whether we're on the simulated payment
feed or wired to APDP.

**Audit Trails** — The verification-chain browser. Pick a module + a
period + click **Run**. Every "Partner X was/wasn't paid" claim gets a
persisted 6-step chain a reviewer can walk through and challenge.

---

## The four audit modules

Every module answers a different question about the same underlying data.
They coexist by design — a partner can (and usually will) appear across
several with different verdicts.

**1. Zero-Commission** — *"Was Partner X paid for their zero-commission
records for period Y?"* Narrow, per-partner. Conclusions: `PAID` /
`NOT_PAID` / `INSUFFICIENT_DATA`. On sample data this reads mostly LOW
confidence — ambiguous data on purpose.

**2. Inventory Mismatch** — *"Do Dealer X's activations of product Y
exceed invoiced purchases in a way that isn't explained by carryover,
SKU consolidation, or an ingestion gap?"* One trail per (dealer, product).
Conclusions: `RECONCILED` / `EXCESS_ACTIVATION` / `INSUFFICIENT_DATA`.
On sample data: 12 real EXCESS_ACTIVATION at HIGH confidence — those are
the actionable rows.

**3. Payment Reconciliation** — *"Was Partner X paid the correct amount
for period Y?"* Broader than Zero-Commission — covers every partner with
commission activity, not just zero-commission cases. Conclusions:
- `PAID_IN_FULL` — within ±1 NGN of expected
- `DISPUTED_ROUNDING` — off by <100 NGN or <1% (rounding / FX / small fees)
- `UNDERPAID` — paid less than expected beyond both tolerances
- `OVERPAID` — paid more than expected beyond both tolerances
- `INSUFFICIENT_DATA` — no activity or dataset gap
On sample data: 939 trails, dominated by `UNDERPAID`/MEDIUM+HIGH.

**4. Eligibility Window** — *"Are the zero-commission records genuinely
outside the 6-month invoice→activation window?"* Verifies the KB's
most-cited zero-commission root cause per IMEI. Conclusions:
- `POLICY_MET` — every zero-comm record legitimately outside the window
- `POLICY_VIOLATED` — inside-window records with no other explaining root
  cause (partner may be owed commission on the listed IMEIs)
- `MIXED_ATTRIBUTION` — inside-window records exist but every one is
  attributable to another documented cause (NULL profile / USP snapshot
  miss / Hynex alias) — the label is imprecise, not the underlying
  calculation
- `INSUFFICIENT_DATA`
On sample data: 487 trails, dominated by `MIXED_ATTRIBUTION`/HIGH — real
Finance insight that the "6-month rule" label is often being pinned when
another root cause is the actual driver.

### Confidence

Every trail carries a `HIGH` / `MEDIUM` / `LOW` confidence, driven by how
many step-level caveats fired. `HIGH` means the chain was clean, `LOW`
means read the step-by-step before acting.

---

## How to run an audit

1. **Audit Trails** tab
2. Pick a **Module** (dropdown, four options)
3. Pick a **Period** (top-right global selector — try Feb 2026 for the
   richest sample data)
4. Click **Run** — takes a few seconds, then trails appear
5. **Search** to filter by partner code or name
6. **Caveat step filter** to isolate trails where a specific step raised
   a caveat (evaluation view — "show me every trail where step 6 flagged
   an ingestion gap")
7. Click any trail row → the full 6-step chain expands. Each step shows
   what was checked, what was found, and whether it raised a caveat

---

## Sample-data caveats (be honest with viewers)

- **All numbers are fictional.** No customer PII, no real dealer names.
- **`Zero-Commission` module reads LOW confidence everywhere.** Legit:
  sample USP codes don't overlap activation codes (trips step 2) and
  sample payments are adjacent-period partials (trips step 5). This is
  the system being honest about ambiguous data, not a bug.
- **`Payment Intelligence` says SIMULATED** because `PAYMENT_SOURCE=simulated`.
  Live APDP integration is scaffolded but not switched on for the demo.
- **`Inventory Intelligence` NO_INVOICE_RECORD counts are large** —
  intentional. The IFS data window doesn't cover every historical
  purchase, so many activations look "unmatched." The audit module treats
  this as a data-coverage caveat, not a mismatch.
- **The chat can be slow** — the Anthropic API is on the hot path and a
  multi-tool answer can take 20–30 seconds. Normal.

---

## What to look at first (2-min GM tour)

1. **Overview** — read the posture band + audit coverage
2. Change the period to **Feb 2026**
3. **Audit Trails** → **Payment Reconciliation** → **Run** → expand one
   `UNDERPAID`/HIGH trail → walk the six steps
4. **Audit Trails** → **Eligibility Window** → **Run** → note that
   `MIXED_ATTRIBUTION` dominates; expand one and read step 5 to see the
   attributed root cause
5. **Inventory Intelligence** → search `hynex` → observe the SKU-alias
   pattern that the audit module recognises

---

## What we'd love feedback on

- Is the audit-conclusion vocabulary (`UNDERPAID` / `POLICY_VIOLATED` /
  `EXCESS_ACTIVATION`) the right Finance-facing language, or do you have
  in-house terms we should adopt?
- Are the six-step chains the right level of detail, or would you rather
  see fewer steps with richer detail per step?
- Which audit module would you want to see wired to real (not simulated)
  data first?
- What would you want to see that isn't here?

Direct any feedback to Nifesimi.
