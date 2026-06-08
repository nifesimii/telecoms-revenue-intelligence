"""Phase 4 — generate the simulated payment dataset from real commission &
exception data.

Run ONCE to produce ``data/samples/payment_simulation.csv``:

    python -m backend.data.generate_payment_simulation

Every simulated payment row is causally derived from real dev_act data:

  * ``commission_owed`` = ``total_commission_ngn`` from
    :func:`get_dealer_summary` (sum of qualified ``commission_rate``).
  * ``payment_rate`` is selected by the dealer's WORST exception flag
    across Phases 2 (activation) and 3 (inventory). Priority:

        ALL_UNQUALIFIED        → 0.20  (Phase 2)
        CONFIRMED_MISMATCH     → 0.40  (Phase 3)
        HIGH_UNQUALIFIED_RATE  → 0.60  (Phase 2)
        none                   → 0.90  (default)

  * ``payment_status`` follows from rate + flag:

        amount_unpaid = 0                                → FULLY_PAID
        amount_unpaid > 0 & ALL_UNQ/CONFIRMED_MISMATCH   → DISPUTED
        amount_unpaid > 0 & HIGH_UNQUALIFIED_RATE        → PARTIALLY_PAID
        amount_unpaid > 0 & no flag                      → PENDING

The output CSV is committed alongside the other sample data and loaded by
the Phase 4 query handlers; this script is *not* invoked at runtime.
"""
from __future__ import annotations

import calendar
import os
import sys
from datetime import datetime, timedelta
from pathlib import Path

# Allow running as ``python backend/data/generate_payment_simulation.py``
# from the project root, in addition to ``python -m`` invocation.
_PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

os.environ.setdefault("USE_SAMPLE_DATA", "true")

import pandas as pd  # noqa: E402

from backend.db.connection import execute_query  # noqa: E402

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

PERIODS: tuple[str, ...] = ("202602", "202603")

# Priority order — worst flag wins (top of list is worst).
# Tuples are ``(rate, flag_name)`` so callers can unpack as ``rate, flag``.
_FLAG_PRIORITY: list[tuple[float, str]] = [
    (0.20, "ALL_UNQUALIFIED"),
    (0.40, "CONFIRMED_MISMATCH"),
    (0.60, "HIGH_UNQUALIFIED_RATE"),
]
_DEFAULT_RATE = 0.90

# Channel mapping by account_profile_class.
_CHANNEL_BY_CLASS: dict[str, str] = {
    "FIXED BROADBAND": "BANK_TRANSFER",
    "DATA PARTNERS": "BANK_TRANSFER",
    "CONNECT STORES": "MTN_INTERNAL_SETTLEMENT",
    "CONNECT HUB": "MTN_INTERNAL_SETTLEMENT",
    "PENTAGON FRANCHISE": "BANK_TRANSFER",
    "DEALER": "BANK_TRANSFER",
    "ENTERPRISE BUSINESS": "BANK_TRANSFER",
}

