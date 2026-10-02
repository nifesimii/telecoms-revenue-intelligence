"""Render requested measures from application-owned evidence, without model prose."""
from __future__ import annotations

from decimal import Decimal
from html import escape
import re

from backend.assurance.overview import SEVERITY_ORDER, UNCHECKED_STATUSES as _UNCHECKED_STATUSES
from backend.audit.trail import CONCLUSIONS, CONFIDENCES, INSUFFICIENT_DATA as _INSUFFICIENT

_MAX_RENDERED_ROWS = 100
_MAX_AUDIT_CAVEATS = 3
_PRIORITY_SEVERITIES = set(SEVERITY_ORDER)
_FINDING_FIELDS = ("severity", "type", "description")


def _text(value: object) -> str:
    text = escape(str(value), quote=False).replace("\n", " ").replace("\r", " ")
    return re.sub(r"([\\`*_{}\[\]()#+.!|>~-])", r"\\\1", text)


def _number(value: object, unit: str) -> str:
    amount = Decimal(str(value))
    if unit == "ngn":
        return f"NGN {amount:,.2f}"
    return f"{amount:,f}".rstrip("0").rstrip(".") if amount % 1 else f"{amount:,.0f}"


def _is_count(value: object) -> bool:
    return isinstance(value, int) and not isinstance(value, bool) and value >= 0


def _validate_finding(finding: object, fields: tuple[str, ...]) -> None:
    if not isinstance(finding, dict) or any(not isinstance(finding.get(key), str) for key in fields):
        raise ValueError("Priority findings require text fields")
    if finding["severity"] not in _PRIORITY_SEVERITIES:
        raise ValueError("Unsupported finding severity")


def _validate_priority(period: dict) -> None:
    """Queue evidence is copied from the Overview computation; reject malformed shapes."""
    try:
        _check_priority(period)
    except (KeyError, TypeError) as exc:
        raise ValueError("Incomplete investigation priority evidence") from exc


def _check_priority(period: dict) -> None:
    priority = period.get("priority")
    if period["status"] == "unavailable":
        if priority is not None:
            raise ValueError("Unavailable priority evidence cannot carry a priority")
        return
    if not isinstance(priority, dict) or not isinstance(priority.get("in_queue"), bool):
        raise ValueError("Available priority evidence requires a priority")
    findings, count, size = priority["findings"], priority["finding_count"], priority["queue_size"]
    if not isinstance(findings, list) or not _is_count(count) or not _is_count(size) or count < len(findings):
        raise ValueError("Priority counts are inconsistent")
    for finding in findings:
        _validate_finding(finding, ("module", *_FINDING_FIELDS))
    if priority.get("commission") is not None:
        _validate_finding(priority["commission"], _FINDING_FIELDS)
    unchecked = priority.get("unchecked_modules", [])
    if not isinstance(unchecked, list) or any(not isinstance(module, str) for module in unchecked):
        raise ValueError("Unchecked modules must be a list of names")
    if not isinstance(priority.get("commission_module_status", ""), str):
        raise ValueError("Commission module status must be text")
    rank = priority["rank"]
    if priority["in_queue"]:
        if (priority["severity"] not in _PRIORITY_SEVERITIES or not _is_count(rank) or not 1 <= rank <= size
                or not findings or any(not isinstance(priority.get(key), str) for key in ("lead_module", "lead_type"))):
            raise ValueError("Queued priority requires severity, rank and findings")
    elif priority["severity"] is not None or rank is not None or findings:
        raise ValueError("A dealer outside the queue has no priority")


