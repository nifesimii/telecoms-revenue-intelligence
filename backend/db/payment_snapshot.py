"""Source-aware payment settlement snapshot for one reporting month.

One snapshot feeds the Payments API, the Overview payment findings and Atlas,
so they cannot disagree. ``config.PAYMENT_SOURCE`` selects the source:

  * ``simulated`` reads ``payment_simulation.csv`` through ``execute_query``
    (KB Section 13).
  * ``apdp`` reads APDP's ``normalized.partner_settlements`` view.

This module is data layer: it holds no SQL (that stays in ``queries.py``) and
never imports the API or assurance layers. An APDP outage raises
:class:`PaymentSourceUnavailable`; the API maps it to HTTP 503.
"""
from __future__ import annotations

import logging
from typing import Any

import pandas as pd
from pydantic import BaseModel

from backend import config
from backend.audit.payment_data import RECON_TO_STATUS
from backend.db.connection import execute_query

logger = logging.getLogger(__name__)


class PaymentSourceUnavailable(RuntimeError):
    """The configured payment source could not be read for this month."""


class PaymentSummaryRecord(BaseModel):
    """One row of the payment dataset for a dealer-month.

    The base fields are populated by every source. The reconciliation fields
    are only populated when ``data_source == "APDP"`` — they're derived from
    ``normalized.partner_settlements`` and let the UI show the richer
    reconciliation state (sales captured vs commissions earned vs paid).
    """

    dealer_id: str
    dealer_name: str
    account_profile_class: str = ""
    report_month: str
    commission_owed: float
    amount_paid: float
    amount_unpaid: float
    payment_status: str
    payment_channel: str
    payment_date: str | None = None
    exception_flag: str | None = None
    data_source: str = "SIMULATED"

    # --- v1.3.0 APDP reconciliation enrichment (None when SIMULATED) ---
    reconciliation_status: str | None = None       # 6-state canonical
    sale_count: int | None = None                   # consumer sales captured
    total_sales_ngn: float | None = None
    statement_gross_revenue_ngn: float | None = None
    payment_variance_ngn: float | None = None       # signed: paid − owed
    paid_count: int | None = None
    partial_count: int | None = None
    disputed_count: int | None = None


class PaymentCoverageResponse(BaseModel):
    """Aggregated coverage payload for ``GET /payments/summary``."""

    period: str
    total_commission_owed: float
    total_amount_paid: float
    total_amount_unpaid: float
    payment_coverage_pct: float
    disputed_count: int
    partially_paid_count: int
    pending_count: int
    fully_paid_count: int
    data_source: str = "SIMULATED"
    records: list[PaymentSummaryRecord]


def row_to_payment_record(row: dict[str, Any]) -> PaymentSummaryRecord:
    """Normalise NaN → None for the nullable string columns before pydantic."""
    cleaned = {}
    for k, v in row.items():
        if isinstance(v, float) and pd.isna(v):
            cleaned[k] = None
        else:
            cleaned[k] = v
    return PaymentSummaryRecord(**cleaned)


# ---------------------------------------------------------------------------
# APDP Postgres → PaymentSummaryRecord adapter
# ---------------------------------------------------------------------------
# The view's reconciliation_status drives payment_status mapping; the rest of
# the record carries the v1.3.0 enrichment fields so the UI can show
# sales-vs-statement-vs-settlement context.


