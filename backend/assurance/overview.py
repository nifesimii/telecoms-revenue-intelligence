"""Complete assurance aggregation; pagination is applied only at the HTTP edge.

No SQL or new business rules: findings come from the registered services;
payment findings use the same source-aware settlement snapshot as Payments.
``overview_snapshot`` is the one entry point shared by ``GET /assurance/overview``
and Atlas (``investigation_priority_evidence`` for one dealer,
``investigation_queue_evidence`` for the month), so all see the same queue.
"""
from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timezone
from decimal import Decimal

from backend.assurance.registry import ASSURANCE_REGISTRY, is_implemented
from backend.assurance.payment_assurance import classify_payment_status

logger = logging.getLogger(__name__)
SEVERITY_ORDER = {"HIGH": 0, "MEDIUM": 1, "LOW": 2}
UNCHECKED_STATUSES = {"UNAVAILABLE", "NOT_IMPLEMENTED", "NO_DATA"}
INVESTIGATION_QUEUE_SOURCE = "Investigation queue"
INVESTIGATION_QUEUE_TOOL = "investigation_queue"


class UnknownOverviewPeriod(LookupError):
    """The reporting month has no data, so no assessment can be made."""


async def overview_snapshot(period, module=None, severity=None):
    """Return ``collect_overview`` for ``period`` using the shared payment snapshot.

    An unknown period raises :class:`UnknownOverviewPeriod` (never an all-clear).
    A payment-source failure leaves ``payment=None`` so the module reports
    UNAVAILABLE while the other checks still run.
    """
    from backend.db import queries
    from backend.db.payment_snapshot import load_payment_snapshot

    if period not in queries.get_available_periods():
        raise UnknownOverviewPeriod(period)
    try:
        payment = load_payment_snapshot(period)
    except Exception:
        logger.exception("Overview payment source unavailable")
        payment = None
    return await collect_overview(period, payment, module, severity)


async def collect_overview(period, payment, selected_module=None, selected_severity=None):
    """Return full findings internally; never return these unbounded to the UI."""
    findings, modules = [], []
    for name, service in ASSURANCE_REGISTRY.items():
        module = {"module": name, "status": "UNAVAILABLE", "finding_count": 0,
                  "affected_dealers": 0, "high_count": 0, "medium_count": 0,
                  "low_count": 0, "missing_invoice_count": 0}
        try:
            if name == "payment":
                if payment is None:
                    modules.append(module)
                    continue
                rows = []
                for record in payment.records:
                    if record.payment_status == "FULLY_PAID":
                        continue
                    severity, kind = classify_payment_status(record.payment_status)
                    rows.append({
                        "dealer_id": record.dealer_id, "dealer_name": record.dealer_name,
                        "severity": severity, "type": kind,
                        "description": f"NGN {record.amount_unpaid:,.2f} outstanding · "
                                       f"{record.payment_status.replace('_', ' ').lower()}",
                        "recommended_action": "Compare entitlement with settlement evidence.",
                    })
                module["status"] = "FLAG" if rows else "PASS"
                if not payment.records:
                    module["status"] = "NO_DATA"
            else:
                result = await service.run(period)
                module["status"] = result.status if is_implemented(service) else "NOT_IMPLEMENTED"
                module["missing_invoice_count"] = int(result.metadata.get("no_invoice_record_count", 0))
                rows = result.findings or []
            for row in rows:
                findings.append({**row, "module": name})
            module["finding_count"] = len(rows)
            module["affected_dealers"] = len({r["dealer_id"] for r in rows})
            for severity in SEVERITY_ORDER:
                module[f"{severity.lower()}_count"] = sum(r["severity"] == severity for r in rows)
        except Exception:
            logger.exception("Overview module unavailable: %s", name)
            module["status"] = "UNAVAILABLE"
        modules.append(module)

    full_queue = rank_dealers(findings, payment)
    selected = [f for f in findings if
                (not selected_module or f["module"] == selected_module)
                and (not selected_severity or f["severity"] == selected_severity)]
    return {
        "period": period,
        "checked_at": datetime.now(timezone.utc).isoformat(),
        "complete": all(m["status"] not in UNCHECKED_STATUSES for m in modules),
        "modules": modules, "finding_count": len(findings),
        "affected_dealers": len(full_queue),
        "cross_module_dealers": sum(len(r["modules"]) > 1 for r in full_queue),
        "payment": ({**payment.model_dump(exclude={"records"}),
                     "record_count": len(payment.records)} if payment else None),
    }, rank_dealers(selected, payment), findings


