# Demo rehearsal — 27 September 2026

Use the local desktop layout at 1440px. Keep Sample data / Synthetic demonstration labels visible. This is a guided evidence review, not production-readiness certification. Hosted-preview parity and projector sizing remain to be checked on the presentation environment.

## Saved evidence route

Open `http://localhost:5173/?view=audit&period=202603`, choose Zero-Commission, search exact dealer `130062` (Amber Arc Communications), and open trail `13945`. This route was opened in Chrome during implementation without creating or replacing evidence.

The saved assessment records **NOT_PAID / MEDIUM**, expected commission **NGN 88,118.92**, and recorded payment **NGN 0.00**. It has one caveat: two zero-commission products are absent from the USP rate card. The source is **simulated**, saved 23 August 2026, pipeline `1.0.0`, run `126fa6e0-1782-4038-a089-e53ae045a8cc`. These describe the stored assessment; they do not prove actual non-payment, current source completeness, or entitlement. Read the evidence limitations before explaining the conclusion. June Zero-Commission has no saved trails in this local snapshot; start in March.

For the same dealer and March period, use Commission and Activation search `130062`, inspect its recorded figures, then use Payments search `130062` for the current configured payment position. The current March simulated Payment source records owed **NGN 88,118.92**, paid **NGN 79,307.03**, and outstanding **NGN 8,811.89**. This differs from the older saved audit's zero payment. Present the discrepancy as a reason to verify evidence freshness, not as an actual unpaid dealer claim. Activation reports 49 records, 46 qualified and three zero-commission records. Payment drafts are for Finance review and must retain their source disclosures when copied or downloaded.

## Separate examples

Inventory: June, dealer `409091`, product `1283279` is a working dealer-product assistant handoff. Search `Synthetic` for explicitly fictional inventory scenarios; retain the scenario label and missing-invoice limitations. A coverage ticket requests confirmation of coverage and snapshot windows before remediation.

Financial Health: optional closing segment. The businesses are separate synthetic whole-business scenarios, including non-MTN activity. Do not imply their statements belong to the commission dealer above. The leverage metric is total liabilities-to-equity.

## Verification and boundaries

- All six local workspaces loaded in isolated Chrome without page errors.
- Commission and Activation retained the selected account when comparison changed from May to March; Financial Health retained the selected business when June changed to May.
- Inventory handoff displayed the exact dealer/product and Inventory context.
- Audit replacement lifecycle is checked with intercepted mock responses, never a live replacement run.
- The rehearsal screenshot is `/private/tmp/fbb-ux-saved-evidence.png`; temporary files are not release artifacts.
- No live model call, Presto query, deployment, source-data edit, or real replacement audit was required.

Before presenting, open the same routes on the intended deployed build and confirm its source labels, periods, saved trail availability, and exports match. Keep a backup screenshot with the source and caveat visible.

## Draft API compatibility

`POST /payments/disputes/draft` still accepts legacy `amount_paid`, but ignores it: source lookup owns owed and paid. The existing `statement_claim_ngn` summary field now means payment-source recorded owed. Conditional position codes replace the former final-decision vocabulary. APDP drafts additionally expose statement/settlement counts, reconciliation status and evidence qualifications; missing source evidence cannot establish an aligned balance. The UI and exported Markdown use these same qualifications.
