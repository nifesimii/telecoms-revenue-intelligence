# demo presentation flow

Working reference for the Atlas video demonstration to Finance and Revenue Assurance.
Use this document to develop the recording sequence and add questions, narration,
or screen actions later.

Take the audience through one investigation: **what we owe → what has been paid →
what changed → what the evidence supports → what Finance should do next**. Then
show the other direction with Partner Sales: **what the partner would owe MTN for
purchases, kept separate from the commission MTN would owe them**.

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

This is the first.
What activation commission is recorded for this dealer? | NGN 1,267,922.85, with the correct dealer and month. 
how many other dealer codes are addressed to the same dealer and what is their total commission
Why did their activation commission change compared with May? 


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

## Partner Sales: the other direction

River Isle Ventures, account 296065, connects the two parts. It is the Atlas
rehearsal's second dealer, the Partner Sales rehearsal partner, and the only account
whose Partner Sales commission account links back to the Commission evidence, in
May 2026. Step numbers refer to the [Partner Sales rehearsal](PARTNER_SALES_REHEARSAL.md).

Before recording, put two windows side by side: Finance in a normal window and the
partner in a private window, signed in as **partner-296065**. As Finance, choose
**Reset simulation**, then **Reset to starting point** shortly before you start.

| # | Part | Do | Say or show |
| --- | --- | --- | --- |
| 1 | Hand-off in Atlas | Switch to River Isle Ventures, 296065. Ask for June activations, then **"And May?"** | 495, then 472. Atlas keeps the dealer, and the demonstration is now in May 2026, the month Partner Sales uses. |
| 2 | The partner's view | Rehearsal steps 2 and 3: start a draft order, add 2 × FBB-5G-ROUTER and 100 × RCC-0100, preview and submit | The partner signs in to their own account only. The order totals NGN 110,000.00. |
| 3 | Finance acts | Steps 4 to 9: review SIM-ORD-0002, issue invoice SIM-INV-0004, record 40000, then 70000. Refresh the partner window after each | Each Finance action reaches the partner on their next refresh: Issued, Partially paid, then Paid. |
| 4 | Two separate balances | Steps 10 and 11: the partner's May commission account, then Finance's purchase obligations and commission account | The May commission account still closes at NGN 822,582.53. The partner would owe MTN for purchases and MTN would owe the partner commission. The two are never netted. |
| 5 | Back to the evidence | Step 12: **Explain activation commission**, then **Return to Partner Sales** | The partner's statement leads back to the recorded evidence Atlas works from. |

Every Partner Sales record is fictional. Issuing an invoice or recording a
collection establishes no actual purchase obligation or payment, and never changes
commission.

### For a shorter recording

- Skip rehearsal steps 13 to 15, the second partner and the final reset. Keep step
  13 if Revenue Assurance wants to see that a partner reaches only their own records.
- Show issuing only, not the rejection variant.
- Allow 20 to 30 seconds for each Atlas answer.

## Future additions

- Additional questions:
- Presenter narration:
- Screen actions or transitions:
- Feedback from Finance:
- Feedback from Revenue Assurance:
- Feedback questions: Would partners use a view like this? Do "purchase
  obligation" and "commission account" match the terms Finance uses?
- Closing message:

## Related rehearsal reference

See [Atlas demo rehearsal](ATLAS_DEMO_REHEARSAL.md) for additional questions,
sample figures, test commands, and verification limits, and the
[Partner Sales rehearsal](PARTNER_SALES_REHEARSAL.md) for every Partner Sales step,
what to expect and what to do if something goes wrong. This document captures
the proposed presentation flow; not every exact wording above has been separately
live-tested.