def _validate(request: dict, evidence: dict) -> None:
    requested = request["measures"]
    received = [m["measure"] for m in evidence["measures"]]
    if len(received) != len(set(received)) or set(received) != set(requested):
        raise ValueError("Evidence measures must match the request exactly")
    periods = request["periods"]
    if len(periods) != len(set(periods)) or evidence["requested_periods"] != periods:
        raise ValueError("Evidence requested periods do not match")
    dealer = request.get("dealer_id")
    if evidence.get("dealer_id") != dealer:
        raise ValueError("Evidence dealer does not match")
    for measure in evidence["measures"]:
        if measure["unit"] not in {"count", "ngn", "text"}:
            raise ValueError("Unsupported measure unit")
        if measure.get("aggregation", "sum") not in {"sum", "snapshot", "none"}:
            raise ValueError("Unsupported measure aggregation")
        seen = set()
        for period in measure["periods"]:
            key = period["period"]
            if key not in periods or key in seen:
                raise ValueError("Evidence period outside request or repeated")
            seen.add(key)
            if period["status"] not in {"available", "unavailable"}:
                raise ValueError("Unsupported evidence status")
            for name, (payload, validate, _) in _DEALER_MONTH.items():
                if name == measure["measure"]:
                    validate(period)
                elif payload in period:
                    raise ValueError(f"{payload} evidence belongs to the {name} measure")
            for row in period["rows"]:
                if dealer is not None and row.get("dealer_id") != dealer:
                    raise ValueError("Evidence row belongs to a different dealer")
            values = [period.get("total"), *(row.get("value") for row in period["rows"])]
            for value in values:
                if value is None:
                    continue
                if measure["unit"] == "text":
                    if not isinstance(value, str):
                        raise ValueError("Text measure value must be a string")
                    continue
                if isinstance(value, bool) or not isinstance(value, (int, float, Decimal)):
                    raise ValueError("Measure value must be numeric")
                if not Decimal(str(value)).is_finite():
                    raise ValueError("Measure value must be finite")

    explanations = evidence.get("explanations", [])
    if explanations and (request.get("operation") != "explain" or not dealer or not set(requested).intersection({
        "activation_commission", "zero_commission_count", "activation_unqualified_count"
    })):
        raise ValueError("Explanation records require a scoped activation explanation")
    for explanation in explanations:
        if explanation["period"] not in periods or explanation["dealer_id"] != dealer:
            raise ValueError("Explanation evidence is outside the requested scope")
        if explanation["status"] not in {"available", "unavailable"}:
            raise ValueError("Unsupported explanation evidence status")
        counts = [explanation.get(key) for key in ("records_checked", "records_with_dates", "total_records")]
        if any(isinstance(value, bool) or not isinstance(value, int) or value < 0 for value in counts):
            raise ValueError("Explanation counts must be nonnegative integers")
        checked, dated, total = counts
        if not 0 <= dated <= checked <= total or checked > 100:
            raise ValueError("Explanation counts violate bounded evidence coverage")


