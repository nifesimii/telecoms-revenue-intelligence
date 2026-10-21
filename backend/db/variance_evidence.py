"""Atlas evidence for one dealer's commission change between two months.

Projects the ``get_month_on_month_variance`` query (activation count and
commission per product denomination, per month) into the evidence contract.
Read-only.

The change per product is the query's later-month total minus its
earlier-month total, both read from the same result. The query's own
``delta_ngn`` column is not used: it sits only on later-month rows, so a
product sold in the earlier month but not the later one would drop out of
the change.

An unknown month or an unreadable source is *unavailable*; a dealer with no
activation records in either month is *no recorded activity*. A product
absent from one recorded month has no activations there, which is stated.
"""
from __future__ import annotations

import logging
from typing import Any

from backend.db.connection import execute_query

logger = logging.getLogger(__name__)

VARIANCE_SOURCE = "Activation commission records"
VARIANCE_TOOL = "get_month_on_month_variance"


def _unavailable(period: str, note: str) -> dict[str, Any]:
    return {"period": period, "status": "unavailable", "source": VARIANCE_SOURCE,
            "tool": VARIANCE_TOOL, "total": None, "truncated": False, "total_rows": 0,
            "note": note, "rows": [], "variance": None}


def _ngn(value: float) -> str:
    return f"NGN {value:,.2f}"


def _month(frame, period: str) -> dict[str, tuple[int, float]]:
    rows = frame[frame["period"].astype(str) == period]
    return {str(r["product_denomination"]): (int(r["activation_count"]), round(float(r["total_commission_ngn"]), 2))
            for _, r in rows.iterrows()}


def commission_variance_evidence(earlier: str, later: str, dealer_id: str | None) -> dict[str, Any]:
    """Commission and activations per product in ``earlier`` and ``later``, and the change."""
    if dealer_id is None:
        return _unavailable(later, "a dealer account is needed; select or name one.")
    from backend.db import queries

    try:
        known = set(queries.get_available_periods())
    except Exception:
        logger.exception("Variance periods unavailable")
        return _unavailable(later, "the recorded months could not be read.")
    unknown = [period for period in (earlier, later) if period not in known]
    if unknown:
        return _unavailable(later, f"no data is recorded for {' or '.join(unknown)}.")
    code = str(dealer_id).strip()
    try:
        frame = execute_query(VARIANCE_TOOL, {"distributor_code": code, "current_period": later,
                                              "prior_period": earlier})
    except Exception:
        logger.exception("Variance unavailable: %s %s %s", code, earlier, later)
        return _unavailable(later, "the activation commission records could not be read.")

    base = {"period": later, "status": "available", "source": VARIANCE_SOURCE,
            "tool": VARIANCE_TOOL, "total": None, "truncated": False, "note": ""}
    if frame.empty:
        return {**base, "total_rows": 0, "rows": [],
                "variance": {"found": False, "earlier": earlier, "later": later}}

    before, after = _month(frame, earlier), _month(frame, later)
    products = []
    for product in sorted(set(before) | set(after)):
        (count_a, amount_a), (count_b, amount_b) = before.get(product, (0, 0.0)), after.get(product, (0, 0.0))
        products.append({"product": product, "earlier_activations": count_a, "earlier_ngn": amount_a,
                         "later_activations": count_b, "later_ngn": amount_b,
                         "change_ngn": round(amount_b - amount_a, 2)})
    totals = {"earlier_activations": sum(p["earlier_activations"] for p in products),
              "earlier_ngn": round(sum(p["earlier_ngn"] for p in products), 2),
              "later_activations": sum(p["later_activations"] for p in products),
              "later_ngn": round(sum(p["later_ngn"] for p in products), 2)}
    totals["change_ngn"] = round(totals["later_ngn"] - totals["earlier_ngn"], 2)
    variance = {"found": True, "earlier": earlier, "later": later,
                "earlier_recorded": bool(before), "later_recorded": bool(after),
                "products": products, "totals": totals}
    rows = [{"dealer_id": code, "dimension": f"{p['product']} · change {earlier} to {later}",
             "value": _ngn(p["change_ngn"])} for p in products]
    rows.append({"dealer_id": code, "dimension": f"Total · change {earlier} to {later}",
                 "value": _ngn(totals["change_ngn"])})
    return {**base, "total_rows": len(rows), "rows": rows, "variance": variance}
