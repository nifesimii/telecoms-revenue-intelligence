"""One dealer-month's audit verdicts for Atlas: read-only, never persisted.

For each registered audit module, the evidence is the trail the Audit
Trails tab would show: the latest *saved* trail when that module has a
saved run for the month (``backend.db.audit_store``, run timestamp stated).
When it has none, or the audit store cannot be read, the module's own
``run_dealer`` builds this one dealer's trails in memory ("checked on
request"). ``run_dealer`` shares its ``run_period``'s subject selection, so
the result equals that dealer's trail in a full run. Nothing is written. A module that cannot be checked either way is unavailable — never
a pass. A dealer that is not one of a module's subjects (e.g. no
zero-commission records) is "no subject", distinct from unavailable.

Step text is copied from the trails unchanged; this module adds no
thresholds, rules or recalculation.
"""
from __future__ import annotations

import logging
import re
from collections import Counter
from datetime import datetime, timezone
from typing import Any

from backend import config
from backend.audit import (
    eligibility_window_audit,
    inventory_mismatch_audit,
    payment_reconciliation_audit,
    zero_commission_audit,
)
from backend.audit.trail import INSUFFICIENT_DATA

logger = logging.getLogger(__name__)

VERIFICATION_SOURCE = "Audit trails"
VERIFICATION_TOOL = "audit_trails"
MAX_TRAILS = 5          # trails shown per module; counts always cover every subject

# Answer order: "was the dealer paid correctly" first.
_ORDER = ("payment_reconciliation", "zero_commission", "eligibility_window", "inventory_mismatch")
# Which subjects each module's run_period audits (for "no subject" answers).
_SUBJECTS = {
    "payment_reconciliation": "dealers with activations in the month",
    "zero_commission": "dealers with zero-commission records in the month",
    "eligibility_window": "dealers with zero-commission records in the month",
    "inventory_mismatch": "dealer products flagged for activations exceeding invoiced purchases",
}
# Steps whose recorded result is the key evidence for each module's conclusion.
# Any step that did not pass is shown as well.
_KEY_STEPS = {
    "payment_reconciliation": {"expected_commission", "payment_record_search", "amount_comparison"},
    "zero_commission": {"applicable_rate", "expected_commission", "payment_record_search"},
    "eligibility_window": {"zero_commission_records_present", "classify_against_window",
                           "root_cause_attribution"},
    "inventory_mismatch": {"mismatch_signal", "purchase_record_lookup", "allocation_calculation"},
}
_PAYMENT_MODULES = {"payment_reconciliation", "zero_commission"}
_INSUFFICIENT_SORTS_LAST = INSUFFICIENT_DATA   # shown trails list unverified subjects after verdicts
# Recorded trail text that names non-authentic evidence is withheld from answers.
_WITHHELD_WORDING = re.compile(r"synthetic|simulated|sample|demo", re.IGNORECASE)


class _NoSavedRun(LookupError):
    """No saved run for this module and month includes this dealer as a subject."""


# ── Per-dealer, in-memory trails: each module's own run_dealer ────────────
# run_dealer selects subjects with the same code as the module's run_period,
# so the trails equal that dealer's slice of a full run. Never persisted.

def _summary_row(period: str, dealer_id: str) -> dict | None:
    """The dealer's summary row, used only to tell an unknown dealer apart."""
    from backend.db.connection import execute_query
    df = execute_query("get_dealer_summary", {"mon_period": period, "distributor_code": dealer_id})
    return None if df is None or df.empty else df.iloc[0].to_dict()


_ON_REQUEST = {
    "zero_commission": zero_commission_audit.run_dealer,
    "eligibility_window": eligibility_window_audit.run_dealer,
    "payment_reconciliation": payment_reconciliation_audit.run_dealer,
    "inventory_mismatch": inventory_mismatch_audit.run_dealer,
}


# ── Saved trails (the Audit Trails tab's store) ───────────────────────────

