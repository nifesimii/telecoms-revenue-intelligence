"""Persistence for zero-commission verification trails.

Writes/reads against the dedicated FBB audit Postgres (separate from
APDP's payment_platform). Config: ``config.FBB_AUDIT_PG_*``. Schema:
``infra/postgres/audit_init.sql`` (schema ``audit``).

The trail is an audit artifact: it must remain queryable months later,
so this is a real persisted table — not a log file. Writes are grouped
by ``run_id``; re-running a period atomically replaces that period's
trails (delete-then-insert in one transaction) so the latest run is the
source of truth without orphaning old rows.
"""
from __future__ import annotations

import json
import uuid
from datetime import datetime, timezone
from typing import Any

import psycopg2
import psycopg2.extras

from backend import config
from backend.audit.trail import VerificationTrail

_conn: psycopg2.extensions.connection | None = None


def _get_conn() -> psycopg2.extensions.connection:
    global _conn
    if _conn is None or _conn.closed:
        _conn = psycopg2.connect(
            host=config.FBB_AUDIT_PG_HOST,
            port=config.FBB_AUDIT_PG_PORT,
            dbname=config.FBB_AUDIT_PG_DB,
            user=config.FBB_AUDIT_PG_USER,
            password=config.FBB_AUDIT_PG_PASSWORD,
            connect_timeout=5,
        )
        _conn.autocommit = False
    return _conn


def healthcheck() -> bool:
    try:
        conn = _get_conn()
        with conn.cursor() as cur:
            cur.execute("SELECT 1")
            cur.fetchone()
        conn.rollback()
        return True
    except Exception:
        return False


_schema_ensured = False


def ensure_schema() -> None:
    """Idempotently ensure the generic `module` column + index exist.

    Runs once per process before the first write. Lets a DB created by an
    older init.sql (without the module column) work without a manual
    migration — the generic audit layer stays self-healing.
    """
    global _schema_ensured
    if _schema_ensured:
        return
    conn = _get_conn()
    try:
        with conn.cursor() as cur:
            cur.execute(
                "ALTER TABLE audit.zero_commission_trail "
                "ADD COLUMN IF NOT EXISTS module VARCHAR(50) NOT NULL "
                "DEFAULT 'zero_commission'"
            )
            cur.execute(
                "CREATE INDEX IF NOT EXISTS idx_zct_module "
                "ON audit.zero_commission_trail(module)"
            )
        conn.commit()
        _schema_ensured = True
    except Exception:
        conn.rollback()
        raise


_INSERT_TRAIL = """
INSERT INTO audit.zero_commission_trail (
    module, partner_code, partner_name, mon_period,
    run_id, generated_at, payment_source, pipeline_version,
    conclusion, confidence, caveat_count, caveat_steps,
    step1_activity_ok, step1_record_count,
    step2_rate_ok, step3_expected_ngn,
    step4_payment_found, step4_amount_paid_ngn,
    step5_near_match_found, step6_upstream_complete,
    steps
) VALUES (
    %(module)s, %(partner_code)s, %(partner_name)s, %(mon_period)s,
    %(run_id)s, %(generated_at)s, %(payment_source)s, %(pipeline_version)s,
    %(conclusion)s, %(confidence)s, %(caveat_count)s, %(caveat_steps)s,
    %(step1_activity_ok)s, %(step1_record_count)s,
    %(step2_rate_ok)s, %(step3_expected_ngn)s,
    %(step4_payment_found)s, %(step4_amount_paid_ngn)s,
    %(step5_near_match_found)s, %(step6_upstream_complete)s,
    %(steps)s
)
"""


def _trail_to_row(
    trail: VerificationTrail, run_id: str, generated_at: datetime, module: str,
) -> dict[str, Any]:
    s = {st.step: st for st in trail.steps}

    def _detail(n: int, key: str, default=None):
        st = s.get(n)
        return st.detail.get(key, default) if st else default

    return {
        "module": module,
        "partner_code": trail.partner_code,
        "partner_name": trail.partner_name,
        "mon_period": trail.mon_period,
        "run_id": run_id,
        "generated_at": generated_at,
        "payment_source": trail.payment_source,
        "pipeline_version": trail.pipeline_version,
        "conclusion": trail.conclusion,
        "confidence": trail.confidence,
        "caveat_count": trail.caveat_count,
        "caveat_steps": trail.caveat_steps,
        # Denormalized per-step mirrors.
        "step1_activity_ok": bool(s[1].passed) if 1 in s else None,
        "step1_record_count": _detail(1, "total_activations"),
        "step2_rate_ok": bool(s[2].passed) if 2 in s else None,
        "step3_expected_ngn": _detail(3, "expected_commission_ngn"),
        "step4_payment_found": _detail(4, "payment_found"),
        "step4_amount_paid_ngn": _detail(4, "amount_paid_ngn"),
        "step5_near_match_found": (not s[5].passed) if 5 in s else None,
        "step6_upstream_complete": bool(s[6].passed) if 6 in s else None,
        "steps": json.dumps([st.to_dict() for st in trail.steps]),
    }


