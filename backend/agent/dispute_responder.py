"""Compose a finance-ready commission dispute response letter.

Pure-Python template — no LLM call. Deterministic, free to run, and the
output is fully grounded in the same query layer the rest of the platform
uses. The agent path (``/chat``) can still produce a dispute response by
asking Claude, but this endpoint is the one wired to the UI button on
Payment exceptions and DISPUTED assurance findings — it returns the same
shape every time, so finance officers can rely on it for the demo.

The letter has four sections:

  1. Activation evidence    — total / qualified / unqualified / rate
  2. Recorded payment position — source owed / paid / outstanding; activation comparison
  3. Root-cause analysis    — zero-commission records classified into the
                              four KB root causes (USP snapshot miss /
                              outside 6-month window / NULL profile class /
                              Hynex denomination split)
  4. Conditional observation — recorded shortfall / excess / alignment for Finance review

The KB rules referenced here MUST match ``knowledge_base/fbb_commission_kb.md``;
if the KB changes, this module must be updated.
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

import pandas as pd

from backend import config
from backend.audit.payment_data import payment_lookup
from backend.db.commission_workspace import provenance
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
        "Possible snapshot miss: confirm whether the profile was present when commission was calculated; current profile evidence alone cannot establish this.",
    ),
    "OUTSIDE_6_MONTH_WINDOW": (
        "Outside the 6-month eligibility window",
        "More than 180 days elapsed between invoice date and first activation date — beyond the standing FBB eligibility window.",
    ),
    "NULL_PROFILE_CLASS": (
        "Missing account profile class",
        "The returned record has no profile class; confirm the profile used during calculation before attributing zero commission to this condition.",
    ),
    "HYNEX_DENOMINATION_SPLIT": (
        "Hynex denomination edge case",
        "The denomination matches the known Hynex / Hynex_1 naming pattern; confirm the applicable split before attributing a cause.",
    ),
}


def _format_ngn(v: float | int | None) -> str:
    n = float(v or 0)
    return f"NGN {n:,.2f}"


def _recommend_position(owed: float, paid: float) -> tuple[str, str]:
    """Describe the recorded balance without deciding entitlement or settlement."""
    balance = round(owed - paid, 2)
    if balance > 0:
        return (
            "RECORDED_SHORTFALL",
            f"The payment source records an outstanding balance of {_format_ngn(balance)}. "
            "If Finance confirms the source coverage, entitlement and settlement evidence, "
            "this balance may require settlement review.",
        )
    if balance < 0:
        return (
            "RECORDED_EXCESS",
            f"Recorded paid exceeds recorded owed by {_format_ngn(-balance)}. "
            "Finance should reconcile the source scope and settlement evidence before "
            "deciding whether an adjustment is needed.",
        )
    return (
        "RECORDED_BALANCE_ALIGNED",
        "Recorded owed and paid amounts align for this account and period. "
        "If Finance confirms the evidence is complete, this may support closure; "
        "the recorded balance alone does not resolve the dealer's claim.",
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
        amount_paid:       legacy input accepted for compatibility but ignored.
                           Owed and paid are read from the configured payment source.

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

    # Match the exact account, never a substring or an activation-derived balance.
    payment_df = payment_lookup(period, config.PAYMENT_SOURCE)
    payment_rows = (payment_df[payment_df["dealer_id"].astype(str) == dealer]
                    if not payment_df.empty else payment_df)
    if len(payment_rows) != 1:
        raise ValueError(f"No unique payment account for dealer {dealer} in period {period}.")
    payment = payment_rows.iloc[0]
    apdp = config.PAYMENT_SOURCE == "apdp"
    owed_key = "expected_commission_ngn" if apdp else "commission_owed"
    paid_key = "total_settled_ngn" if apdp else "amount_paid"
    if any(pd.isna(payment.get(key)) for key in (owed_key, paid_key)):
        raise ValueError(f"Incomplete payment amounts for dealer {dealer} in period {period}.")
    claimed = float(payment[owed_key])
    paid = float(payment[paid_key])
    payment_source = ("APDP recorded settlements; source completeness and fixture/live provenance "
                      "must be confirmed by Finance" if apdp else
                      "Simulated settlements (payment_simulation.csv); demonstration data, "
                      "not evidence of actual payment or entitlement")
    activation_source = provenance(period, "activation")["source"]
    statement_count = settlement_count = None
    reconciliation_status = None
    evidence_qualifications: list[str] = []
    statement_present = settlement_present = True
    if apdp:
        # APDP coalesces absent amounts to zero. Counts and source status
        # establish whether those numbers have supporting records.
        statement_count = (int(payment["statement_count"])
                           if pd.notna(payment.get("statement_count")) else None)
        settlement_count = (int(payment["settlement_count"])
                            if pd.notna(payment.get("settlement_count")) else None)
        reconciliation_status = (str(payment["reconciliation_status"])
                                 if pd.notna(payment.get("reconciliation_status")) else None)
        statement_present = (statement_count is not None and statement_count > 0
                             and reconciliation_status != "SALES_WITHOUT_STATEMENT")
        settlement_present = (settlement_count is not None and settlement_count > 0
                              and reconciliation_status != "STATEMENT_WITHOUT_PAYMENT")
        if not statement_present:
            evidence_qualifications.append(
                "Statement evidence is absent or not established. The source's recorded "
                "owed amount may be a normalized zero, not confirmed zero entitlement. "
                "The displayed balance cannot establish alignment or support dispute closure."
            )
        if not settlement_present:
            evidence_qualifications.append(
                "Settlement evidence is absent or not established. The source's recorded "
                "paid amount may be a normalized zero; absence does not prove non-payment. "
                "Finance must confirm payment coverage and references."
            )
        if reconciliation_status != "RECONCILED":
            evidence_qualifications.append(
                f"Source reconciliation status: {reconciliation_status or 'not supplied'}. "
                "An arithmetic balance does not resolve this source finding."
            )

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
    if apdp and (not statement_present or (
        round(claimed - paid, 2) == 0
        and (not settlement_present or reconciliation_status != "RECONCILED")
    )):
        position_code = "INSUFFICIENT_PAYMENT_EVIDENCE"
        position_para = (
            "The available APDP evidence does not establish an aligned payment position. "
            "Finance must confirm statement and settlement coverage and resolve any "
            "source reconciliation finding before deciding the dispute."
        )
    else:
        position_code, position_para = _recommend_position(claimed, paid)

    # 4. Render markdown.
    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    ref = f"DISP-{dealer}-{period}"
    lines: list[str] = []
    lines.append(f"# Commission dispute review — {dealer_name}")
    lines.append("")
    lines.append("**Draft for Finance review — not an approved response or settlement decision.**")
    lines.append("")
    lines.append(f"**Payment source:** {payment_source}.  ")
    lines.append(f"**Activation source:** {activation_source}.  ")
    lines.append("Source amounts are recorded observations; Finance must confirm coverage and supporting evidence before sharing or acting on this draft.")
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
        "month. This draft summarises the available recorded evidence for Finance "
        "review. It does not approve, decline or promise settlement."
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
    lines.append(f"- Non-zero commission records: **{qualified:,} ({qual_rate:.1f}%)**")
    lines.append(f"- Zero-commission records: **{zero_count:,}**")
    lines.append("")
    lines.append("## 2. Recorded payment position")
    lines.append("")
    lines.append(f"- Activation commission (separate comparison): **{_format_ngn(qualified_earned)}**")
    lines.append(f"- Payment-source recorded owed: **{_format_ngn(claimed)}**")
    lines.append(f"- Payment-source recorded paid: **{_format_ngn(paid)}**")
    outstanding = max(0.0, round(claimed - paid, 2))
    lines.append(f"- Outstanding (recorded owed − paid, minimum zero): **{_format_ngn(outstanding)}**")
    if apdp:
        lines.append(f"- Statement records: **{statement_count if statement_count is not None else 'Not supplied'}**")
        lines.append(f"- Settlement records: **{settlement_count if settlement_count is not None else 'Not supplied'}**")
        lines.append(f"- Source reconciliation status: **{reconciliation_status or 'Not supplied'}**")
        for qualification in evidence_qualifications:
            lines.append(f"- **Evidence qualification:** {qualification}")
    lines.append("")
    lines.append("Activation commission is a separate comparison, not a substitute for payment-source owed. Differences do not establish a cause or entitlement.")
    lines.append("")
    if zero_count > 0:
        lines.append("## 3. Candidate KB explanations — require verification")
        lines.append("")
        lines.append(
            f"For the {zero_count:,} zero-commission records, the template groups "
            "candidate explanations using the FBB Commission KB. These are not verified root causes:"
        )
        lines.append("")
        for cause, n in sorted(classifications.items(), key=lambda kv: -kv[1]):
            label, explainer = _CAUSE_LABELS.get(cause, (cause, ""))
            lines.append(f"- **{n:,} records — {label}.** {explainer}")
        lines.append("")
        lines.append(
            "USP snapshot miss is a fallback candidate, not proof that a profile was absent. "
            "Hynex naming alone does not confirm a split caused zero commission. "
            "Confirm snapshot, profile and invoice/activation evidence before attributing a cause."
        )
        lines.append("")
    lines.append("## 4. Conditional Finance observation")
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
        "Finance should confirm source coverage, payment references and any difference "
        "between recorded owed and activation commission before approving a response. "
        "Any next action and timing require separate confirmation."
    )
    lines.append("")
    lines.append("Prepared for Finance review; no approval or service commitment is implied.")
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
            "statement_count": statement_count,
            "settlement_count": settlement_count,
            "reconciliation_status": reconciliation_status,
            "evidence_qualifications": evidence_qualifications,
        },
    }
