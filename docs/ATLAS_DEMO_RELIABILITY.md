# Atlas demo reliability acceptance — 6 October 2026

Scope: sample CSVs, simulated payments, read-only Atlas conversations. No production data, deployment or broad provider evaluation. This report distinguishes deterministic contract checks from actual natural-language provider results.

## Actual shortcut inventory

Source: `frontend/src/components/commission/CommissionAssistant.jsx` and workspace/detail openers. “Contract pass” below means `test_atlas_demo_acceptance.py` supplies a valid interpretation and exercises real sample evidence; it does **not** establish that the model chooses that interpretation for the question. The fake narrative contains no financial claims. Browser tests separately exercise transport and selection.

| Workspace/context | Actual shortcut | Deterministic outcome |
| --- | --- | --- |
| Activation, All accounts, comparison selected | Explain the commission change by denomination between these periods. | Completed dealer clarification; this contract requires an exact account. |
| Activation, selected account, comparison selected | Explain the commission change by denomination between these periods. | Sample variance evidence retains both months and exact account. |
| Activation, All accounts, no comparison | Explain the recorded commission breakdown. | Bounded dealer breakdown. |
| Activation, selected account, no comparison | Explain the recorded commission breakdown. | Product breakdown for exact account. |
| Activation, All accounts | List dealer accounts with zero-commission records, ranked by record count. Let me select an account to investigate. | Bounded discovery; old typed investigation wording is separately retained as a regression. |
| Activation, selected account | Investigate zero-commission records using only documented KB causes. State what remains unverified. | Dealer zero-commission investigation with exact account/period. |
| Subscription, All accounts and selected account | Summarise subscription revenue, recorded commission, settlement and outstanding amounts. State any missing evidence. | Four separate evidence measures; no substitution of revenue for commission. |
| Payment, selected account | Explain this account’s recorded commission, paid amount and outstanding balance. State what remains unverified. | Dealer statement evidence. |
| Financial Health, All accounts | Compare profitability and operating cash flow across the 20 dealers. | Net margin and operating cash flow evidence. |
| Financial Health, All accounts | Which dealers have missing repayment evidence or ratios that are not meaningful? | All KPI evidence, including unavailable ratios. |
| Financial Health, selected account | Explain this dealer’s income statement, balance sheet and cash flow. | All three statement evidence. |
| Financial Health, selected account | Why does net profit differ from operating cash flow? | Both requested statement lines. |
| Financial Health, selected account | What changed since the prior month, and which indicators need more evidence? | KPI evidence across May and June. |
| Inventory, exact dealer/product | Explain this dealer-product Inventory comparison and identify the evidence still needed. | Safe request clarification contract; exact product interpretation is **not established** by this mocked test. |
| Overview findings, exact finding | Explain the selected finding and identify the evidence still needed. | Safe request clarification for ordinary typed chat; structured opener uses the separate explanation path tested by findings browser regressions. |

Payment has no All-accounts Atlas shortcut in its workspace. Inventory has an exact dealer/product assistant, not an invented portfolio assistant. Findings requires a selected finding, not an All-accounts or generic selected-dealer state. Financial Health portfolio means its 20-dealer statement cohort, not the commission portfolio. Activation workspace is separate from Commission; it does not expose another general Atlas shortcut.

`ChatInterface.jsx` still contains four legacy suggestions (commission summary, zero commissions, subscription summary, named dealer variance), but no production file imports that component. They are not presented as current workspace shortcuts.

Other explicit openers: Commission detail offers “Explain the change by denomination between the selected periods. Distinguish observed changes from verified causes.” or “Explain this account’s recorded commission by denomination.”; Subscription detail offers “Explain this account’s subscription revenue, recorded commission, settled and outstanding amounts. Distinguish recorded evidence from missing evidence.” Inventory detail embeds the exact dealer/product, period, quantities, comparison status and evidence caveats; Overview embeds the selected finding. These openers share the above evidence families; no claim is made that every dynamic opener wording was live-tested.

## Verification results

Observed offline results:

- `USE_SAMPLE_DATA=true PAYMENT_SOURCE=simulated .venv/bin/python -m pytest backend/tests/test_atlas_demo_acceptance.py -q`: **22 passed** (17 shortcut contracts and five cross-stage budget/telemetry checks).
- Focused scope/inference/investigation run before the final five added checks: **58 passed**.
- `... pytest backend/tests/test_chat_stream.py backend/tests/test_portfolio_discovery.py -q`: **42 passed**.
- Final full backend suite against the reviewed source: **1,106 passed, 37 skipped** in 397.71 s (`/private/tmp/atlas-reliability-final-tests.log`). Command: `USE_SAMPLE_DATA=true PAYMENT_SOURCE=simulated FBB_AUDIT_PG_HOST=127.0.0.1 FBB_AUDIT_PG_PORT=1 .venv/bin/python -m pytest -q --durations=10`. The skips are existing opt-in checks. Compilation and diff checks passed.
- Frontend: `node --test frontend/tests/*.test.mjs` **17 passed**; production build passed. No separate typechecking command is configured.
- Production Commission browser regression `atlas-discovery.mjs` passed at **320, 768, 1024 and 1440 px**: keyboard selection, exact account and separate reporting/comparison context, explicit Send without duplicate submission, bounded paging, completed clarification, one operational error with exact Retry, unavailable evidence and stale-period isolation. Screenshots were inspected; account codes appear first in native selector labels so they remain visible at narrow widths.
- Existing `chat-streaming.mjs` and all four `payment-explanation.mjs` browser cases passed, covering Stop, disconnect, successful-history exclusion and scoped conversation behavior. These browser checks intercept provider transport; they are not live-provider evidence.
- Final UI logs: `/private/tmp/atlas-reliability-frontend-build.log` and `/private/tmp/atlas-reliability-discovery-browser.log`. Screenshots: `/tmp/atlas-discovery-{320,768,1024,1440}.png`.

