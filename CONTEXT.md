# FBB Trade Partner Finance

Terms used to explain partner commissions, their supporting revenue, and
dealer business financial health.

## Language

**Activation commission**:
The recorded commission associated with a partner's device activations.
It is distinct from subscription revenue and payment settlement.

**ORSC subscription revenue**:
The recorded data subscription amount associated with devices sold by a partner,
used as the revenue basis for Ongoing Revenue Service Commission (ORSC).
Subscription revenue alone does not establish commission payable.
_Avoid_: ORC, ORSC payable (when referring only to subscription revenue)

**No source records**:
No records are available for the selected revenue stream and reporting period.
This does not establish a verified zero balance.

**Zero-amount record**:
A source record exists with a recorded amount of zero. The amount alone does
not establish why it is zero.

**Synthetic demo data**:
Fictional records constructed to demonstrate a workflow; they are not evidence
of actual partner revenue or amounts owed.

**Simulated subscription commission**:
A supplied fictional calculation under the illustrative subscription policy,
separate from ORSC recorded revenue and activation settlement. It never
establishes actual MTN payable. See `docs/SUBSCRIPTION_COMMISSION_DEMO.md`.

**Subscription expectation variance**:
Recorded simulated commission minus the supplied fictional dealer expectation.
A missing expectation gives an unknown variance, not a zero expectation.

**Subscription churn indicator**:
Context supported by three consecutive months without paid subscriptions and
sufficient activity history. It is separate from this month's exclusion reason;
one month without renewal does not establish churn.

**Dealer financial health**:
The financial condition of a dealer's whole business, considered by MTN Finance
when assessing potential funding candidates. It extends beyond the dealer's
MTN commission and settlement account.
