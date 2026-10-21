# demo presentation flow

Working reference for the Atlas video demonstration to Finance and Revenue Assurance.
Use this document to develop the recording sequence and add questions, narration,
or screen actions later.

Take the audience through one investigation: **what we owe → what has been paid →
what changed → what the evidence supports → what Finance should do next**.

## Opening and setup

Introduce Atlas as an assistant for explaining and investigating recorded FBB
trade-partner commissions. Explain that the demonstration uses fictional sample
data and does not establish actual payments or production account balances.

Select **Stone Light Networks, account 74050**, **June 2026**, and start a fresh
Atlas conversation. Keep the dealer selected while asking follow-up questions.

Based on the platform's scope, Finance will likely focus on amounts and settlement,
while Revenue Assurance will likely focus on evidence, exceptions, and whether a
conclusion is justified. These are suggested audience priorities, not recorded
feedback from the teams.

## Main demo questions

| Step | Ask Atlas | What a good answer should demonstrate |
| --- | --- | --- |
| 1 | What activation commission is recorded for this dealer? | NGN 1,267,922.85, with the correct dealer and month. |
| 2 | How much has been paid, and what remains outstanding? | Recorded settlement and outstanding amounts, with clear separation from subscription commission. |
| 3 | Does that prove the dealer actually received the money? | Distinguishes recorded or simulated settlement evidence from bank or Oracle confirmation. |
| 4 | Why did their activation commission change compared with May? | Explains the NGN 51,331.98 increase using the product comparison. |
| 5 | Which product contributed most to the increase? | Identifies MIFI_1 and its NGN 33,906.87 contribution. |
| 6 | Why do they have zero-commission records? | Identifies 104 records, discloses bounded inspection, and preserves uncertainty about causes. |
| 7 | Which causes are confirmed, and which still need evidence? | Separates observations, documented possibilities, and verified findings. |
| 8 | Were all those records outside the eligibility window? | Explains the audit's findings and the unresolved eligibility-policy conflict. |
| 9 | What subscription revenue did they generate, and how much subscription commission was recorded? | Keeps NGN 14,080.50 revenue separate from NGN 1,518.00 commission. |

For a short recording, prioritize steps **1, 2, 4, 6, and 7**, followed by the
question about additional evidence below.

## Follow-up questions that test understanding

Use these naturally after an answer. They test whether Atlas can identify the
figure, supporting evidence, uncertainty, and next action.

- What evidence supports that conclusion?
- Are you explaining the amount, or establishing why it happened?
- What can we conclude confidently, and what remains unknown?
- What additional evidence would resolve this?
- Explain that in plain language for the dealer.

## Broader Finance and Revenue Assurance questions

These are likely discussion areas based on the platform's purpose. Use a
portfolio-level view where the question concerns all dealers.

- Which dealers should we investigate first this month?
- Which dealers have both payment and inventory findings?
- Where is missing source data preventing a reliable conclusion?
- Can you show the verification steps behind this finding?
- Does a high-confidence audit result mean the underlying business rule is confirmed?

## Clarification and conversation continuity

With account 74050 and June 2026 selected, ask this sequence:

1. **What were their sales?**
2. **I mean actual retail sales to customers.**
3. **Use recorded activations instead, for June.**
4. **And May?**

Atlas should clarify the meaning of sales, explain that customer-sales evidence
is missing, and then return **887 June activations** and **846 May activations**
after the alternative is accepted. It should retain the dealer throughout.

## Eligibility point to explain during the recording

The knowledge base contains conflicting reporting-month and invoice-to-activation
eligibility definitions. Finance must confirm the authoritative rule before Atlas
can establish actual eligibility. Audit labels and confidence describe the
recorded checks; they do not resolve that policy conflict.

Use this as an example of Atlas identifying a decision that Finance must resolve.

## Future additions

- Additional questions:
- Presenter narration:
- Screen actions or transitions:
- Feedback from Finance:
- Feedback from Revenue Assurance:
- Closing message:

## Related rehearsal reference

See [Atlas demo rehearsal](ATLAS_DEMO_REHEARSAL.md) for additional questions,
sample figures, test commands, and verification limits. This document captures
the proposed presentation flow; not every exact wording above has been separately
live-tested.
