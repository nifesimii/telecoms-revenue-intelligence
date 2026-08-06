"""Payment-reconciliation verification-chain builder (third audit module).

Audits the general claim *"Partner X was paid the correct amount for
period Y"* for every partner with commission activity in the period —
not only the zero-commission-flagged ones. Answers four questions in
one chain: was anything owed? was anything paid? does the amount match?
if not, by how much and in which direction?

Distinction from ``zero_commission_audit``:
  * ``zero_commission`` audits the narrow claim "the partner was flagged
    with zero commission — was that correct?" and answers PAID / NOT_PAID.
  * ``payment_reconciliation`` audits the general claim "was the partner
    paid what they were owed?" and answers PAID_IN_FULL / UNDERPAID /
    OVERPAID / DISPUTED_ROUNDING / INSUFFICIENT_DATA — so a partial
    payment (previously conflated with NOT_PAID/LOW in the zero_commission
    trail) here becomes a first-class UNDERPAID verdict.

The two modules coexist by design: Finance triages zero-commission
records via the narrow module and reviews everyone else via this one.
No behaviour change to zero_commission.

Shared payment-data helpers. This module reuses the payment lookup,
adjacent-period, and dataset-coverage helpers already in
``zero_commission_audit`` (imported with leading-underscore names). They
are conceptually shared payment-plumbing, not zero-commission-specific;
the natural refactor when a fourth payment-aware module lands is to
lift them into a ``backend/audit/payment_data.py`` shared module.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

import pandas as pd

from backend import config
from backend.audit.trail import TrailStep, VerificationTrail
from backend.audit.zero_commission_audit import (
    _adjacent_period_payments,
    _extract_payment,
    _known_periods,
    _payment_lookup,
    _payment_source_covers_period,
)
from backend.db.connection import execute_query

# Tolerance for "paid in full" comparisons, in NGN. Matches the tolerance
# used by zero_commission so the two modules classify the same partner
# consistently at the equality boundary.
_PAY_TOLERANCE = 1.0

# Absolute-NGN tolerance for the DISPUTED_ROUNDING bucket — payments that
# are close-but-not-equal to expected. The intent is to isolate small
# systematic differences (rounding, fee/tax deductions, FX conversion)
# from real under/overpayment.
_ROUNDING_ABS_NGN = 100.0

# Relative tolerance for the same DISPUTED_ROUNDING bucket. A partner
# owed 10,000,000 NGN and paid 9,999,500 (off by 500 → outside abs
# tolerance but 0.005%) should still be DISPUTED_ROUNDING, not UNDERPAID.
_ROUNDING_REL_PCT = 0.01   # 1%


# ---------------------------------------------------------------------------
# Inputs struct — everything the pure builder needs, pre-fetched.
# ---------------------------------------------------------------------------

@dataclass
class PaymentReconciliationInputs:
    partner_code: str
    partner_name: str
    mon_period: str
    payment_source: str                  # "simulated" | "apdp"

    # Step 1 — activity
    total_activations: int
    qualified_count: int                 # activations with a non-zero rate

    # Step 2 — expected
    expected_commission_ngn: float

    # Step 3 — payment record
    payment_found: bool = False
    amount_paid_ngn: float = 0.0
    payment_status: str | None = None

    # Step 5 — near matches
    adjacent_period_payments: list[dict[str, Any]] = field(default_factory=list)

    # Step 6 — upstream completeness
    period_present_in_payment_data: bool = True
    known_ingestion_gap: bool = False


# ---------------------------------------------------------------------------
# Pure builder — the 6-step chain + conclusion.
# ---------------------------------------------------------------------------

def build_trail(inp: PaymentReconciliationInputs) -> VerificationTrail:
    steps: list[TrailStep] = []
    expected = round(float(inp.expected_commission_ngn), 2)
    paid = round(float(inp.amount_paid_ngn), 2)
    delta = round(paid - expected, 2)

    # ── Step 1 — Activity check ──────────────────────────────────────────
    had_activity = inp.total_activations > 0
    steps.append(TrailStep(
        step=1,
        name="partner_activity",
        checked="Did the partner have any activation records for this period?",
        result=(
            f"{inp.total_activations} activation records "
            f"({inp.qualified_count} qualified)."
            if had_activity else
            "No activation records found for this partner/period."
        ),
        passed=had_activity,
        caveat=None if had_activity
        else "No activation records — no basis to compute an expected payout.",
        detail={
            "source_table": "fbb_comm_dev_act",
            "total_activations": inp.total_activations,
            "qualified_count": inp.qualified_count,
        },
    ))

    # ── Step 2 — Expected commission ─────────────────────────────────────
    steps.append(TrailStep(
        step=2,
        name="expected_commission",
        checked="Compute the commission the partner was entitled to.",
        result=f"Expected commission NGN {expected:,.2f}.",
        passed=True,
        caveat=("Expected commission is NGN 0.00 — no qualified activations. "
                "Any payment received is over-payment; any absence is correct.")
        if expected <= _PAY_TOLERANCE and had_activity else None,
        detail={
            "expected_commission_ngn": expected,
            "basis": "sum of commission_rate over qualified activations",
        },
    ))

    # ── Step 3 — Payment record search ───────────────────────────────────
    steps.append(TrailStep(
        step=3,
        name="payment_record_search",
        checked=f"Search the {inp.payment_source} payment data for this partner/period.",
        result=(
            f"Payment record found: NGN {paid:,.2f} ({inp.payment_status})."
            if inp.payment_found else
            "No payment record found for this partner/period."
        ),
        passed=inp.payment_found,
        # Absence of a payment isn't itself a caveat — it's a data point
        # the amount-comparison step interprets. Data-completeness worry
        # lives on step 6.
        caveat=None,
        detail={
            "payment_source": inp.payment_source,
            "payment_found": inp.payment_found,
            "amount_paid_ngn": paid,
            "payment_status": inp.payment_status,
        },
    ))

    # ── Step 4 — Amount comparison ───────────────────────────────────────
    bucket = _classify_amount(expected, paid)
    steps.append(TrailStep(
        step=4,
        name="amount_comparison",
        checked=("Compare paid vs expected with rounding tolerances "
                 "(abs NGN + relative %)."),
        result=(
            f"Delta = NGN {delta:+,.2f} "
            f"({delta / expected * 100:+.2f}% of expected)."
            if expected > _PAY_TOLERANCE else
            f"Delta = NGN {delta:+,.2f} (expected is zero — % undefined)."
        ),
        # PAID_IN_FULL is the only "clean" bucket. Others record a caveat
        # so the confidence rule downweights them relative to a full match.
        passed=(bucket == "PAID_IN_FULL"),
        caveat=(None if bucket == "PAID_IN_FULL"
                else f"Amount classified as {bucket} — see step-4 detail."),
        detail={
            "expected_commission_ngn": expected,
            "amount_paid_ngn": paid,
            "delta_ngn": delta,
            "rounding_abs_ngn_tolerance": _ROUNDING_ABS_NGN,
            "rounding_rel_pct_tolerance": _ROUNDING_REL_PCT,
            "bucket": bucket,
        },
    ))

    # ── Step 5 — Near-match check ────────────────────────────────────────
    near = list(inp.adjacent_period_payments)
    near_found = bool(near)
    steps.append(TrailStep(
        step=5,
        name="near_match",
        checked=("Look for payments to this partner in adjacent periods "
                 "(same partner, off-by-one month reference)."),
        result=(
            f"{len(near)} payment(s) to this partner in adjacent periods."
            if near else "No adjacent-period payments found."
        ),
        passed=not near_found,
        caveat=("Possible payment posted under an adjacent period reference; "
                "reconcile before finalising the amount bucket.")
        if near_found else None,
        detail={
            "adjacent_period_payments": near,
            "expected_commission_ngn": expected,
            "amount_paid_ngn": paid,
        },
    ))

    # ── Step 6 — Upstream completeness ───────────────────────────────────
    upstream_ok = inp.period_present_in_payment_data and not inp.known_ingestion_gap
    steps.append(TrailStep(
        step=6,
        name="upstream_completeness",
        checked=("Does the payment dataset have complete coverage for this "
                 "period (not a known ingestion gap)?"),
        result=(
            "Payment data is complete for this period."
            if upstream_ok else
            "Payment data is INCOMPLETE for this period — coverage gap detected."
        ),
        passed=upstream_ok,
        caveat=("Payment dataset lacks complete coverage for this period. "
                "Cannot classify reconciliation against incomplete data.")
        if not upstream_ok else None,
        detail={
            "payment_source": inp.payment_source,
            "period_present_in_payment_data": inp.period_present_in_payment_data,
            "known_ingestion_gap": inp.known_ingestion_gap,
        },
    ))

    conclusion, confidence = _conclude(inp, steps, expected, paid, bucket)
    return VerificationTrail(
        partner_code=inp.partner_code,
        partner_name=inp.partner_name,
        mon_period=inp.mon_period,
        payment_source=inp.payment_source,
        steps=steps,
        conclusion=conclusion,
        confidence=confidence,
    )


def _classify_amount(expected: float, paid: float) -> str:
    """Bucket a (expected, paid) pair into one of the four amount conclusions.

    Returns one of ``PAID_IN_FULL`` / ``DISPUTED_ROUNDING`` / ``UNDERPAID`` /
    ``OVERPAID``. Callers still need to gate on step 1 (activity) and step 6
    (data completeness) before trusting this bucket as the trail conclusion.
    """
    delta = paid - expected

    # Exact within a small NGN tolerance — the clean case.
    if abs(delta) <= _PAY_TOLERANCE:
        return "PAID_IN_FULL"

    # Close-but-not-equal: rounding/FX/small-fee deductions.
    within_abs = abs(delta) <= _ROUNDING_ABS_NGN
    within_rel = expected > 0 and abs(delta) <= expected * _ROUNDING_REL_PCT
    if within_abs or within_rel:
        return "DISPUTED_ROUNDING"

    # Real divergence.
    return "OVERPAID" if delta > 0 else "UNDERPAID"


def _conclude(
    inp: PaymentReconciliationInputs,
    steps: list[TrailStep],
    expected: float,
    paid: float,
    bucket: str,
) -> tuple[str, str]:
    """Derive (conclusion, confidence) from the step results."""
    caveat_step_names = [s.name for s in steps if s.caveat]
    step1 = next(s for s in steps if s.step == 1)
    step6 = next(s for s in steps if s.step == 6)

    # No activity → nothing to reconcile.
    if not step1.passed:
        return "INSUFFICIENT_DATA", "LOW"

    # Upstream gap → can't classify against incomplete data.
    if not step6.passed:
        return "INSUFFICIENT_DATA", "LOW"

    # Nothing owed and nothing paid — the clean zero case.
    if expected <= _PAY_TOLERANCE and paid <= _PAY_TOLERANCE:
        conclusion = "PAID_IN_FULL"
    else:
        # The amount-comparison bucket is the conclusion.
        conclusion = bucket

    # Confidence follows caveat profile. The step-4 caveat that the
    # bucket itself raised is expected for any non-PAID_IN_FULL trail —
    # excluding it prevents double-counting.
    weighted = [n for n in caveat_step_names if n != "amount_comparison"]
    if not weighted:
        confidence = "HIGH"
    elif len(weighted) == 1:
        confidence = "MEDIUM"
    else:
        confidence = "LOW"

    return conclusion, confidence


# ---------------------------------------------------------------------------
# Input gathering — fetch from the existing query layer.
# ---------------------------------------------------------------------------

def gather_inputs(
    partner_code: str,
    mon_period: str,
    payment_source: str,
    *,
    summary_row: dict[str, Any] | None = None,
    payment_df: pd.DataFrame | None = None,
    all_periods: list[str] | None = None,
) -> PaymentReconciliationInputs:
    """Assemble a :class:`PaymentReconciliationInputs` for one partner."""
    if summary_row is None:
        df = execute_query(
            "get_dealer_summary",
            {"mon_period": mon_period, "distributor_code": partner_code},
        )
        summary_row = df.iloc[0].to_dict() if not df.empty else {}

    if payment_df is None:
        payment_df = _payment_lookup(mon_period, payment_source)

    total_activations = int(summary_row.get("total_activations") or 0)
    zero_comm = int(summary_row.get("zero_commission_count") or 0)
    qualified = max(0, total_activations - zero_comm)

    paid, found, status = _extract_payment(payment_df, partner_code, payment_source)

    adjacent = _adjacent_period_payments(
        partner_code, mon_period, payment_source, all_periods,
    )

    period_present = _payment_source_covers_period(payment_df, mon_period, payment_source)

    return PaymentReconciliationInputs(
        partner_code=str(partner_code),
        partner_name=str(summary_row.get("distributor_name") or partner_code),
        mon_period=str(mon_period),
        payment_source=payment_source,
        total_activations=total_activations,
        qualified_count=qualified,
        expected_commission_ngn=float(summary_row.get("total_commission_ngn") or 0.0),
        payment_found=found,
        amount_paid_ngn=paid,
        payment_status=status,
        adjacent_period_payments=adjacent,
        period_present_in_payment_data=period_present,
        known_ingestion_gap=not period_present,
    )


# ---------------------------------------------------------------------------
# Orchestrator — run the whole period.
# ---------------------------------------------------------------------------

def run_period(mon_period: str, payment_source: str | None = None) -> list[VerificationTrail]:
    """Build a trail for every partner with activation activity in the
    period. Broader net than zero_commission (which only trails flagged
    partners) — this is a full reconciliation sweep.
    """
    source = payment_source or config.PAYMENT_SOURCE

    summary_df = execute_query("get_dealer_summary", {"mon_period": mon_period})
    if summary_df.empty:
        return []

    # All partners with any activity — full reconciliation coverage.
    active = summary_df[summary_df["total_activations"].astype(int) > 0]
    if active.empty:
        return []

    # Shared lookups fetched once.
    payment_df = _payment_lookup(mon_period, source)
    all_periods = _known_periods()

    trails: list[VerificationTrail] = []
    for _, row in active.iterrows():
        inp = gather_inputs(
            str(row["distributor_code"]),
            mon_period,
            source,
            summary_row=row.to_dict(),
            payment_df=payment_df,
            all_periods=all_periods,
        )
        trails.append(build_trail(inp))
    return trails


# ---------------------------------------------------------------------------
# Module registration (generic audit registry)
# ---------------------------------------------------------------------------

STEP_NAMES = [
    "partner_activity",
    "expected_commission",
    "payment_record_search",
    "amount_comparison",
    "near_match",
    "upstream_completeness",
]


def _register() -> None:
    from backend.audit.base import AuditModule, register
    register(AuditModule(
        name="payment_reconciliation",
        label="Payment Reconciliation",
        claim=("Partner X was paid the correct amount for period Y — "
               "PAID_IN_FULL / UNDERPAID / OVERPAID / DISPUTED_ROUNDING / "
               "INSUFFICIENT_DATA."),
        step_names=STEP_NAMES,
        build=run_period,
    ))


_register()
