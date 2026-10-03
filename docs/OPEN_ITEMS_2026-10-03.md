# Open items — 2026-10-03

Work left after Atlas dealer names (#8), activation/payment exceptions (#4)
and the month-wide investigation queue (#6) landed on `main` (HEAD `cb92a28`).
Each item is written so an agent can pick it up cold. Items are ordered by
priority within each section.

## Before you start (every item)

- Read `CLAUDE.md`, `ARCHITECTURE.md` and `docs/ATLAS_MEASURE_SCOPE.md`.
- Work on a branch or worktree. Worktrees can start from a stale commit: run
  `git merge --ff-only main` first.
- The working tree on `main` holds another session's uncommitted edits
  (`PROGRESS.md`, `backend/agent/prompts.py`, `frontend/src/components/MessageBubble.jsx`,
  `frontend/src/components/commission/CommissionAssistant.jsx`, three files
  under `frontend/tests/`, `.github/hooks/`). Do not commit, revert or
  reformat them; stage only your own files.
- Record your own test baseline first:
  `.venv/bin/python -m pytest backend/tests -q -p no:cacheprovider`
  (846 passed, 29 skipped on committed `main`). Work test-first.
- Atlas rules that apply everywhere:
  - The application writes answer text: the model fills a `MeasureScope`
    (`backend/agent/measure_scope.py`), `backend/agent/tool_executor.py`
    reads evidence and `backend/agent/measure_response.py` validates and
    renders it.
  - Answers never say "synthetic", "simulated", "sample", "demo" or "ORSC".
    Subscription commission is called "subscription commission".
  - Missing data is never zero or a pass. "Unavailable" is distinct from
    "none found".
  - Validators raise `ValueError`. Rendered values go through `_text`.
  - SQL lives only in `backend/db/queries.py` and is read-only. Lower layers
    never import `backend.api`. Page sizes are at most 100.

---

## A. Atlas behaviour (do these first)

### A1. A month-wide question asked with a dealer selected ends in an error

**Problem.** Suppose a dealer is selected in the UI and the user asks "top 10
HIGH-severity dealers for June". The model may fill an `investigation_queue`
scope that still carries the selected `dealer_id`. `MeasureScope` rejects
that combination (`backend/agent/measure_scope.py:132`). The `ValidationError`
from `MeasureScope.model_validate` (`backend/agent/agent.py:154`) is not
caught, so the stream ends with an `error` event and no answer.

**Evidence.** `backend/tests/test_chat_stream.py:485`
(`test_chat_stream_investigation_queue_for_one_dealer_reads_no_evidence`)
pins the current behaviour: no evidence is read, and the last event is
`error`.

**Done when.** The user gets the month-wide queue. Recommended fix: for
measures in `ALL_DEALER_MEASURES`, drop the selected dealer from the scope
before validation, because the selected dealer is context, not a filter. A
clarification answer is the acceptable fallback. Either way:
- the test above is updated to expect a real answer;
- the queue reader still never receives a dealer;
- a scope that mixes `investigation_queue` with a dealer measure is still
  rejected.

**Size.** Small.

### A2. New measures are not in the live golden evaluation set

**Problem.** `backend/tests/evals/golden.jsonl` has 28 cases (all passed live
on 2026-10-03, per `PROGRESS.md`). None of them covers:
- dealer names inside measure questions;
- activation exceptions;
- payment exceptions;
- the investigation queue.

These measures have only been tested offline with a mocked model, so whether
the real model routes to them is unproven.

**Done when.** `golden.jsonl` has these cases, with the expected figures from
sample data for 202606:

| Question | Expected |
| --- | --- |
| "What do we owe Amber Arc in June 2026?" | Resolves to 130062 in the same answer. |
| "What do we owe River Isle in June 2026?" | Asks which dealer: there are 6 matches; River Isle Ventures alone maps to 4 codes. |
| "Which dealers have payment exceptions in June 2026?" | 887 dealers, NGN 8,049,638.78 outstanding. |
| "Which dealers have activation exceptions in June 2026?" | 155 dealers. |
| "Top 10 HIGH-severity dealers for June 2026" | 61 of 922 match, NGN 2,737,023.81 outstanding; rank 1 is River Isle Ventures (296065), NGN 594,652.08. |
| "Which dealers have both payment and inventory findings in June 2026?" | 31 dealers, NGN 3,065,571.04 outstanding. |
| "Which dealers have the worst assurance health in June 2026?" | Routes to the investigation queue, not Financial Health. |

Then run them live: `RUN_EVALS=1 .venv/bin/python -m pytest backend/tests/test_evals.py -v`.

**Note.** The live run makes billed API calls and needs `ANTHROPIC_API_KEY`.
Get the user's go-ahead before running it. Adding the cases needs no approval.

**Size.** Small to medium. It may surface routing fixes in the `SCOPE_TOOL`
text.

### A3. Policy answers intermittently fall back (cause unknown)

**Problem.** `PROGRESS.md` (2026-10-03) records intermittent policy-answer
fallbacks during live rehearsal; the cause was not established. Named policy
topics now avoid them for two known questions, but the underlying cause is
still there.

**Done when.** The cause is found from logs or reproduced with repeated live
runs, and is either fixed or written up with evidence. Do not guess a fix
without a reproduction. Live runs are billed, so ask first.

**Size.** Unknown. This is an investigation.

---

## B. Live-mode (Presto) gaps

These do not affect the sample-data demo. Fix them before anyone runs Atlas
against Presto.

### B1. Subscription commission is always "unavailable" in live mode

**Problem.** `queries.has_source_period` returns `False` whenever
`USE_SAMPLE_DATA` is false (`backend/db/queries.py:1746`: "Live queries have
no implemented coverage contract yet"). As a result:
- `_subscription_commission` (`backend/db/dealer_statement.py:231`) always
  reports `unavailable` in live mode;
- the same check gates statements in `backend/db/measure_evidence.py:74`.

The source key itself is the sample fixture `subscription_commission_demo`
(`backend/db/dealer_statement.py:198`, `backend/config.py:130`).

**Done when.**
- There is a live coverage check: a parameterized, `mon_period`-filtered
  SELECT in `queries.py` that proves the source holds rows for the month.
- The subscription commission source is a live table, not the demo fixture.
- Tests cover covered, uncovered and unreadable months in live mode with
  mocked Presto.

**Blocked on.** Knowing which development-schema table holds subscription
commission owed/paid. None is listed in `CLAUDE.md`'s allowed tables, so
confirm the table with the user first.

**Size.** Medium, once the table is known.

### B2. On-request audit checks read the whole month (cost unmeasured)

**Problem.** Atlas's `verification_outcome` runs the audit modules'
`run_dealer(period, dealer_id)` on request. `run_dealer` shares
`_select_subjects` with `run_period`, which reads the whole month and then
filters to one dealer. For example, inventory reads `get_inventory_comparison`
for the full period (`backend/audit/inventory_mismatch_audit.py:506`). On
sample CSVs this is fast. On Presto it has never been measured.

**Done when.** Timings for one `run_dealer` call per module against Presto
development are recorded in `docs/INFERENCE_LATENCY.md`. Per `CLAUDE.md`,
optimise only with evidence. If a module is too slow, add a dealer-filtered
query in `queries.py`.

**Blocked on.** Presto access.

**Size.** Small to measure, medium to fix.

---

## C. Needs a decision before code

### C1. "ORSC" still appears in a screen's source label

`backend/db/commission_workspace.py:18` returns the provenance
`"Sample CSVs · synthetic March 2026 ORSC demo data"` for the Subscriptions
stream in 202603. The agreed rename to "subscription commission" covered
Atlas answer text only, not the UI.
- **Decision needed:** should the UI drop "ORSC" too?
- **Recommendation:** change it to "subscription", because the demo should
  not say ORSC.
- **Leave alone:** the "Synthetic"/"Demo" badges elsewhere in the UI. They
  are deliberate data-source disclosures.

### C2. Eligibility definition (Finance)

Finance must decide between reporting-month and invoice-to-activation
eligibility (`PROGRESS.md`, 2026-10-03). This is a business decision, not
agent work. Atlas currently states the uncertainty.

---

## D. Code tidiness (low priority; no user-visible bugs)

Each of these came from code review. They are safe to batch into one
refactor branch. Keep behaviour identical, so existing tests pass unchanged.

1. **Queue bounds written out in several places.**
   - `MeasureScope` hard-codes `le=100` and
     `queue_severity: Literal['HIGH','MEDIUM','LOW']`, and lists the four
     module names (`backend/agent/measure_scope.py:65-68`).
   - The reader has `QUEUE_MAX_LIMIT` (`backend/assurance/overview.py:226`).
   - The validator uses `SEVERITY_ORDER` / `ASSURANCE_REGISTRY`.
   - Derive the scope's values from those constants, so a fifth assurance
     module needs no hand edit.
2. **Measure-name special cases outside the tables.**
   `measure_response.py:108` (`if name == "investigation_queue"`) and
   `tool_executor.py:72` (`_reader_options`) special-case the queue by name.
   Move these into the `_STANDALONE` / `_STANDALONE_EVIDENCE` registries as a
   request-check hook and an options slot.
3. **Inconsistent reader idiom.** `investigation_queue_evidence` raises
   `ValueError` for a dealer, while `investigation_priority_evidence` returns
   `_unavailable(...)` for a scope mismatch. Pick one. `_read_queue` returns a
   4-tuple with `note` as the error sentinel; a small result type would be
   clearer. `_unavailable`'s `payload` parameter is really the evidence key.
4. **Duplicated exception renderers.** The activation and payment exception
   measures duplicate their validate/render shapes in `measure_response.py`.
   Extract the shared shape.
5. **Private imports across modules.**
   - `dealer_resolution.py:15` imports `_text`.
   - `exception_evidence.py:83` uses `activation_workspace._SEVERITY_RANK`.
   - `routes.py:653` `_STATUS_RANK` restates `payment_snapshot.EXCEPTION_STATUSES`
     (`backend/db/payment_snapshot.py:209`) plus FULLY_PAID.

   Make the shared pieces public in their owning module. The API may import
   from `backend/db`, but not the other way round.
6. **Queue validator gaps.**
   - `_check_queue` (`measure_response.py:1265`, about 50 lines) checks the
     number of table rows but not that each row matches its dealer. Split it
     into per-dealer and totals checks.
   - `outstanding_ngn` is a float built from a `Decimal`. If a source ever
     sends amounts with more than 2 decimal places, the cent-sum check could
     raise a false `ValueError`. Carry `Decimal` or a string.
7. **Recorded dealer names with doubled internal spaces.** Typed names are
   normalised (`dealer_resolution.py:52`), but recorded names are not, so
   "Amber  Arc" in the data would miss an exact match. No such names exist in
   current data.
8. **Presentation nits.**
   - The queue table capitalises module names, but the "Not checked:" line
     prints them lowercase.
   - "Lead finding" shows a code ("Payment · COMMISSION\_DISPUTE"), as
     `investigation_priority` does. Change both together, or neither.
   - Single-dealer exception answers omit the ordering note. That is
     harmless with one row.

---

## Suggested order

1. A1, alone.
2. A2: add the cases, then ask before the live run.
3. D, as one refactor branch. Run it after A1, since both touch
   `measure_scope.py` and `test_chat_stream.py`.
4. C1, after the user decides.
5. B1 and B2, when Presto access and the subscription table are confirmed.
6. A3, alongside any live run.

Merge each branch before starting the next one that touches the measure
registries or `test_chat_stream.py`. Parallel branches there have caused
merge conflicts before.