def rank_dealers(findings, payment):
    """Group matching findings before ranking; one evidence subject per module."""
    payments = {r.dealer_id: r for r in payment.records} if payment else {}
    dealers = {}
    # The leading finding is the most severe; payment evidence breaks ties.
    ordered = sorted(findings, key=lambda f: (SEVERITY_ORDER.get(f["severity"], 3),
                                f["module"] != "payment", f["dealer_id"],
                                f["type"], f["description"]))
    for finding in ordered:
        code = finding["dealer_id"]
        if code not in dealers:
            record = payments.get(code)
            dealers[code] = {
                "dealer_id": code, "dealer_name": finding["dealer_name"],
                "severity": finding["severity"], "lead_finding": finding,
                "modules": [], "finding_count": 0,
                "module_findings": {},
                "amount_outstanding": record.amount_unpaid if record else None,
                "payment_status": record.payment_status if record else None,
            }
        row = dealers[code]
        if row["dealer_name"] == code and finding["dealer_name"] != code:
            row["dealer_name"] = finding["dealer_name"]
        row["finding_count"] += 1
        if finding["module"] not in row["modules"]:
            row["modules"].append(finding["module"])
            row["module_findings"][finding["module"]] = finding
    return sorted(dealers.values(), key=lambda r: (
        SEVERITY_ORDER.get(r["severity"], 3),
        -(r["amount_outstanding"] or 0), r["dealer_id"]))


def _unavailable(period, note, payload="priority"):
    return {"period": period, "status": "unavailable",
            "source": INVESTIGATION_QUEUE_SOURCE, "tool": INVESTIGATION_QUEUE_TOOL,
            "total": None, "truncated": False, "total_rows": 0, "note": note,
            "rows": [], payload: None}


def _finding_summary(finding):
    return {"module": finding["module"], "severity": finding["severity"],
            "type": finding["type"], "description": finding["description"]}


def _read_queue(period):
    """The full unfiltered queue, or the note that makes it unavailable.

    Returns ``(note, queue, statuses, unchecked)``; ``note`` is ``None`` when
    the queue can be read. An unknown month, an overview failure or no checked
    module is missing evidence, never an empty queue.
    """
    try:
        summary, queue, _ = asyncio.run(overview_snapshot(period))
    except UnknownOverviewPeriod:
        return (f"The investigation queue is unavailable for {period}: "
                "no data is recorded for this month."), None, None, None
    except Exception:
        logger.exception("Investigation queue unavailable: %s", period)
        return (f"The investigation queue is unavailable for {period}: "
                "the overview could not be computed."), None, None, None
    statuses = {m["module"]: m["status"] for m in summary["modules"]}
    unchecked = [name for name, status in statuses.items() if status in UNCHECKED_STATUSES]
    if len(unchecked) == len(statuses):
        # No module ran, so an empty queue is missing evidence, not a clear result.
        return (f"The investigation queue is unavailable for {period}: "
                "no assurance module could be checked."), None, None, None
    return None, queue, statuses, unchecked


