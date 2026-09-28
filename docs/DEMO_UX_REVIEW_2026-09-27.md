# Pre-demo UX and UI review — 27 September 2026

## Verdict

Conditionally ready for a guided Finance/Revenue Assurance pilot demonstration. The visual language is coherent and appropriate for a finance investigation tool. The remaining material risks concern evidence credibility, investigation continuity and demo preparation. This is not production-readiness certification.

Six Codex reviewers were created through Herdr, one per requested tab. Their code reviews are recorded below. The primary reviewer also loaded all six local tabs in Chrome at 1440px, inspected screenshots and checked interaction paths. No application code or datasets were changed, no audit replacement jobs were run, and no live AI calls were made. This review does not establish parity with the deployed preview.

## Three priorities for the next 24 hours

1. **Make the conclusion no stronger than its evidence.** Payment dispute drafts need source qualifications and Finance-review wording; Commission needs confidence beside saved conclusions; Audit eligibility language must be conditional; the Financial Health leverage label should name total liabilities; Inventory ticket text should request evidence confirmation rather than assert a diagnosis.
2. **Keep the investigator on the selected dealer.** Commission and Activation comparison changes currently discard selection. Financial Health month changes reset the whole workspace. Audit replacement-run state must survive period navigation if live runs will be demonstrated.
3. **Prepare the evidence and the presentation path.** The June default Zero-Commission audit view loaded with zero saved trails. Select and rehearse an actual saved dealer/module/period route before presenting. Preserve visible sample/synthetic labels and carry them into exports. Avoid a broad redesign before the demo.

## Tab-by-tab assessment

| Tab | Keep | Highest-value improvement |
|---|---|---|
| Commission | Clear headline, distinction between commission and settlement, drill-down by account | Show saved conclusion confidence; preserve account/filter state when comparison changes |
| Activation | Qualification and zero-record distinctions, matching-set summaries | Preserve dealer across comparisons; identify synthetic reporting periods; separate refresh failure from loading |
| Inventory | Explicit missing-invoice and synthetic-evidence limitations | Carry dealer/product scope into the assistant; make coverage-ticket diagnosis conditional |
| Payments | Owed/settled/outstanding hierarchy and distinction between total and filtered scope | Make draft response amounts and evidence qualifications match the reviewed account |
| Financial Health | Clear statement entry points and missing-evidence explanations | Rename leverage metric to total liabilities-to-equity; keep the dealer selected across month changes |
| Audit Trails | Confidence, caveats, saved-evidence limitations and evidence export | Fix unconditional eligibility wording; preserve active-run state; rehearse a populated saved-evidence route |

## Visual and interaction judgment

The restrained yellow accent, consistent type, white table surfaces, account-level actions and visible reporting period form a credible finance UI. A new colour system, navigation redesign or more charts would introduce risk without resolving the material findings.

The main pages devote substantial space to headings, controls and explanatory text before the first account row. This is most visible in Inventory and Payments. After the demo, consider compressing repeated explanatory material and moving secondary filters into an expandable section while preserving essential evidence limitations. This is a polish opportunity, not a correctness defect or a 24-hour prerequisite.

Financial Health represents separate whole-business scenarios, including non-MTN activity. Presenting it as a continuation of a commission dealer investigation would imply a connection that the current demo does not provide. Recommended positioning: a short optional closing segment, pending the user's preference.

## Browser observations and limits

- All six local June tabs loaded. No uncaught page errors occurred during the initial six-tab pass.
- Commission and Activation returned from the selected dealer to the list after changing comparison. Financial Health returned to its dealer list after changing reporting month.
- June Zero-Commission showed zero saved trails. March Zero-Commission showed 620 saved trails across 575 subjects/dealers, all with recorded caveats. Availability alone does not validate their conclusions or freshness. Rehearse a specific saved trail before using it.
- At a 390px viewport, document scroll width was 811px for Commission and 718px for Activation. Inventory, Payments and Financial Health stayed at 390px. This is a responsive-layout issue requiring further diagnosis; use the rehearsed desktop layout for this imminent demo.
- Screenshots and temporary browser logs are in `/private/tmp/fbb-demo-review/`. The review did not exhaustively test keyboard operation, injected network failures, model answers, every export, live replacement runs, or deployed-preview parity. The detailed reviewer claims remain code findings except where explicitly confirmed above.