def _saved_trails(module: str, period: str, dealer_id: str):
    """(this dealer's trails in the LATEST saved run, that run's timestamp).

    Raises _NoSavedRun when the module has no saved run for the month, or
    when the dealer is not a subject of the latest one (the caller then
    checks on request rather than stamping "no subject" with that run).
    """
    from backend.db import audit_store
    rows = audit_store.get_period_trails(period, module)
    if not rows:
        raise _NoSavedRun(module)
    run_at = max(row["generated_at"] for row in rows)
    latest = next(row for row in rows if row["generated_at"] == run_at)
    run = latest.get("run_id")
    in_run = [row for row in rows
              if (row.get("run_id") == run if run is not None else row["generated_at"] == run_at)]
    mine = [row for row in in_run if str(row["partner_code"]).split(":")[0] == dealer_id]
    if not mine:
        raise _NoSavedRun(module)
    return mine, run_at


def _stamp(value: datetime) -> str:
    if value.tzinfo is not None:
        value = value.astimezone(timezone.utc)
    return value.strftime("%Y-%m-%d %H:%M UTC")


# ── Payload shaping ───────────────────────────────────────────────────────

def _withheld(text: Any) -> bool:
    return isinstance(text, str) and bool(_WITHHELD_WORDING.search(text))


def _shown(module: str, text: Any) -> str | None:
    if not isinstance(text, str) or not text.strip() or _withheld(text):
        return None
    if module == "eligibility_window":
        # Same display qualification as the Audit Trails tab (db.audit_workspace.detail):
        # being inside the window alone does not establish entitlement.
        text = text.replace("should have earned commission", "other eligibility checks required")
    return text


def _trail_summary(module: str, trail: dict) -> dict:
    steps = sorted(trail.get("steps") or [], key=lambda s: int(s["step"]))
    keys = _KEY_STEPS.get(module, set())
    evidence = [{"step": int(s["step"]), "name": str(s["name"]).replace("_", " "),
                 "result": _shown(module, s.get("result"))}
                for s in steps if s["name"] in keys or not s.get("passed")]
    code = str(trail["partner_code"])
    shown_steps = [s for s in steps if s["name"] in keys or not s.get("passed")]
    withheld = (sum(_withheld(s.get("result")) for s in shown_steps)
                + sum(_withheld(s.get("caveat")) for s in steps))
    summary = {
        "subject": code,
        "product_code": code.split(":", 1)[1] if ":" in code else None,
        "conclusion": trail["conclusion"],
        "confidence": trail["confidence"],
        "evidence": [line for line in evidence if line["result"]],
        "caveats": [c for c in (_shown(module, s.get("caveat")) for s in steps) if c],
        # Inventory comparison scenarios disclose that they are not authentic records.
        "limited": any(s["detail"].get("scenario_id") for s in steps if isinstance(s.get("detail"), dict)),
        # Recorded text withheld above, disclosed as a count so evidence is never silently shortened.
        "withheld": withheld,
    }
    if module == "eligibility_window":
        details = {step["name"]: step["detail"] if isinstance(step.get("detail"), dict) else {}
                   for step in steps}
        fields = {
            "total": ("zero_commission_records_present", "zero_commission_count"),
            "unknown": ("fetch_dates", "without_dates_count"),
            "inside": ("classify_against_window", "inside_window_count"),
            "outside": ("classify_against_window", "outside_window_count"),
            "future": ("classify_against_window", "future_dated_count"),
            "window_days": ("classify_against_window", "window_days"),
        }
        counts = {key: details.get(step, {}).get(field) for key, (step, field) in fields.items()}
        # Old saved trails may lack structured detail. Never recover counts from prose.
        if (all(isinstance(value, int) and not isinstance(value, bool) and value >= 0
                for value in counts.values())
                and counts["total"] == sum(counts[key] for key in ("inside", "outside", "future", "unknown"))):
            summary["eligibility_counts"] = counts
    return summary


def _module_payload(module, label, status, basis, run_at, trails, note=None, payment_source=None):
    trails = sorted(trails, key=lambda t: (t["conclusion"] == _INSUFFICIENT_SORTS_LAST, str(t["partner_code"])))
    counts = Counter(t["conclusion"] for t in trails)
    caveats = []
    if (basis == "saved" and module in _PAYMENT_MODULES and payment_source
            and payment_source != config.PAYMENT_SOURCE):
        caveats.append("The saved run used a different payment source from the current setting.")
    return {
        "module": module, "label": label, "status": status, "basis": basis,
        "run_at": _stamp(run_at) if run_at is not None else None,
        "subjects": _SUBJECTS.get(module, "its flagged subjects"),
        "subject_count": len(trails),
        "conclusions": [{"conclusion": c, "count": n} for c, n in sorted(counts.items())],
        "trails": [_trail_summary(module, t) for t in trails[:MAX_TRAILS]],
        "caveats": caveats, "note": note,
    }


