"""Zero-commission verification-chain builder (Phase 1).

Produces a :class:`VerificationTrail` for one (partner, period) — the
audit artifact behind a "Partner X was not paid commission for period Y"
claim. Six ordered checks, then a conclusion + confidence.

Design note — separation for testability:
  * ``build_trail(inputs)`` is a PURE function of a ``ZeroCommissionInputs``
    struct. All the judgment logic lives here and is unit-testable with
    synthetic inputs (no DB, no query layer).
  * ``gather_inputs(...)`` fetches the struct from the existing query layer.
  * ``run_period(...)`` orchestrates: flag partners → gather → build → return.

On the "applicable rate/contract" check (step 2): there is no dedicated
contract-terms table in this platform. The commission rate is inline on
each activation row (``fbb_comm_dev_act.commission_rate``); eligibility is
governed by ``usp_dimension`` (``account_profile_class``) plus the KB's
6-month window rule. Step 2 therefore records those sub-checks rather than
citing a contract row, and says so explicitly in its detail.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

import pandas as pd

from backend import config
from backend.audit.trail import TrailStep, VerificationTrail
from backend.db.connection import execute_query

# Tolerance for "paid in full" comparisons, in NGN.
_PAY_TOLERANCE = 1.0


# ---------------------------------------------------------------------------
# Inputs struct — everything the pure builder needs, pre-fetched.
# ---------------------------------------------------------------------------

@dataclass
class ZeroCommissionInputs:
    partner_code: str
    partner_name: str
    mon_period: str
    payment_source: str                 # "simulated" | "apdp"

    # Step 1 — activity
    total_activations: int
    zero_commission_count: int

    # Step 2 — rate / eligibility.
    # There is no partner-level contract table. Eligibility is assessed from:
    #   (a) account_profile_class on the activation row (NULL ⇒ root cause), and
    #   (b) whether the zero-commission products exist in the USP product rate
    #       card (usp_dimension.item_no) — absence ⇒ "USP snapshot miss".
    account_profile_class: str | None    # None / "" ⇒ NULL profile class

    # Step 3 — expected commission
    expected_commission_ngn: float       # what qualified activations earned

    # ── Fields with defaults (must follow all non-default fields) ────────
    # Step 2 detail
    zero_comm_product_codes: list[str] = field(default_factory=list)
    products_missing_from_usp: list[str] = field(default_factory=list)
    commission_by_denomination: dict[str, float] = field(default_factory=dict)

    # Step 4 — payment record
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

def build_trail(inp: ZeroCommissionInputs) -> VerificationTrail:
    steps: list[TrailStep] = []
    qualified = max(0, inp.total_activations - inp.zero_commission_count)

    # ── Step 1 — Qualifying activity check ───────────────────────────────
    had_activity = inp.total_activations > 0
    steps.append(TrailStep(
        step=1,
        name="qualifying_activity",
        checked="Did the partner have activation records for this period?",
        result=(
            f"{inp.total_activations} activation records found "
            f"({qualified} qualified, {inp.zero_commission_count} zero-commission)."
            if had_activity else
            "No activation records found for this partner/period."
        ),
        passed=had_activity,
        caveat=None if had_activity
        else "No activation records — cannot assess commission entitlement.",
        detail={
            "source_table": "fbb_comm_dev_act",
            "total_activations": inp.total_activations,
            "qualified_count": qualified,
            "zero_commission_count": inp.zero_commission_count,
        },
    ))

    # ── Step 2 — Applicable rate / contract check ────────────────────────
    # No contract table; assess profile eligibility + USP product coverage.
    has_profile = bool(inp.account_profile_class)
    usp_miss = bool(inp.products_missing_from_usp)
    rate_ok = has_profile and not usp_miss
    if not has_profile:
        s2_caveat = ("NULL account_profile_class — a documented zero-commission "
                     "root cause. No profile means no rate can be matched.")
    elif usp_miss:
        s2_caveat = (
            f"{len(inp.products_missing_from_usp)} zero-commission product(s) "
            "absent from the USP rate card — 'USP snapshot miss' root cause."
        )
    else:
        s2_caveat = None
    steps.append(TrailStep(
        step=2,
        name="applicable_rate",
        checked=("Is there a valid, non-expired commission rate / eligibility "
                 "for this partner/product/period?"),
        result=(
            f"Profile class '{inp.account_profile_class or '(none)'}'; "
            f"{qualified} of {inp.total_activations} activations carry a non-zero rate; "
            f"{len(inp.products_missing_from_usp)} zero-comm product(s) missing from USP."
        ),
        passed=rate_ok,
        caveat=s2_caveat,
        detail={
            "no_contract_table": True,
            "basis": ("rate is inline on fbb_comm_dev_act rows; eligibility from "
                      "account_profile_class + usp_dimension product rate card "
                      "(item_no) + KB 6-month window"),
            "account_profile_class": inp.account_profile_class,
            "qualified_count": qualified,
            "zero_comm_product_codes": inp.zero_comm_product_codes,
            "products_missing_from_usp": inp.products_missing_from_usp,
        },
    ))

    # ── Step 3 — Expected commission computation ─────────────────────────
    # Expected = what the qualified activations earned. Zero-commission
    # records contribute 0 by rule; the audit is about whether that 0 is
    # correct, so a fully-zero partner (expected 0 with activity) is a caveat.
    expected = round(float(inp.expected_commission_ngn), 2)
    all_zero_with_activity = had_activity and qualified == 0
    steps.append(TrailStep(
        step=3,
        name="expected_commission",
        checked="Compute the commission the partner was entitled to.",
        result=(
            f"Expected commission NGN {expected:,.2f} from {qualified} qualified "
            f"activations."
            + ("  All activations were zero-commission — expected entitlement is "
               "NGN 0.00." if all_zero_with_activity else "")
        ),
        passed=True,
        caveat=("Every activation was zero-commission; entitlement computes to "
                "NGN 0.00. Confirm this reflects genuine ineligibility, not a "
                "rate-lookup failure.") if all_zero_with_activity else None,
        detail={
            "expected_commission_ngn": expected,
            "inputs": {
                "qualified_count": qualified,
                "basis": "sum of commission_rate over qualified activations",
                "commission_by_denomination": inp.commission_by_denomination,
            },
        },
    ))

    # ── Step 4 — Payment record search ───────────────────────────────────
    paid = round(float(inp.amount_paid_ngn), 2)
    steps.append(TrailStep(
        step=4,
        name="payment_record_search",
        checked=f"Search the {inp.payment_source} payment data for this partner/period.",
        result=(
            f"Payment record found: NGN {paid:,.2f} ({inp.payment_status})."
            if inp.payment_found else
            "No payment record found for this partner/period."
        ),
        passed=inp.payment_found,
        # Absence of a payment is the crux of a 'not paid' claim, not a
        # data caveat — so no caveat here on a clean not-found. The caveat
        # about whether the *dataset* is complete belongs to step 6.
        caveat=None,
        detail={
            "payment_source": inp.payment_source,
            "query": (f"payment record where distributor_code={inp.partner_code} "
                      f"and report_month={inp.mon_period}"),
            "payment_found": inp.payment_found,
            "amount_paid_ngn": paid,
            "payment_status": inp.payment_status,
        },
    ))

    # ── Step 5 — Near-match check ────────────────────────────────────────
    near = list(inp.adjacent_period_payments)
    is_partial = inp.payment_found and 0 < paid < (expected - _PAY_TOLERANCE)
    near_found = bool(near) or is_partial
    steps.append(TrailStep(
        step=5,
        name="near_match",
        checked=("Before concluding 'not paid', check adjacent periods and "
                 "partial-amount matches."),
        result=(
            (f"{len(near)} payment(s) to this partner in adjacent periods. "
             if near else "")
            + ("Partial payment detected (paid < expected). " if is_partial else "")
            + ("No near-matches — clean." if not near_found else "")
        ).strip(),
        passed=not near_found,
        caveat=("Possible payment under a different period/reference, or a "
                "partial settlement. Manual review before finalising 'not paid'.")
        if near_found else None,
        detail={
            "adjacent_period_payments": near,
            "partial_payment": is_partial,
            "expected_commission_ngn": expected,
            "amount_paid_ngn": paid,
        },
    ))

    # ── Step 6 — Upstream completeness check ─────────────────────────────
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
                "Cannot distinguish 'not paid' from 'not yet ingested'.")
        if not upstream_ok else None,
        detail={
            "payment_source": inp.payment_source,
            "period_present_in_payment_data": inp.period_present_in_payment_data,
            "known_ingestion_gap": inp.known_ingestion_gap,
        },
    ))

    # ── Step 7 — Conclusion + confidence ─────────────────────────────────
    conclusion, confidence = _conclude(inp, steps, expected, paid)
    return VerificationTrail(
        partner_code=inp.partner_code,
        partner_name=inp.partner_name,
        mon_period=inp.mon_period,
        payment_source=inp.payment_source,
        steps=steps,
        conclusion=conclusion,
        confidence=confidence,
    )


def _conclude(
    inp: ZeroCommissionInputs,
    steps: list[TrailStep],
    expected: float,
    paid: float,
) -> tuple[str, str]:
    """Derive (conclusion, confidence) from the step results."""
    caveat_steps = [s.name for s in steps if s.caveat]
    step6 = next(s for s in steps if s.step == 6)
    step1 = next(s for s in steps if s.step == 1)

    # No activity at all → nothing to conclude about payment.
    if not step1.passed:
        return "INSUFFICIENT_DATA", "LOW"

    # Upstream gap → can't tell 'not paid' from 'not ingested'.
    if not step6.passed:
        return "INSUFFICIENT_DATA", "LOW"

    # Determine paid vs not paid.
    if inp.payment_found and paid >= expected - _PAY_TOLERANCE:
        conclusion = "PAID"
    elif expected <= _PAY_TOLERANCE:
        # Nothing was owed (all zero-commission) and none paid — correctly zero.
        conclusion = "PAID"
    else:
        conclusion = "NOT_PAID"

    # Confidence from caveat profile.
    non_step6_caveats = [c for c in caveat_steps if c != "upstream_completeness"]
    if not caveat_steps:
        confidence = "HIGH"
    elif len(non_step6_caveats) == 1:
        confidence = "MEDIUM"
    else:
        confidence = "LOW"

    return conclusion, confidence


# ---------------------------------------------------------------------------
# Input gathering — fetch from the existing query layer.
# ---------------------------------------------------------------------------

def _load_usp_items() -> set[str]:
    """Set of product codes (item_no) present in the USP rate card.

    Reads usp_dimension directly. On any failure returns an empty set —
    conservative: every product then reads as 'missing from USP', which
    surfaces as a step-2 caveat rather than a false clean.
    """
    try:
        from backend.db.queries import _load_csv  # sample-mode reader
        df = _load_csv("usp_dimension")
        if "item_no" in df.columns:
            return {str(v) for v in df["item_no"].dropna().unique()}
    except Exception:
        pass
    return set()


def _zero_comm_product_codes(partner_code: str, mon_period: str) -> list[str]:
    """Distinct product codes among the partner's zero-commission records."""
    try:
        df = execute_query(
            "get_zero_commission_records",
            {"mon_period": mon_period, "distributor_code": partner_code},
        )
        if "product_code" in df.columns:
            return [str(v) for v in df["product_code"].dropna().unique()]
    except Exception:
        pass
    return []