## Suggested 24-hour allocation

- First 6 hours: correct high-risk conclusion/provenance wording and the selected-dealer comparison resets. Validate the precise changes with focused checks.
- Next 4 hours: rehearse one actual dealer-period from Commission through Activation, Payments and saved Audit evidence; use a separately labelled Inventory synthetic example if needed.
- Next 4 hours: check export wording, failure/retry states and the exact screen/projector size. Confirm the deployed build and data match the rehearsed version.
- Final 10 hours: retain contingency, prepare backup screenshots, and freeze discretionary interface changes. Do not spend the buffer on new features.

If time is insufficient to correct dispute drafts or active audit-run handling, exclude those actions from the demo and browse saved evidence instead. This is a presentation containment measure, not a claim that the issues are fixed.

## Detailed reviewer evidence

### Commission

**Conditionally demo-ready. Code review evidence.**

- **P1 — Saved verification omits confidence beside the conclusion.** `frontend/src/components/commission/ZeroCommissionEvidence.jsx:41` renders the saved conclusion and caveats but not the confidence supplied by `backend/audit/trail.py:142`. Add confidence beside the conclusion, especially where a low-confidence “not paid” assessment might otherwise appear definitive.
- **P2 — Changing comparison discards the investigation.** `frontend/src/components/commission/CommissionWorkspace.jsx:43` keys the account workspace by comparison period, remounting account/filter state declared at line 51. Preserve selection and filters while refreshing comparison-dependent evidence.

Preserve the distinction between recorded commission, settlement and subscription revenue, and the warning that zero records are investigation signals rather than proof of entitlement.


### Activation

**Verdict: conditionally demo-ready.** Three code-supported issues merit correction before an unscripted demo. This was read-only; no browser testing, runtime verification, changes, or commits.

1. **P2 — Synthetic activation data loses its provenance label.**  
   Evidence: [activation_workspace.py:103](/Users/ademoyeoluwanifesimi/Documents/telecoms-revenue-intelligence/backend/db/activation_workspace.py:103) and [activation_workspace.py:114](/Users/ademoyeoluwanifesimi/Documents/telecoms-revenue-intelligence/backend/db/activation_workspace.py:114) call `provenance()` without a period. The synthetic-month label requires that argument at [commission_workspace.py:18](/Users/ademoyeoluwanifesimi/Documents/telecoms-revenue-intelligence/backend/db/commission_workspace.py:18).  
   **Impact:** January/April–June figures and exports say only “Sample CSVs,” obscuring which observations were generated for demonstration.  
   **Smallest correction:** Pass the reporting period into both provenance calls; identify synthetic comparison periods too.

2. **P2 — Changing comparison exits the account investigation.**  
   Evidence: [ActivationIntelligencePanel.jsx:61](/Users/ademoyeoluwanifesimi/Documents/telecoms-revenue-intelligence/frontend/src/components/activation/ActivationIntelligencePanel.jsx:61) clears `selected`; the comparison selector remains available above account detail at line 71.  
   **Impact:** Finance loses the account context when trying another comparison month and must locate and reopen the dealer.  
   **Smallest correction:** Preserve the selected dealer when changing comparison and reload its detail.

3. **P2 — Failed refresh is presented as perpetual loading.**  
   Evidence: [ActivationIntelligencePanel.jsx:80](/Users/ademoyeoluwanifesimi/Documents/telecoms-revenue-intelligence/frontend/src/components/activation/ActivationIntelligencePanel.jsx:80) passes `busy || query.isError` as `busy`. [ActivationAccounts.jsx:21](/Users/ademoyeoluwanifesimi/Documents/telecoms-revenue-intelligence/frontend/src/components/activation/ActivationAccounts.jsx:21) applies `aria-busy`, and line 25 displays “Updating accounts…”.  
   **Impact:** After a failed refresh with cached data, the error notice conflicts with an indefinite loading status, including for assistive technology.  
   **Smallest correction:** Separate fetching status from error-based action disabling; show “Last successful results” once fetching stops.