OUTPUT_PATH: Path = (
    _PROJECT_ROOT / "data" / "samples" / "payment_simulation.csv"
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _period_end_plus(period: str, days: int) -> str:
    year = int(period[:4])
    month = int(period[4:6])
    last_day = calendar.monthrange(year, month)[1]
    end = datetime(year, month, last_day)
    return (end + timedelta(days=days)).strftime("%Y-%m-%d")


def _dealer_flags(period: str) -> tuple[set[str], set[str], set[str]]:
    """Return (ALL_UNQ dealers, CONFIRMED_MISMATCH dealers, HIGH_UNQ dealers)
    for the period, each as a set of distributor_code strings."""

    acts = execute_query("get_activation_exceptions", {"mon_period": period})
    inv = execute_query("get_inventory_comparison", {"mon_period": period})

    all_unq = set(
        acts.loc[acts["exception_type"] == "ALL_UNQUALIFIED", "dealer_id"]
        .astype(str)
        .tolist()
    )
    high_unq = set(
        acts.loc[acts["exception_type"] == "HIGH_UNQUALIFIED_RATE", "dealer_id"]
        .astype(str)
        .tolist()
    )
    mismatch = set(
        inv.loc[inv["finding_type"] == "CONFIRMED_MISMATCH", "dealer_id"]
        .astype(str)
        .tolist()
    )
    return all_unq, mismatch, high_unq


def _resolve_flag(
    dealer_id: str,
    all_unq: set[str],
    mismatch: set[str],
    high_unq: set[str],
) -> tuple[float, str | None]:
    """Pick the worst flag for a dealer and return (rate, flag_name|None)."""
    if dealer_id in all_unq:
        return _FLAG_PRIORITY[0]
    if dealer_id in mismatch:
        return _FLAG_PRIORITY[1]
    if dealer_id in high_unq:
        return _FLAG_PRIORITY[2]
    return _DEFAULT_RATE, None


def _payment_status(amount_unpaid: float, flag: str | None) -> str:
    if amount_unpaid == 0:
        return "FULLY_PAID"
    if flag in ("ALL_UNQUALIFIED", "CONFIRMED_MISMATCH"):
        return "DISPUTED"
    if flag == "HIGH_UNQUALIFIED_RATE":
        return "PARTIALLY_PAID"
    return "PENDING"


def _payment_date(period: str, status: str) -> str | None:
    if status == "FULLY_PAID":
        return _period_end_plus(period, 25)
    if status == "PARTIALLY_PAID":
        return _period_end_plus(period, 30)
    return None


def _payment_channel(account_profile_class: str | None) -> str:
    if not account_profile_class or pd.isna(account_profile_class):
        return "BANK_TRANSFER"
    return _CHANNEL_BY_CLASS.get(
        str(account_profile_class).strip(), "BANK_TRANSFER"
    )


# ---------------------------------------------------------------------------
# Main generation
# ---------------------------------------------------------------------------


def generate() -> pd.DataFrame:
    rows: list[dict] = []
    for period in PERIODS:
        all_unq, mismatch, high_unq = _dealer_flags(period)
        summary = execute_query("get_dealer_summary", {"mon_period": period})

        for _, dealer in summary.iterrows():
            dealer_id = str(dealer["distributor_code"])
            commission_owed = float(dealer["total_commission_ngn"])
            rate, flag = _resolve_flag(dealer_id, all_unq, mismatch, high_unq)
            amount_paid = round(commission_owed * rate, 2)
            amount_unpaid = round(commission_owed - amount_paid, 2)
            status = _payment_status(amount_unpaid, flag)
            channel = _payment_channel(dealer.get("account_profile_class"))
            pay_date = _payment_date(period, status)

            rows.append(
                {
                    "distributor_code": dealer_id,
                    "distributor_name": str(dealer["distributor_name"]),
                    "account_profile_class": (
                        ""
                        if pd.isna(dealer.get("account_profile_class"))
                        else str(dealer["account_profile_class"])
                    ),
                    "report_month": period,
                    "commission_owed": commission_owed,
                    "amount_paid": amount_paid,
                    "amount_unpaid": amount_unpaid,
                    "payment_rate": rate,
                    "payment_status": status,
                    "payment_channel": channel,
                    "payment_date": pay_date,
                    "exception_flag": flag,
                    "data_source": "SIMULATED",
                }
            )

    return pd.DataFrame(rows)


def main() -> None:
    OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    df = generate()
    df.to_csv(OUTPUT_PATH, index=False)

    print(f"Generated {len(df):,} payment rows -> {OUTPUT_PATH}")
    print()
    print("Status distribution by period:")
    print(
        df.groupby(["report_month", "payment_status"])
        .size()
        .unstack(fill_value=0)
        .to_string()
    )
    print()
    print("Coverage % per period:")
    for period, grp in df.groupby("report_month"):
        total_owed = float(grp["commission_owed"].sum())
        total_paid = float(grp["amount_paid"].sum())
        pct = total_paid / total_owed * 100.0 if total_owed > 0 else 0.0
        print(
            f"  {period}: owed NGN {total_owed:,.2f}, paid NGN {total_paid:,.2f}, "
            f"coverage {pct:.2f}%"
        )


if __name__ == "__main__":
    main()
