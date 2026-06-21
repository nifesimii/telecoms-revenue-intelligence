"""
Generate realistic telecom-batch CSV fixtures for one settlement period.

Produces three correlated files matching SCHEMA_v1.3.0.md input specs:
  - dealer_sales.csv
  - commission_statements.csv
  - settlement_records.csv

Intentional discrepancies are seeded so reconciliation logic has real
cases to surface:
  * one dealer has sales NOT covered by any commission statement (= leakage)
  * one commission statement has no matching settlement (= unpaid)
  * one settlement is PARTIAL (= dispute candidate)
  * one settlement is DISPUTED (= flagged on FBB side)

Deterministic via --seed. Default settlement period = current month.

Usage:
    python tools/generate_telecom_fixtures.py --period 202410 --out tools/fixtures
"""
from __future__ import annotations

import argparse
import csv
import os
import random
from datetime import datetime, timedelta, timezone
from pathlib import Path

DEALERS = [
    ("FBB_D00001", "MTN Connect Solutions",     "PARTNER_A", "+2348031000001"),
    ("FBB_D00002", "Hynex Distribution Ltd",    "PARTNER_A", "+2348031000002"),
    ("FBB_D00003", "Kashmir Global Networks",   "PARTNER_B", "+2348031000003"),
    ("FBB_D00004", "Citicom Telecom Services",  "PARTNER_B", "+2348031000004"),
    ("FBB_D00005", "Naijatech Partners",        "PARTNER_C", "+2348031000005"),
]

PRODUCTS = [
    # (product_type, product_code, unit_price_ngn, commission_rate)
    ("FBB_DEVICE", "MIFI_4G_BASIC", 25_000, 0.08),
    ("FBB_DEVICE", "MIFI_5G_PRO",   65_000, 0.10),
    ("FBB_DEVICE", "ROUTER_HOME",   45_000, 0.07),
    ("BUNDLE",     "DATA_50GB",      8_500, 0.05),
    ("AIRTIME",    "TOPUP_1000",     1_000, 0.03),
]

PAYMENT_METHODS = ["MOMO", "MOMO", "MOMO", "CASH", "CARD"]  # MoMo-weighted
STATEMENT_STATUSES = ["FINAL", "FINAL", "FINAL", "DRAFT"]


def _period_dates(period: str) -> tuple[datetime, datetime]:
    """Return (first_day, last_day) of the YYYYMM period in UTC."""
    year, month = int(period[:4]), int(period[4:])
    start = datetime(year, month, 1, tzinfo=timezone.utc)
    next_month = (
        datetime(year + 1, 1, 1, tzinfo=timezone.utc)
        if month == 12
        else datetime(year, month + 1, 1, tzinfo=timezone.utc)
    )
    return start, next_month - timedelta(seconds=1)


def _random_ts_in(start: datetime, end: datetime, rng: random.Random) -> str:
    delta = (end - start).total_seconds()
    ts = start + timedelta(seconds=rng.random() * delta)
    return ts.replace(microsecond=0).isoformat()


def _random_imei(rng: random.Random) -> str:
    # 15 digits, deterministic per rng.
    return "".join(str(rng.randint(0, 9)) for _ in range(15))


