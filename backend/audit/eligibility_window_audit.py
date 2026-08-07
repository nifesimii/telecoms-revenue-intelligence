"""Eligibility-window verification-chain builder (fourth audit module).

Audits the KB's most-cited zero-commission root cause per-record: the
6-month invoice→activation eligibility rule. For each partner with any
zero-commission activation records in the period, the trail asks:

    Are those zero-commission records genuinely outside the 6-month
    invoice→activation window, or are some inside the window with no
    explaining alternate KB root cause (i.e. potential underpayment)?

Distinction from the other payment/commission modules:
  * ``zero_commission`` audits "was the partner paid at all?" (payment lookup)
  * ``payment_reconciliation`` audits "was the amount right?" (amount comparison)
  * ``eligibility_window`` audits "was the ZERO ITSELF correct?" (policy check
    against invoice→activation gap, per IMEI)

Subject of the audit. One trail per partner with zero-commission activity —
same subject shape as ``zero_commission_audit`` so a reviewer can pivot
between the two modules on the same subject. Per-IMEI verdicts land inside
step details, keeping the trail count manageable while preserving
drill-down evidence.

Data source. ``get_zero_commission_records(mon_period, distributor_code)``
returns per-IMEI rows with ``invoice_date`` and ``first_activation_date``
— enough to compute the gap directly. Rate/eligibility fields for the
step-5 root-cause attribution come from ``get_dealer_summary`` +
``usp_dimension`` (shared with ``zero_commission_audit``).

Known limitation. Dates in the sample data are parseable but occasionally
missing on individual IMEI rows; those records are counted separately and
surface as step-2 caveats rather than being silently dropped.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any

import pandas as pd

from backend import config
from backend.audit.product_aliases import siblings_of
from backend.audit.trail import TrailStep, VerificationTrail
from backend.audit.zero_commission_audit import _load_usp_items
from backend.db.connection import execute_query

# KB Section 2 / Issue 2 — the 6-month eligibility window is 180 days.
# Keep this as a named constant so the same value gates step 4 and shows in
# every trail's detail — a reviewer never has to guess what "6 months" meant.
_ELIGIBILITY_WINDOW_DAYS = 180

_DATA_SOURCE = "fbb_comm_dev_act"


# ---------------------------------------------------------------------------
# Inputs struct — everything the pure builder needs, pre-fetched.
# ---------------------------------------------------------------------------

@dataclass
class EligibilityWindowInputs:
    partner_code: str
    partner_name: str
    mon_period: str
    account_profile_class: str | None

    # Zero-commission IMEI-level records for this partner/period, each
    # augmented with a parsed invoice→activation gap in days.
    # Row shape: {imei, product_code, product_name, invoice_date_str,
    #             activation_date_str, gap_days | None, has_dates: bool}
    zero_records: list[dict[str, Any]] = field(default_factory=list)

    # Step 5 — cross-check against other KB root causes.
    products_missing_from_usp: list[str] = field(default_factory=list)

    # Step 6 — dataset-level completeness for the period.
    dates_fully_populated: bool = True


# ---------------------------------------------------------------------------
# Pure builder — the 6-step chain + conclusion.
# ---------------------------------------------------------------------------

def build_trail(inp: EligibilityWindowInputs) -> VerificationTrail:
    steps: list[TrailStep] = []
    total = len(inp.zero_records)
    has_activity = total > 0

    # ── Step 1 — Any zero-commission records to audit? ────────────────────
    steps.append(TrailStep(
        step=1,
        name="zero_commission_records_present",
        checked="Does the partner have any zero-commission activation records for this period?",
        result=(
            f"{total} zero-commission record(s) found."
            if has_activity else
            "No zero-commission records — nothing to audit."
        ),
        passed=has_activity,
        caveat=None if has_activity
        else "No zero-commission records — the eligibility-window claim is vacuously true.",
        detail={
            "source_table": _DATA_SOURCE,
            "zero_commission_count": total,
        },
    ))

    # ── Step 2 — Dates available on the records? ──────────────────────────
    with_dates = [r for r in inp.zero_records if r.get("has_dates")]
    without_dates = [r for r in inp.zero_records if not r.get("has_dates")]
    n_with = len(with_dates)
    n_without = len(without_dates)
    dates_ok = n_without == 0
    steps.append(TrailStep(
        step=2,
        name="fetch_dates",
        checked=("Are invoice_date and first_activation_date populated on "
                 "each zero-commission record?"),
        result=(
            f"{n_with} record(s) with both dates; {n_without} missing one or both."
        ),
        passed=dates_ok,
        caveat=(None if dates_ok else
                f"{n_without} record(s) missing invoice_date or "
                "first_activation_date — cannot compute the gap for those."),
        detail={
            "with_dates_count": n_with,
            "without_dates_count": n_without,
        },
    ))

    # ── Step 3 — Compute gaps per record ─────────────────────────────────
    gaps = [int(r["gap_days"]) for r in with_dates if r.get("gap_days") is not None]
    if gaps:
        gap_min, gap_max = min(gaps), max(gaps)
        gap_median = sorted(gaps)[len(gaps) // 2]
        gap_result = (
            f"Gap distribution over {len(gaps)} record(s): "
            f"min={gap_min}d, median={gap_median}d, max={gap_max}d."
        )
    else:
        gap_min = gap_max = gap_median = None
        gap_result = "No records with both dates — no gaps to compute."
    steps.append(TrailStep(
        step=3,
        name="compute_gaps",
        checked="Compute invoice→activation gap (in days) for each record.",
        result=gap_result,
        passed=True,
        caveat=None,
        detail={
            "gap_days_min": gap_min,
            "gap_days_median": gap_median,
            "gap_days_max": gap_max,
            "records_with_gap": len(gaps),
        },
    ))

    # ── Step 4 — Classify each record against the 6-month window ─────────
    inside_window: list[dict[str, Any]] = []
    outside_window: list[dict[str, Any]] = []
    future_dated: list[dict[str, Any]] = []
    for r in with_dates:
        g = r.get("gap_days")
        if g is None:
            continue
        if g < 0:
            future_dated.append(r)
        elif g <= _ELIGIBILITY_WINDOW_DAYS:
            inside_window.append(r)
        else:
            outside_window.append(r)
    n_inside = len(inside_window)
    n_outside = len(outside_window)
    n_future = len(future_dated)
    steps.append(TrailStep(
        step=4,
        name="classify_against_window",
        checked=(f"Bucket each record: inside window (0-{_ELIGIBILITY_WINDOW_DAYS}d), "
                 f"outside window (>{_ELIGIBILITY_WINDOW_DAYS}d), or future-dated (<0d)."),
        result=(
            f"{n_outside} outside window (zero-commission CORRECT), "
            f"{n_inside} inside window (should have earned commission), "
            f"{n_future} future-dated (data quality issue)."
        ),
        # Pass when every record is legitimately outside the window.
        passed=(n_inside == 0 and n_future == 0),
        caveat=(None if (n_inside == 0 and n_future == 0) else
                f"{n_inside} record(s) inside the eligibility window — "
                "step 5 will check for other zero-commission root causes."
                if n_inside > 0 else
                f"{n_future} record(s) have activation before invoice — "
                "data quality issue independent of the eligibility rule."),
        detail={
            "window_days": _ELIGIBILITY_WINDOW_DAYS,
            "outside_window_count": n_outside,
            "inside_window_count": n_inside,
            "future_dated_count": n_future,
            "inside_window_imeis": [r["imei"] for r in inside_window],
        },
    ))

    # ── Step 5 — Root-cause attribution for inside-window records ────────
    # For each record inside the window, check if another documented
    # zero-commission root cause explains it (KB Section 6):
    #   - NULL account_profile_class (Issue 6)
    #   - Product missing from USP rate card (Issue 2 / USP snapshot miss)
    #   - Hynex/Hynex_1 alias split (Issue 4)
    # Records inside the window with NONE of these explanations are the
    # candidate policy violations.
    profile_null = not bool(inp.account_profile_class)
    usp_missing = set(inp.products_missing_from_usp or [])

    attributed: list[dict[str, Any]] = []
    unexplained: list[dict[str, Any]] = []
    for r in inside_window:
        causes = []
        if profile_null:
            causes.append("null_account_profile_class")
        if str(r.get("product_code") or "") in usp_missing:
            causes.append("usp_snapshot_miss")
        if siblings_of(str(r.get("product_code") or "")):
            causes.append("known_alias_group")
        r_with_causes = {**r, "alt_root_causes": causes}
        (attributed if causes else unexplained).append(r_with_causes)

    n_attributed = len(attributed)
    n_unexplained = len(unexplained)
    steps.append(TrailStep(
        step=5,
        name="root_cause_attribution",
        checked=("For each inside-window record, check for another documented "
                 "zero-commission root cause (NULL profile class, USP snapshot "
                 "miss, known alias split)."),
        result=(
            f"{n_attributed} of {n_inside} inside-window record(s) attributable "
            f"to other root causes; {n_unexplained} unexplained."
            if n_inside > 0 else
            "No inside-window records to attribute."
        ),
        passed=(n_unexplained == 0),
        caveat=(f"{n_unexplained} record(s) inside the eligibility window with "
                "no other zero-commission root cause — partner may be owed "
                "commission on these records.")
        if n_unexplained > 0 else None,
        detail={
            "attributed_count": n_attributed,
            "unexplained_count": n_unexplained,
            "unexplained_imeis": [r["imei"] for r in unexplained],
        },
    ))

    # ── Step 6 — Upstream completeness ────────────────────────────────────
    steps.append(TrailStep(
        step=6,
        name="upstream_completeness",
        checked=("Is the activation dataset itself complete for this period — "
                 "date fields reliably populated across zero-commission records?"),
        result=(
            "Date fields are reliably populated across the sampled records."
            if inp.dates_fully_populated else
            "Date fields have significant gaps across zero-commission records — "
            "eligibility check runs against incomplete data."
        ),
        passed=inp.dates_fully_populated,
        caveat=("Date coverage on zero-commission records is incomplete for "
                "this period. Eligibility verdicts should be treated as partial.")
        if not inp.dates_fully_populated else None,
        detail={
            "data_source": _DATA_SOURCE,
            "dates_fully_populated": inp.dates_fully_populated,
        },
    ))

    # ── Conclusion + confidence ───────────────────────────────────────────
    conclusion, confidence = _conclude(
        inp, steps, has_activity,
        n_outside=n_outside, n_inside=n_inside, n_unexplained=n_unexplained,
    )
    return VerificationTrail(
        partner_code=inp.partner_code,
        partner_name=inp.partner_name,
        mon_period=inp.mon_period,
        payment_source=_DATA_SOURCE,
        steps=steps,
        conclusion=conclusion,
        confidence=confidence,
    )


def _conclude(
    inp: EligibilityWindowInputs,
    steps: list[TrailStep],
    has_activity: bool,
    *,
    n_outside: int,
    n_inside: int,
    n_unexplained: int,
) -> tuple[str, str]:
    """Derive (conclusion, confidence)."""
    step2 = next(s for s in steps if s.step == 2)
    step6 = next(s for s in steps if s.step == 6)

    # No zero-commission activity → nothing to audit.
    if not has_activity:
        return "INSUFFICIENT_DATA", "LOW"

    # Upstream date coverage gap → can't trust the buckets.
    if not step6.passed:
        return "INSUFFICIENT_DATA", "LOW"

    # Determine the policy verdict.
    if n_unexplained > 0:
        # Records inside the window with no other explanation → underpayment.
        conclusion = "POLICY_VIOLATED"
    elif n_inside > 0:
        # Inside-window records exist but every one is attributable to
        # another KB root cause — the 6-month rule wasn't the actual driver.
        conclusion = "MIXED_ATTRIBUTION"
    else:
        # Every zero-comm record is legitimately outside the window.
        conclusion = "POLICY_MET"

    # Confidence follows caveat profile, excluding step-4's expected caveat
    # when any inside-window records exist (step 5 already reasons about
    # those; double-counting would drop confidence unnecessarily).
    caveat_names = [s.name for s in steps if s.caveat]
    weighted = [n for n in caveat_names if n != "classify_against_window"]
    if not weighted:
        confidence = "HIGH"
    elif len(weighted) == 1:
        confidence = "MEDIUM"
    else:
        confidence = "LOW"

    # A step-2 date-missing caveat is definitive — knock confidence down.
    if not step2.passed and confidence == "HIGH":
        confidence = "MEDIUM"

    return conclusion, confidence


# ---------------------------------------------------------------------------
# Input gathering — fetch from the existing query layer.
# ---------------------------------------------------------------------------

def _parse_invoice_date(value: Any) -> datetime | None:
    """Parse invoice_date (``YYYY-MM-DD``) into a datetime, or None."""
    if value is None:
        return None
    s = str(value).strip()
    if not s or s.lower() == "nan":
        return None
    try:
        return datetime.strptime(s[:10], "%Y-%m-%d")
    except ValueError:
        return None


def _parse_activation_date(value: Any) -> datetime | None:
    """Parse first_activation_date (``YYYYMMDD HH:MM:SS``) into a datetime.

    Tolerates a plain ``YYYYMMDD`` (no time part) or the ISO variant, in
    case source data drifts.
    """
    if value is None:
        return None
    s = str(value).strip()
    if not s or s.lower() == "nan":
        return None
    # Try YYYYMMDD [HH:MM:SS] first — the observed format.
    for fmt in ("%Y%m%d %H:%M:%S", "%Y%m%d", "%Y-%m-%d %H:%M:%S", "%Y-%m-%d"):
        try:
            return datetime.strptime(s, fmt)
        except ValueError:
            continue
    return None


def _augment_record_with_gap(row: dict[str, Any]) -> dict[str, Any]:
    """Return the record dict with a parsed ``gap_days`` and ``has_dates``."""
    inv = _parse_invoice_date(row.get("invoice_date"))
    act = _parse_activation_date(row.get("first_activation_date"))
    if inv is None or act is None:
        return {**row, "gap_days": None, "has_dates": False}
    return {**row, "gap_days": (act - inv).days, "has_dates": True}


def gather_inputs(
    partner_code: str,
    partner_name: str,
    account_profile_class: str | None,
    mon_period: str,
    *,
    usp_items: set[str] | None = None,
) -> EligibilityWindowInputs:
    """Assemble :class:`EligibilityWindowInputs` for one partner."""
    zero_df = execute_query(
        "get_zero_commission_records",
        {"mon_period": str(mon_period), "distributor_code": str(partner_code)},
    )
    records: list[dict[str, Any]] = []
    if zero_df is not None and not zero_df.empty:
        for _, row in zero_df.iterrows():
            records.append(_augment_record_with_gap(row.to_dict()))

    if usp_items is None:
        usp_items = _load_usp_items()

    zero_products = list({str(r.get("product_code") or "") for r in records if r.get("product_code")})
    missing_from_usp = [p for p in zero_products if p and p not in usp_items]

    # Dataset-completeness heuristic: if more than 20% of records are
    # missing a date, flag the whole period as incomplete. Below that,
    # treat missing dates as individual data-quality noise (caveats at
    # step 2) rather than upstream failure.
    total = len(records)
    without_dates = sum(1 for r in records if not r["has_dates"])
    dates_fully_populated = total == 0 or (without_dates / total) < 0.20

    return EligibilityWindowInputs(
        partner_code=str(partner_code),
        partner_name=str(partner_name or partner_code),
        mon_period=str(mon_period),
        account_profile_class=account_profile_class,
        zero_records=records,
        products_missing_from_usp=missing_from_usp,
        dates_fully_populated=dates_fully_populated,
    )


# ---------------------------------------------------------------------------
# Orchestrator — run the whole period.
# ---------------------------------------------------------------------------

def run_period(mon_period: str, payment_source: str | None = None) -> list[VerificationTrail]:
    """Build a trail for every partner with any zero-commission activity in
    the period. ``payment_source`` accepted for interface parity with
    :class:`~backend.audit.base.AuditModule.build`; unused here.
    """
    _ = payment_source

    summary_df = execute_query("get_dealer_summary", {"mon_period": mon_period})
    if summary_df.empty:
        return []
    flagged = summary_df[summary_df["zero_commission_count"].astype(int) > 0]
    if flagged.empty:
        return []

    usp_items = _load_usp_items()

    trails: list[VerificationTrail] = []
    for _, row in flagged.iterrows():
        inp = gather_inputs(
            str(row["distributor_code"]),
            str(row.get("distributor_name") or row["distributor_code"]),
            row.get("account_profile_class") or None,
            mon_period,
            usp_items=usp_items,
        )
        trails.append(build_trail(inp))
    return trails


# ---------------------------------------------------------------------------
# Module registration (generic audit registry)
# ---------------------------------------------------------------------------

STEP_NAMES = [
    "zero_commission_records_present",
    "fetch_dates",
    "compute_gaps",
    "classify_against_window",
    "root_cause_attribution",
    "upstream_completeness",
]


def _register() -> None:
    from backend.audit.base import AuditModule, register
    register(AuditModule(
        name="eligibility_window",
        label="Eligibility Window",
        claim=("Zero-commission records attributed to the 6-month invoice→"
               "activation rule are genuinely outside that window — "
               "POLICY_MET / POLICY_VIOLATED / MIXED_ATTRIBUTION / "
               "INSUFFICIENT_DATA."),
        step_names=STEP_NAMES,
        build=run_period,
    ))


_register()

_ = config  # imported for header-parity with other audit modules