def _payment_lookup(period: str, source: str) -> pd.DataFrame:
    """Per-dealer payment rows for the period, from the active payment source."""
    if source == "apdp":
        # partner_settlements exposes total_settled_ngn per dealer/period.
        from backend.db import apdp as apdp_db
        rows = apdp_db.get_partner_settlements(period)
        return pd.DataFrame(rows)
    # Simulated path.
    return execute_query("get_payment_summary", {"mon_period": period})


def gather_inputs(
    partner_code: str,
    mon_period: str,
    payment_source: str,
    *,
    summary_row: dict[str, Any] | None = None,
    usp_items: set[str] | None = None,
    payment_df: pd.DataFrame | None = None,
    all_periods: list[str] | None = None,
) -> ZeroCommissionInputs:
    """Assemble a :class:`ZeroCommissionInputs` for one partner.

    The optional keyword args let ``run_period`` pass shared lookups (USP
    item set, payment frame, period list) so we don't refetch them per
    partner.
    """
    if summary_row is None:
        df = execute_query(
            "get_dealer_summary",
            {"mon_period": mon_period, "distributor_code": partner_code},
        )
        summary_row = df.iloc[0].to_dict() if not df.empty else {}

    if usp_items is None:
        usp_items = _load_usp_items()
    if payment_df is None:
        payment_df = _payment_lookup(mon_period, payment_source)

    profile = summary_row.get("account_profile_class") or None

    # Step 2 — USP product coverage for the partner's zero-comm products.
    zero_products = _zero_comm_product_codes(str(partner_code), str(mon_period))
    missing_from_usp = [p for p in zero_products if p not in usp_items]

    # Payment lookup for this partner in this period.
    paid, found, status = _extract_payment(payment_df, partner_code, payment_source)

    # Step 5 — adjacent-period payments (period ± 1 within known periods).
    adjacent = _adjacent_period_payments(
        partner_code, mon_period, payment_source, all_periods,
    )

    # Step 6 — does the payment dataset cover this period at all?
    period_present = _payment_source_covers_period(payment_df, mon_period, payment_source)

    return ZeroCommissionInputs(
        partner_code=str(partner_code),
        partner_name=str(summary_row.get("distributor_name") or partner_code),
        mon_period=str(mon_period),
        payment_source=payment_source,
        total_activations=int(summary_row.get("total_activations") or 0),
        zero_commission_count=int(summary_row.get("zero_commission_count") or 0),
        account_profile_class=profile,
        zero_comm_product_codes=zero_products,
        products_missing_from_usp=missing_from_usp,
        expected_commission_ngn=float(summary_row.get("total_commission_ngn") or 0.0),
        commission_by_denomination=summary_row.get("commission_by_denomination") or {},
        payment_found=found,
        amount_paid_ngn=paid,
        payment_status=status,
        adjacent_period_payments=adjacent,
        period_present_in_payment_data=period_present,
        known_ingestion_gap=not period_present,
    )