def render_measure_response(request: dict, evidence: dict) -> str:
    """Produce a concise answer using only the supplied scoped evidence."""
    _validate(request, evidence)
    parts = []
    for measure in evidence["measures"]:
        if measure["measure"] in _DEALER_MONTH:
            parts.extend(_DEALER_MONTH[measure["measure"]][2](measure, evidence.get("dealer_id")))
            continue
        periods = measure["periods"]
        is_text = measure["unit"] == "text"
        aggregation = measure.get("aggregation", "sum")
        row_only = is_text or aggregation == "none"
        available = [p for p in periods if p["status"] == "available" and (
            any(row.get("value") is not None for row in p["rows"]) if row_only else p.get("total") is not None)]
        covered = [p["period"] for p in available]
        missing = [p for p in request["periods"] if p not in covered]
        comparing = request.get("operation") in {"compare", "explain"} and len(request["periods"]) > 1
        if row_only:
            parts.append(f"{_text(measure['label'])}{':' if available else ': unavailable.'}")
        elif comparing or (aggregation == "snapshot" and available):
            parts.append(f"{_text(measure['label'])}:")
            for period in available:
                parts.append(f"{_text(period['period'])}: {_number(period['total'], measure['unit'])}.")
            if comparing and not missing and len(request["periods"]) == 2:
                earlier, later = sorted(available, key=lambda p: p["period"])
                delta = Decimal(str(later["total"])) - Decimal(str(earlier["total"]))
                change_label = "Snapshot change" if aggregation == "snapshot" else "Change"
                parts.append(f"{change_label} ({later['period']} − {earlier['period']}): {_number(delta, measure['unit'])}.")
            elif comparing:
                parts.append("Comparison unavailable: two fully evidenced periods are required.")
        elif available:
            total = sum(Decimal(str(p["total"])) for p in available)
            partial = "Partial total — " if missing else ""
            parts.append(f"{partial}{_text(measure['label'])}: {_number(total, measure['unit'])}.")
        else:
            parts.append(f"{_text(measure['label'])}: unavailable.")
        if request.get("dealer_id"):
            parts.append(f"Dealer: {_text(request['dealer_id'])}.")
        if request.get("operation") == "breakdown" and request.get("breakdown") == "month" and not row_only:
            by_period = {p["period"]: p["total"] for p in available}
            lines = ["| Period | Value |", "| --- | --- |"]
            for period in request["periods"]:
                value = _number(by_period[period], measure["unit"]) if period in by_period else "Unavailable"
                lines.append(f"| {_text(period)} | {value} |")
            parts.append("\n".join(lines))
        elif row_only or request.get("operation") == "breakdown" or (
            request.get("operation") in {"compare", "explain"} and request.get("breakdown") == "product"
        ):
            rows = [(period["period"], row) for period in available for row in period["rows"]]
            if rows:
                lines = ["| Period | Dealer | Detail | Value |", "| --- | --- | --- | --- |"]
                for period, row in rows[:_MAX_RENDERED_ROWS]:
                    value = row.get("value")
                    rendered_value = "Unavailable" if value is None else _text(value) if is_text else _number(value, measure["unit"])
                    name, code = row.get("dealer_name"), row.get("dealer_id")
                    dealer = f"{_text(name)} ({_text(code)})" if name and code else _text(name or code or "—")
                    dimension = row.get("dimension") or "—"
                    lines.append(f"| {_text(period)} | {dealer} | {_text(dimension)} | {rendered_value} |")
                parts.append("\n".join(lines))
                if len(rows) > _MAX_RENDERED_ROWS or any(p.get("truncated") for p in available):
                    parts.append("Breakdown truncated; displayed rows are not the complete set. Totals use the available aggregate evidence.")
            elif request.get("operation") == "breakdown":
                parts.append("Requested breakdown unavailable: no detailed evidence rows were supplied.")
        if covered:
            parts.append(f"Covered periods: {', '.join(map(_text, covered))}.")
        if missing:
            parts.append(f"Unavailable periods: {', '.join(map(_text, missing))}. Missing evidence is not zero.")
        if measure.get("note"):
            parts.append(_text(measure["note"]))
        provenance = {}
        for period in periods:
            key = (period["source"], period.get("note", ""))
            provenance.setdefault(key, []).append(period["period"])
        for (source, note), source_periods in provenance.items():
            details = f"Periods: {', '.join(map(_text, source_periods))}. Source: {_text(source)}."
            if note:
                details += f" {_text(note)}"
            parts.append(details)
    if request.get("operation") == "explain":
        explanations = evidence.get("explanations", [])
        if explanations:
            for observation in explanations:
                details = f"{_text(observation['period'])}, dealer {_text(observation['dealer_id'])}: "
                if observation["status"] == "available":
                    details += (f"checked {observation['records_checked']:,} of {observation['total_records']:,} "
                                f"zero-commission records; {observation['records_with_dates']:,} checked records have dates. ")
                else:
                    details += "Zero-commission record evidence unavailable. "
                details += f"Source: {_text(observation['source'])}."
                if observation.get("note"):
                    details += " " + _text(observation["note"])
                parts.append(details)
            parts.append("The underlying cause remains unverified; these observations alone do not establish a cause.")
        else:
            parts.append("The underlying cause is unverified. Explaining why requires supporting source records "
                         "for the requested measure and periods, including eligibility evidence where applicable. "
                         "Recorded amounts and changes alone do not establish a cause.")
    return "\n\n".join(parts)