def apdp_row_to_payment_record(row: dict[str, Any]) -> PaymentSummaryRecord:
    owed   = float(row.get("expected_commission_ngn") or 0)
    paid   = float(row.get("total_settled_ngn") or 0)
    unpaid = max(0.0, round(owed - paid, 2))
    recon  = row.get("reconciliation_status") or "RECONCILED"
    dealer = row.get("dealer_id") or ""
    return PaymentSummaryRecord(
        dealer_id             = dealer,
        dealer_name           = dealer,  # APDP view doesn't carry the name
        account_profile_class = "",
        report_month          = row.get("settlement_period") or "",
        commission_owed       = round(owed, 2),
        amount_paid           = round(paid, 2),
        amount_unpaid         = unpaid,
        payment_status        = RECON_TO_STATUS.get(recon, "PENDING"),
        payment_channel       = "",
        payment_date          = None,
        exception_flag        = recon if recon != "RECONCILED" else None,
        data_source           = "APDP",
        reconciliation_status = recon,
        sale_count            = int(row.get("sale_count") or 0),
        total_sales_ngn       = float(row.get("total_sales_ngn") or 0),
        statement_gross_revenue_ngn = float(row.get("statement_gross_revenue_ngn") or 0),
        payment_variance_ngn  = float(row.get("payment_variance_ngn") or 0),
        paid_count            = int(row.get("paid_count") or 0),
        partial_count         = int(row.get("partial_count") or 0),
        disputed_count        = int(row.get("disputed_count") or 0),
    )


def apdp_payment_snapshot(period: str) -> PaymentCoverageResponse:
    """Build the snapshot from APDP partner_settlements rows."""
    from backend.db import apdp as apdp_db  # imported lazily to avoid psycopg2 cost in sample mode
    try:
        raw_rows = apdp_db.get_partner_settlements(period)
    except Exception as e:
        logger.exception("APDP partner_settlements read failed")
        raise PaymentSourceUnavailable(f"APDP unreachable: {e}") from e

    records = [apdp_row_to_payment_record(r) for r in raw_rows]

    total_owed   = round(sum(r.commission_owed for r in records), 2)
    total_paid   = round(sum(r.amount_paid     for r in records), 2)
    total_unpaid = round(sum(r.amount_unpaid   for r in records), 2)
    coverage_pct = round(total_paid / total_owed * 100.0, 1) if total_owed > 0 else 0.0

    status_counts: dict[str, int] = {}
    for r in records:
        status_counts[r.payment_status] = status_counts.get(r.payment_status, 0) + 1

    return PaymentCoverageResponse(
        period                 = period,
        total_commission_owed  = total_owed,
        total_amount_paid      = total_paid,
        total_amount_unpaid    = total_unpaid,
        payment_coverage_pct   = coverage_pct,
        disputed_count         = status_counts.get("DISPUTED", 0),
        partially_paid_count   = status_counts.get("PARTIALLY_PAID", 0),
        pending_count          = status_counts.get("PENDING", 0),
        fully_paid_count       = status_counts.get("FULLY_PAID", 0),
        data_source            = "APDP",
        records                = records,
    )


def load_payment_snapshot(period: str) -> PaymentCoverageResponse:
    """Payment status across all dealers for ``period`` from the configured source."""
    if config.PAYMENT_SOURCE == "apdp":
        return apdp_payment_snapshot(period)

    df = execute_query("get_payment_summary", {"mon_period": period})

    records = [row_to_payment_record(row) for row in df.to_dict(orient="records")]

    total_owed = float(df["commission_owed"].astype(float).sum()) if not df.empty else 0.0
    total_paid = float(df["amount_paid"].astype(float).sum()) if not df.empty else 0.0
    total_unpaid = (
        float(df["amount_unpaid"].astype(float).sum()) if not df.empty else 0.0
    )
    coverage_pct = (
        round(total_paid / total_owed * 100.0, 1) if total_owed > 0 else 0.0
    )

    status_counts = (
        df["payment_status"].value_counts().to_dict() if not df.empty else {}
    )

    return PaymentCoverageResponse(
        period=period,
        total_commission_owed=round(total_owed, 2),
        total_amount_paid=round(total_paid, 2),
        total_amount_unpaid=round(total_unpaid, 2),
        payment_coverage_pct=coverage_pct,
        disputed_count=int(status_counts.get("DISPUTED", 0)),
        partially_paid_count=int(status_counts.get("PARTIALLY_PAID", 0)),
        pending_count=int(status_counts.get("PENDING", 0)),
        fully_paid_count=int(status_counts.get("FULLY_PAID", 0)),
        data_source="SIMULATED",
        records=records,
    )