def _module_evidence(module, period: str, dealer_id: str, store_ok: bool) -> dict:
    if store_ok:
        try:
            trails, run_at = _saved_trails(module.name, period, dealer_id)
            source = next((t.get("payment_source") for t in trails), None)
            return _module_payload(module.name, module.label, "verified" if trails else "no_subject",
                                   "saved", run_at, trails, payment_source=source)
        except _NoSavedRun:
            pass
        except Exception:
            logger.exception("Saved audit trails unreadable: %s %s", module.name, period)
    build = _ON_REQUEST.get(module.name)
    if build is None:
        return _module_payload(module.name, module.label, "unavailable", None, None, [],
                               note="this audit has no single-dealer check and no saved run for the month.")
    try:
        trails = [t.to_dict() for t in build(period, dealer_id, config.PAYMENT_SOURCE)]
    except Exception:
        logger.exception("Audit check failed: %s %s %s", module.name, period, dealer_id)
        return _module_payload(module.name, module.label, "unavailable", None, None, [],
                               note="the audit could not be run for this dealer and month.")
    return _module_payload(module.name, module.label, "verified" if trails else "no_subject",
                           "on_request", None, trails)


def _unavailable(period: str, note: str) -> dict:
    return {"period": period, "status": "unavailable", "source": VERIFICATION_SOURCE,
            "tool": VERIFICATION_TOOL, "total": None, "truncated": False, "total_rows": 0,
            "note": note, "rows": [], "verification": None}


def verification_outcome_evidence(period: str, dealer_id: str | None, *, focus: str | None = None) -> dict:
    """Every registered audit module's verdict for one dealer-month (read-only)."""
    if focus not in (None, "eligibility_window"):
        raise ValueError("Unsupported verification focus")
    if dealer_id is None:
        return _unavailable(period, "Verification needs a dealer account; select or name one.")
    from backend.db import queries
    try:
        known = queries.get_available_periods()
    except Exception:
        logger.exception("Available periods unreadable")
        return _unavailable(period, f"Audit verification is unavailable for {period}: "
                                    "the reporting months could not be read.")
    if period not in known:
        return _unavailable(period, f"Audit verification is unavailable for {period}: "
                                    "no data is recorded for this month.")
    dealer = str(dealer_id).strip()
    try:
        recorded = _summary_row(period, dealer) is not None
    except Exception:
        logger.exception("Dealer summary unreadable: %s %s", period, dealer)
        recorded = True   # unknown, not absent: let each module answer or be unavailable
    if not recorded:
        return {"period": period, "status": "available", "source": VERIFICATION_SOURCE,
                "tool": VERIFICATION_TOOL, "total": None, "truncated": False, "total_rows": 0,
                "note": "", "rows": [], "verification": {"found": False}}
    from backend.audit.base import list_modules
    from backend.db import audit_store
    store_ok = audit_store.healthcheck()
    rank = {name: i for i, name in enumerate(_ORDER)}
    modules = sorted(list_modules(), key=lambda m: (rank.get(m.name, len(rank)), m.name))
    if focus:
        modules = [module for module in modules if module.name == focus]
    results = [_module_evidence(module, period, dealer, store_ok) for module in modules]
    if all(m["status"] == "unavailable" for m in results):
        return _unavailable(period, f"Audit verification is unavailable for {period}: "
                                    "no audit module could be checked.")
    rows = []
    for m in results:
        if m["status"] == "verified":
            value = ", ".join(f"{c['conclusion']} {c['count']}" for c in m["conclusions"])
        else:
            value = "no subject" if m["status"] == "no_subject" else "unavailable"
        rows.append({"dealer_id": dealer, "dimension": m["label"], "value": value})
    return {"period": period, "status": "available", "source": VERIFICATION_SOURCE,
            "tool": VERIFICATION_TOOL, "total": None, "truncated": False,
            "total_rows": len(rows), "note": "", "rows": rows,
            "verification": {"found": True, "modules": results}}