def _render_priority(measure: dict, dealer_id: str | None) -> list[str]:
    """State the Overview queue position; missing evidence is never a low priority."""
    parts = []
    for period in measure["periods"]:
        month, priority = _text(period["period"]), period.get("priority")
        if period["status"] == "unavailable":
            note = _text(period.get("note") or "the investigation queue could not be read.")
            parts.append(f"Investigation priority unavailable for {month}: {note}")
            parts.append("Missing evidence is not a low priority.")
            continue
        dealer = _text(dealer_id or "—")
        if not priority["in_queue"]:
            parts.append(f"Dealer {dealer} is not in the investigation queue for {month} "
                         f"(queue of {priority['queue_size']:,} dealers).")
        else:
            parts.append(f"Investigation priority for dealer {dealer}, {month}: {_text(priority['severity'])} — "
                         f"rank {priority['rank']:,} of {priority['queue_size']:,} in the investigation queue.")
            parts.append(f"Overall priority is set by the {_text(priority['lead_module'])} finding "
                         f"({_text(priority['lead_type'])}).")
            commission = priority.get("commission")
            if commission:
                commission_line = f"{_text(commission['severity'])} ({_text(commission['type'])})."
            elif priority.get("commission_module_status") in _UNCHECKED_STATUSES:
                commission_line = "commission module could not be checked."
            else:
                commission_line = "no commission finding this month."
            parts.append(f"Commission-module priority: {commission_line}")
            lines = ["| Module | Severity | Finding | Detail |", "| --- | --- | --- | --- |"]
            for finding in priority["findings"]:
                lines.append(f"| {_text(finding['module'].capitalize())} | {_text(finding['severity'])} | "
                             f"{_text(finding['type'])} | {_text(finding['description'])} |")
            parts.append("\n".join(lines))
            if priority["finding_count"] > len(priority["findings"]):
                parts.append(f"Each module's most severe finding is shown; the dealer has "
                             f"{priority['finding_count']:,} findings in total.")
            parts.append("Queue order: severity, then amount outstanding (largest first).")
        if priority.get("unchecked_modules"):
            parts.append(f"Not checked: {', '.join(map(_text, priority['unchecked_modules']))}; "
                         "the queue may be incomplete.")
        if period.get("note"):
            parts.append(_text(period["note"]))
    sources = dict.fromkeys(_text(period["source"]) for period in measure["periods"])
    parts.append(f"Source: {', '.join(sources)}.")
    return parts


_STATEMENT_POSITIONS = {"PAID_IN_FULL": "paid in full", "UNDERPAID": "underpaid", "OVERPAID": "overpaid"}


def _is_amount(value: object) -> bool:
    return (isinstance(value, (int, float, Decimal)) and not isinstance(value, bool)
            and Decimal(str(value)).is_finite())


def _validate_statement(period: dict) -> None:
    """Statement evidence is projected from the dealer statement composer; reject malformed shapes."""
    try:
        _check_statement(period)
    except (KeyError, TypeError, AttributeError) as exc:
        raise ValueError("Incomplete dealer statement evidence") from exc


def _check_statement(period: dict) -> None:
    statement = period.get("statement")
    if period["status"] == "unavailable":
        if statement is not None:
            raise ValueError("Unavailable statement evidence cannot carry a statement")
        return
    if not isinstance(statement, dict) or not isinstance(statement.get("found"), bool):
        raise ValueError("Available statement evidence requires a statement")
    if not statement["found"]:
        if period["rows"]:
            raise ValueError("A dealer without activity has no statement lines")
        return
    if not isinstance(statement["dealer_name"], str):
        raise ValueError("Statement dealer name must be text")
    commission, position, payment = statement["commission"], statement["position"], statement["payment"]
    counts = [commission[key] for key in ("total_activations", "qualified_activation_count", "zero_commission_count")]
    if not all(_is_count(count) for count in counts) or max(counts[1:]) > counts[0]:
        raise ValueError("Statement activation counts are inconsistent")
    by_denomination = commission["by_denomination"]
    if not isinstance(by_denomination, dict) or any(
            not isinstance(key, str) or not _is_amount(value) for key, value in by_denomination.items()):
        raise ValueError("Statement commission lines must be amounts")
    amounts = [commission["expected_ngn"], payment["amount_paid_ngn"],
               *(position[key] for key in ("expected_ngn", "paid_ngn", "outstanding_ngn"))]
    if not all(_is_amount(value) for value in amounts):
        raise ValueError("Statement amounts must be finite numbers")
    if commission["expected_ngn"] != position["expected_ngn"]:
        raise ValueError("Statement amount owed is inconsistent")
    if position["variance_pct"] is not None and not _is_amount(position["variance_pct"]):
        raise ValueError("Statement variance must be a number")
    if position["headline"] not in _STATEMENT_POSITIONS:
        raise ValueError("Unsupported statement position")
    if not isinstance(payment["payment_found"], bool) or not isinstance(payment["source"], str):
        raise ValueError("Statement payment evidence is incomplete")
    if payment["payment_status"] is not None and not isinstance(payment["payment_status"], str):
        raise ValueError("Statement payment status must be text")
    orsc = statement["orsc"]
    if orsc is not None and (not _is_count(orsc["device_count"]) or not _is_count(orsc["zero_amount_count"])
                             or not _is_amount(orsc["total_subscription_amount_ngn"])):
        raise ValueError("Statement subscription evidence is incomplete")
    audit = statement["audit"]
    trails = audit["trails"]
    if not isinstance(audit["readable"], bool) or not isinstance(trails, list) or (trails and not audit["readable"]):
        raise ValueError("Statement audit evidence is inconsistent")
    for trail in trails:
        if not isinstance(trail["module"], str) or not isinstance(trail["label"], str) or not (
                trail["conclusion"] is None or isinstance(trail["conclusion"], str)):
            raise ValueError("Statement audit trails require text fields")


