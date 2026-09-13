"""Complete assurance aggregation; pagination is applied only at the HTTP edge.

No SQL or new business rules: findings come from the registered services;
payment findings use the same source-aware settlement snapshot as Payments.
"""
from __future__ import annotations

import logging
from datetime import datetime, timezone

from backend.assurance.registry import ASSURANCE_REGISTRY, is_implemented
from backend.assurance.payment_assurance import classify_payment_status

logger = logging.getLogger(__name__)
SEVERITY_ORDER = {"HIGH": 0, "MEDIUM": 1, "LOW": 2}


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
        "complete": all(m["status"] not in {"UNAVAILABLE", "NOT_IMPLEMENTED", "NO_DATA"} for m in modules),
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
