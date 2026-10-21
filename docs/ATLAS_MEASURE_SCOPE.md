# Atlas requested-measure enforcement

Status: implemented and verified; user confirmed the design and test seams.
Source: `/private/tmp/atlas-measure-scope-handoff.md` and its three accepted policies.

## Accepted behavior

- Answer the requested measure or explicit set of measures, including essential
  dealer, period, provenance, coverage and uncertainty context.
- Reuse a business definition established in the active conversation. Clarify
  only what the latest question, active scope and conversation cannot resolve.
- When evidence is unavailable, identify what is missing. An alternative may be
  offered without figures; its figures require the user's acceptance.
- Preserve explanations when requested, without presenting observations or KB
  possibilities as verified causes.

## Implementation

Use the shared buffered/streamed agent boundary to resolve a structured request
containing measure identifiers, operation, dealer and requested periods. Keep the
latest question distinct from workspace context so a Payment workspace cannot
implicitly turn an activation question into a payment investigation.

Natural-language resolution remains probabilistic. Validate the resulting scope
and fail to a focused clarification when it is unresolved. Do not describe the
resolver, a second model review, or a lexical answer check as a guarantee.

Apply a deterministic policy between the resolved request and data tools. Read
only the evidence needed for that scope, project away unrelated measures, and
retain results separately for every tool/parameter combination. Build requested
figures from validated evidence references with application-owned metric labels
and formatting. A model cannot supply an invented number or relabel an
activation count as sales through that rendering boundary.

Explanations show supported comparisons and bounded source observations. Causes
require verification; free-form provider prose is not rendered. The KB currently
describes both reporting-month and invoice-to-activation eligibility windows.
The application does not choose between those conflicting rules or infer a product not matched to the commission rate card from a zero rate. Exact-dealer activation explanation requests may
inspect up to 100 zero-record date observations and disclose what remains
unverified. Other explanations preserve source-specific uncertainty.

Do not send unvalidated draft text to the browser. Keep stream progress and
cancellation, then publish only accepted answer content. This changes text
delivery timing, so regression checks must cover the transport contract.

Use existing scoped conversation history for agreed definitions; do not add a
preference store, authentication, data integration, or a multi-agent product.

## Evidence findings

| Measure | Existing evidence | Boundary |
| --- | --- | --- |
| Activation count | `get_dealer_summary.total_activations` | Filter exact dealer before projection; omit commission fields. |
| Activation commission | `get_dealer_summary.total_commission_ngn` | Full query retains denomination breakdown; triage does not. |
| Subscription revenue | `get_orsc_summary.total_subscription_amount_ngn` | Separate from subscription commission and sales. |
| Subscription commission and settlement | Recorded subscription evidence service | Preserve nullable amounts and completeness flags. |
| Customer sales | No adequate evidence in current Atlas contract | Need dated customer transactions, quantities, actual amounts and returns. |
| Dealer purchases | Inventory comparison purchase fields | Comparison excludes purchase-only products; cannot establish total purchases. |
| Financial Health revenue | Synthetic financial reports | Never present as actual sales. |

Existing triage responses contain overlapping, capped dealer lists and hints for
additional investigation. They are unsuitable for complete requested breakdowns
or totals. Project the complete query result before triage where necessary.

Missing sample months may currently become empty query results and zero
headlines. Establish source-specific coverage before treating a figure as zero.
Activation period metadata is not proof of subscription or payment coverage.
Reuse existing provenance helpers and keep synthetic origins visible.

Payment triage omits APDP sales enrichment, so say that customer sales are
unavailable through the scoped Atlas evidence, not that no sales data exist
anywhere in the platform.

## Confirmed test seams and acceptance cases

Use the public buffered and streamed agent/chat interfaces with provider fakes
and real sample evidence, plus the new measure-policy boundary.
Do not make billed provider calls.

1. An explicit activation request obtains activation evidence without sales
   clarification, commission figures or an unrelated investigation.
2. An ambiguous sales request clarifies; a user-established definition survives
   follow-ups and retains the selected dealer.
3. Unsupported measures identify missing evidence and withhold proxy figures
   until acceptance.
4. Multiple requested measures and requested explanations remain supported.
5. A year/range retains the requested range and explicitly distinguishes queried,
   available and missing months. Missing months never become zero.
6. Adversarial model tool choices or evidence references cannot escape the
   resolved measure/dealer/period contract.
7. Unaccepted prose or numbers never appear in streamed events, including on
   provider failure, truncation, cancellation or iteration exhaustion.
8. Old history and workspace labels cannot authorize unrelated measures.
9. Sample/synthetic provenance survives concise rendering.

Fake-provider checks prove application behavior for the supplied interpretation;
they do not establish live model intent-recognition accuracy.

## Verification and completion

Run focused pytest files during each slice, Python compilation for modified
modules, and the full offline backend suite once at completion. Run frontend
transport tests and the production build if the delivery contract is affected.
This repository has no configured standalone typecheck.

Perform separate Standards and Spec reviews against the initial commit
`75c86736503c454d68ce5678840d48374b553046`, excluding pre-existing dirty changes.
Update architecture/progress documentation and commit only this implementation
to the current branch. No deployment or production writes.

## Operating limits

- Sales meanings persist through the existing conversation history; there is no
  application-wide default or new preference store.
- Requests are bounded to 12 measures and 24 months; comparisons currently target
  two explicit months. Breakdown displays are capped at 100 rows with disclosure.
- Supported metrics cover activation counts/commission, recorded subscription
  revenue/commission/settlement, simulated payment figures/status, inventory
  comparisons, and synthetic Financial Health values. Specific financial KPIs,
  statements and lines have validated selectors; whole reports require explicit
  whole-report requests. Dealer code lookup remains a separate non-financial path.
- Customer sales and complete dealer purchases remain unavailable through this
  evidence contract. Offers do not authorize proxy figures.
- A missing product breakdown or unsupported filter is explicitly unavailable;
  complete values are never reconstructed from capped triage lists.
- Live Presto execution was already an unimplemented stub. This work adds no
  integration; source coverage remains unavailable where it cannot be verified.
- Exact core KB excerpts support general policy questions. Ordinary chat no longer
  generates unrestricted prose or fetches arbitrary addenda; existing standalone
  tools, finding explanations and their endpoints are unchanged.
- Offline checks establish application enforcement for supplied interpretations.
  Live intent-recognition accuracy and model-generated scope choices have not been
  evaluated in this implementation session.

## Verification record

- Full offline backend suite: `USE_SAMPLE_DATA=true RUN_LIVE_AGENT_TESTS=0 RUN_EVALS=0 .venv/bin/python -m pytest backend/tests -q` — 500 passed, 29 skipped.
- Frontend transport: `node --test frontend/tests/*.test.mjs` — 11 passed.
- Production build: `npm --prefix frontend run build` — passed.
- Python compilation and `git diff --check` — passed. No configured standalone typecheck.
- Isolated localhost HTTP checks with a fake scope provider and real sample data
  returned 806 March activations for the fixture account and a sales clarification;
  injected commission prose never crossed the response boundary. The process was
  stopped after verification. Streamed HTTP and real SDK framing/cancellation were
  checked in the offline suite.
- Separate Standards and Spec reviewers found no remaining issues after remedies.
  No paid provider calls, production writes, or deployment occurred.