def _linked_conclusion(conclusion: str | None) -> str:
    if conclusion is None:
        return "no conclusion recorded"
    if conclusion == _INSUFFICIENT:
        return f"{_text(conclusion)} (unverified — not a pass)"
    return _text(conclusion)


def _render_statement(measure: dict, dealer_id: str | None) -> list[str]:
    """Owed, paid, outstanding and status first; missing evidence is never zero."""
    parts = []
    for period in measure["periods"]:
        month, statement = _text(period["period"]), period.get("statement")
        dealer = _text(dealer_id or "—")
        if period["status"] == "unavailable":
            note = _text(period.get("note") or "the dealer statement could not be composed.")
            parts.append(f"Dealer statement unavailable for dealer {dealer}, {month}: {note}")
            parts.append("Missing evidence is not zero.")
            continue
        if not statement["found"]:
            parts.append(f"Dealer {dealer} has no recorded activity in {month}; check the dealer code.")
            continue
        commission, position, payment = statement["commission"], statement["position"], statement["payment"]
        parts.append(f"Dealer statement for {_text(statement['dealer_name'])} ({dealer}), {month}.")
        parts.append(f"Amount owed: {_number(position['expected_ngn'], 'ngn')} (activation commission).")
        if payment["payment_found"]:
            outstanding, pct = Decimal(str(position["outstanding_ngn"])), position["variance_pct"]
            overpaid = outstanding < 0
            share = ("" if pct is None else
                     f" ({'overpaid by ' if overpaid else ''}{_number(abs(Decimal(str(pct))), 'count')}% of amount owed)")
            status = _text(payment["payment_status"] or "not recorded")
            parts.append(f"Amount paid: {_number(position['paid_ngn'], 'ngn')}.")
            if overpaid:
                parts.append(f"Amount outstanding: none — overpaid by {_number(-outstanding, 'ngn')}{share}.")
            else:
                parts.append(f"Amount outstanding: {_number(outstanding, 'ngn')}{share}.")
            parts.append(f"Payment status: {status}; statement position: "
                         f"{_STATEMENT_POSITIONS[position['headline']]}.")
        else:
            parts.append(f"Amount paid: unavailable — no payment record was found in "
                         f"{_text(payment['source'])} for this dealer-month. Missing is not zero.")
            parts.append("Amount outstanding: unavailable without a payment record.")
            parts.append("Payment status: no payment record.")
        lines = ["| Component | Amount |", "| --- | --- |"]
        for denomination, amount in commission["by_denomination"].items():
            lines.append(f"| Activation commission · {_text(denomination)} | {_number(amount, 'ngn')} |")
        lines.append(f"| Activation commission (amount owed) | {_number(commission['expected_ngn'], 'ngn')} |")
        orsc = statement["orsc"]
        if orsc is not None:
            lines.append("| Subscription amount (ORSC; not part of amount owed) | "
                         f"{_number(orsc['total_subscription_amount_ngn'], 'ngn')} |")
        parts.append("\n".join(lines))
        parts.append(f"Activations: {commission['total_activations']:,} recorded, "
                     f"{commission['qualified_activation_count']:,} commission-bearing, "
                     f"{commission['zero_commission_count']:,} zero-commission.")
        if orsc is None:
            parts.append("Subscription (ORSC): unavailable — no subscription record was returned for this "
                         "month (none recorded, or the subscription source could not be read). Not zero.")
        else:
            parts.append(f"Subscription (ORSC): {orsc['device_count']:,} devices, "
                         f"{orsc['zero_amount_count']:,} zero-amount records.")
        audit = statement["audit"]
        # The composer reads only some modules and skips per-module read failures:
        # state what was returned, never "none recorded".
        if audit["trails"]:
            conclusions = "; ".join(f"{_text(t['label'])}: {_linked_conclusion(t['conclusion'])}"
                                    for t in audit["trails"])
            parts.append(f"Linked audit conclusions: {conclusions}.")
        elif audit["readable"]:
            parts.append("Linked audit conclusions: none returned.")
        else:
            parts.append("Linked audit trails: unavailable — the audit store could not be read.")
        parts.append("Ask for the verification outcome for full audit results.")
        if period.get("note"):
            parts.append(_text(period["note"]))
        parts.append(f"Sources: activation commission and subscription records; {_text(payment['source'])}; "
                     "verification audit trails.")
    return parts