def replace_period_trails(
    mon_period: str,
    payment_source: str,
    trails: list[VerificationTrail],
    *,
    module: str = "zero_commission",
    triggered_by: str = "api",
) -> dict[str, Any]:
    """Atomically replace all trails for a (module, period) with a fresh run.

    Delete-then-insert in one transaction so a re-run leaves exactly the
    latest run's rows for that module. Returns run provenance.
    """
    ensure_schema()
    run_id = str(uuid.uuid4())
    started = datetime.now(timezone.utc)
    conn = _get_conn()
    try:
        with conn.cursor() as cur:
            # Ledger row for provenance.
            cur.execute(
                """
                INSERT INTO audit.assurance_run
                    (run_id, module, mon_period, payment_source, trail_count,
                     started_at, triggered_by)
                VALUES (%s, %s, %s, %s, %s, %s, %s)
                """,
                (run_id, module, mon_period, payment_source, len(trails),
                 started, triggered_by),
            )
            # Clear this module's previous trails for the period.
            cur.execute(
                "DELETE FROM audit.zero_commission_trail "
                "WHERE mon_period = %s AND module = %s",
                (mon_period, module),
            )
            # Insert the fresh run.
            for trail in trails:
                cur.execute(_INSERT_TRAIL, _trail_to_row(trail, run_id, started, module))
            # Stamp completion.
            cur.execute(
                "UPDATE audit.assurance_run SET completed_at = %s WHERE run_id = %s",
                (datetime.now(timezone.utc), run_id),
            )
        conn.commit()
    except Exception:
        conn.rollback()
        raise

    return {
        "run_id": run_id,
        "module": module,
        "mon_period": mon_period,
        "payment_source": payment_source,
        "trail_count": len(trails),
        "started_at": started.isoformat(),
    }


# ---------------------------------------------------------------------------
# Query helpers — the evaluation surface.
# ---------------------------------------------------------------------------

def _query(sql: str, params: dict[str, Any]) -> list[dict[str, Any]]:
    conn = _get_conn()
    try:
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            cur.execute(sql, params)
            rows = [dict(r) for r in cur.fetchall()]
        conn.rollback()
        return rows
    except Exception:
        conn.rollback()
        raise


def get_period_trails(mon_period: str, module: str = "zero_commission") -> list[dict[str, Any]]:
    """All trails for a (module, period)."""
    return _query(
        "SELECT * FROM audit.zero_commission_trail "
        "WHERE mon_period = %(p)s AND module = %(m)s "
        "ORDER BY conclusion, partner_code",
        {"p": mon_period, "m": module},
    )


def get_partner_trail(
    partner_code: str, mon_period: str, module: str = "zero_commission",
) -> dict[str, Any] | None:
    rows = _query(
        "SELECT * FROM audit.zero_commission_trail "
        "WHERE partner_code = %(pc)s AND mon_period = %(p)s AND module = %(m)s "
        "ORDER BY generated_at DESC LIMIT 1",
        {"pc": partner_code, "p": mon_period, "m": module},
    )
    return rows[0] if rows else None


def get_trails_with_caveat_step(
    step_name: str, mon_period: str | None = None, module: str = "zero_commission",
) -> list[dict[str, Any]]:
    """Evaluation query: every trail where a given step raised a caveat.

    e.g. ``get_trails_with_caveat_step('upstream_completeness')`` answers
    "show me all trails where step 6 raised a caveat".
    """
    # Use the containment operator (@>) rather than `= ANY(...)` so the GIN
    # index on caveat_steps is usable at scale. The two are logically
    # equivalent, but only @> can drive a Bitmap Index Scan; = ANY() forces
    # a seq scan. Verified against the running DB.
    sql = (
        "SELECT partner_code, partner_name, mon_period, conclusion, confidence, "
        "caveat_steps FROM audit.zero_commission_trail "
        "WHERE caveat_steps @> ARRAY[%(step)s] AND module = %(m)s"
    )
    params: dict[str, Any] = {"step": step_name, "m": module}
    if mon_period:
        sql += " AND mon_period = %(p)s"
        params["p"] = mon_period
    sql += " ORDER BY mon_period, partner_code"
    return _query(sql, params)


def get_conclusion_breakdown(
    mon_period: str, module: str = "zero_commission",
) -> list[dict[str, Any]]:
    """Aggregate: trail counts by (conclusion, confidence) for a module/period."""
    return _query(
        "SELECT conclusion, confidence, COUNT(*) AS n "
        "FROM audit.zero_commission_trail "
        "WHERE mon_period = %(p)s AND module = %(m)s "
        "GROUP BY conclusion, confidence ORDER BY conclusion, confidence",
        {"p": mon_period, "m": module},
    )
