# Atlas evidence-based investigations

Approved scope: complete, realistic sample-data investigations for zero commissions,
month-on-month activation commission changes, and earned-versus-paid discrepancies.
The workspace identifies sample data; answers do not repeat synthetic-data disclaimers.

## Contract

One read-only investigation service owns counts, classifications, source references,
policy version, bounded record pages and next actions. Chat, Findings evidence and
commission dispute drafts reuse it. A record is assigned one primary recorded rejection
reason; other observed conditions are supporting evidence, not additional counted causes.
The four permitted KB causes remain the only commission causes. Missing, stale,
contradictory or duplicate supporting evidence stays unresolved.

Persisted calculation evidence is keyed by period, dealer and device, with a fingerprint
of the underlying zero-commission record. Historical classification and product mapping
are fictional source evidence and may differ from the current activation extract.
Runtime never creates evidence to fit an answer. No payable amount is recalculated.
Missing monetary impact is not replaced with an estimated entitlement.

The existing sample eligibility policy is invoice-to-activation calendar days 0–180
inclusive. Unknown live policy cannot inherit this assumption. Full population counts
are computed before paging; pages have a maximum of 100 records.

Variance explanations reconcile product contributions exactly to recorded totals and
compare qualification counts and zero-cause populations. They distinguish an arithmetic
contribution from the reason an individual record earned zero. Payment investigation
uses the configured payment source; simulated process records must not enrich APDP.
A workflow status alone cannot prove why a payment was held.

## Verification

Regression covers the reported June account 296065, more than 100 affected records,
eligibility boundaries, missing/stale evidence, overlapping conditions, source isolation,
variance reconciliation, payment amount reconciliation, scoped follow-ups and rendering.
Natural-language routing is checked separately from deterministic evidence calculations.

## Demonstration walkthrough

Select River Isle Ventures, account 296065, June 2026, in Payments:

1. “Why does this dealer have zero commission?” — 50 records: 48 recorded products not matched to the calculation-month commission
   rate card and 2 outside the 180-day window.
2. “Show me the affected records.” — the first 20 records, including invoice and
   activation dates, date gaps, rejection reasons and source references.
3. “Show the next page.” — a disjoint page, preserving full-population counts.
4. “What should Finance do next?” — owner-specific review actions.
5. “Draft the dealer explanation.” — a read-only draft for review.
6. “Why did their commission change compared with May?” — NGN 39,873.42 increase;
   472 → 495 activations; 425 → 445 non-zero commission activations; 47 → 50 zero
   records, with product contributions summing to the change.
7. “Why were they not paid the full commission in June?” — NGN 594,652.08 remaining
   against NGN 991,086.80 owed and NGN 396,434.72 paid; recorded dispute-review batch.

These seven turns passed a real provider rehearsal after resolving conflicting
variance routing instructions. Buffered and streamed paths also have mocked-provider
regressions with real sample readers. Browser verification confirmed the original
zero-commission question and a five-record evidence table render in the Payments
workspace. Existing Payment table queryFn console warnings and an unavailable local
saved-audit store were observed independently of the new chat path; neither blocked
these investigation answers. No production data, payment action, or deployment was used.

Saved audit outcomes are not rewritten. Their original input evidence and run time
may differ from the current investigation support; do not treat an old saved verdict
as verification of a newly generated fixture.

## Conversational answer boundary

Ordinary chat now sends the validated request and bounded structured evidence to
a second Claude call through the existing Anthropic Python SDK. Claude chooses
the wording. The application retains retrieval, calculations, classification,
source status, tables and audit disclosure. The input also includes validated
policy context and application-derived figures that still live in the existing
response builders. This follows the SDK's separation between application-run
tools and model composition ([official tool lifecycle](https://platform.claude.com/docs/en/agents-and-tools/tool-use/how-tool-use-works)).

The model returns an answer with references to supplied facts. Substitution owns
numerical and identifier formatting. Exact source product/date labels can also
be resolved to their existing fact references; unknown labels and ambiguous
month aliases are rejected. Purely numeric identifiers, counts and amounts still
require explicit references. The generation projection supplies calculated
largest-positive-contribution and all-product-growth facts, keeping the original
raw evidence unchanged. Fact meanings distinguish period levels from changes
and total activation counts from qualified counts.
Known-invalid values, references, causal
assertions and direct payment-label contradictions are rejected before any text
event. One repair uses the same request deadline and retry allowance; failure
returns a short message while preserving already retrieved evidence. The model
sees at most twelve rows per narrative sample, with omissions identified. For
record-page requests it receives only status, family and scoped identity/date
facts; exact page ranges and the complete bounded table are application-owned.
This prevents a second model-written range or duplicate table. Missing evidence
does not become a zero-sized population. Account codes and machine-readable
periods remain in supporting evidence even when the prose uses a recorded name
or a readable month. Monetary policy-table cells retain their NGN units.

These checks constrain known failure modes, not all meanings of natural language.
A valid fact can still be described incorrectly. Do not treat reference checking,
mocked-provider tests or an independent model review as proof of factual accuracy.
Use the public conversation walkthrough to assess factual correctness and
naturalness, including follow-ups, dates, unknown evidence and payment distinctions.

Live evaluation exposed and prompted fixes for missing policy-identifier facts,
page-range duplication, activation counts described as product counts, an affected
subset described as a whole dealer month, and a flat product described as growing.
Targeted public regressions cover these failures and valid counterpart answers;
independent Standards and Spec reviews are recorded in PROGRESS.md. The previous
successful result above describes the original deterministic implementation;
the separate Claude-composition verification results are recorded in PROGRESS.md.