def render_dealer_codes(evidence: dict) -> str:
    """Render bounded recorded identities without projecting financial fields."""
    rows = evidence['rows']
    displayed = rows[:_MAX_RENDERED_ROWS]
    total = evidence['total_codes']
    partial = bool(evidence.get('has_more')) or len(rows) > _MAX_RENDERED_ROWS or evidence.get('page', 1) > 1
    parts = [f"Recorded dealer codes: {total:,}." if rows else "No matching dealer codes were found in the searched records."]
    if displayed:
        lines = ['| Dealer code | Recorded names | First observed | Last observed |',
                 '| --- | --- | --- | --- |']
        for row in displayed:
            names = ', '.join(_text(name) for name in row['recorded_names'])
            lines.append(f"| {_text(row['dealer_id'])} | {names} | {_text(row['first_observed_period'])} | {_text(row['last_observed_period'])} |")
        parts.append('\n'.join(lines))
    if partial:
        parts.append(f"Partial list: showing {len(displayed)} of {total:,} recorded codes; this is not the complete list.")
    source = evidence.get('data_source', 'Unknown')
    parts.append('Source: Recorded dealer records. Coverage is limited to supplied records.' if source.upper() == 'SAMPLE'
                 else f"Source: {_text(source)}.")
    source_labels = {'fbb_comm_dev_act': 'Activation records', 'fbb_comm_orsc': 'Subscription records'}
    for source_name, periods in evidence.get('coverage_by_source', {}).items():
        label = source_labels.get(source_name, 'Other source records')
        parts.append(f"{label}: {', '.join(map(_text, periods)) if periods else 'no covered months'}.")
    if evidence.get('association_note'):
        parts.append(_text(evidence['association_note']))
    return '\n\n'.join(parts)


_VERIFIED_STATUSES = ("verified", "no_subject", "unavailable")
_VERIFICATION_BASES = {"saved", "on_request"}
_LIMITED_TRAIL = ("This product's comparison evidence is not authentic invoice or stock data; "
                  "no purchase, carryover or alias conclusion is established.")


def _validate_verification(period: dict) -> None:
    """Audit-trail evidence is copied from the audit modules; reject malformed shapes."""
    try:
        _check_verification(period)
    except (KeyError, TypeError, AttributeError) as exc:
        raise ValueError("Incomplete verification evidence") from exc


def _texts(values: object) -> bool:
    return isinstance(values, list) and all(isinstance(value, str) for value in values)


