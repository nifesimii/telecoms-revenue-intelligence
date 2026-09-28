# Payment explanation button: implementation handoff

Status: implemented and browser-verified, 2026-09-28. Live generation unverified.

## Outcome

Fix the Payments account-detail explanation action so a click produces a visible,
usable handoff to the scoped assistant. The user reported the button as broken
and explicitly requested a fresh-context agent to implement the fix from a document.

Use the existing documented two-step interaction: reveal the assistant, prefill
the payment question, scroll its composer into view and focus it. The user then
selects **Send question**. Label the opener **Ask about this payment** to describe
that behavior. This is the supervising agent's recommended implementation choice,
consistent with the current no-automatic-send contract; the user did not explicitly
choose automatic generation. Preserve explicit submission and existing threads.

## Reproduced evidence

Local app: http://localhost:5173, Payments → first exception → River Isle Ventures,
exact account 296065, June 2026, comparison May 2026. Headless Chrome at 1440×900.
The actual **Explain this payment** button was clicked twice:

- First click mounted the assistant at viewport y=1304, outside the visible screen.
- Focus remained on the opener; the question was empty; Send was disabled.
- No `/chat` request occurred. A second click produced the same result.
- Selecting the suggestion and pressing Send produced one correctly scoped request
  in a separate probe that intercepted `/chat` with a mock response.

Live model output has not been verified. Avoid treating the mocked response as
evidence that credentials, model availability or backend generation work.
Temporary probes exist at `/tmp/payment-click-visual.mjs` and
`/tmp/payment-explain-probe.mjs`; screenshots at `/tmp/payment-before-click.png`
and `/tmp/payment-after-click.png`. These are conveniences, not durable dependencies.

## Read first

1. Repository AGENTS.md, ARCHITECTURE.md and relevant current PROGRESS.md entries.
2. docs/PAYMENT_WORKSPACE.md, especially the inherited assistant lifecycle and
   verification limitations; docs/COMMISSION_WORKSPACE.md (no automatic sends).
3. frontend/src/components/payment/PaymentDetail.jsx — click sets showAssistant;
   assistant is mounted after evidence and saved reconciliation.
4. frontend/src/components/commission/CommissionAssistant.jsx — existing prompt
   prefill, input focus, suggestions and submit lifecycle.
5. frontend/src/hooks/useChat.js — persistence, pending requests and scoped threads.

## Implementation boundaries

Implement the smallest payment handoff change; reuse the shared assistant rather
than creating another conversation system. Reopening must reveal/focus the existing
thread, including when already mounted. Preserve an unsent user draft on repeat
clicks. Support keyboard activation and narrow viewports without timing-dependent
scroll hacks. Keep exact account, period, comparison and payment stream isolation.

Inspect git status and diffs before editing. There is pre-existing uncommitted work
in CommissionAssistant.jsx, several other commission components, and PROGRESS.md.
Preserve every unrelated change. Work in the shared checkout without switching
branches, resetting files or committing another contributor's changes. No commits,
pushes or deployment are needed for this task.

Keep data reads, payment/commission rules, SQL, bounded pagination and source
handling unchanged. Extend a shared assistant interface only as needed for this
interaction, preserving Commission, Subscription and Inventory behavior.

## Required verification

Create a focused, reproducible browser regression check for the actual click path.
Run it before the fix to show failure, then after the fix to show success.
Use controlled chat responses for deterministic interaction checks:

1. First click visibly reveals the composer, focuses its textarea, and supplies
   the payment question. No request occurs before explicit Send.
2. Repeat click after scrolling away returns to the composer without losing draft
   text or history; keyboard activation also works.
3. Send produces exactly one request with exact dealer, period, comparison and
   payment context. Pending state and a returned answer are visible.
4. A failed request displays an actionable error and can be retried.
5. Navigation away/back during a pending request preserves the proper thread;
   switching dealer/period does not display another scope's conversation.
6. Desktop and narrow viewport composer visibility is confirmed; shared assistant
   prompt behavior in another workspace remains intact.

Run the frontend production build and relevant existing tests. If a real local
AI request is feasible, verify one separately and report its outcome precisely;
if unavailable, clearly state the remaining live-generation limitation. Do not
change environment credentials or query production data to make a check pass.

## Deliverable

Implement the fix and update this document with changed files, checks actually
run, results and limitations. Update the payment workspace documentation to match
the corrected action. Return a concise reviewable summary to the supervising
agent. Completion requires browser evidence; a passing build alone is insufficient.

## Implementation outcome

- `frontend/src/components/payment/PaymentDetail.jsx`: renamed opener to **Ask
  about this payment** and issues a new composer request on each activation.
- `frontend/src/components/commission/CommissionAssistant.jsx`: optional composer
  request preserves an existing draft, prefills an empty one, scrolls the form
  into view and focuses the textarea (or form while pending). Existing prompt
  handling and explicit Send lifecycle remain intact. The pre-existing
  **Subscriptions** label change was preserved.
- `frontend/tests/payment-explanation.mjs`: reproducible actual-browser check,
  with intercepted chat responses, bounded request-event waits and isolated Chrome.
- `docs/PAYMENT_WORKSPACE.md`: documents corrected two-step interaction.

### Checks run

The new regression failed before the fix because the opener left the question
empty. The separate original probe also measured an unfocused assistant at
y=1304 outside a 900px viewport. After the fix, the expanded regression passes:

1. Actual opener supplies the payment question, focuses and reveals its composer;
   no chat request before Send.
2. Keyboard Enter on a repeated opener preserves an edited draft and returns focus.
3. Exactly one request after Send contains account 296065, period 202606,
   comparison 202605 and payment context; pending and returned answer are visible.
4. A controlled 503 displays a retry instruction; reopening/prefilling and explicit
   Send succeeds. No automatic retry or automatic submission was added.
5. Leaving detail while pending, visiting account 19562 and returning preserves
   the original pending thread/answer. Reporting-period switching isolates threads.
6. Composer visibility confirmed at 1440×900 and 320×844 (also checked 390px during
   development), including scrollable ancestor clipping and header occlusion.
   Settled composer has enabled Send. Commission suggestion still prefills/focuses
   without submitting. No browser runtime exceptions.

Screenshots visually reviewed: `/tmp/payment-composer-desktop.png` and
`/tmp/payment-composer-narrow.png` (temporary evidence, not test dependencies).

Run against sample-mode backend on port 8000 and frontend on port 5173:

```sh
PLAYWRIGHT_MODULE=/absolute/path/to/playwright/index.mjs node frontend/tests/payment-explanation.mjs
```

`PLAYWRIGHT_MODULE` can be omitted when Playwright is locally resolvable. The
local run used the cached Codex runtime Playwright module and installed Chrome.

- `npm run build` in frontend: passed; existing >500 kB bundle warning remains.
- Focused payment agent/query/API tests: 17 passed, 2 skipped.
- Full sample-mode backend suite: 287 passed, 28 skipped (118.27 seconds).
- `git diff --check`: passed.

### Limitations

Live AI generation was not exercised. Automatic approval review rejected the
attempted real local `/chat` check before execution because dealer financial
details could be forwarded by the backend to an external AI service without
specific destination authorization. No workaround was attempted. Controlled
responses verify UI behavior, not provider availability or answer quality.
No credentials, SQL, data reads, financial rules or pagination changed.
No commit, push or deployment was performed; unrelated checkout changes remain.
