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

**Subscription commission**:
Recurring partner earnings attributed to subscriptions on devices the partner
originally sold. Recorded subscription revenue alone does not establish these
earnings; an approved entitlement policy and recorded commission evidence are
needed to establish actual amounts owed.

**Settled subscription commission**:
The portion of recorded subscription commission supported by settlement evidence.
Missing settlement evidence does not establish a paid amount of zero.

**Outstanding subscription commission**:
Recorded subscription commission less recorded settlement for the same account
and period. It is unknown when either amount lacks evidence.

**No source records**:
No records are available for the selected revenue stream and reporting period.
This does not establish a verified zero balance.

**Zero-amount record**:
A source record exists with a recorded amount of zero. The amount alone does
not establish why it is zero.

**Synthetic demo data**:
Fictional records constructed to demonstrate a workflow; they are not evidence
of actual partner revenue or amounts owed.

**Dealer financial health**:
The financial condition of a dealer's whole business, considered by MTN Finance
when assessing potential funding candidates. It extends beyond the dealer's
MTN commission and settlement account.

**Partner sales invoice**:
An invoice from MTN to a trade partner for goods purchased by that partner.
It represents the partner's purchase obligation, distinct from commission MTN
owes the partner.

**Partner Commission Account**:
The view of a trade partner's recorded commission earnings, settlements, and
outstanding commission owed by MTN. Sales invoice balances are separate obligations.
_Avoid_: Receivable account (without identifying whose receivable and its source)

**Simulated invoice**:
A fictional invoice used to demonstrate a sales workflow. It does not establish
an actual purchase obligation or an invoice issued by MTN. Each one comes from a
partner order MTN Finance issued, apart from the example invoices the simulation
starts with.

**Draft order**:
An unsubmitted partner order a partner login is preparing for its own account. It
is private to that partner and establishes no obligation. Finance has no invoice
drafts: it issues what partners submit.
_Avoid_: Proforma, quote, invoice draft

**Simulation reset**:
Returning the whole simulation to its starting example records for everyone signed in.
Records from before the reset can no longer be changed, even where a later record has
the same reference.

**Invoice collection**:
A payment from a trade partner toward a specific MTN sales invoice. It reduces
the invoice obligation and is distinct from MTN settling commission to the partner.

**Opening outstanding commission**:
Commission remaining unpaid at the start of the statement period, supported
by opening-balance evidence rather than inferred from that period's earnings.

**Closing outstanding commission**:
Opening outstanding commission plus recorded period earnings less period
settlements, when all components are evidenced. Invoice collections do not change it.

**Account code**:
The identifier of one exact trade partner account. Same-named accounts have
different account codes.
_Avoid_: Partner code (that names an audit subject)

**Partner login**:
A demonstration sign-in tied to exactly one trade partner account code. Same-named
accounts have separate logins.

**Internal login**:
A demonstration sign-in shared in role by Finance and Revenue Assurance users.

**Partner order**:
What a partner login submits from its own draft order: fixed lines and total under a
`SIM-ORD-` reference, read-only once submitted. It is not an invoice or a purchase
obligation; only MTN Finance issuing it makes one. A draft order is private to its
partner and reaches Finance only by submission.
_Avoid_: Purchase order

**Rejected order**:
A partner order MTN Finance declined, with the reason it gave the partner. It is final:
it cannot be resubmitted or issued later, and the partner starts a new draft instead.

**Issued order**:
A partner order MTN Finance issued as a simulated invoice with the same lines and
total, and its own dates. Like a rejection, issuing is final.