**Strength worth preserving:** The finance wording explicitly distinguishes zero commission from an error or amount owed ([ActivationSummary.jsx:23](/Users/ademoyeoluwanifesimi/Documents/telecoms-revenue-intelligence/frontend/src/components/activation/ActivationSummary.jsx:23)), and missing prior records from zero activity. These distinctions make the investigation workflow credible.

### Inventory

**Verdict: conditionally demo-ready.** The Inventory comparison workflow is well guarded, but two handoff issues should be corrected before demonstrating investigation end to end.

Code-only review; no browser testing, file changes or commits.

1. **P2 — Coverage ticket recommends remediation beyond the evidence.**  
   **Evidence:** [data_coverage.py:38](/Users/ademoyeoluwanifesimi/Documents/telecoms-revenue-intelligence/backend/db/data_coverage.py:38) derives severity solely from dealer count and declares a full refresh/reload “likely required” above ten dealers. [data_coverage.py:132](/Users/ademoyeoluwanifesimi/Documents/telecoms-revenue-intelligence/backend/db/data_coverage.py:132) asserts commission accuracy is affected. Inventory displays this recommendation directly at [DataCoverageTicketModal.jsx:51](/Users/ademoyeoluwanifesimi/Documents/telecoms-revenue-intelligence/frontend/src/components/inventory/DataCoverageTicketModal.jsx:51).  
   **Impact:** Finance can copy a ticket implying a diagnosed source problem and commission impact when the comparison establishes only missing invoice evidence. This undermines the tab’s otherwise careful qualifications.  
   **Smallest correction:** Describe potential impact and request confirmation of invoice coverage/window first; make reload and commission rerun recommendations conditional on that confirmation.

2. **P2 — Inventory’s assistant handoff inherits unrelated commission context.**  
   **Evidence:** [InventoryDetail.jsx:44](/Users/ademoyeoluwanifesimi/Documents/telecoms-revenue-intelligence/frontend/src/components/inventory/InventoryDetail.jsx:44) creates a dealer-product Inventory question, but [App.jsx:159](/Users/ademoyeoluwanifesimi/Documents/telecoms-revenue-intelligence/frontend/src/App.jsx:159) routes it to Commission without Inventory scope. [CommissionAssistant.jsx:13](/Users/ademoyeoluwanifesimi/Documents/telecoms-revenue-intelligence/frontend/src/components/commission/CommissionAssistant.jsx:13) prepends portfolio-level activation/subscription commission context; its visible scope also says “All accounts” at line 35.  
   **Impact:** A specific Inventory investigation lands in a differently labelled workspace and sends conflicting context. The Inventory question survives, but the handoff is confusing and risks an off-topic explanation. Actual model behavior was not tested.  
   **Smallest correction:** Pass an explicit Inventory scope with dealer/product identity and use it for the assistant label and request context.

**Strength worth preserving:** The evidence hierarchy clearly separates observations from conclusions. [InventoryDetail.jsx:29](/Users/ademoyeoluwanifesimi/Documents/telecoms-revenue-intelligence/frontend/src/components/inventory/InventoryDetail.jsx:29) explains unknown purchases and negative differences; line 38 prevents synthetic scenarios from inheriting saved verification. Preserve these distinctions alongside the implemented retry, empty-state and keyboard-focus recovery paths.

### Payments

**Verdict: conditionally ready for a guided Payment review; hold the dispute-response demo until findings 1–2 are corrected.** Code-only review; no browser testing, runtime verification, changes, or commits.

1. **P1 — Dispute drafts can contradict the displayed payment position.**  
   Evidence: the modal sends the paid amount but not commission owed ([DisputeDraftModal.jsx:62](/Users/ademoyeoluwanifesimi/Documents/telecoms-revenue-intelligence/frontend/src/components/payment/DisputeDraftModal.jsx:62)). The generator substitutes activation earnings for the statement claim ([dispute_responder.py:183](/Users/ademoyeoluwanifesimi/Documents/telecoms-revenue-intelligence/backend/agent/dispute_responder.py:183)), then presents it as “Statement amount issued” and calculates outstanding from it ([dispute_responder.py:235](/Users/ademoyeoluwanifesimi/Documents/telecoms-revenue-intelligence/backend/agent/dispute_responder.py:235)).  
   **Impact:** When payment-source owed and activation earnings differ, Finance sees different outstanding balances between account evidence and the downloadable response.  
   **Smallest correction:** Retrieve the exact payment account’s recorded owed/paid amounts for the draft; retain activation earnings as a separately labelled comparison.