def _extract_payment(
    payment_df: pd.DataFrame, partner_code: str, source: str
) -> tuple[float, bool, str | None]:
    if payment_df is None or payment_df.empty:
        return 0.0, False, None
    code_col = "dealer_id" if source == "apdp" else "distributor_code"
    paid_col = "total_settled_ngn" if source == "apdp" else "amount_paid"
    status_col = "reconciliation_status" if source == "apdp" else "payment_status"
    if code_col not in payment_df.columns:
        return 0.0, False, None
    match = payment_df[payment_df[code_col].astype(str) == str(partner_code)]
    if match.empty:
        return 0.0, False, None
    row = match.iloc[0]
    paid = float(row.get(paid_col) or 0.0)
    status = str(row.get(status_col)) if status_col in match.columns else None
    return paid, True, status


def _adjacent_period_payments(
    partner_code: str, period: str, source: str, all_periods: list[str] | None
) -> list[dict[str, Any]]:
    """Payments to this partner in the immediately adjacent periods."""
    if not all_periods:
        return []
    try:
        idx = sorted(all_periods).index(str(period))
    except ValueError:
        return []
    neighbours = []
    ordered = sorted(all_periods)
    for j in (idx - 1, idx + 1):
        if 0 <= j < len(ordered):
            neighbours.append(ordered[j])

    out: list[dict[str, Any]] = []
    for p in neighbours:
        df = _payment_lookup(p, source)
        paid, found, status = _extract_payment(df, partner_code, source)
        if found and paid > _PAY_TOLERANCE:
            out.append({"period": p, "amount_paid_ngn": paid, "status": status})
    return out


