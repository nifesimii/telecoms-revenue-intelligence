# Inventory sample-data assessment — 2026-09-27

This is the pre-enrichment baseline. The subsequently implemented synthetic cohort,
walkthrough and updated distribution are in `INVENTORY_DEMO_SCENARIOS.md`.

Read-only assessment of the existing January–June fixtures using
`execute_query("get_inventory_comparison", {"mon_period": period})` in sample
mode. No fixtures were changed. Counts below are dealer–product combinations,
not unique dealers; excess units include observed mismatches only.

| Month | Observed mismatches | Observed excess units | Invoice gaps | Within purchases | Exact matches (subset of within) | Invoice gap share |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| January | 10 | 131 | 3,868 | 49 | 6 | 98.50% |
| February | 12 | 162 | 4,006 | 49 | 5 | 98.50% |
| March | 24 | 224 | 4,150 | 62 | 9 | 97.97% |
| April | 24 | 200 | 4,084 | 61 | 7 | 97.96% |
| May | 26 | 247 | 4,150 | 60 | 9 | 97.97% |
| June | 29 | 275 | 4,150 | 57 | 7 | 97.97% |

## What already exists

Every month contains all three classifications, exact matches, purchases greater
than activations, and observed excesses from one unit to larger quantities.
The largest individual excess ranges from 54 to 104 units across the months.
Zeros in the former shared summary cards were a consequence of filtering, not
missing mismatch scenarios. Coverage-gap purchases and excess are unknown;
they must never be interpreted as zero.

## Specific opportunities for richer scenarios

1. **Broader invoice matches.** Almost 98% of combinations lack matching purchase
   evidence. Add a deliberately selected, explicitly synthetic set of matched
   invoices to demonstrate both within-purchase and excess comparisons across
   more dealers/products. Retain genuine missing-evidence examples. No target
   percentage is claimed to represent real operations.
2. **Period-aware evidence before monthly purchase stories.** The shared IFS file
   has 2,000 raw rows dated March 5–28, 2026. Current comparison semantics read
   that available dataset without filtering invoice dates by the selected
   reporting month. Adding January–June invoices alone would pool purchases
   across months. Agree the purchase window and carryover semantics before
   implementing dated purchase/replenishment scenarios.
3. **Controlled evidence-resolution examples.** A small named synthetic cohort
   could demonstrate missing invoices becoming available, or a product-code
   alias being confirmed, with expected before/after classifications. These need
   explicit evidence versions or separate fixtures: changing the shared IFS file
   currently changes comparisons for every month. Do not present that as a
   time-based resolution workflow that the app does not yet support.
4. **Zero versus unknown purchase quantity.** No current comparison contains a
   recorded purchase quantity of zero. An explicitly synthetic edge case could
   demonstrate a known-zero quantity, observed excess and undefined percentage,
   distinct from a missing invoice. Confirm that zero-quantity invoice records
   are a meaningful source scenario before adding one.

January and April–June activation data are synthetic volume-scaled extensions;
February/March activation fixtures and shared IFS history were retained. This
explains some repetitive monthly patterns. See `data/samples/README.md`.

Recommended next data increment: define a small synthetic cohort and its expected
classifications, then decide invoice-window semantics before generating additional
purchase history. Keep existing source fixtures intact and label synthetic evidence.

## Summary-card contract

- Needs Investigation: observed excess units, observed mismatches, invoice gaps.
- Invoice Coverage Gaps: affected combinations, distinct affected dealers,
  activation records without matched invoice evidence.
- Within Recorded Purchases: combinations, recorded purchased units, activation
  records for those combinations. The difference is not a stock balance.

All metrics use the entire current filtered result, before pagination. Purchases
remain null when no recorded quantities exist. Classification and invoice-window
semantics are unchanged.