def generate(period: str, out_dir: Path, seed: int, sales_per_dealer: int) -> None:
    rng = random.Random(seed)
    start, end = _period_dates(period)
    out_dir.mkdir(parents=True, exist_ok=True)

    sales_rows: list[dict] = []
    # By (dealer_code, product_type) → list of sales for aggregation later
    by_dealer_product: dict[tuple[str, str], list[dict]] = {}

    # ── 1. Dealer sales ───────────────────────────────────────────────────────
    for dealer_code, _, partner_code, _ in DEALERS:
        n = sales_per_dealer + rng.randint(-5, 5)
        for i in range(max(1, n)):
            product_type, product_code, unit_price, _rate = rng.choice(PRODUCTS)
            qty = rng.choices([1, 1, 1, 2, 3], k=1)[0]
            amount = unit_price * qty
            method = rng.choice(PAYMENT_METHODS)
            row = {
                "transaction_ref": f"DMS_{dealer_code}_{period}_{i:04d}",
                "sale_date": _random_ts_in(start, end, rng),
                "dealer_code": dealer_code,
                "partner_code": partner_code,
                "product_type": product_type,
                "product_code": product_code,
                "imei": _random_imei(rng) if product_type == "FBB_DEVICE" else "",
                "total_amount_ngn": amount,
                "payment_method": method,
                "consumer_msisdn": (
                    f"+23480{rng.randint(10_000_000, 99_999_999)}"
                    if method == "MOMO"
                    else ""
                ),
                "source_system": "DEALER_MGMT_X",
            }
            sales_rows.append(row)
            by_dealer_product.setdefault(
                (dealer_code, product_type), []
            ).append(row)

    _write_csv(out_dir / "dealer_sales.csv", sales_rows)

    # ── 2. Commission statements ──────────────────────────────────────────────
    # One statement per (dealer, product_type) combination — but skip one dealer
    # entirely to seed a "sales without matching statement" leakage case.
    skip_dealer = DEALERS[-1][0]  # Naijatech — no statements at all

    statement_rows: list[dict] = []
    statement_refs_by_dealer: dict[str, list[str]] = {}

    for (dealer_code, product_type), sales in by_dealer_product.items():
        if dealer_code == skip_dealer:
            continue
        rate = next(r for p, _, _, r in PRODUCTS if p == product_type)
        # Real-world: not every sale qualifies — model a 70-95% qualification rate.
        qualified = int(len(sales) * rng.uniform(0.70, 0.95))
        gross_revenue = sum(s["total_amount_ngn"] for s in sales[:qualified])
        commission = round(gross_revenue * rate, 2)
        ref = f"STMT_{dealer_code}_{product_type}_{period}"
        statement_rows.append(
            {
                "statement_ref": ref,
                "statement_date": _random_ts_in(end, end + timedelta(days=3), rng),
                "settlement_period": period,
                "dealer_code": dealer_code,
                "partner_code": next(
                    p for c, _, p, _ in DEALERS if c == dealer_code
                ),
                "product_type": product_type,
                "activation_count": len(sales),
                "qualified_count": qualified,
                "gross_revenue_ngn": gross_revenue,
                "commission_rate": rate,
                "commission_amount_ngn": commission,
                "status": rng.choice(STATEMENT_STATUSES),
                "source_system": "COMMISSION_ENGINE",
            }
        )
        statement_refs_by_dealer.setdefault(dealer_code, []).append(ref)

    _write_csv(out_dir / "commission_statements.csv", statement_rows)

    # ── 3. Settlement records ─────────────────────────────────────────────────
    # Pay most statements. Seeded discrepancies:
    #   * one statement: no settlement at all (UNPAID)
    #   * one statement: PARTIAL payment
    #   * one statement: DISPUTED
    settlement_rows: list[dict] = []
    statements = [s for s in statement_rows if s["status"] != "DRAFT"]
    unpaid_idx = rng.randrange(len(statements)) if statements else None
    partial_idx = rng.randrange(len(statements)) if statements else None
    disputed_idx = rng.randrange(len(statements)) if statements else None

    for i, stmt in enumerate(statements):
        if i == unpaid_idx:
            continue  # No settlement row at all.

        dealer_code = stmt["dealer_code"]
        msisdn = next(m for c, _, _, m in DEALERS if c == dealer_code)
        is_partial = i == partial_idx
        is_disputed = i == disputed_idx
        payout_method = rng.choices(["MOMO", "BANK"], weights=[7, 3])[0]
        amount = stmt["commission_amount_ngn"]
        if is_partial:
            amount = round(amount * rng.uniform(0.3, 0.7), 2)

        settlement_rows.append(
            {
                "settlement_ref": f"PAY_{dealer_code}_{stmt['product_type']}_{period}",
                "linked_statement_ref": stmt["statement_ref"],
                "settlement_date": _random_ts_in(
                    end + timedelta(days=2), end + timedelta(days=10), rng
                ),
                "settlement_period": period,
                "dealer_code": dealer_code,
                "amount_ngn": amount,
                "payout_method": payout_method,
                "momo_transaction_id": (
                    f"MOMO_{rng.randint(10_000_000, 99_999_999)}"
                    if payout_method == "MOMO"
                    else ""
                ),
                "dealer_msisdn": msisdn if payout_method == "MOMO" else "",
                "status": (
                    "DISPUTED" if is_disputed
                    else "PARTIAL" if is_partial
                    else "PAID"
                ),
                "source_system": (
                    "MTN_MOMO_DISBURSEMENT" if payout_method == "MOMO"
                    else "ORACLE_AP"
                ),
            }
        )

    _write_csv(out_dir / "settlement_records.csv", settlement_rows)

    print(
        f"Wrote {len(sales_rows)} sales / "
        f"{len(statement_rows)} statements / "
        f"{len(settlement_rows)} settlements → {out_dir}/"
    )


def _write_csv(path: Path, rows: list[dict]) -> None:
    if not rows:
        path.write_text("")
        return
    fieldnames = list(rows[0].keys())
    with path.open("w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)


def _default_period() -> str:
    now = datetime.now(timezone.utc)
    return f"{now.year}{now.month:02d}"


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[1])
    parser.add_argument("--period", default=_default_period(), help="YYYYMM")
    parser.add_argument(
        "--out",
        default=str(Path(__file__).parent / "fixtures"),
        help="Output directory",
    )
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument(
        "--sales-per-dealer",
        type=int,
        default=30,
        help="Approximate number of dealer-sales rows per dealer",
    )
    args = parser.parse_args()

    if not (len(args.period) == 6 and args.period.isdigit()):
        parser.error(f"--period must be YYYYMM, got {args.period!r}")

    out_dir = Path(args.out) / args.period
    generate(args.period, out_dir, args.seed, args.sales_per_dealer)


if __name__ == "__main__":
    main()