def _payment_source_covers_period(
    payment_df: pd.DataFrame, period: str, source: str
) -> bool:
    """True if the payment dataset has any rows for this period."""
    if payment_df is None or payment_df.empty:
        return False
    # Simulated path carries report_month; apdp carries settlement_period.
    for col in ("report_month", "settlement_period"):
        if col in payment_df.columns:
            return (payment_df[col].astype(str) == str(period)).any()
    # If the frame is already period-scoped (no period column), non-empty = covered.
    return not payment_df.empty


# ---------------------------------------------------------------------------
# Orchestrator — run the whole period.
# ---------------------------------------------------------------------------

def run_period(mon_period: str, payment_source: str | None = None) -> list[VerificationTrail]:
    """Build a trail for every partner flagged with zero-commission activity
    in the period. Returns the trails; persistence is the caller's job.
    """
    source = payment_source or config.PAYMENT_SOURCE

    summary_df = execute_query("get_dealer_summary", {"mon_period": mon_period})
    if summary_df.empty:
        return []

    flagged = summary_df[summary_df["zero_commission_count"].astype(int) > 0]
    if flagged.empty:
        return []

    # Shared lookups — fetched once, reused across partners.
    usp_items = _load_usp_items()
    payment_df = _payment_lookup(mon_period, source)
    all_periods = _known_periods()

    trails: list[VerificationTrail] = []
    for _, row in flagged.iterrows():
        inp = gather_inputs(
            str(row["distributor_code"]),
            mon_period,
            source,
            summary_row=row.to_dict(),
            usp_items=usp_items,
            payment_df=payment_df,
            all_periods=all_periods,
        )
        trails.append(build_trail(inp))
    return trails


def _known_periods() -> list[str]:
    try:
        from backend.db import queries
        return [str(p) for p in queries.get_available_periods()]
    except Exception:
        return []