def investigation_priority_evidence(period: str, dealer_id: str | None) -> dict:
    """One dealer's place in the Overview investigation queue for ``period``.

    Synchronous; safe to call from a worker thread (uses ``asyncio.run``).
    Values are read unchanged from ``collect_overview``/``rank_dealers``:
    no thresholds or judgement are added here. Missing data is reported as
    unavailable, never as "not in queue" or a low priority.
    """
    if dealer_id is None:
        return _unavailable(period, "Investigation priority needs a dealer account; select or name one.")
    note, queue, statuses, unchecked = _read_queue(period)
    if note:
        return _unavailable(period, note)
    code = str(dealer_id)
    rank, entry = next(((i, r) for i, r in enumerate(queue, 1) if r["dealer_id"] == code),
                       (None, None))
    findings, rows = [], []
    if entry:
        lead = entry["lead_finding"]
        ordered = [lead["module"]] + [m for m in entry["modules"] if m != lead["module"]]
        for module in ordered:
            finding = _finding_summary(entry["module_findings"][module])
            findings.append(finding)
            rows.append({"dealer_id": code, "dealer_name": entry["dealer_name"],
                         "dimension": f"{module.capitalize()} · {finding['type']}",
                         "value": f"{finding['severity']}: {finding['description']}"})
    commission = entry["module_findings"].get("commission") if entry else None
    return {
        "period": period, "status": "available",
        "source": INVESTIGATION_QUEUE_SOURCE, "tool": INVESTIGATION_QUEUE_TOOL,
        "total": None, "truncated": False, "total_rows": len(rows), "note": "",
        "rows": rows,
        "priority": {
            "in_queue": entry is not None,
            "severity": entry["severity"] if entry else None,
            "rank": rank,
            "queue_size": len(queue),
            "lead_module": entry["lead_finding"]["module"] if entry else None,
            "lead_type": entry["lead_finding"]["type"] if entry else None,
            "findings": findings,
            "finding_count": entry["finding_count"] if entry else 0,
            "commission": _finding_summary(commission) if commission else None,
            "commission_module_status": statuses.get("commission", "UNAVAILABLE"),
            "unchecked_modules": unchecked,
            "payment_status": entry["payment_status"] if entry else None,
            "amount_outstanding": entry["amount_outstanding"] if entry else None,
        },
    }


QUEUE_DEFAULT_LIMIT = 10
QUEUE_MAX_LIMIT = 100


def investigation_queue_evidence(period: str, dealer_id: str | None = None, *, severity: str | None = None,
                                 modules=(), limit: int = QUEUE_DEFAULT_LIMIT) -> dict:
    """The month's whole investigation queue, filtered and bounded for Atlas.

    The queue is the same full, unfiltered ranking ``investigation_priority``
    and the Overview screen read. ``severity`` keeps dealers whose overall
    severity matches; ``modules`` keeps dealers with findings in every listed
    module. Filters never re-rank: each listed dealer keeps its full-queue rank.
    At most ``limit`` dealers are listed; counts and the outstanding total cover
    every matching dealer (only dealers with a payment record have an amount).
    """
    if dealer_id is not None:
        raise ValueError("The investigation queue covers all dealers; use investigation_priority for one")
    modules = list(modules)
    if not 1 <= limit <= QUEUE_MAX_LIMIT:
        raise ValueError("Queue limit must be between 1 and 100")
    note, queue, _, unchecked = _read_queue(period)
    if note:
        return _unavailable(period, note, "queue")
    matching = [(rank, entry) for rank, entry in enumerate(queue, 1)
                if (severity is None or entry["severity"] == severity)
                and set(modules) <= set(entry["modules"])]
    payment_checked = "payment" not in unchecked
    with_payment = [entry["amount_outstanding"] for _, entry in matching
                    if entry["amount_outstanding"] is not None]
    dealers = [{"rank": rank, "dealer_id": entry["dealer_id"], "dealer_name": entry["dealer_name"],
                "severity": entry["severity"], "lead_module": entry["lead_finding"]["module"],
                "lead_type": entry["lead_finding"]["type"], "modules": list(entry["modules"]),
                "amount_outstanding": entry["amount_outstanding"]}
               for rank, entry in matching[:limit]]
    rows = [{"dealer_id": d["dealer_id"], "dealer_name": d["dealer_name"], "dimension": f"Rank {d['rank']}",
             "value": f"{d['severity']}: {d['lead_module'].capitalize()} · {d['lead_type']}"}
            for d in dealers]
    outstanding = sum((Decimal(str(value)) for value in with_payment), Decimal("0"))
    return {
        "period": period, "status": "available",
        "source": INVESTIGATION_QUEUE_SOURCE, "tool": INVESTIGATION_QUEUE_TOOL,
        "total": None, "note": "", "truncated": len(matching) > len(dealers),
        "total_rows": len(rows), "rows": rows,
        "queue": {
            "severity": severity, "modules": modules, "limit": limit,
            "queue_size": len(queue), "match_count": len(matching),
            # Dealers without a payment record add nothing; an unchecked payment module has no total.
            "outstanding_ngn": float(outstanding.quantize(Decimal("0.01"))) if payment_checked else None,
            "payment_dealer_count": len(with_payment) if payment_checked else None,
            "unchecked_modules": unchecked, "dealers": dealers,
        },
    }