def _check_verification(period: dict) -> None:
    verification = period.get("verification")
    if period["status"] == "unavailable":
        if verification is not None:
            raise ValueError("Unavailable verification evidence cannot carry verdicts")
        return
    if not isinstance(verification, dict) or not isinstance(verification.get("found", True), bool):
        raise ValueError("Available verification evidence requires a found flag")
    if verification.get("found") is False:
        if period["rows"] or verification.get("modules"):
            raise ValueError("A dealer without recorded activity has no audit verdicts")
        return
    modules = verification["modules"] if isinstance(verification, dict) else None
    if not isinstance(modules, list) or not modules:
        raise ValueError("Available verification evidence requires audit modules")
    rows = period["rows"]
    if len(rows) != len(modules) or len({row["dealer_id"] for row in rows}) != 1:
        raise ValueError("Verification rows must be one per module for one dealer")
    dealer = rows[0]["dealer_id"]
    for module in modules:
        if any(not isinstance(module[key], str) for key in ("module", "label", "subjects")):
            raise ValueError("Audit modules require text names")
        status, basis, trails = module["status"], module["basis"], module["trails"]
        if status not in _VERIFIED_STATUSES or not _texts(module["caveats"]) or not isinstance(trails, list):
            raise ValueError("Unsupported audit module status")
        if status == "unavailable":
            if basis is not None or trails or module["subject_count"] != 0 or not isinstance(module["note"], str):
                raise ValueError("An unavailable audit module needs a reason and no verdicts")
            continue
        if basis not in _VERIFICATION_BASES:
            raise ValueError("Audit verdicts must come from a saved run or an on-request check")
        run_at = module["run_at"]
        if (basis == "saved") != isinstance(run_at, str) or (basis != "saved" and run_at is not None) or (
                basis == "saved" and not re.fullmatch(r"\d{4}-\d{2}-\d{2} \d{2}:\d{2} UTC", run_at)):
            raise ValueError("A saved verdict must state its UTC run time")
        count, conclusions = module["subject_count"], module["conclusions"]
        if (not _is_count(count) or (status == "verified") != (count > 0) or len(trails) > count
                or (status == "verified") != bool(trails) or not isinstance(conclusions, list)):
            raise ValueError("Audit subject counts are inconsistent")
        if any(c["conclusion"] not in CONCLUSIONS or not _is_count(c["count"]) or not c["count"]
               for c in conclusions) or sum(c["count"] for c in conclusions) != count:
            raise ValueError("Audit conclusion counts are inconsistent")
        for trail in trails:
            if trail["conclusion"] not in CONCLUSIONS or trail["confidence"] not in CONFIDENCES:
                raise ValueError("Unsupported audit conclusion")
            if not isinstance(trail["subject"], str) or trail["subject"].split(":")[0] != dealer:
                raise ValueError("Audit trail belongs to a different dealer")
            if trail["product_code"] is not None and not isinstance(trail["product_code"], str):
                raise ValueError("Product code must be text")
            if (not _texts(trail["caveats"]) or not isinstance(trail["limited"], bool)
                    or not _is_count(trail.get("withheld", 0))):
                raise ValueError("Audit trail caveats must be text")
            for line in trail["evidence"]:
                if not _is_count(line["step"]) or any(not isinstance(line[k], str) for k in ("name", "result")):
                    raise ValueError("Audit step evidence must be text")


_DELTA = re.compile(r"Delta = NGN ([+-])([\d,]+\.\d{2})"
                    r"(?: \(([+-])(\d[\d,]*\.\d+)% of expected\)| (\(expected is zero — % undefined\)))?\.")


def _delta_words(text: str) -> str:
    """The reconciliation's signed delta, stated in words: never a negative amount or percentage."""
    def words(match: re.Match) -> str:
        sign, amount, _, pct, undefined = match.groups()
        if float(amount.replace(",", "")) == 0:
            lead, share = f"Paid as expected (difference NGN {amount})", "of expected"
        elif sign == "-":
            lead = f"Paid NGN {amount} less than expected"
            if pct is not None:
                return f"{lead} (short by {pct}% of expected)."
        else:
            lead, share = f"Overpaid by NGN {amount}", "of expected"
            if pct is not None:
                return f"{lead} (overpaid by {pct}% {share})."
        if pct is not None:
            return f"{lead} ({pct}% {share})."
        return f"{lead} {undefined}." if undefined else f"{lead}."
    return _DELTA.sub(words, text)


