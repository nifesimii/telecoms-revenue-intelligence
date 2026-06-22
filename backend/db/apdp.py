"""APDP Postgres reader — partner_settlements view.

The only piece of the FBB backend that talks to APDP's Postgres. Kept
narrow on purpose: this module knows two things and nothing else —

  1. How to connect (env-driven, pooled via psycopg2 connection re-use)
  2. How to read the ``normalized.partner_settlements`` reconciliation view

Everything else stays in the existing Presto/sample-data path.

The view's contract is documented in
``apdp/migrate_v1_3_0.sql`` and ``apdp/flink_jobs/SCHEMA_v1.3.0.md``.
"""
from __future__ import annotations

from contextlib import contextmanager
from typing import Any

import psycopg2
import psycopg2.extras

from backend import config

# Lazy singleton — reused across calls. psycopg2 connections are not
# thread-safe so we re-create on any error rather than juggle a pool.
_conn: psycopg2.extensions.connection | None = None


def _get_conn() -> psycopg2.extensions.connection:
    global _conn
    if _conn is None or _conn.closed:
        _conn = psycopg2.connect(
            host     = config.APDP_PG_HOST,
            port     = config.APDP_PG_PORT,
            dbname   = config.APDP_PG_DB,
            user     = config.APDP_PG_USER,
            password = config.APDP_PG_PASSWORD,
            connect_timeout = 5,
        )
        _conn.autocommit = True
    return _conn


@contextmanager
def _cursor():
    conn = _get_conn()
    try:
        cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
        yield cur
    finally:
        try:
            cur.close()
        except Exception:
            pass


_SELECT_COLUMNS = """
    dealer_id,
    settlement_period,
    COALESCE(sale_count, 0)                  AS sale_count,
    COALESCE(total_sales_ngn, 0)::float      AS total_sales_ngn,
    COALESCE(statement_count, 0)             AS statement_count,
    COALESCE(expected_commission_ngn, 0)::float    AS expected_commission_ngn,
    COALESCE(statement_gross_revenue_ngn, 0)::float AS statement_gross_revenue_ngn,
    COALESCE(settlement_count, 0)            AS settlement_count,
    COALESCE(total_settled_ngn, 0)::float    AS total_settled_ngn,
    COALESCE(paid_count, 0)                  AS paid_count,
    COALESCE(partial_count, 0)               AS partial_count,
    COALESCE(disputed_count, 0)              AS disputed_count,
    COALESCE(payment_variance_ngn, 0)::float AS payment_variance_ngn,
    reconciliation_status
"""


def get_partner_settlements(settlement_period: str) -> list[dict[str, Any]]:
    """Return one row per dealer for the given YYYYMM period.

    Raises ``psycopg2.Error`` on connection / query failure. Callers
    handle the fallback decision (e.g. surface 503, swap to simulated).
    """
    sql = f"SELECT {_SELECT_COLUMNS} FROM normalized.partner_settlements WHERE settlement_period = %(p)s ORDER BY dealer_id"
    with _cursor() as cur:
        cur.execute(sql, {"p": settlement_period})
        return [dict(r) for r in cur.fetchall()]


def get_partner_settlements_two_periods(
    period_a: str, period_b: str
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """Return (rows_a, rows_b) for the variance endpoint."""
    sql = f"SELECT {_SELECT_COLUMNS} FROM normalized.partner_settlements WHERE settlement_period = ANY(%(periods)s) ORDER BY dealer_id"
    with _cursor() as cur:
        cur.execute(sql, {"periods": [period_a, period_b]})
        all_rows = [dict(r) for r in cur.fetchall()]
    rows_a = [r for r in all_rows if r["settlement_period"] == period_a]
    rows_b = [r for r in all_rows if r["settlement_period"] == period_b]
    return rows_a, rows_b


def healthcheck() -> bool:
    """Light ping — used by /health to advertise live vs simulated mode."""
    try:
        with _cursor() as cur:
            cur.execute("SELECT 1")
            cur.fetchone()
        return True
    except Exception:
        return False