2. **P1 — Exportable responses lose the workspace’s evidence qualifications.**  
   Evidence: the workspace explicitly identifies simulated settlements ([PaymentIntelligencePanel.jsx:96](/Users/ademoyeoluwanifesimi/Documents/telecoms-revenue-intelligence/frontend/src/components/payment/PaymentIntelligencePanel.jsx:96)), but the letter asserts “No further settlement is due” and “the dispute is declined” ([dispute_responder.py:125](/Users/ademoyeoluwanifesimi/Documents/telecoms-revenue-intelligence/backend/agent/dispute_responder.py:125)). It also promises review within three business days ([dispute_responder.py:275](/Users/ademoyeoluwanifesimi/Documents/telecoms-revenue-intelligence/backend/agent/dispute_responder.py:275)). The generated letter carries no corresponding simulation qualification.  
   **Impact:** Copy/download turns demonstration evidence into an apparently authoritative MTN decision and service commitment.  
   **Smallest correction:** Carry source provenance and “draft for Finance review” into the exported text; replace final decisions with conditional observations and remove the unsupported turnaround commitment.

3. **P2 — Completing composition breaks keyboard continuity.**  
   Evidence: focus is assigned only when the dialog opens ([DisputeDraftModal.jsx:33](/Users/ademoyeoluwanifesimi/Documents/telecoms-revenue-intelligence/frontend/src/components/payment/DisputeDraftModal.jsx:33)). Successful composition removes the form containing the focused Compose button ([DisputeDraftModal.jsx:142](/Users/ademoyeoluwanifesimi/Documents/telecoms-revenue-intelligence/frontend/src/components/payment/DisputeDraftModal.jsx:142)); no completion focus transfer is implemented. The dealer-position label also lacks an association with its textarea ([DisputeDraftModal.jsx:144](/Users/ademoyeoluwanifesimi/Documents/telecoms-revenue-intelligence/frontend/src/components/payment/DisputeDraftModal.jsx:144)).  
   **Impact:** Keyboard and screen-reader users can lose their place during the principal response workflow.  
   **Smallest correction:** Focus a labelled result heading after composition, announce completion, and associate the textarea using `htmlFor`/`id`.

**Strength worth preserving:** The main workflow carefully separates full-period totals from filtered accounts, distinguishes missing records from zero balances, and states that aggregate differences do not establish causes. Preserve that same evidence discipline in dispute responses.

### Financial Health

**Verdict: conditionally demo-ready.** Two P2 issues merit correction before presenting. This was a read-only code review with a direct Python model check; no browser testing or test suite execution.

1. **P2 — Changing month drops the dealer investigation.**  
   **Evidence:** [FinancialHealthWorkspace.jsx:13](/Users/ademoyeoluwanifesimi/Documents/telecoms-revenue-intelligence/frontend/src/components/financial/FinancialHealthWorkspace.jsx:13) keys the entire workspace by period; dealer selection, search and sorting are local state at lines 17–20. Changing month therefore remounts the workspace and returns to the dealer list.  
   **Impact:** A presenter reviewing a dealer’s balance sheet cannot move to another month without finding the dealer again and reopening the statement.  
   **Smallest correction:** Preserve dealer selection across period changes and reload the exact dealer-period report; reset pagination separately. This behavior is inferred from code, not browser-observed.

2. **P2 — The leverage headline does not identify its actual numerator.**  
   **Evidence:** [financial_health.py:43](/Users/ademoyeoluwanifesimi/Documents/telecoms-revenue-intelligence/backend/db/financial_health.py:43) labels the KPI “Debt-to-equity” but calculates **total liabilities / total equity**, including trade payables through line 106. [FinancialDetail.jsx:41](/Users/ademoyeoluwanifesimi/Documents/telecoms-revenue-intelligence/frontend/src/components/financial/FinancialDetail.jsx:41) places that definition inside a collapsed calculation.  
   **Impact:** Finance can read the headline as borrowing leverage. The direct June model check confirms Cedar’s numerator includes NGN 2,300,000.00 of payables alongside NGN 4,400,000.00 of borrowings.  
   **Smallest correction:** Rename the visible metric “Total liabilities-to-equity,” preserving the intended calculation.

