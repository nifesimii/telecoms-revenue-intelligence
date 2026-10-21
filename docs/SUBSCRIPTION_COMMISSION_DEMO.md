# Subscription commission demo

## Decision — 28 September 2026

The demo must show the commercial relationship from a dealer's sold device to
monthly subscription revenue, recorded subscription commission, settlement and
outstanding commission. Revenue and dealer earnings are distinct amounts.

The existing subscription source contains device, dealer and month attribution,
but only `data_subscription_amount` as its monetary field. It does not establish
an approved commission payable. An older KB addendum incorrectly equated that
field to payable commission; this has been corrected. The actual subscription
rate, eligible revenue basis, eligibility and attribution policy, and upstream
commission/settlement fields remain unconfirmed. The activation rate must not be
reused as subscription policy.

## Demo representation

Use separate fictional recorded upstream commission and settlement fixtures in
sample mode, linked to existing dealer/device/month records. Preserve existing
subscription revenue and activation/payment fixtures. The fixtures demonstrate
the platform's presentation of upstream results; they are not a runtime
commission calculator or evidence of MTN's actual policy.

The fixture reuses source attribution; it does not independently verify the
original selling dealer. January through June contain 1,200 source device
records. Zero-revenue devices receive recorded-zero commission as an explicit
demo scenario, not an eligibility rule. Other commission amounts are arbitrary
scenario values capped at the floor of revenue solely for fictional plausibility
(whole NGN, or cents for sub-NGN revenue). This prevents demo commission exceeding
revenue; it establishes no approved rate or entitlement formula. Runtime code
reads recorded amounts. The fixture includes fully settled, partially settled
and unpaid dealer-month examples. A blank settlement amount means unavailable;
an explicit zero amount means a recorded unpaid position.

The subscription workspace shows:

- Recorded subscription revenue, preserving its current meaning.
- Subscription commission attributed to the dealer.
- Subscription commission settled and outstanding.
- Dealer-level detail and existing device counts for the selected month.

The demo's established sample-data context supplies provenance. Do not repeat a
synthetic badge on every figure. Preserve provenance in source metadata and this
document. Missing commission or settlement evidence is unavailable, never an
inferred zero. A recorded zero remains distinguishable from missing evidence.

## Data and API contract

`amount_ngn` continues to mean subscription revenue in the ORSC workspace.
The additive nullable fields are `subscription_commission_ngn`,
`subscription_settled_ngn` and `subscription_outstanding_ngn`. Row and summary
values must use the same fixture records and exact dealer code/reporting month.
Outstanding is the difference between the recorded commission and settlement.
Account filters, pagination and matching CSV export must agree on these amounts.
Live mode must leave unsupported subscription commission fields unavailable;
it must never manufacture them from live revenue or load demo evidence.

Contextual assistance uses the existing `get_orsc_summary` tool with the same
sample evidence as the workspace, keeping recorded revenue separate from the
explicit commission fields. No new agent tool, dynamic query, write endpoint or
production-table write is introduced. Existing activation settlement and dealer
statement reconciliation remain scoped to activation; their revenue-only
subscription context must be labelled as revenue.

## Path to live data

Before presenting live subscription commission as owed, confirm the approved
policy and the meaning of each source field with Finance and the upstream owner.
Obtain separately recorded commission and settlement evidence with dealer,
device and reporting-period attribution. Replace the sample evidence adapter
with validated read-only source data while preserving the distinction between
revenue, commission and settlement.
