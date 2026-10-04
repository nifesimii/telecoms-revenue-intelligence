# ORSC demo data

`fbb_comm_orsc_sample.csv` is the existing February 2026 reference sample.
`fbb_comm_orsc_202603.csv` is **synthetic March 2026 demo data**, not a March
source extract, validated revenue or a commission-payable figure.

The March fixture retains February's 200 device records, 157 dealer accounts,
dealer identities, products, invoice dates and first activation dates. Continued
subscription activity in March is a demo assumption. Historical invoice and
activation dates are deliberately unchanged.

For input row index `i` (starting at zero), the fictional March amount equals
the February amount multiplied by `(90 + i % 31) / 100`, rounded half-up to two
decimal places. This creates repeatable increases and decreases for comparison.
The 69 zero amounts remain zero; no business root cause is asserted for them.
These factors are fixture-generation choices, not commission rules.

Regenerate from the repository root:

```sh
python -m backend.data.generate_orsc_demo
```

The sample-mode configuration loads each month separately. Commission workspace
summary, detail and CSV export identify March ORSC as synthetic. February remains
unchanged; an absent month still has no source records. Live Presto reads are
unaffected. Restart an already-running backend after changing bundled fixtures
because sample CSVs are cached in memory.

## January–June 2026 coverage

January, April, May and June are synthetic demo extensions. February and March
activation/ORSC fixtures and existing payment records are preserved. The period
selector discovers all six months automatically and defaults to June.

Regenerate the added months and their derived simulated payments:

```sh
USE_SAMPLE_DATA=true PAYMENT_SOURCE=simulated python -m backend.data.generate_half_year_demo
```

January uses February's dealer roster and rows at 90% activation volume. April,
May and June use March at 95%, 105% and 110%. Each dealer retains at least one
record; stable source ordering determines selection/repetition. Recorded product
prices and per-device commissions are copied, not recalculated. Synthetic IMEIs
are unique across added activation months. Invoice, activation and snapshot dates
shift together by calendar months, clamping days at month end. This preserves
approximate invoice age; it does not assert eligibility or resolve source anomalies.

ORSC retains the same 157 accounts and 200 records per month. Amounts use the
month's volume percentage plus a deterministic -5 to +5 percentage-point variation
by row, rounded half-up to cents; zero amounts stay zero. January dates shift back
one month and its devices have synthetic IDs. April–June retain March's historical
devices/dates as assumed continuing subscriptions. These are demonstration choices,
not forecasts, commission rules or evidence of actual revenue.

The shared IFS purchase history and commission rate-card reference remain unchanged: inventory
comparisons continue using the existing cumulative purchase evidence rather than
inventing duplicate monthly purchases. Added payments derive from each month's
commission totals and the existing exception/rate mapping. All are SIMULATED.
Financial Health independently extends its existing four fictional businesses and
reconciled statement model through June; these businesses are not linked to the
commission dealer roster. Restart the backend to clear cached CSVs after generation.

## Inventory shared synthetic scenarios

`inventory_demo_scenarios.csv` adds 16 labelled comparison scenarios across 13
dealers and six products: 12 fictional purchase quantities and four retained
missing-invoice controls. Existing source CSVs remain unchanged. This separate
sample-only overlay is used by Inventory comparisons, with provenance carried
through API/UI, assurance and coverage tickets.

Regenerate only these two Inventory artifacts:

```sh
python -m backend.data.generate_inventory_demo
# Or inspect an isolated generation without replacing bundled artifacts:
python -m backend.data.generate_inventory_demo --output-dir /tmp/inventory-demo
```

The generated manifest records source hashes, scenario identities, and baseline
and enriched outcomes for January–June. Quantities are fixed, not recalculated
to preserve a desired classification after source drift. The generator rejects
existing IFS matches, invalid quantities and changed June anchor counts.

These are shared fictional purchase snapshots, not month-dated invoices. The
same quantity is compared with each month's existing activation count. Scenario
labels describe June's anchor examples; other months can classify differently.
No stock carryover, replenishment, alias resolution or actual coverage improvement
is asserted. Blank purchase quantities remain unknown. See
`docs/INVENTORY_DEMO_SCENARIOS.md` for the walkthrough and limits.

Restart the backend after regenerating cached CSVs. Search `Synthetic` in the
Inventory tab to isolate the cohort. Saved trails from other evidence are not
shown as verification of the synthetic quantities.

## Subscription commission statements

`subscription_commission_demo.csv` contains fictional recorded commission and
settlement amounts for the existing subscription dealer/device/month keys.
Subscription revenue remains in the original ORSC files. These statements are
sample-only evidence, not an implementation of MTN's commission calculation.

Regenerate the separate fixture with:

```sh
python -m backend.data.generate_subscription_commission_demo
```

The Commission workspace, matching-account export and subscription assistant
share these amounts. Subscription settlements remain separate from the existing
activation payment fixture. See `docs/SUBSCRIPTION_COMMISSION_DEMO.md` for the
fixture assumptions, unavailable-data behavior and path to live evidence.


### Financial Health cohort

`financial_health_dealers.json` freezes 20 existing sample dealer codes/names,
selected across March activation-volume ranks among codes present January–June
2026. `backend/db/financial_health.py` assigns fictional accounting scenarios to
these identities; selection and scenario assignment do not describe actual dealer
financial condition. Financial Health figures remain synthetic in every data
mode, and modeled commission income is independent of commission fixtures.

## Atlas investigation evidence

`commission_calculation_evidence.csv` and `settlement_process_evidence.csv` are
persisted fictional upstream decision/workflow records. They enrich the existing
January–June activation/payment fixtures without changing any recorded totals.
Regenerate with `python -m backend.data.generate_investigation_demo` and restart
the backend to clear the shared CSV cache. They are never created at request time.

Calculation records bind period, account and device to an activation fingerprint.
The generator preserves the invoice/activation dates: outside-window records take
that primary reason; inside-window records demonstrate snapshot misses, historical
NULL profiles, and a fictional Hynex/Hynex_1 mapping for router code 1283281. The
current activation extract is not rewritten to pretend its current profile was
missing. Historical lookup decisions supply that separate evidence. Non-anchor
records at deterministic intervals remain unresolved controls. These scenario
choices are not inferred historical facts, new commission rules, or live aliases.
Account 296065 in June has 48 lookup misses and 2 window exclusions.

Settlement records reconcile exactly to the existing owed/paid amounts and identify
a batch plus recorded workflow state. They apply only to simulated payments, never
APDP. Missing, duplicate, stale or contradictory support cannot establish a cause.
Workspace badges disclose sample data; conversational findings do not repeat the
label. See `docs/ATLAS_INVESTIGATIONS.md` for behavior and verification.
