# Richer Inventory demo scenarios

## Implementation contract

This increment implements the broader invoice-match opportunity in
`INVENTORY_DATA_ASSESSMENT.md` with an isolated, deterministic synthetic cohort.
It also records baseline-versus-enriched comparisons so the effect of adding
purchase evidence can be demonstrated without presenting a fictional ingestion
event as historical fact.

- Preserve all existing activation, IFS, USP, ORSC and payment fixture bytes.
- Store fictional purchase quantities in `inventory_demo_scenarios.csv`, with
  stable scenario IDs, labels, dealer/product keys and nullable purchased units.
- Apply only through the sample Inventory query. Existing matching IFS evidence
  must never be replaced or combined silently with fictional evidence.
- Compare the same fixed shared quantity with each reporting month's existing
  activations. This follows current shared-dataset semantics; it does not add
  period-matched invoice history, replenishment or stock-balance rules.
- Include exact, above-activation, small-excess and large-excess examples across
  multiple dealers/products, plus intentionally missing invoice evidence.
- Keep unknown purchases/gaps/percentages null. Only positive finite quantities
  can stand for supplied synthetic purchase evidence.
- Carry scenario provenance through query/API, table/detail, assurance and
  coverage-ticket text. Exclude fictional quantities from carryover/alias checks;
  new verification of a synthetic scenario is inconclusive, not proof of an
  actual inventory discrepancy.
- Do not present an older saved trail as verification of the new fictional
  quantities. The underlying saved trails remain unchanged.
- Preserve bounded pagination, maximum 100 rows, deterministic sorting and
  server-side aggregates across all filtered results.

The generator and manifest must make regeneration reproducible and show expected
outcomes in January–June. Exact/over/under labels describe the anchor demonstration;
the actual classification always follows the selected month's activation count.

## Deliberately deferred

Monthly purchase windows and evidence-arrival timelines require a separate
business/data contract. Confirmed SKU aliases require source evidence; this
increment creates none. Zero-quantity source invoice records are not invented
because their source meaning has not been established. These are boundaries of
the richer sample-data change, not missing commission rules.

## Verification boundaries

Proposed automated boundaries are the public inventory query, bounded comparison
API and fixture-generator outputs. Existing focused tests and the full sample
suite must continue to pass. No Presto connection or production write is involved.

The UI uses the existing inventory layout, adds visible scenario provenance, and
makes scenarios discoverable by searching `Synthetic`. Scenario labels describe
fictional demonstrations; dealer/product identities and activation counts remain
those of the existing sample data.

## Try the scenarios

Select **June 2026**, open **Inventory**, and search **Synthetic**. Keep that
search while switching the three views:

- Needs Investigation: six observed mismatches, 102 observed excess units and
  four retained invoice gaps.
- Invoice Coverage Gaps: four combinations, four dealers and 723 activations
  without purchase evidence. Purchased quantities remain unknown.
- Within Recorded Purchases: six combinations, 1,219 purchased units and 1,116
  activation records. Three combinations match exactly.

Representative examples (find by dealer code to distinguish repeated names):

| Scenario | Dealer / product | Purchases | June activations | Difference |
| --- | --- | ---: | ---: | ---: |
| Exact | Stone Light Networks — 74050 / 1283279 | 379 | 379 | 0 |
| Purchase cushion | Azure Leaf Communications — 69031 / 1212360 | 300 | 246 | −54 |
| Small excess | Quartz Meadow Networks — 90032 / 1283279 | 186 | 187 | +1 |
| Larger excess | Ember Hill Networks — 98052 / 1186254 | 200 | 244 | +44 |
| Missing evidence | Silver Grove Communications — 213044 / 1283279 | Unknown | 208 | Unknown |

Changing months changes activation counts; it does not represent invoice arrival
or a stock movement. Changing the reporting month resets the view/search as before.

## Whole-month enriched distribution

| Month | Observed mismatches | Excess units | Invoice gaps | Within purchases |
| --- | ---: | ---: | ---: | ---: |
| January | 10 | 131 | 3,856 | 61 |
| February | 12 | 162 | 3,994 | 61 |
| March | 27 | 284 | 4,138 | 71 |
| April | 27 | 238 | 4,072 | 70 |
| May | 29 | 325 | 4,138 | 69 |
| June | 35 | 377 | 4,138 | 63 |

The original baseline remains recorded in `INVENTORY_DATA_ASSESSMENT.md` and the
generated `data/samples/inventory_demo_manifest.json`. This small illustrative
cohort does not turn the overall dataset into representative operational coverage.

## Standards review

Independent Herdr review found no hard standards violations. Two maintainability
suggestions were addressed: synthetic audit disclosures now target named steps,
and assurance selects its summary wording explicitly. The reviewer confirmed no
unresolved findings after these fixes and the mobile search-width correction.

## Spec review

Independent Herdr review identified an outdated assertion requiring IFS provenance
for every audit trail. The existing test now requires the four known February
synthetic holdouts to be inconclusive/LOW with explicit synthetic provenance,
while retaining the IFS requirement for every other trail. The reviewer confirmed
the fix and found no other unresolved spec issue.

Full-suite verification also exposed stale Overview fixture counts: March's three
additional synthetic Inventory findings change total findings from 1,676 to
1,679 (789 to 792 when Payments is unavailable). Existing tests now use those
explicit counts and the export check requires exactly three labelled synthetic
Inventory findings with demonstration-only actions. Monetary, dealer, paging and
payment-outage checks are retained.

Review outcome: Standards — 0 unresolved; Spec — 0 unresolved.

Final validation: 274 backend tests passed, 28 existing skips; five frontend tests
and production build passed. Python compilation passed; no standalone typecheck
is configured. Generator regeneration was byte-identical and original fixture
hashes were preserved. Browser verification covered all three scenario views,
month changes, detail provenance, suppressed historical-audit fetching, ticket
disclosure and 320/768/1024/1440px layouts. Existing bundle-size and favicon-404
warnings remain. No deployment or production writes were performed.
