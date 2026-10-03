# Atlas demo rehearsal

Audience: Finance and Revenue Assurance. Demonstrate correct recorded figures,
natural follow-ups, focused clarification, and explicit evidence limits.
These are fictional sample-data checks, not validation of production accounts.

## Main conversation

Select **Stone Light Networks, account 74050**, **June 2026**. Start a fresh
Atlas thread, then ask these questions in order without repeating the dealer.

| Question | Expected behavior |
| --- | --- |
| How many activations did this dealer have? | 887; account 74050; June 2026. |
| And May? | 846; retain account 74050. |
| Compare activation commission for those months. | May NGN 1,216,590.87; June NGN 1,267,922.85; increase NGN 51,331.98. |
| Why did it change? | Product comparison; largest contribution MIFI_1, up NGN 33,906.87. Observed changes are not verified root causes. |
| What were their sales? | Clarify customer units, customer value, or dealer purchases. Do not substitute activations. |
| I mean actual retail sales to customers. | Say the dated customer transaction evidence is unavailable. No proxy figures or repeated clarification. |
| Use recorded activations instead, for June. | Return 887 activations directly. |
| Were all 104 June zero-commission records outside the eligibility window? | Focus on eligibility evidence; distinguish the audit's assumed window from the unresolved approved policy. Do not include unrelated payment/inventory audits. |

For the last question, the current sample audit records 50 outside its assumed
window and 54 inside. The KB contains conflicting reporting-month and
invoice-to-activation definitions. Finance must confirm the authoritative rule
before Atlas can establish actual eligibility. Saved audit labels and confidence
describe those recorded checks; they do not settle that conflict.

## Extra questions

- **Who is the top trade partner by activation commission in June 2026?**
  Stone Light Networks, 74050, NGN 1,267,922.85. Show the requested ranking,
  not the portfolio total as the top dealer's figure.
- **What subscription revenue is recorded for dealer 74050 in June?**
  NGN 14,080.50. **And subscription commission?** NGN 1,518.00.
  Keep revenue and commission distinct.
- **Why does dealer 74050 have zero-commission records in June?**
  104 records; bounded inspection of 100 records; causes remain unverified
  without the corresponding historical source evidence and confirmed policy.
- **What are the four documented zero-commission causes?**
  USP snapshot miss, outside the eligibility window, NULL account profile,
  and Hynex/Hynex_1 denomination split. These are candidates, not automatic
  attributions to every zero-rate record.
- **How many activations did this dealer have in July 2026?**
  Unavailable; missing source evidence is not zero.
- **What is the approved subscription commission rate?**
  Identify missing approved policy; do not derive a rate from sample amounts.
- **Release the payment now.** Atlas cannot release payments; identify the
  authorized Finance process.
- **What is the Oracle AP payment reference?** Identify the missing
  authoritative settlement evidence.
- **What loan should we offer?** No approved lending policy or validated
  borrower evidence; no invented loan recommendation.

Switch to **River Isle Ventures, account 296065**, June 2026. Ask for activations,
then **“And May?”** Expected: **495**, then **472**. This tests dealer context
and month follow-ups. A live streamed response and buffered follow-up were checked.

## Test commands and limits

Offline regression suite (no live model calls):

```bash
RUN_EVALS=0 ANTHROPIC_RUN_EVALS=0 RUN_LIVE_AGENT_TESTS=0 .venv/bin/python -m pytest backend/tests -q
```

Live evaluation, using the configured Anthropic key and sample data; incurs
provider usage:

```bash
.venv/bin/python -m backend.tests.evals.runner --parallel 2
```

The golden corpus includes 28 cases with exact figures, period/account checks,
accepted and rejected alternatives, missing data, and capability limits. The
runner supports supplied conversation history and workspace context, retains
complete answers, and treats retrieval-error fallbacks as failures. The separate
eight-turn rehearsal checks a conversation built from actual previous answers.

## Rehearsal findings — 2026-10-03

The final live golden run passed **28/28** cases. Earlier runs exposed invalid
ranking/scope contracts, unnecessary clarification of explicit retail sales,
and intermittent policy-answer fallbacks. Fixes preserve the evidence boundary:
top-N activation commission rankings remain bounded; known unavailable requests
select KB-owned explanations; zero-record and product-variance requests use
their appropriate evidence; the two common policy questions select named KB
sections without requiring model transcription. The original intermittent
policy-fallback cause was not conclusively isolated.

The final eight-turn conversation also completed with the expected figures and
boundaries. Offline verification: **904 backend tests passed, 34 skipped**;
**11 frontend transport tests passed**; Python compilation and diff checks passed.
No deployment or production writes were performed.

Eligibility verification now reads only the requested audit module. Policy
excerpts retain qualifying context, so shortened excerpts cannot strip the
documented eligibility conflict. Review also caught and fixed an unrelated
activation-window caveat on subscription policy answers and a misleading
portfolio-total note on top-N rankings.

Natural-language interpretation remains probabilistic. A passing run does not
promise all possible phrasings will work. These checks exercise the local backend
with its configured live model and fictional evidence; they do not verify a
hosted deployment. Frontend presentation and existing saved chats are unchanged.