def _render_audit_module(module: dict, dealer: str) -> str:
    label, status = f"**{_text(module['label'])}**", module["status"]
    if status == "unavailable":
        return f"{label}: unavailable: " + _text(
            f"{module['note']} Not verified; missing evidence is not a pass.")
    saved = module["basis"] == "saved"
    basis = (f"From the saved audit run of {module['run_at']}." if saved
             else "Checked on request with the current audit code; nothing was saved.")
    if status == "no_subject":
        where = f" in the saved audit run of {module['run_at']}" if saved else ""
        whom = "" if saved else f", and dealer {dealer} is not one"
        return f"{label}: " + _text(f"no audit subject{where}. This audit covers only {module['subjects']}"
                                    f"{whom}; nothing to verify (not a pass or a failure).")
    trails, count = module["trails"], module["subject_count"]
    bullets = []
    if count == 1:
        trail = trails[0]
        verdict = (f"{trail['conclusion']} (confidence {trail['confidence']})"
                   + (": unverified, not a pass." if trail["conclusion"] == _INSUFFICIENT else "."))
        header = f"{verdict} {basis}"
        bullets.extend(f"Step {e['step']}, {e['name']}: {_delta_words(e['result'])}" for e in trail["evidence"])
        if trail["limited"]:
            bullets.append(_LIMITED_TRAIL)
    else:
        counts = ", ".join(f"{c['conclusion']} {c['count']:,}" for c in module["conclusions"])
        header = f"{count:,} subjects — {counts}. {basis}"
        for trail in trails:
            subject = (f"Product {trail['product_code']}" if trail["product_code"] is not None
                       else f"Subject {trail['subject']}")
            words = [f"{subject}: {trail['conclusion']} (confidence {trail['confidence']})"
                     + (", unverified." if trail["conclusion"] == _INSUFFICIENT else "."),
                     *(_delta_words(e["result"]) for e in trail["evidence"])]
            if trail["limited"]:
                words.append(_LIMITED_TRAIL)
            bullets.append(" ".join(words))
        if count > len(trails):
            bullets.append(f"Showing {len(trails)} of {count:,} subjects.")
    caveats = [*module["caveats"], *(c for trail in trails for c in trail["caveats"])]
    bullets.extend(f"Caveat: {c}" for c in list(dict.fromkeys(caveats))[:_MAX_AUDIT_CAVEATS])
    withheld = sum(trail.get("withheld", 0) for trail in trails)
    if withheld:
        bullets.append(f"{withheld:,} trail detail(s) not shown.")
    if count > 1 and any(c["conclusion"] == _INSUFFICIENT for c in module["conclusions"]):
        bullets.append("INSUFFICIENT_DATA means the audit could not verify the claim; it is not a pass.")
    return "\n".join([f"{label}: {_text(header)}", *(f"- {_text(bullet)}" for bullet in bullets)])


def _render_verification(measure: dict, dealer_id: str | None) -> list[str]:
    """Each audit module's verdict; unavailable and no-subject are never a pass."""
    parts, dealer = [], dealer_id or "—"
    for period in measure["periods"]:
        month = _text(period["period"])
        if period["status"] == "unavailable":
            note = _text(period.get("note") or "the audit trails could not be read.")
            parts.append(f"Verification outcome unavailable for {month}: {note}")
            parts.append("Missing evidence is not a pass.")
            continue
        if not period["verification"].get("found", True):
            parts.append(f"Dealer {_text(dealer)} has no recorded activity in {month}; check the dealer code.")
            continue
        modules = period["verification"]["modules"]
        tally = {status: sum(m["status"] == status for m in modules) for status in _VERIFIED_STATUSES}
        noun = "module" if len(modules) == 1 else "modules"
        parts.append(f"Verification outcome for dealer {_text(dealer)}, {month}: " + _text(
            f"{len(modules)} audit {noun} — {tally['verified']} with a verdict, "
            f"{tally['no_subject']} with no subject, {tally['unavailable']} unavailable."))
        parts.extend(_render_audit_module(module, dealer) for module in modules)
        if period.get("note"):
            parts.append(_text(period["note"]))
    if any(period["status"] == "unavailable" or period["verification"].get("found", True)
           for period in measure["periods"]):
        sources = dict.fromkeys(_text(period["source"]) for period in measure["periods"])
        parts.append(f"Source: {', '.join(sources)}.")
    return parts


# Dealer-month measures: each period carries one payload key that only its
# measure may use. measure -> (payload key, validate(period), render(measure, dealer_id)).
_DEALER_MONTH = {
    "investigation_priority": ("priority", _validate_priority, _render_priority),
    "dealer_statement": ("statement", _validate_statement, _render_statement),
    "verification_outcome": ("verification", _validate_verification, _render_verification),
}