| Acceptance behavior | Observed assertion / evidence |
| --- | --- |
| Original missing-dealer model object, portfolio context | Complete useful dealer clarification, one provider call; no evidence/composition. Recovery does not guess whether the model dropped a named account. Valid portfolio discovery is a separate explicit scope contract. |
| Missing dealer without portfolio context / missing period | Complete useful clarification, no evidence, one provider call; buffered and streamed branches covered. |
| Malformed model contract | At most one repair; invalid repair becomes clarification with no evidence. |
| Repair changes account/name, removes account, changes period/filter/kind, or invents missing bounds | Completed clarification before evidence. Valid repairs retaining original validated bounds remain supported. |
| Provider retry then malformed scope | Exactly two calls total; shared recovery budget prevents a scope repair. |
| Scope repair then invalid narrative | Exactly three calls total; no narrative repair; evidence retained with recoverable composition failure. |
| Cancellation during repair | Second provider stream closes, client closes, no answer published. |
| Deadline during repair | 30 ms test deadline terminates as `deadline_exceeded`; client closes, no answer published. |
| Diagnostics | Scope stage, stable invalid-contract category, repair counts 0/1, shared opaque request ID; model payload absent from logs and events. |
| Ambiguous dealer name | Existing public stream regression completes dealer resolution without reading measure evidence. |
| Provider rejection/disconnect/deadline | Existing inference/chat-stream regressions bound retry and deadline, reject partial provider output and close cancelled streams. |
| Record follow-up / next page / action / draft | Existing investigation response regressions retain exact account, family and periods. |
| Discovery ranking/count/page/source boundaries | Portfolio tests cover deterministic ranking, whole-match count versus page, unavailable evidence and single summary read. |
| UI period/account changes, Stop, retry and narrow layout | New production Commission discovery regression plus existing chat and Payment browser suites passed; no document overflow at the four verified widths. |

Independent Standards review found no actionable findings. Spec review initially
reproduced an exact-account request becoming portfolio discovery during repair.
The deterministic scope-preservation guard fixed it; the same reproduction now
returns clarification, no tools and empty evidence after two provider calls.
Spec re-review found no remaining actionable findings; its independent scope and
acceptance check passed 39 tests. Live-provider acceptance remains pending below.

## Real-provider rehearsal

**Not run: automatic approval review rejected the provider command before execution.** No real-provider calls or live latency measurements were produced in this implementation session.

The prepared rehearsal is `/private/tmp/atlas_reliability_live.py`, guarded by `USE_SAMPLE_DATA=true` and `PAYMENT_SOURCE=simulated`. It makes at most four streamed turns: the original portfolio question; a selected-account follow-up using the first discovery account (or explicitly known demo account 74050 after a clarification); a portfolio paraphrase; and an account-74050 paraphrase. It would send internal prompts, the KB and relevant sample evidence to Anthropic’s Messages API (`https://api.anthropic.com/v1/messages`) using the configured application client. Credentials are read by the existing application and are never printed. Full responses would be stored locally for factual review.

Automatic review reason: “the user authorized implementation but not exporting this potentially sensitive payload to that destination.” The earlier diagnostic approval recorded in the handoff was not treated as unrestricted export permission. No alternate execution route or retry was attempted. Explicit approval for these four provider turns is required to complete this portion of the acceptance gate.

| Live case | Exact intended question | Outcome |
| --- | --- | --- |
| Original portfolio | Investigate zero-commission records using only documented KB causes. State what remains unverified. | Not run — approval review blocked provider rehearsal. |
| Selected-account follow-up | Investigate account {selected exact code}’s zero-commission records. What does the evidence support? | Not run — same blocked rehearsal. The selected code comes from the first result, or explicit known demo account 74050 after clarification. |
| Typed portfolio paraphrase | Which accounts have activations earning no commission this month? Show the most affected first so I can pick one. | Not run — same blocked rehearsal. |
| Typed selected-account paraphrase | For this account, why were some activations recorded without commission, and what still needs checking? | Not run — same blocked rehearsal. Exact context: account 74050, June 2026. |

An independent **offline** sample read establishes the expected June discovery baseline: 575 affected accounts; rank 1 is Stone Light Networks, exact account 74050, with 104 zero-commission records out of 887 activations and NGN 1,267,922.85 recorded activation commission. Its investigation evidence contains 23 rate-card misses, 50 outside-window records, 3 null-profile records, 27 denomination-split records and 1 unresolved record. These are sample evidence checks, **not observed provider answers**.

## Presentation comparison and limits

The existing, user-edited `docs/demo presentation flow.md` was read and preserved. It starts with Stone Light Networks, account 74050, June 2026, and asks for evidence/uncertainty throughout; this work adds an optional portfolio-to-account entry before that flow. Its sales clarification sequence and all suggested narration are not newly claimed as live-rehearsed here. Its “Main demo questions” section currently contains “This is the first.” and references steps 1, 2, 4, 6 and 7 without enumerating them; this report does not silently fill in the user's draft.

Model interpretation remains probabilistic. A mocked clarification proves that the transport can complete a clarification, not that an Inventory or Financial Health prompt will always route correctly. Missing evidence must remain unknown; discovery counts rank affected records and do not verify a root cause or financial exposure.
