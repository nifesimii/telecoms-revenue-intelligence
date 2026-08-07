"""Inventory-mismatch verification-chain builder (second audit module).

Produces a :class:`VerificationTrail` for one (dealer, product) pair — the
audit artifact behind an "Excess activation vs invoiced purchases" claim.
Six ordered checks, then a conclusion + confidence.

Mirrors :mod:`backend.audit.zero_commission_audit` in shape so the generic
:class:`~backend.audit.base.AuditModule` registry has two live domains.
The chain is domain-specific but the file layout, separation for
testability (pure ``build_trail`` + IO-fetching ``gather_inputs`` +
orchestrating ``run_period``), and registration idiom are identical.

Subject-of-audit key. One trail per (dealer_id, product_code). The audit
table's uniqueness is ``UNIQUE (partner_code, mon_period, run_id)``, so
we compose ``partner_code = f"{dealer_id}:{product_code}"`` to preserve
per-product granularity without a schema migration. Dealer/product codes
are also stored as discrete fields inside step 1's ``detail`` so
aggregate queries stay clean.

Known limitation. Step 4 ("prior-period stock") reuses
``get_inventory_comparison(prior_period)``, which only returns
dealer-product pairs with activations in the target period. Cases where
the prior period had ONLY purchases for the SKU (no activations at all)
won't be caught — those become the natural motivation for a dedicated
``get_partner_purchase_history`` query later.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

import pandas as pd

from backend import config
from backend.audit.payment_data import known_periods as _known_periods
from backend.audit.product_aliases import alias_group, siblings_of
from backend.audit.trail import TrailStep, VerificationTrail
from backend.db.connection import execute_query

# Data source label written to the persisted trail row. VARCHAR(20) with no
# CHECK — this module reads IFS invoice data, not payment data.
_DATA_SOURCE = "ifs"


# ---------------------------------------------------------------------------
# Inputs struct — everything the pure builder needs, pre-fetched.
# ---------------------------------------------------------------------------

@dataclass
class InventoryMismatchInputs:
    dealer_id: str
    dealer_name: str
    product_code: str
    product_name: str
    mon_period: str

    # Step 1 — signal
    activation_count: int
    qualified_count: int
    finding_type: str                   # CONFIRMED_MISMATCH | NO_INVOICE_RECORD

    # Step 2 — purchase record
    has_invoice_record: bool

    # Step 3 — allocation
    total_units_purchased: float | None
    inventory_gap: float | None         # activation_count − purchased; None if no invoice
    gap_pct: float | None

    # Step 4 — prior-period carryover
    prior_period: str | None = None
    prior_leftover_units: float = 0.0   # max(0, prior_purchased − prior_activated)

    # Step 5 — SKU consolidation
    sibling_codes: list[str] = field(default_factory=list)
    sibling_purchases: dict[str, float] = field(default_factory=dict)  # code → units

    # Step 6 — upstream completeness
    ifs_records_present: bool = True
    known_ingestion_gap: bool = False


# ---------------------------------------------------------------------------
# Pure builder — the 6-step chain + conclusion.
# ---------------------------------------------------------------------------

def build_trail(inp: InventoryMismatchInputs) -> VerificationTrail:
    steps: list[TrailStep] = []
    gap = float(inp.inventory_gap) if inp.inventory_gap is not None else None
    purchased = float(inp.total_units_purchased) if inp.total_units_purchased is not None else None

    # ── Step 1 — Mismatch signal ──────────────────────────────────────────
    # Informational: records the raw numbers. Doesn't gate anything — the
    # subject only exists because the assurance flagger already fired.
    steps.append(TrailStep(
        step=1,
        name="mismatch_signal",
        checked=("Did the inventory-assurance flagger raise a signal for "
                 "this dealer/product for this period?"),
        result=(
            f"Flagged as {inp.finding_type}. "
            f"{inp.activation_count} activations "
            f"({inp.qualified_count} qualified) vs "
            + (f"{purchased:.0f} purchased." if purchased is not None
               else "no invoice record.")
        ),
        passed=True,
        caveat=None,
        detail={
            "source_table": "fbb_comm_dev_act + ifs_invoice_history",
            "dealer_id": inp.dealer_id,
            "dealer_name": inp.dealer_name,
            "product_code": inp.product_code,
            "product_name": inp.product_name,
            "activation_count": inp.activation_count,
            "qualified_count": inp.qualified_count,
            "finding_type": inp.finding_type,
        },
    ))

    # ── Step 2 — Purchase record lookup ───────────────────────────────────
    steps.append(TrailStep(
        step=2,
        name="purchase_record_lookup",
        checked="Is there any IFS invoice record for this dealer+product?",
        result=(
            f"IFS invoice record found: {purchased:.0f} units purchased."
            if inp.has_invoice_record else
            "No IFS invoice record found for this dealer+product."
        ),
        passed=inp.has_invoice_record,
        caveat=(None if inp.has_invoice_record else
                "No IFS invoice — cannot distinguish over-activation from "
                "an invoice that lives outside the available data window."),
        detail={
            "source_table": "ifs_invoice_history",
            "dedup_key": ("customer_no, part_no, implied_units, "
                          "actual_completion_date"),
            "has_invoice_record": inp.has_invoice_record,
            "total_units_purchased": purchased,
        },
    ))

    # ── Step 3 — Allocation calculation ───────────────────────────────────
    # Deterministic. Purchased=0 with activations>0 is a special caveat:
    # the mismatch is real but gap_pct is undefined.
    zero_purchase_with_activity = (
        inp.has_invoice_record and purchased == 0 and inp.activation_count > 0
    )
    steps.append(TrailStep(
        step=3,
        name="allocation_calculation",
        checked=("Compute gap = activations − purchases and gap% relative "
                 "to purchased units."),
        result=(
            f"Gap = {gap:.0f} units, {inp.gap_pct:.1f}% over allocation."
            if gap is not None and inp.gap_pct is not None else
            (f"Gap = {gap:.0f} units; gap% undefined (zero purchased)."
             if gap is not None else
             "Cannot compute gap without an invoice record.")
        ),
        passed=True,
        caveat=("Purchases recorded as zero for a product with activations — "
                "gap% is undefined (division by zero); mismatch is real but "
                "requires manual investigation of the invoice source.")
        if zero_purchase_with_activity else None,
        detail={
            "activation_count": inp.activation_count,
            "total_units_purchased": purchased,
            "inventory_gap": gap,
            "gap_pct": inp.gap_pct,
        },
    ))

    # ── Step 4 — Prior-period stock carryover ─────────────────────────────
    # If prior-period leftover stock ≥ current gap, the activation is
    # likely from carryover — not overselling. Caveat, not a conclusion.
    prior_leftover = float(inp.prior_leftover_units)
    carryover_covers_gap = (
        gap is not None and gap > 0 and prior_leftover >= gap
    )
    steps.append(TrailStep(
        step=4,
        name="prior_period_stock",
        checked=("Could the prior-period leftover stock plausibly cover "
                 "the current-period gap?"),
        result=(
            "No prior period available for carryover check."
            if not inp.prior_period else
            f"Prior period {inp.prior_period}: {prior_leftover:.0f} units "
            f"of leftover stock "
            + ("≥ current gap — plausible carryover."
               if carryover_covers_gap else "< current gap.")
        ),
        passed=not carryover_covers_gap,
        caveat=("Prior-period leftover stock is enough to cover the current "
                "gap — activation is likely a carryover, not overselling. "
                "Manual review before finalising the mismatch.")
        if carryover_covers_gap else None,
        detail={
            "prior_period": inp.prior_period,
            "prior_leftover_units": prior_leftover,
            "current_gap_units": gap,
            "note": ("Reused get_inventory_comparison(prior_period); misses "
                     "cases where prior period had only purchases and no "
                     "activations for this SKU."),
        },
    ))

    # ── Step 5 — Product-alias reconciliation ─────────────────────────────
    # If a sibling SKU's current-period purchases cover the gap, this is
    # SKU consolidation (Hynex/Hynex_1 pattern), not a mismatch.
    sibling_total = sum(float(v) for v in inp.sibling_purchases.values())
    alias_covers_gap = (
        gap is not None and gap > 0 and sibling_total >= gap
        and bool(inp.sibling_codes)
    )
    steps.append(TrailStep(
        step=5,
        name="product_alias_reconciliation",
        checked=("Are there known-alias sibling SKUs whose current-period "
                 "purchases would cover the gap?"),
        result=(
            "No known aliases for this product code."
            if not inp.sibling_codes else
            f"Sibling SKUs {inp.sibling_codes}: "
            f"{sibling_total:.0f} units purchased in period "
            + ("≥ current gap — likely SKU consolidation."
               if alias_covers_gap else "< current gap.")
        ),
        passed=not alias_covers_gap,
        caveat=("A sibling SKU's purchases cover the gap — activation "
                "spread across alias codes (known KB pattern, e.g. Hynex / "
                "Hynex_1). Consolidate before flagging as excess.")
        if alias_covers_gap else None,
        detail={
            "sibling_codes": inp.sibling_codes,
            "sibling_purchases": inp.sibling_purchases,
            "sibling_total_units": sibling_total,
            "current_gap_units": gap,
        },
    ))

    # ── Step 6 — Upstream completeness ────────────────────────────────────
    upstream_ok = inp.ifs_records_present and not inp.known_ingestion_gap
    steps.append(TrailStep(
        step=6,
        name="upstream_completeness",
        checked=("Does the IFS invoice dataset have complete coverage "
                 "for this period (not a known ingestion gap)?"),
        result=(
            "IFS data is present for this period."
            if upstream_ok else
            "IFS data is INCOMPLETE for this period — coverage gap detected."
        ),
        passed=upstream_ok,
        caveat=("IFS dataset lacks complete coverage for this period. "
                "Cannot distinguish real mismatch from missing invoice data.")
        if not upstream_ok else None,
        detail={
            "data_source": _DATA_SOURCE,
            "ifs_records_present": inp.ifs_records_present,
            "known_ingestion_gap": inp.known_ingestion_gap,
        },
    ))

    # ── Conclusion + confidence ───────────────────────────────────────────
    conclusion, confidence = _conclude(inp, steps, gap)
    return VerificationTrail(
        partner_code=f"{inp.dealer_id}:{inp.product_code}",
        partner_name=f"{inp.dealer_name} · {inp.product_code}",
        mon_period=inp.mon_period,
        payment_source=_DATA_SOURCE,
        steps=steps,
        conclusion=conclusion,
        confidence=confidence,
    )


def _conclude(
    inp: InventoryMismatchInputs,
    steps: list[TrailStep],
    gap: float | None,
) -> tuple[str, str]:
    """Derive (conclusion, confidence) from the step results."""
    caveat_step_names = [s.name for s in steps if s.caveat]
    step2 = next(s for s in steps if s.step == 2)
    step4 = next(s for s in steps if s.step == 4)
    step5 = next(s for s in steps if s.step == 5)
    step6 = next(s for s in steps if s.step == 6)

    # Missing invoice OR upstream gap → can't conclude.
    if not step2.passed or not step6.passed:
        conclusion = "INSUFFICIENT_DATA"
    # Carryover or SKU consolidation explains the gap → RECONCILED.
    elif not step4.passed or not step5.passed:
        conclusion = "RECONCILED"
    # Signal survived every explanatory step → EXCESS_ACTIVATION.
    elif gap is not None and gap > 0:
        conclusion = "EXCESS_ACTIVATION"
    else:
        # No positive gap after step 3 — signal doesn't actually indicate excess.
        conclusion = "RECONCILED"

    # Confidence from caveat profile — mirrors zero_commission's rule shape.
    if not caveat_step_names:
        confidence = "HIGH"
    elif len(caveat_step_names) == 1:
        confidence = "MEDIUM"
    else:
        confidence = "LOW"

    # INSUFFICIENT_DATA always reads LOW confidence — the definitive
    # caveats at steps 2 or 6 leave no room for high certainty.
    if conclusion == "INSUFFICIENT_DATA":
        confidence = "LOW"

    return conclusion, confidence


# ---------------------------------------------------------------------------
# Input gathering — fetch from the existing query layer.
# ---------------------------------------------------------------------------

def _prior_period(mon_period: str, known_periods: list[str]) -> str | None:
    """The period immediately before ``mon_period`` in the known set."""
    if not known_periods:
        return None
    ordered = sorted(str(p) for p in known_periods)
    try:
        idx = ordered.index(str(mon_period))
    except ValueError:
        return None
    return ordered[idx - 1] if idx > 0 else None


def _prior_leftover_for(
    prior_df: pd.DataFrame, dealer_id: str, product_code: str
) -> float:
    """Prior-period leftover units for a dealer+product from the
    prior-period comparison view. Returns 0 if no matching row.
    """
    if prior_df is None or prior_df.empty:
        return 0.0
    match = prior_df[
        (prior_df["dealer_id"].astype(str) == str(dealer_id))
        & (prior_df["product_code"].astype(str) == str(product_code))
    ]
    if match.empty:
        return 0.0
    row = match.iloc[0]
    purchased = row.get("total_units_purchased")
    if purchased is None or pd.isna(purchased):
        return 0.0
    activated = float(row.get("activation_count") or 0.0)
    leftover = float(purchased) - activated
    return max(0.0, leftover)


def _sibling_purchases_for(
    period_df: pd.DataFrame, dealer_id: str, siblings: list[str]
) -> dict[str, float]:
    """Current-period purchases per sibling SKU for this dealer.

    Reads from ``get_inventory_comparison`` output — which only carries
    products with activations in the period. A sibling with purchases but
    no activations therefore appears as 0 here; documented as a limit
    on step 5's precision.
    """
    out: dict[str, float] = {}
    if period_df is None or period_df.empty or not siblings:
        return out
    for code in siblings:
        match = period_df[
            (period_df["dealer_id"].astype(str) == str(dealer_id))
            & (period_df["product_code"].astype(str) == str(code))
        ]
        if match.empty:
            out[code] = 0.0
            continue
        purchased = match.iloc[0].get("total_units_purchased")
        out[code] = 0.0 if purchased is None or pd.isna(purchased) else float(purchased)
    return out


def gather_inputs(
    row: dict[str, Any],
    mon_period: str,
    *,
    period_df: pd.DataFrame | None = None,
    prior_period: str | None = None,
    prior_df: pd.DataFrame | None = None,
    ifs_records_present: bool = True,
) -> InventoryMismatchInputs:
    """Assemble :class:`InventoryMismatchInputs` for one (dealer, product).

    ``row`` is a single record from ``get_inventory_comparison``. Callers
    pass shared frames (``period_df``, ``prior_df``) so we don't refetch
    per row.
    """
    dealer_id = str(row["dealer_id"])
    product_code = str(row["product_code"])
    finding_type = str(row.get("finding_type") or "")

    purchased = row.get("total_units_purchased")
    has_invoice = purchased is not None and not (isinstance(purchased, float) and pd.isna(purchased))

    gap = row.get("inventory_gap")
    gap_val = None if gap is None or (isinstance(gap, float) and pd.isna(gap)) else float(gap)
    gap_pct = row.get("gap_pct")
    gap_pct_val = None if gap_pct is None or (isinstance(gap_pct, float) and pd.isna(gap_pct)) else float(gap_pct)

    siblings = siblings_of(product_code)
    sibling_purchases = _sibling_purchases_for(period_df, dealer_id, siblings) if period_df is not None else {}

    prior_leftover = _prior_leftover_for(prior_df, dealer_id, product_code) if prior_df is not None else 0.0

    return InventoryMismatchInputs(
        dealer_id=dealer_id,
        dealer_name=str(row.get("dealer_name") or dealer_id),
        product_code=product_code,
        product_name=str(row.get("product_name") or product_code),
        mon_period=str(mon_period),
        activation_count=int(row.get("activation_count") or 0),
        qualified_count=int(row.get("qualified_count") or 0),
        finding_type=finding_type,
        has_invoice_record=bool(has_invoice),
        total_units_purchased=None if not has_invoice else float(purchased),
        inventory_gap=gap_val,
        gap_pct=gap_pct_val,
        prior_period=prior_period,
        prior_leftover_units=prior_leftover,
        sibling_codes=siblings,
        sibling_purchases=sibling_purchases,
        ifs_records_present=ifs_records_present,
        known_ingestion_gap=not ifs_records_present,
    )


# ---------------------------------------------------------------------------
# Orchestrator — run the whole period.
# ---------------------------------------------------------------------------

def run_period(mon_period: str, payment_source: str | None = None) -> list[VerificationTrail]:
    """Build a trail for every (dealer, product) flagged by the inventory
    assurance for the period. ``payment_source`` is accepted for interface
    parity with the generic ``AuditModule.build`` signature but ignored —
    this module always reads IFS.
    """
    _ = payment_source  # interface parity with AuditModule.build

    # Reject unknown periods early — the sample-data reader raises when the
    # period isn't in the CSV partition map, and pandas may raise inside the
    # merge if either side of the join is empty. Returning [] for an unknown
    # period mirrors what the UI expects.
    known = _known_periods()
    if known and str(mon_period) not in known:
        return []

    try:
        period_df = execute_query(
            "get_inventory_comparison", {"mon_period": str(mon_period)}
        )
    except Exception:
        return []
    if period_df is None or period_df.empty:
        return []

    # Emit trails for the two flagged finding types. WITHIN_ALLOCATION rows
    # are not audit subjects — no claim to verify.
    flagged = period_df[period_df["finding_type"].isin(
        ["CONFIRMED_MISMATCH", "NO_INVOICE_RECORD"]
    )]
    if flagged.empty:
        return []

    # Shared lookups — fetched once, reused across rows.
    prior_period = _prior_period(mon_period, _known_periods())
    prior_df = None
    if prior_period:
        try:
            prior_df = execute_query(
                "get_inventory_comparison", {"mon_period": prior_period}
            )
        except Exception:
            prior_df = None

    ifs_records_present = _ifs_covers_period(mon_period)

    trails: list[VerificationTrail] = []
    for _, row in flagged.iterrows():
        inp = gather_inputs(
            row.to_dict(),
            mon_period,
            period_df=period_df,
            prior_period=prior_period,
            prior_df=prior_df,
            ifs_records_present=ifs_records_present,
        )
        trails.append(build_trail(inp))
    return trails


def _ifs_covers_period(mon_period: str) -> bool:
    """True if the IFS sample/table has any rows relevant to this period.

    Sample mode: the ifs_invoice_history CSV isn't partitioned by period,
    so presence of any records is the check. Live mode would inspect an
    ingestion-manifest table; here we default to True unless the file is
    empty or absent.
    """
    try:
        from backend.db.queries import _load_csv
        df = _load_csv("ifs_invoice_history")
        return df is not None and not df.empty
    except Exception:
        return False


# ---------------------------------------------------------------------------
# Module registration (generic audit registry)
# ---------------------------------------------------------------------------

# Ordered step keys this module emits — mirrors build_trail's chain.
STEP_NAMES = [
    "mismatch_signal",
    "purchase_record_lookup",
    "allocation_calculation",
    "prior_period_stock",
    "product_alias_reconciliation",
    "upstream_completeness",
]


def _register() -> None:
    from backend.audit.base import AuditModule, register
    register(AuditModule(
        name="inventory_mismatch",
        label="Inventory Mismatch",
        claim=("Dealer X's activations of product Y exceed invoiced "
               "purchases in a way not explained by carryover, SKU "
               "consolidation, or an ingestion gap."),
        step_names=STEP_NAMES,
        build=run_period,
    ))


_register()

# `config` imported but not currently used beyond typing readability of the
# signature. Keep the import so a future PAYMENT_SOURCE-aware variant can
# be added without churning the header.
_ = config
