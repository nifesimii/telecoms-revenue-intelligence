"""Compose a finance-ready commission dispute response letter.

Pure-Python template — no LLM call. Deterministic, free to run, and the
output is fully grounded in the same query layer the rest of the platform
uses. The agent path (``/chat``) can still produce a dispute response by
asking Claude, but this endpoint is the one wired to the UI button on
Payment exceptions and DISPUTED assurance findings — it returns the same
shape every time, so finance officers can rely on it for the demo.

The letter has four sections:

  1. Activation evidence    — total / qualified / unqualified / rate
  2. Commission calculation — earned / claimed / paid / outstanding
  3. Root-cause analysis    — zero-commission records classified into the
                              four KB root causes (USP snapshot miss /
                              outside 6-month window / NULL profile class /
                              Hynex denomination split)
  4. Recommended position   — FULL / PARTIAL / DECLINE based on variance

The KB rules referenced here MUST match ``knowledge_base/fbb_commission_kb.md``;
if the KB changes, this module must be updated.
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

import pandas as pd

from backend.db.connection import execute_query


# Six-month window in days. Matches the KB definition (1) of an activation
# being outside the eligibility window from its invoice date.
_WINDOW_DAYS = 180


def _parse_date(v: Any) -> datetime | None:
    """Best-effort date parse. Returns None for NaN / unparseable values.

    The raw data ships dates in two shapes:
      ``2025-08-30``          (invoice_date)
      ``20260210 10:42:02``   (first_activation_date)
    """
    if v is None or (isinstance(v, float) and pd.isna(v)) or v == "":
        return None
    s = str(v).strip()
    for fmt in ("%Y-%m-%d", "%Y%m%d %H:%M:%S", "%Y%m%d", "%Y-%m-%d %H:%M:%S"):
        try:
            return datetime.strptime(s, fmt)
        except ValueError:
            continue
    return None


def _classify_zero_record(row: dict[str, Any]) -> str:
    """Map one zero-commission record to one of the four KB root causes."""
    profile = row.get("account_profile_class")
    if profile is None or (isinstance(profile, float) and pd.isna(profile)) or profile == "":
        return "NULL_PROFILE_CLASS"

    denom = str(row.get("product_denomination") or "").lower()
    if "hynex" in denom:
        return "HYNEX_DENOMINATION_SPLIT"

    inv = _parse_date(row.get("invoice_date"))
    act = _parse_date(row.get("first_activation_date"))
    if inv and act and (act - inv).days > _WINDOW_DAYS:
        return "OUTSIDE_6_MONTH_WINDOW"

    # Everything else falls under the "USP snapshot miss" bucket — the
    # dealer's profile was present at audit time but missing when the
    # commission engine looked it up.
    return "USP_SNAPSHOT_MISS"


# Human-friendly labels + KB rule citations used in the letter.
_CAUSE_LABELS = {
    "USP_SNAPSHOT_MISS": (
        "USP snapshot miss",
        "Dealer profile was not present in the USP dimension snapshot at the moment of commission calculation, even if the profile is on file today.",
    ),
    "OUTSIDE_6_MONTH_WINDOW": (
        "Outside the 6-month eligibility window",
        "More than 180 days elapsed between invoice date and first activation date — beyond the standing FBB eligibility window.",
    ),
    "NULL_PROFILE_CLASS": (
        "Missing account profile class",
        "Dealer record has no profile class on file — the activation cannot be matched to a commission rate.",
    ),
    "HYNEX_DENOMINATION_SPLIT": (
        "Hynex denomination edge case",
        "Product belongs to the known Hynex / Hynex_1 split that the commission engine handles separately.",
    ),
}


def _format_ngn(v: float | int | None) -> str:
    n = float(v or 0)
    return f"NGN {n:,.2f}"


def _recommend_position(qualified_earned: float, claimed: float, paid: float) -> tuple[str, str]:
    """Return (position_code, paragraph) based on variance vs the statement."""
    outstanding = round(claimed - paid, 2)
    earned_minus_paid = round(qualified_earned - paid, 2)

    # Tolerance ±NGN 1 for rounding.
    if abs(earned_minus_paid) <= 1 and outstanding <= 1:
        return (
            "NO_FURTHER_ACTION",
            "Records align: the dealer has been paid in full for activations that qualified. "
            "We recommend closing this dispute with no further settlement action.",
        )
    if earned_minus_paid > 1:
        return (
            "PARTIAL_PAYMENT_AGREED",
            f"The qualified activations support an additional {_format_ngn(earned_minus_paid)} "
            f"beyond what has been paid to date. We recommend settling this additional amount "
            f"in the next payment cycle.",
        )
    if earned_minus_paid < -1 and paid > claimed:
        return (
            "DISPUTE_DECLINED",
            f"The paid amount already exceeds the commission earned by the dealer's qualified "
            f"activations by {_format_ngn(abs(earned_minus_paid))}. No further settlement is due; "
            f"the dispute is declined on the basis of the activation evidence above.",
        )
    return (
        "DECLINED_INSUFFICIENT_QUALIFICATION",
        f"The statement claims {_format_ngn(claimed)} but qualified activations only support "
        f"{_format_ngn(qualified_earned)}. We recommend declining the additional "
        f"{_format_ngn(claimed - qualified_earned)} unless the dealer provides evidence that "
        f"any of the unqualified activations should be re-classified.",
    )


def compose_dispute_response(
    *,
    distributor_code: str,
    mon_period: str,
    dispute_text: str | None = None,
    amount_paid: float | None = None,
) -> dict[str, Any]:
    """Build the dispute-response payload for one (dealer, period).

    Args:
        distributor_code:  dealer code (matches fbb_comm_dev_act).
        mon_period:        YYYYMM reporting period.
        dispute_text:      optional free-text quote from the dealer's claim;
                           included verbatim in the letter so the recipient
                           sees what we're responding to.
        amount_paid:       optional override for the paid amount (when the
                           caller already has it from /payments/summary).
                           If omitted, defaults to the qualified-earned
                           figure (assumes statement was paid in full).

    Returns:
        ``{"markdown": str, "summary": {...}}`` where ``summary`` carries
        the structured numbers for the UI badge + audit trail.
    """
    period = str(mon_period)
    dealer = str(distributor_code)

    # 1. Activation summary — single row when distributor_code is provided.
    summary_df = execute_query(
        "get_dealer_summary",
        {"mon_period": period, "distributor_code": dealer},
    )
    if summary_df.empty:
        raise ValueError(
            f"No commission data for dealer {dealer} in period {period}."
        )
    s = summary_df.iloc[0]
    dealer_name = s.get("dealer_name") or dealer
    profile_class = s.get("account_profile_class") or "—"
    total_acts = int(s.get("total_activations") or 0)
    qualified_earned = float(s.get("total_commission_ngn") or 0)
    zero_count = int(s.get("zero_commission_count") or 0)
    qualified = max(0, total_acts - zero_count)
    qual_rate = (qualified / total_acts * 100.0) if total_acts > 0 else 0.0

    claimed = qualified_earned  # statement claim mirrors qualified-earned in sample mode
    paid = float(amount_paid) if amount_paid is not None else qualified_earned

    # 2. Zero-commission records, classified.
    classifications: dict[str, int] = {}
    if zero_count > 0:
        zero_df = execute_query(
            "get_zero_commission_records",
            {"mon_period": period, "distributor_code": dealer},
        )
        for _, row in zero_df.iterrows():
            cause = _classify_zero_record(row.to_dict())
            classifications[cause] = classifications.get(cause, 0) + 1

    # 3. Recommended position.
    position_code, position_para = _recommend_position(qualified_earned, claimed, paid)

    # 4. Render markdown.
    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    ref = f"DISP-{dealer}-{period}"
    lines: list[str] = []
    lines.append(f"# Commission dispute review — {dealer_name}")
    lines.append("")
    lines.append(f"**Reference:** {ref}  ")
    lines.append(f"**Date:** {today}  ")
    lines.append(f"**Reporting period:** {period}  ")
    lines.append(f"**Dealer code:** {dealer}  ")
    lines.append(f"**Account profile class:** {profile_class}  ")
    lines.append("")
    lines.append(f"Dear {dealer_name},")
    lines.append("")
    lines.append(
        f"Thank you for raising a commission dispute for the {period} reporting "
        "month. We have reviewed our records against the standing FBB commission "
        "schedule and provide the following evidence-based response."
    )
    if dispute_text:
        lines.append("")
        lines.append("## Your stated position")
        lines.append("")
        for ln in dispute_text.strip().splitlines():
            lines.append(f"> {ln}")
    lines.append("")
    lines.append("## 1. Activation evidence")
    lines.append("")
    lines.append(f"- Total activations in {period}: **{total_acts:,}**")
    lines.append(f"- Qualified for commission: **{qualified:,} ({qual_rate:.1f}%)**")
    lines.append(f"- Unqualified: **{zero_count:,}**")
    lines.append("")
    lines.append("## 2. Commission calculation")
    lines.append("")
    lines.append(f"- Commission earned from qualified activations: **{_format_ngn(qualified_earned)}**")
    lines.append(f"- Statement amount issued: **{_format_ngn(claimed)}**")
    lines.append(f"- Settlement to date: **{_format_ngn(paid)}**")
    outstanding = max(0.0, round(claimed - paid, 2))
    lines.append(f"- Outstanding (statement − paid): **{_format_ngn(outstanding)}**")
    lines.append("")
    if zero_count > 0:
        lines.append("## 3. Root-cause analysis")
        lines.append("")
        lines.append(
            f"Of the {zero_count:,} unqualified activations, the following "
            "documented conditions apply (per the FBB Commission KB):"
        )
        lines.append("")
        for cause, n in sorted(classifications.items(), key=lambda kv: -kv[1]):
            label, explainer = _CAUSE_LABELS.get(cause, (cause, ""))
            lines.append(f"- **{n:,} records — {label}.** {explainer}")
        lines.append("")
        lines.append(
            "These conditions result in zero commission per the standing commission "
            "schedule, regardless of the activation value."
        )
        lines.append("")
    lines.append("## 4. Recommended settlement position")
    lines.append("")
    lines.append(f"**{position_code.replace('_', ' ')}**")
    lines.append("")
    lines.append(position_para)
    lines.append("")
    lines.append("## 5. Next steps")
    lines.append("")
    lines.append(
        "If you have additional information that may revise the position above, "
        "please reply with:"
    )
    lines.append("")
    lines.append("- IMEIs of devices you believe were incorrectly classified as unqualified")
    lines.append("- Invoice dates from your records that fall within the 6-month window")
    lines.append("- Evidence of profile registration as of the activation date")
    lines.append("")
    lines.append(
        "We will re-review this dispute within **3 business days** of receiving "
        "additional evidence."
    )
    lines.append("")
    lines.append("Regards,  ")
    lines.append("MTN FBB Finance Team")
    lines.append("")
    lines.append("---")
    lines.append(f"*Generated by FBB Revenue Intelligence Platform · {today} UTC*")

    return {
        "markdown": "\n".join(lines),
        "summary": {
            "reference": ref,
            "dealer_id": dealer,
            "dealer_name": dealer_name,
            "mon_period": period,
            "total_activations": total_acts,
            "qualified_activations": qualified,
            "unqualified_activations": zero_count,
            "qualification_rate_pct": round(qual_rate, 1),
            "qualified_commission_ngn": round(qualified_earned, 2),
            "statement_claim_ngn": round(claimed, 2),
            "amount_paid_ngn": round(paid, 2),
            "outstanding_ngn": round(outstanding, 2),
            "root_cause_classifications": classifications,
            "position_code": position_code,
        },
    }
