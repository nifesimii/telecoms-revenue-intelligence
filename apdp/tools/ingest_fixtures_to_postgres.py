"""Direct-ingest APDP fixture CSVs into Postgres, bypassing Kafka + Flink.

Rationale. Per ``apdp/CLAUDE.md`` the Flink Docker build is broken and the
Kafka→Postgres sink was never wired. For the FBB demo we only need
``normalized.transactions`` populated so ``normalized.partner_settlements``
returns real rows when FBB has ``PAYMENT_SOURCE=apdp``. We can get there
by running the pure-Python ``normalizer_core.normalize_telecom_*``
functions on the fixture CSVs and inserting the results directly.

Usage:
    python apdp/tools/ingest_fixtures_to_postgres.py \\
        --fixtures /tmp/apdp-fixtures \\
        --period 202602 \\
        --dsn 'postgresql://fbb_audit:fbb_audit_pass@localhost:5544/fbb_audit'
"""
from __future__ import annotations

import argparse
import csv
import json
import sys
from pathlib import Path
from typing import Any

import psycopg2
import psycopg2.extras

# Add apdp/ to sys.path so we can import normalizer_core without an install step.
_APDP_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(_APDP_ROOT))
from flink_jobs.normalizer_core import (  # noqa: E402
    normalize_telecom_commission_statement,
    normalize_telecom_dealer_sale,
    normalize_telecom_settlement,
)


_INSERT_SQL = """
INSERT INTO normalized.transactions (
    transaction_id, provider, event_type,
    amount, currency, amount_ngn,
    fx_rate, fx_source, status, transaction_type,
    payment_source, ingestion_mode,
    partner_id, dealer_id, product_type,
    gross_revenue, commission_amount, commission_rate,
    settlement_period, linked_statement_ref,
    sender_phone, receiver_phone,
    initiated_at, completed_at, metadata
) VALUES (
    %(transaction_id)s, %(provider)s, %(event_type)s,
    %(amount)s, %(currency)s, %(amount_ngn)s,
    %(fx_rate)s, %(fx_source)s, %(status)s, %(transaction_type)s,
    %(payment_source)s, %(ingestion_mode)s,
    %(partner_id)s, %(dealer_id)s, %(product_type)s,
    %(gross_revenue)s, %(commission_amount)s, %(commission_rate)s,
    %(settlement_period)s, %(linked_statement_ref)s,
    %(sender_phone)s, %(receiver_phone)s,
    %(initiated_at)s, %(completed_at)s, %(metadata)s
)
ON CONFLICT (transaction_id) DO NOTHING
"""


def _norm_to_row(n: dict, settlement_period: str) -> dict[str, Any]:
    """Flatten normalizer output → insertable row.

    The normalizer returns nested ``sender``/``receiver`` dicts + a
    ``metadata`` map. The table has flat sender_phone / receiver_phone
    columns plus a JSONB metadata column. Also backfills settlement_period
    on events that don't carry it in the raw (dealer_sale doesn't).
    """
    sender = n.get("sender") or {}
    receiver = n.get("receiver") or {}
    return {
        "transaction_id":     n["transaction_id"],
        "provider":           n["provider"],
        "event_type":         n.get("event_type"),
        "amount":             n.get("amount"),
        "currency":           n.get("currency"),
        "amount_ngn":         n.get("amount_ngn"),
        "fx_rate":            n.get("fx_rate"),
        "fx_source":          n.get("fx_source"),
        "status":             n.get("status"),
        "transaction_type":   n.get("transaction_type"),
        "payment_source":     n.get("payment_source"),
        "ingestion_mode":     n.get("ingestion_mode"),
        "partner_id":         n.get("partner_id"),
        "dealer_id":          n.get("dealer_id"),
        "product_type":       n.get("product_type"),
        "gross_revenue":      n.get("gross_revenue"),
        "commission_amount":  n.get("commission_amount"),
        "commission_rate":    n.get("commission_rate"),
        # dealer_sale doesn't carry settlement_period in raw — backfill.
        "settlement_period":  n.get("settlement_period") or settlement_period,
        "linked_statement_ref": n.get("linked_statement_ref"),
        "sender_phone":       sender.get("phone"),
        "receiver_phone":     receiver.get("phone"),
        "initiated_at":       n.get("initiated_at"),
        "completed_at":       n.get("completed_at"),
        "metadata":           json.dumps(n.get("metadata") or {}),
    }


def _iter_csv(path: Path):
    with path.open(newline="") as f:
        yield from csv.DictReader(f)


def ingest(fixtures_dir: Path, period: str, dsn: str) -> None:
    period_dir = fixtures_dir / period
    if not period_dir.is_dir():
        raise SystemExit(f"No fixtures for period {period} at {period_dir}")

    sales_csv    = period_dir / "dealer_sales.csv"
    stmts_csv    = period_dir / "commission_statements.csv"
    settles_csv  = period_dir / "settlement_records.csv"

    for p in (sales_csv, stmts_csv, settles_csv):
        if not p.is_file():
            raise SystemExit(f"Missing fixture file: {p}")

    conn = psycopg2.connect(dsn)
    try:
        with conn.cursor() as cur:
            # Dealer sales
            sale_rows = []
            for raw in _iter_csv(sales_csv):
                # Add settlement_period into the raw so the normalizer can
                # carry it through. The generator omits it on sales; the
                # normalizer copies it from raw.settlement_period.
                raw["settlement_period"] = period
                n = normalize_telecom_dealer_sale({"raw": raw})
                sale_rows.append(_norm_to_row(n, period))
            psycopg2.extras.execute_batch(cur, _INSERT_SQL, sale_rows, page_size=500)
            print(f"  dealer_sale:            {len(sale_rows):>6} rows")

            # Commission statements
            stmt_rows = []
            for raw in _iter_csv(stmts_csv):
                n = normalize_telecom_commission_statement({"raw": raw})
                stmt_rows.append(_norm_to_row(n, period))
            psycopg2.extras.execute_batch(cur, _INSERT_SQL, stmt_rows, page_size=500)
            print(f"  commission_statement:   {len(stmt_rows):>6} rows")

            # Settlements
            settle_rows = []
            for raw in _iter_csv(settles_csv):
                # The generator's settlement_ref maps to statement_ref via
                # linked_statement_ref. The normalizer transforms it to the
                # tel_stmt_ prefix; the view joins on that transformed id.
                n = normalize_telecom_settlement({"raw": raw})
                settle_rows.append(_norm_to_row(n, period))
            psycopg2.extras.execute_batch(cur, _INSERT_SQL, settle_rows, page_size=500)
            print(f"  settlement:             {len(settle_rows):>6} rows")

        conn.commit()
    finally:
        conn.close()


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--fixtures", required=True, help="Fixture root (contains <period>/ subdirs)")
    parser.add_argument("--period", required=True, help="YYYYMM")
    parser.add_argument(
        "--dsn",
        default="postgresql://fbb_audit:fbb_audit_pass@localhost:5544/fbb_audit",
        help="Postgres DSN — defaults to the local fbb-audit-pg container",
    )
    args = parser.parse_args()
    ingest(Path(args.fixtures), args.period, args.dsn)


if __name__ == "__main__":
    main()