**Strength worth preserving:** Missing evidence remains visibly distinct from a healthy result. [FinancialDetail.jsx:38](/Users/ademoyeoluwanifesimi/Documents/telecoms-revenue-intelligence/frontend/src/components/financial/FinancialDetail.jsx:38) distinguishes unavailable, not applicable and not meaningful values, displays reasons, and exposes calculation inputs. This supports an evidence-based Finance discussion without implying a funding recommendation.

### Audit Trails

**Verdict: conditionally demo-ready for browsing saved evidence.** Correct the misleading eligibility wording before presenting that module; avoid demonstrating replacement runs until their navigation lifecycle is fixed.

Code-only review of project guidance, Audit Trails components, and supporting API logic. No browser testing, audit execution, changes, or commits.

1. **P2 — Eligibility qualification asserts an outcome regardless of evidence.**  
   **Evidence:** [auditPresentation.js:19](/Users/ademoyeoluwanifesimi/Documents/telecoms-revenue-intelligence/frontend/src/components/audit/auditPresentation.js:19) adds “Inside the window; other eligibility checks required” to every eligibility trail. It appears beneath the conclusion through [AuditEvidence.jsx:30](/Users/ademoyeoluwanifesimi/Documents/telecoms-revenue-intelligence/frontend/src/components/audit/AuditEvidence.jsx:30), including trails with zero inside-window records.  
   **Impact:** Finance can see contradictory eligibility statements in both the screen and downloaded report.  
   **Smallest correction:** Use conditional wording: “Being inside the window alone does not establish commission entitlement; other eligibility checks are required.”

2. **P1 — Changing period loses visibility and protection for an active replacement run.**  
   **Evidence:** [AuditTrailPanel.jsx:17](/Users/ademoyeoluwanifesimi/Documents/telecoms-revenue-intelligence/frontend/src/components/audit/AuditTrailPanel.jsx:17) remounts the workspace when the period changes. Running state belongs to that workspace at line 24; the asynchronous replacement request starts at line 55. The global period selector remains enabled during runs: [App.jsx:72](/Users/ademoyeoluwanifesimi/Documents/telecoms-revenue-intelligence/frontend/src/App.jsx:72).  
   **Impact:** Switching months hides the pending operation and its eventual outcome. Returning to the original month permits another replacement request while the first may still be running.  
   **Smallest correction:** Keep pending-run state above the period-keyed workspace, retain its module/period and outcome, and block duplicate runs for that scope.

3. **P2 — A shrinking saved collection can produce a false empty state.**  
   **Evidence:** Refresh preserves the current offset at [AuditTrailPanel.jsx:72](/Users/ademoyeoluwanifesimi/Documents/telecoms-revenue-intelligence/frontend/src/components/audit/AuditTrailPanel.jsx:72). The API slices at that offset without adjustment: [audit_workspace_routes.py:79](/Users/ademoyeoluwanifesimi/Documents/telecoms-revenue-intelligence/backend/api/audit_workspace_routes.py:79). The UI interprets an empty page as “No matching saved trails” and calculates its range from the old offset at [AuditTrailPanel.jsx:99](/Users/ademoyeoluwanifesimi/Documents/telecoms-revenue-intelligence/frontend/src/components/audit/AuditTrailPanel.jsx:99).  
   **Impact:** After evidence replacement, users can see “No matching” alongside a positive matching total and an impossible page range.  
   **Smallest correction:** Reset to page one when the returned total makes the current offset invalid.

**Strength worth preserving:** Evidence presentation explicitly separates recorded assessments from verified financial outcomes, qualifies positive payments beneath `NOT_PAID`, and exposes saved source, run, version, and freshness limitations. This supports a credible Finance explanation without overstating certainty.
