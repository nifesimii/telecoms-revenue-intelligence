# Audit Module — Inventory Mismatch

Design spec for the second audit module, mirroring `zero_commission_audit`
under the generic `AuditModule` registry. Written before implementation so
the shape is checkable, and the file survives session boundaries.

> Status: implemented as of 2026-08-03 (this document was the design brief
> that shipped alongside `backend/audit/inventory_mismatch_audit.py`).

---

## 1. What it audits

**Claim:** *"Dealer X's activations of product Y exceed their purchases in
a way that is not explainable by data lag, SKU consolidation, or an
ingestion gap."*

**Subject of the audit:** one `VerificationTrail` per **(dealer_id,
product_code)** pair for which the inventory-assurance flagger raised a
`CONFIRMED_MISMATCH` or `NO_INVOICE_RECORD` signal.

The subject key (`partner_code` on the trail row) is the composite
`"{dealer_id}:{product_code}"` — the audit table's uniqueness is
`UNIQUE (partner_code, mon_period, run_id)`, and we want per-product
granularity without a schema migration. Dealer and product codes are
also stored as discrete fields inside step 1's `detail`, so aggregation
queries stay clean.

## 2. Data sources

| Source | Query | Used by |
|---|---|---|
| Activations for the period | `get_inventory_comparison(mon_period)` | steps 1–3 |
| Prior-period activation-vs-purchase view | `get_inventory_comparison(prior_period)` | step 4 |
| Product aliases | `backend/audit/product_aliases.py` (hardcoded, mirrors KB) | step 5 |
| IFS ingestion presence | `get_inventory_comparison(mon_period)` shape/count | step 6 |

No new SQL required — reuses `get_inventory_comparison` at two periods.

**Limitation (documented in the module docstring):** the step-4 prior-period
check misses cases where the prior period had *only* purchases for that
SKU (no activations), because `get_inventory_comparison` filters IFS to
products with activations in the target period. A dedicated
`get_partner_purchase_history` query would close the gap and is the
natural follow-up when this pattern is validated.

## 3. The 6-step chain

| # | Step name | What it checks | Passes when | Caveat when |
|---|---|---|---|---|
| 1 | `mismatch_signal` | Did the flagger raise for this (dealer, product)? Records raw numbers. | Signal present. | Never (informational). |
| 2 | `purchase_record_lookup` | Is there any IFS invoice record for this dealer+product? | `finding_type != NO_INVOICE_RECORD`. | No IFS row — can't distinguish over-activation from missing invoice data. |
| 3 | `allocation_calculation` | Compute `gap = activation_count − units_purchased` and `gap_pct`. | Always (deterministic). | Purchases = 0 → gap_pct undefined (division by zero). |
| 4 | `prior_period_stock` | Query prior period. Is prior leftover stock (`purchased − activated`) ≥ current gap? | No prior leftover, or leftover < gap. | Prior leftover ≥ gap → activation is likely carryover, not overselling. |
| 5 | `product_alias_reconciliation` | Check KB aliases (`Hynex ↔ Hynex_1`, etc.). Does a sibling SKU's current-period purchase cover the gap? | No sibling or sibling stock < gap. | Sibling purchases ≥ gap → SKU consolidation, not a mismatch. |
| 6 | `upstream_completeness` | Are IFS records present in the dataset for this period? | Non-empty IFS view. | IFS gap → mismatch may be an ingestion artifact. |

## 4. Conclusions & confidence

**Conclusion vocabulary added** (in `backend/audit/trail.py::CONCLUSIONS`):
- `RECONCILED` — steps 4 or 5 explain the gap
- `EXCESS_ACTIVATION` — mismatch signal survives all six steps
- `INSUFFICIENT_DATA` — steps 2 or 6 blocked a verdict *(reused from
  zero_commission)*

**Confidence rules:**
- `HIGH` — zero caveats on steps 2/4/5/6
- `MEDIUM` — one such caveat
- `LOW` — two or more

`NO_INVOICE_RECORD` rows always produce `INSUFFICIENT_DATA` / `LOW` — step 2's
caveat is definitive for those.

## 5. File layout

```
backend/audit/
├── inventory_mismatch_audit.py    NEW — module body + step chain + registration
├── product_aliases.py             NEW — hardcoded alias groups, source-of-truth
│                                        for both zero_commission and inventory
└── base.py                        EDIT — one import line in _ensure_loaded()

backend/audit/trail.py             EDIT — extend CONCLUSIONS tuple

backend/knowledge_base/
└── fbb_commission_kb.md           EDIT — add "Inventory mismatch root causes"
                                        section (four canonical causes)

frontend/src/components/audit/
└── AuditTrailPanel.jsx            EDIT — add color tones for RECONCILED /
                                        EXCESS_ACTIVATION conclusions

backend/tests/
└── test_inventory_mismatch_audit.py  NEW — synthetic + integration tests
```

Zero changes to storage, endpoints, or the audit-run UI shell — the
generic `AuditModule` registry carries the new module.

## 6. Payment-source field usage

`VerificationTrail.payment_source` is a `VARCHAR(20)` on the persisted row
with no CHECK constraint. Inventory-mismatch trails set it to `"ifs"` —
semantically "the data source the audit consulted." This keeps the schema
generic without renaming the column.

## 7. What this proves

Landing this second module validates three claims from the audit-layer
design:

1. The generic `AuditModule` registry actually holds two live domains.
2. The `VerificationTrail` shape (subject + steps + conclusion +
   confidence) generalises beyond payment claims.
3. The `audit.zero_commission_trail` table's `module` column carries
   heterogeneous trails without schema churn.

Any further audit module (ORSC payment, underpayment/overpayment, etc.)
becomes strictly a "write one file + register" change after this.
