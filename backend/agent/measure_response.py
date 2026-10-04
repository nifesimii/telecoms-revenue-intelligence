"""Render requested measures from application-owned evidence, without model prose."""
from __future__ import annotations

from decimal import Decimal
from html import escape
import re

from backend.assurance.overview import (
    QUEUE_DEFAULT_LIMIT, QUEUE_MAX_LIMIT, SEVERITY_ORDER, UNCHECKED_STATUSES as _UNCHECKED_STATUSES,
)
from backend.assurance.registry import ASSURANCE_REGISTRY
from backend.audit.trail import CONCLUSIONS, CONFIDENCES, INSUFFICIENT_DATA as _INSUFFICIENT
from backend.db.payment_snapshot import EXCEPTION_STATUSES

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
            for name, (payload, validate, _) in _STANDALONE.items():
                if name == measure["measure"]:
                    validate(period)
                    if name == "investigation_queue" and period["status"] == "available":
                        _check_queue_request(request, period["queue"])
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
        if not 0 <= dated <= checked <= total:
            raise ValueError("Explanation counts violate bounded evidence coverage")


def render_measure_response(request: dict, evidence: dict) -> str:
    """Produce a concise answer using only the supplied scoped evidence."""
    if request['measures'] == ['dealer_investigation']:
        from backend.agent.investigation_response import render_investigation
        investigation = evidence['investigation']
        if (investigation['dealer_id'] != request['dealer_id']
                or investigation['periods'] != sorted(request['periods'])
                or investigation['family'] != request['investigation_family']):
            raise ValueError('Investigation scope mismatch')
        return render_investigation(investigation, request.get('presentation', 'explanation'))
    _validate(request, evidence)
    parts = []
    for measure in evidence["measures"]:
        if measure["measure"] == "verification_outcome":
            parts.extend(_render_verification(measure, evidence.get("dealer_id"),
                                              request.get("verification_focus")))
            continue
        if measure["measure"] in _STANDALONE:
            parts.extend(_STANDALONE[measure["measure"]][2](measure, evidence.get("dealer_id")))
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
        ranking = (measure["measure"] == "activation_commission" and request.get("limit") is not None
                   and request.get("operation") == "breakdown" and request.get("breakdown") == "dealer")
        ranked_rows = []
        if ranking and available:
            ranked_rows = sorted(available[0]["rows"],
                                 key=lambda row: (-Decimal(str(row["value"])), str(row["dealer_id"])))[:request["limit"]]
        if ranking and ranked_rows:
            selected_total = sum(Decimal(str(row["value"])) for row in ranked_rows)
            if request["limit"] == 1:
                row = ranked_rows[0]
                parts.append(f"Highest activation commission: {_number(selected_total, measure['unit'])} — "
                             f"{_text(row.get('dealer_name') or row['dealer_id'])} ({_text(row['dealer_id'])}).")
            else:
                parts.append(f"Top {len(ranked_rows)} dealers by activation commission: "
                             f"{_number(selected_total, measure['unit'])} combined.")
        elif row_only:
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
            rows = ([(available[0]["period"], row) for row in ranked_rows] if ranking else
                    [(period["period"], row) for period in available for row in period["rows"]])
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
                if ranking:
                    parts.append(f"Showing {len(rows)} of {available[0].get('total_rows', len(available[0]['rows'])):,} dealers, "
                                 "ranked by commission descending; ties use dealer account code. "
                                 "The headline amount covers only the displayed dealers.")
                elif len(rows) > _MAX_RENDERED_ROWS or any(p.get("truncated") for p in available):
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
            note = period.get("note", "")
            if ranking:
                note = note.replace(
                    " Showing the first 100 evidence rows; any total includes all matching records.", "")
            key = (period["source"], note)
            provenance.setdefault(key, []).append(period["period"])
        for (source, note), source_periods in provenance.items():
            details = f"Periods: {', '.join(map(_text, source_periods))}. Source: {_text(source)}."
            if note:
                details += f" {_text(note)}"
            parts.append(details)
    # Standalone renderers state their own limits on cause.
    if request.get("operation") == "explain" and not set(request["measures"]) & set(_STANDALONE):
        explanations = evidence.get("explanations", [])
        if explanations:
            for observation in explanations:
                if 'investigation' in observation:
                    from backend.agent.investigation_response import render_investigation
                    parts.append(render_investigation(observation['investigation']))
                    continue
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
            if any("investigation" not in observation for observation in explanations):
                parts.append("The underlying cause remains unverified; these observations alone do not establish a cause.")
        else:
            parts.append("The underlying cause is unverified. Explaining why requires supporting source records "
                         "for the requested measure and periods, including eligibility evidence where applicable. "
                         "Recorded amounts and changes alone do not establish a cause.")
    # Measures sharing a dealer, period or source repeat the same context and
    # provenance verbatim; state each such fact once, keeping its first position.
    return "\n\n".join(dict.fromkeys(parts))


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
    if statement["orsc_status"] not in _SUBSCRIPTION_STATES or (orsc is None) == (statement["orsc_status"] == "recorded"):
        raise ValueError("Statement subscription revenue state is inconsistent")
    _check_statement_subscription(statement)
    audit = statement["audit"]
    trails = audit["trails"]
    if not isinstance(audit["readable"], bool) or not isinstance(trails, list) or (trails and not audit["readable"]):
        raise ValueError("Statement audit evidence is inconsistent")
    for trail in trails:
        if not isinstance(trail["module"], str) or not isinstance(trail["label"], str) or not (
                trail["conclusion"] is None or isinstance(trail["conclusion"], str)):
            raise ValueError("Statement audit trails require text fields")


_SUBSCRIPTION_STATES = {"recorded", "not_recorded", "unavailable"}
# Subscription commission can also be held back when the dealer's records are incomplete.
_SUBSCRIPTION_COMMISSION_STATES = _SUBSCRIPTION_STATES | {"incomplete"}
_SUBSCRIPTION_AMOUNTS = ("owed_ngn", "paid_ngn", "outstanding_ngn")


def _cents(value: object) -> Decimal:
    return Decimal(str(value)).quantize(Decimal("0.01"))


def _check_statement_subscription(statement: dict) -> None:
    """Subscription commission is its own settlement; the combined total is a plain sum."""
    subscription, combined = statement["subscription_commission"], statement["combined"]
    status = subscription["status"]
    if status not in _SUBSCRIPTION_COMMISSION_STATES or not _is_count(subscription["record_count"]):
        raise ValueError("Unsupported subscription commission state")
    amounts = [subscription[key] for key in _SUBSCRIPTION_AMOUNTS]
    recorded = status == "recorded"
    if recorded and not all(_is_amount(value) for value in amounts):
        raise ValueError("Recorded subscription commission requires amounts")
    if not recorded and any(value is not None for value in amounts):
        raise ValueError("Missing subscription commission cannot carry amounts")
    if combined["includes_subscription"] is not recorded:
        raise ValueError("Combined total must include subscription commission only when recorded")
    position, found = statement["position"], statement["payment"]["payment_found"]
    expected = {"owed_ngn": position["expected_ngn"], "paid_ngn": position["paid_ngn"],
                "outstanding_ngn": position["outstanding_ngn"]}
    for key, activation in expected.items():
        value = combined[key]
        if key != "owed_ngn" and not found:
            if value is not None:
                raise ValueError("Combined paid and outstanding need the activation payment record")
            continue
        total = _cents(activation) + (_cents(subscription[key]) if recorded else 0)
        if not _is_amount(value) or _cents(value) != total:
            raise ValueError("Combined statement total is not the sum of its commission types")


def _linked_conclusion(conclusion: str | None) -> str:
    if conclusion is None:
        return "no conclusion recorded"
    if conclusion == _INSUFFICIENT:
        return f"{_text(conclusion)} (unverified — not a pass)"
    return _text(conclusion)


def _outstanding(value: object, share: str = "") -> str:
    """Outstanding amounts never render negative: an overpayment is stated as such."""
    amount = Decimal(str(value))
    if amount < 0:
        return f"none — overpaid by {_number(-amount, 'ngn')}{share}"
    return f"{_number(amount, 'ngn')}{share}"


def _type_row(label: str, owed: object, paid: object | None, outstanding: str | None) -> str:
    paid_text = "unavailable" if paid is None else _number(paid, "ngn")
    return f"| {label} | {_number(owed, 'ngn')} | {paid_text} | {outstanding or 'unavailable'} |"


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
        subscription, combined = statement["subscription_commission"], statement["combined"]
        recorded, found = combined["includes_subscription"], payment["payment_found"]
        parts.append(f"Dealer statement for {_text(statement['dealer_name'])} ({dealer}), {month}.")
        scope = "activation and subscription commission" if recorded else "activation commission only"
        parts.append(f"Amount owed: {_number(combined['owed_ngn'], 'ngn')} ({scope}).")
        if found:
            parts.append(f"Amount paid: {_number(combined['paid_ngn'], 'ngn')}.")
            parts.append(f"Amount outstanding: {_outstanding(combined['outstanding_ngn'])}.")
            activation_status = (f"activation commission {_text(payment['payment_status'] or 'not recorded')} "
                                 f"(statement position: {_STATEMENT_POSITIONS[position['headline']]})")
        else:
            parts.append(f"Amount paid: unavailable — no activation payment record was found in "
                         f"{_text(payment['source'])} for this dealer-month. Missing is not zero.")
            parts.append("Amount outstanding: unavailable without an activation payment record.")
            activation_status = "activation commission has no payment record"
        subscription_status = "" if not recorded else (
            f"; subscription commission {_number(subscription['paid_ngn'], 'ngn')} settled of "
            f"{_number(subscription['owed_ngn'], 'ngn')} owed, as reported")
        parts.append(f"Payment status: {activation_status}{subscription_status}.")
        pct = position["variance_pct"]
        share = "" if pct is None else (f" ({'overpaid by ' if Decimal(str(position['outstanding_ngn'])) < 0 else ''}"
                                        f"{_number(abs(Decimal(str(pct))), 'count')}% of amount owed)")
        lines = ["| Commission | Owed | Paid | Outstanding |", "| --- | --- | --- | --- |",
                 _type_row("Activation commission", commission["expected_ngn"],
                           position["paid_ngn"] if found else None,
                           _outstanding(position["outstanding_ngn"], share) if found else None)]
        if recorded:
            lines.append(_type_row("Subscription commission", subscription["owed_ngn"], subscription["paid_ngn"],
                                   _outstanding(subscription["outstanding_ngn"])))
        lines.append(_type_row("Total" if recorded else "Total (activation only)", combined["owed_ngn"],
                               combined["paid_ngn"],
                               None if combined["outstanding_ngn"] is None else _outstanding(combined["outstanding_ngn"])))
        parts.append("\n".join(lines))
        if subscription["status"] == "not_recorded":
            parts.append(f"Subscription commission: none recorded for this dealer in {month}.")
        elif subscription["status"] == "incomplete":
            parts.append(f"Subscription commission: this dealer's subscription records for {month} are "
                         "incomplete, so it is not stated — missing is not zero.")
        elif not recorded:
            parts.append("Subscription commission: unavailable for this month — missing is not zero.")
        lines = ["| Component | Amount |", "| --- | --- |"]
        for denomination, amount in commission["by_denomination"].items():
            lines.append(f"| Activation commission · {_text(denomination)} | {_number(amount, 'ngn')} |")
        lines.append(f"| Activation commission (amount owed) | {_number(commission['expected_ngn'], 'ngn')} |")
        parts.append("\n".join(lines))
        parts.append(f"Activations: {commission['total_activations']:,} recorded, "
                     f"{commission['qualified_activation_count']:,} commission-bearing, "
                     f"{commission['zero_commission_count']:,} zero-commission.")
        revenue = statement["orsc"]
        if revenue is not None:
            devices = revenue["device_count"]
            parts.append(f"Subscription revenue: {_number(revenue['total_subscription_amount_ngn'], 'ngn')} across "
                         f"{devices:,} device{'' if devices == 1 else 's'} (not part of the amount owed); "
                         f"{revenue['zero_amount_count']:,} zero-amount records.")
        elif statement["orsc_status"] == "not_recorded":
            parts.append(f"Subscription revenue: none recorded for this dealer in {month}.")
        else:
            parts.append("Subscription revenue: unavailable for this month — missing is not zero.")
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
        parts.append(f"Sources: activation commission, subscription commission and subscription revenue records; "
                     f"{_text(payment['source'])}; verification audit trails.")
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


def _affiliation_headline(evidence: dict, period: str) -> str:
    """Lead with how many OTHER codes share the anchor's recorded name."""
    count = evidence['other_count']
    plural = '' if count == 1 else 's'
    if evidence['anchor_type'] == 'code':
        anchor = f"{_text(evidence['anchor_name'])} ({_text(evidence['anchor_id'])})"
        if count:
            return f"{anchor} shares its recorded dealer name with {count:,} other dealer code{plural} in {period}."
        return f"No other dealer codes are recorded under {anchor} in {period}."
    anchor = f'"{_text(evidence["anchor_query"])}"'
    if count:
        return f"{count:,} dealer code{plural} are recorded under {anchor} in {period}."
    return f"No dealer codes are recorded under {anchor} in {period}."


def render_affiliation(evidence: dict) -> str:
    """Render the sibling account codes recorded under one dealer, with month commission.

    Codes grouped by recorded name are an unverified association, never a confirmed
    legal entity; a code without an activation record that month is unavailable, not zero.
    """
    if evidence['status'] == 'unavailable' or not evidence['found']:
        return _text(evidence['note'])
    period = _text(evidence['period'])
    parts = [_affiliation_headline(evidence, period)]
    with_commission = evidence['others_with_commission']
    if with_commission:
        total = _number(evidence['indicative_total_ngn'], 'ngn')
        parts.append(f"Combined recorded activation commission across {with_commission:,} of those codes: "
                     f"{total} (indicative total of recorded activation commission for {period}).")
    # A code anchor names itself in the headline; the table lists only the OTHER codes.
    display_rows = [row for row in evidence['rows'] if not row['is_anchor']]
    if display_rows:
        lines = ['| Dealer code | Recorded names | Recorded activation commission |',
                 '| --- | --- | --- |']
        for row in display_rows:
            names = ', '.join(_text(name) for name in row['recorded_names'])
            commission = (_number(row['commission_ngn'], 'ngn') if row['commission_status'] == 'available'
                          else 'Unavailable')
            lines.append(f"| {_text(row['dealer_id'])} | {names} | {commission} |")
        parts.append('\n'.join(lines))
    unavailable = evidence['others_unavailable']
    if unavailable:
        plural = '' if unavailable == 1 else 's'
        parts.append(f"{unavailable:,} of those code{plural} have no recorded activation commission in "
                     f"{period}; missing records are not zero and are excluded from the total.")
    if evidence['truncated']:
        parts.append(f"Partial list: showing {len(display_rows):,} of {evidence['total_codes']:,} recorded "
                     "codes; this is not the complete list.")
    parts.append(_text(evidence['note']))
    parts.append(f"Source: {_text(evidence['source'])}. Coverage is limited to supplied records.")
    return '\n\n'.join(dict.fromkeys(parts))


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
            counts = trail.get("eligibility_counts")
            if counts is not None:
                keys = {"total", "inside", "outside", "future", "unknown", "window_days"}
                if (module["module"] != "eligibility_window" or not isinstance(counts, dict)
                        or set(counts) != keys or not all(_is_count(value) for value in counts.values())
                        or counts["total"] != sum(counts[key] for key in ("inside", "outside", "future", "unknown"))):
                    raise ValueError("Eligibility classification counts are inconsistent")
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


def _render_demo_eligibility(measure: dict, dealer: str) -> list[str]:
    """Lead with the structured window result; preserve the recorded trail for inspection."""
    from backend.agent.knowledge_response import eligibility_evidence_note, eligibility_policy
    from backend.agent.prompts import KB_CONTENT

    parts, details = [], []
    for period in measure["periods"]:
        scope = f"Dealer {_text(dealer)} · {_text(period['period'])}"
        if period["status"] == "unavailable":
            parts.append(f"Eligibility check unavailable. {scope}.")
            parts.append(_text(period.get("note") or "The audit evidence could not be read."))
            parts.append("Source: audit\\_trails · unavailable.")
            continue
        if not period["verification"].get("found", True):
            parts.append(f"No recorded activity. {scope}; check the dealer code.")
            parts.append("Source: audit\\_trails · no dealer activity found.")
            continue
        modules = [module for module in period["verification"]["modules"]
                   if module["module"] == "eligibility_window"]
        if len(modules) != 1:
            raise ValueError("Verification evidence does not include the requested focus")
        module = modules[0]
        counts = (module["trails"][0].get("eligibility_counts")
                  if module["status"] == "verified" and module["subject_count"] == 1 else None)
        if module["status"] == "no_subject":
            parts.append(f"No zero-commission records to check. {scope}.")
        elif module["status"] == "unavailable":
            parts.append(f"Eligibility check unavailable. {scope}.")
            parts.append(_text(module["note"]))
            parts.append("Source: audit\\_trails · unavailable.")
        elif counts is not None and counts["window_days"] != 180:
            parts.append(f"The 180-day classification is unavailable. {scope}.")
            parts.append(f"The recorded audit used a {counts['window_days']:,}-day window; "
                         "its counts cannot answer the current demo rule.")
        elif counts is None:
            parts.append(f"The 180-day classification is unavailable. {scope}.")
            parts.append("The recorded audit does not provide complete counts for this rule; "
                         "it cannot establish whether all records were outside the window.")
        else:
            parts.append(f"**{counts['outside']:,} of {counts['total']:,} zero-commission records "
                         f"were outside the 180-day window; {counts['inside']:,} were inside.**")
            parts.append(f"{scope}.")
            if counts["unknown"] or counts["future"]:
                parts.append(f"{counts['unknown']:,} could not be classified because dates were missing or invalid; "
                             f"{counts['future']:,} had activation before invoice and require a data check.")
        if module["basis"] == "saved":
            parts.append(f"Source: audit\\_trails · saved eligibility audit from {_text(module['run_at'])}.")
        elif module["basis"] == "on_request":
            parts.append("Source: audit\\_trails · eligibility audit checked on request; nothing was saved.")
        details.extend([f"**{scope}**", _render_audit_module(module, dealer)])
    parts.append(_text(eligibility_policy(KB_CONTENT, sample_mode=True)))
    if details:
        parts.extend(["### Verification evidence", _text(eligibility_evidence_note(KB_CONTENT)), *details])
    return parts


def _render_verification(measure: dict, dealer_id: str | None, focus: str | None = None) -> list[str]:
    """Each audit module's verdict; unavailable and no-subject are never a pass."""
    from backend import config
    if focus == "eligibility_window" and config.USE_SAMPLE_DATA:
        return _render_demo_eligibility(measure, dealer_id or "—")
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
        if focus:
            modules = [module for module in modules if module["module"] == focus]
            if not modules:
                raise ValueError("Verification evidence does not include the requested focus")
        tally = {status: sum(m["status"] == status for m in modules) for status in _VERIFIED_STATUSES}
        noun = "module" if len(modules) == 1 else "modules"
        parts.append(f"Verification outcome for dealer {_text(dealer)}, {month}: " + _text(
            f"{len(modules)} audit {noun} — {tally['verified']} with a verdict, "
            f"{tally['no_subject']} with no subject, {tally['unavailable']} unavailable."))
        for module in modules:
            if module["module"] == "eligibility_window" and module["status"] == "verified":
                from backend.agent.knowledge_response import eligibility_evidence_note, eligibility_policy
                from backend.agent.prompts import KB_CONTENT
                parts.append(_text(eligibility_policy(KB_CONTENT, sample_mode=config.USE_SAMPLE_DATA)))
                if config.USE_SAMPLE_DATA:
                    parts.append(_text(eligibility_evidence_note(KB_CONTENT)))
                else:
                    parts.append("The following is a recorded audit result; its confidence describes the "
                                 "recorded check, not confirmation that the disputed eligibility rule is correct.")
            parts.append(_render_audit_module(module, dealer))
        if period.get("note"):
            parts.append(_text(period["note"]))
    if any(period["status"] == "unavailable" or period["verification"].get("found", True)
           for period in measure["periods"]):
        sources = dict.fromkeys(_text(period["source"]) for period in measure["periods"])
        parts.append(f"Source: {', '.join(sources)}.")
    return parts


def _validate_variance(period: dict) -> None:
    """Variance evidence is projected from the month-on-month query; reject malformed shapes."""
    try:
        _check_variance(period)
    except (KeyError, TypeError, AttributeError) as exc:
        raise ValueError("Incomplete commission variance evidence") from exc


_VARIANCE_COUNTS = ("earlier_activations", "later_activations")
_VARIANCE_AMOUNTS = ("earlier_ngn", "later_ngn", "change_ngn")


def _check_variance(period: dict) -> None:
    variance = period.get("variance")
    if period["status"] == "unavailable":
        if variance is not None:
            raise ValueError("Unavailable variance evidence cannot carry a variance")
        return
    if not isinstance(variance, dict) or not isinstance(variance.get("found"), bool):
        raise ValueError("Available variance evidence requires a found flag")
    earlier, later = variance["earlier"], variance["later"]
    if not isinstance(earlier, str) or later != period["period"] or not earlier < later:
        raise ValueError("Variance months must be the earlier month and the evidence month")
    if not variance["found"]:
        if period["rows"]:
            raise ValueError("A dealer without activity has no variance lines")
        return
    if not isinstance(variance["earlier_recorded"], bool) or not isinstance(variance["later_recorded"], bool):
        raise ValueError("Variance must state which months have records")
    products, totals = variance["products"], variance["totals"]
    if not isinstance(products, list) or not products or len({p["product"] for p in products}) != len(products):
        raise ValueError("Variance requires distinct product lines")
    for line in [*products, totals]:
        if not all(_is_count(line[key]) for key in _VARIANCE_COUNTS) or not all(
                _is_amount(line[key]) for key in _VARIANCE_AMOUNTS):
            raise ValueError("Variance lines require counts and amounts")
        if _cents(line["later_ngn"]) - _cents(line["earlier_ngn"]) != _cents(line["change_ngn"]):
            raise ValueError("Variance change is not the later amount less the earlier amount")
    if any(not isinstance(p["product"], str) for p in products):
        raise ValueError("Variance products must be text")
    for key in (*_VARIANCE_COUNTS, "earlier_ngn", "later_ngn"):
        if _cents(sum(Decimal(str(p[key])) for p in products)) != _cents(totals[key]):
            raise ValueError("Variance totals are not the sum of the product lines")


def _change_words(value: object) -> str:
    """A change in words: never a negative amount."""
    amount = _cents(value)
    if amount == 0:
        return "no change"
    return f"{'up' if amount > 0 else 'down'} {_number(abs(amount), 'ngn')}"


def _change_share(change: object, earlier: object) -> str:
    base = _cents(earlier)
    if base == 0:
        return "new" if _cents(change) else "—"
    return f"{_number(abs(_cents(change) / base * 100).quantize(Decimal('0.1')), 'count')}%"


def _render_variance(measure: dict, dealer_id: str | None) -> list[str]:
    """Each product's commission in both months and the change; never a cause."""
    parts, dealer = [], _text(dealer_id or "—")
    for period in measure["periods"]:
        variance = period.get("variance")
        if period["status"] == "unavailable":
            note = _text(period.get("note") or "the activation commission records could not be read.")
            parts.append(f"Commission variance unavailable for dealer {dealer}, {_text(period['period'])}: {note}")
            parts.append("Missing evidence is not zero.")
            continue
        earlier, later = _text(variance["earlier"]), _text(variance["later"])
        if not variance["found"]:
            parts.append(f"Dealer {dealer} has no recorded activations in {earlier} or {later}; check the dealer code.")
            continue
        totals = variance["totals"]
        change = _change_words(totals["change_ngn"])
        share = _change_share(totals["change_ngn"], totals["earlier_ngn"])
        parts.append(f"Activation commission for dealer {dealer}, {earlier} to {later}: {change} "
                     f"(from {_number(totals['earlier_ngn'], 'ngn')} to {_number(totals['later_ngn'], 'ngn')}"
                     f"{'' if share in {'new', '—'} or change == 'no change' else ', ' + share}).")
        for month, recorded in ((earlier, variance["earlier_recorded"]), (later, variance["later_recorded"])):
            if not recorded:
                parts.append(f"Dealer {dealer} has no recorded activations in {month}; "
                             "that month is counted as no recorded activity.")
        lines = [f"| Product | Activations {earlier} | Commission {earlier} | Activations {later} | "
                 f"Commission {later} | Change | Change % |", "| --- | --- | --- | --- | --- | --- | --- |"]
        for label, line in [*((_text(p["product"]), p) for p in variance["products"]), ("Total", totals)]:
            lines.append(f"| {label} | {line['earlier_activations']:,} | {_number(line['earlier_ngn'], 'ngn')} | "
                         f"{line['later_activations']:,} | {_number(line['later_ngn'], 'ngn')} | "
                         f"{_change_words(line['change_ngn'])} | {_change_share(line['change_ngn'], line['earlier_ngn'])} |")
        parts.append("\n".join(lines))
        movers = sorted((p for p in variance["products"] if _cents(p["change_ngn"])),
                        key=lambda p: (-abs(_cents(p["change_ngn"])), p["product"]))
        if movers:
            parts.append(f"Largest change: {_text(movers[0]['product'])}, {_change_words(movers[0]['change_ngn'])}.")
        parts.append("This splits the change by product; it does not establish why it changed. "
                     "Ask for the verification outcome to check zero-commission records against the documented causes.")
        if period.get("note"):
            parts.append(_text(period["note"]))
    sources = dict.fromkeys(_text(period["source"]) for period in measure["periods"])
    parts.append(f"Source: {', '.join(sources)}.")
    return parts


_GAP_KINDS = ("profile_class", "invoice")
_GAP_LABELS = {"profile_class": "Account profile class not recorded", "invoice": "No IFS invoice record"}
_GAP_PHRASES = {"profile_class": "account profile class not recorded", "invoice": "no IFS invoice record"}
_GAP_FIELDS = {"profile_class": ("total_activations", "zero_commission_count"),
               "invoice": ("activation_count", "affected_products")}


def _validate_coverage(period: dict) -> None:
    """Coverage evidence is copied from the data coverage collectors; reject malformed shapes."""
    try:
        _check_coverage(period)
    except (KeyError, TypeError, AttributeError) as exc:
        raise ValueError("Incomplete data coverage evidence") from exc


def _check_coverage(period: dict) -> None:
    coverage = period.get("coverage")
    if period["status"] == "unavailable":
        if coverage is not None:
            raise ValueError("Unavailable coverage evidence cannot carry gaps")
        return
    if not isinstance(coverage, dict) or any(
            not isinstance(coverage[key], bool) for key in ("dealer_scoped", "found", "sample_data")):
        raise ValueError("Available coverage evidence requires scope flags")
    if not coverage["found"]:
        if not coverage["dealer_scoped"] or coverage["gaps"] is not None or period["rows"]:
            raise ValueError("Only a dealer without activity has no coverage gaps")
        return
    gaps = coverage["gaps"]
    if not isinstance(gaps, dict) or tuple(gaps) != _GAP_KINDS:
        raise ValueError("Coverage evidence requires both gap checks")
    if all(gaps[kind]["status"] == "unavailable" for kind in _GAP_KINDS):
        raise ValueError("Coverage with no readable check is unavailable")
    listed = 0
    for kind in _GAP_KINDS:
        gap = gaps[kind]
        dealers, count = gap["dealers"], gap["dealer_count"]
        if gap["status"] == "unavailable":
            if count is not None or dealers:
                raise ValueError("An unreadable coverage check cannot list dealers")
            continue
        if gap["status"] != "checked" or not _is_count(count) or not isinstance(dealers, list) or len(dealers) > count:
            raise ValueError("Coverage dealer counts are inconsistent")
        for dealer in dealers:
            if not isinstance(dealer["dealer_id"], str) or not isinstance(dealer["dealer_name"], str) or not all(
                    _is_count(dealer[field]) for field in _GAP_FIELDS[kind]):
                raise ValueError("Coverage dealers require names and counts")
        listed += len(dealers)
    if len(period["rows"]) != listed:
        raise ValueError("Coverage rows must be one per listed dealer")


def _gap_line(kind: str, dealer: dict) -> str:
    name = f"{_text(dealer['dealer_name'])} ({_text(dealer['dealer_id'])})"
    if kind == "profile_class":
        return (f"| {name} | {dealer['total_activations']:,} | "
                f"{dealer['zero_commission_count']:,} zero-commission |")
    return f"| {name} | {dealer['activation_count']:,} | {dealer['affected_products']:,} products |"


def _render_coverage(measure: dict, dealer_id: str | None) -> list[str]:
    """Name each source data gap; an unreadable check is never a clean bill."""
    parts = []
    for period in measure["periods"]:
        month, coverage = _text(period["period"]), period.get("coverage")
        whom = f"dealer {_text(dealer_id)}, " if dealer_id else ""
        if period["status"] == "unavailable":
            note = _text(period.get("note") or "the coverage sources could not be read.")
            parts.append(f"Data coverage unavailable for {whom}{month}: {note}")
            parts.append("Missing evidence is not a clean result.")
            continue
        if not coverage["found"]:
            parts.append(f"Dealer {_text(dealer_id)} has no recorded activity in {month}; check the dealer code.")
            continue
        gaps = coverage["gaps"]
        checked = [kind for kind in _GAP_KINDS if gaps[kind]["status"] == "checked"]
        named = [kind for kind in checked if gaps[kind]["dealer_count"]]
        if dealer_id:
            found = ", ".join(_GAP_PHRASES[kind] for kind in named)
            parts.append(f"Data coverage for {whom}{month}: " + (f"gaps found — {found}." if named
                         else "no gap found in the checks that ran."))
        else:
            counts = "; ".join(f"{_GAP_PHRASES[kind]}: {gaps[kind]['dealer_count']:,} "
                               f"dealer{'' if gaps[kind]['dealer_count'] == 1 else 's'}" for kind in checked)
            parts.append(f"Data coverage for {month}: {counts}.")
        for kind in _GAP_KINDS:
            gap = gaps[kind]
            if gap["status"] == "unavailable":
                parts.append(f"{_GAP_LABELS[kind]}: check unavailable — the source could not be read. "
                             "Not checked is not a clean result.")
                continue
            if not gap["dealer_count"]:
                continue
            header = ("| Dealer | Activations | Zero-commission records |" if kind == "profile_class"
                      else "| Dealer | Activations on those products | Products without an invoice |")
            lines = [f"{_GAP_LABELS[kind]}:", header, "| --- | --- | --- |",
                     *(_gap_line(kind, dealer) for dealer in gap["dealers"])]
            parts.append("\n".join(lines))
            if gap["dealer_count"] > len(gap["dealers"]):
                parts.append(f"Showing {len(gap['dealers']):,} of {gap['dealer_count']:,} dealers, "
                             "most activations first.")
        if "profile_class" in named:
            parts.append("A missing account profile class means the dealer code has no customer-master "
                         "entry; it is one of the four documented zero-commission causes.")
        if "invoice" in named:
            parts.append("A missing invoice record limits the inventory comparison for those products; "
                         "it does not by itself establish a mismatch or an amount owed.")
        if coverage["sample_data"]:
            parts.append("Sample data: invoice gaps may include synthetic demonstration scenarios, "
                         "not authentic IFS evidence.")
        if period.get("note"):
            parts.append(_text(period["note"]))
    sources = dict.fromkeys(_text(period["source"]) for period in measure["periods"])
    parts.append(f"Source: {', '.join(sources)} (activation records and IFS invoice comparison).")
    return parts


def _check_bounded_listing(period: dict, body: dict) -> int:
    """Shared exception-listing shape; the matching dealer count, or -1 when the dealer is not found."""
    if not isinstance(body, dict) or any(not isinstance(body[key], bool) for key in ("dealer_scoped", "found")):
        raise ValueError("Available exception evidence requires scope flags")
    if not body["found"]:
        if not body["dealer_scoped"] or body["dealer_count"] is not None or body["dealers"] or period["rows"]:
            raise ValueError("Only a dealer without records is not found")
        return -1
    count, dealers = body["dealer_count"], body["dealers"]
    if not _is_count(count) or not isinstance(dealers, list) or len(dealers) > min(count, _MAX_RENDERED_ROWS):
        raise ValueError("Exception dealer counts are inconsistent")
    if body["dealer_scoped"] and count > 1:
        raise ValueError("A dealer-scoped listing holds at most one dealer")
    if len(period["rows"]) != len(dealers) or period["truncated"] != (count > len(dealers)):
        raise ValueError("Exception rows must be one per listed dealer")
    if count > len(dealers) and len(dealers) < _MAX_RENDERED_ROWS:
        raise ValueError("A truncated listing shows the full bound")
    for dealer in dealers:
        if not isinstance(dealer["dealer_id"], str) or not isinstance(dealer["dealer_name"], str):
            raise ValueError("Exception dealers require a code and name")
    return count


def _validate_activation_exceptions(period: dict) -> None:
    """Activation exception evidence is the Activation Exceptions view; reject malformed shapes."""
    try:
        _check_activation_exceptions(period)
    except (KeyError, TypeError, AttributeError) as exc:
        raise ValueError("Incomplete activation exception evidence") from exc


def _check_finding_label(finding: dict) -> None:
    if not isinstance(finding["type"], str) or not isinstance(finding["label"], str):
        raise ValueError("Activation findings require a type and label")
    if finding["severity"] not in _PRIORITY_SEVERITIES:
        raise ValueError("Unsupported finding severity")


def _check_activation_exceptions(period: dict) -> None:
    body = period.get("activation_exceptions")
    if period["status"] == "unavailable":
        if body is not None:
            raise ValueError("Unavailable exception evidence cannot carry exceptions")
        return
    count = _check_bounded_listing(period, body)
    if count < 0:
        if body["finding_count"] is not None or body["by_finding"]:
            raise ValueError("A dealer without records has no findings")
        return
    findings, by_finding = body["finding_count"], body["by_finding"]
    if not _is_count(findings) or not isinstance(by_finding, list):
        raise ValueError("Activation exception counts are inconsistent")
    for entry in by_finding:
        _check_finding_label(entry)
        if not _is_count(entry["dealer_count"]) or not 1 <= entry["dealer_count"] <= count:
            raise ValueError("Finding dealer counts exceed the matching dealers")
    if len({entry["type"] for entry in by_finding}) != len(by_finding) or (
            sum(entry["dealer_count"] for entry in by_finding) != findings):
        raise ValueError("Finding counts do not add up")
    if bool(count) != bool(findings) or findings < count:
        raise ValueError("Every listed dealer has at least one finding")
    for dealer in body["dealers"]:
        if not _is_count(dealer["activation_count"]) or not _is_count(dealer["zero_commission_count"]):
            raise ValueError("Exception dealers require activation counts")
        if not isinstance(dealer["findings"], list) or not dealer["findings"]:
            raise ValueError("A listed dealer requires findings")
        for finding in dealer["findings"]:
            _check_finding_label(finding)


def _validate_payment_exceptions(period: dict) -> None:
    """Payment exception evidence is the Payments Exceptions view; reject malformed shapes."""
    try:
        _check_payment_exceptions(period)
    except (KeyError, TypeError, AttributeError) as exc:
        raise ValueError("Incomplete payment exception evidence") from exc


def _check_payment_exceptions(period: dict) -> None:
    body = period.get("payment_exceptions")
    if period["status"] == "unavailable":
        if body is not None:
            raise ValueError("Unavailable exception evidence cannot carry exceptions")
        return
    count = _check_bounded_listing(period, body)
    if count < 0:
        if body["outstanding_ngn"] is not None or body["status_counts"] or body["dealer_status"] is not None:
            raise ValueError("A dealer without records has no payment exceptions")
        return
    if not _is_amount(body["outstanding_ngn"]) or _cents(body["outstanding_ngn"]) < 0:
        raise ValueError("Outstanding total must be a nonnegative amount")
    statuses = body["status_counts"]
    if (not isinstance(statuses, list) or len({s["status"] for s in statuses}) != len(statuses)
            or any(s["status"] not in EXCEPTION_STATUSES or not _is_count(s["dealer_count"])
                   or not s["dealer_count"] for s in statuses)
            or sum(s["dealer_count"] for s in statuses) != count):
        raise ValueError("Payment status counts do not add up")
    dealers = body["dealers"]
    for dealer in dealers:
        if dealer["payment_status"] not in EXCEPTION_STATUSES or not all(
                _is_amount(dealer[key]) for key in ("commission_owed", "amount_paid", "amount_unpaid")):
            raise ValueError("Payment exceptions require an exception status and amounts")
        if dealer["exception_flag"] is not None and not isinstance(dealer["exception_flag"], str):
            raise ValueError("Source flag must be text")
    if len(dealers) == count and sum(_cents(d["amount_unpaid"]) for d in dealers) != _cents(body["outstanding_ngn"]):
        raise ValueError("Outstanding total is not the sum of the exceptions")
    status = body["dealer_status"]
    if not body["dealer_scoped"]:
        if status is not None:
            raise ValueError("Only a dealer-scoped listing carries a dealer status")
    elif not isinstance(status, str) or (status in EXCEPTION_STATUSES) != bool(count) or (
            dealers and dealers[0]["payment_status"] != status):
        raise ValueError("The dealer's recorded status must match its exceptions")


def _exception_unavailable(label: str, period: dict, dealer_id: str | None) -> list[str]:
    whom = f"dealer {_text(dealer_id)}, " if dealer_id else ""
    note = _text(period.get("note") or "the source could not be read.")
    return [f"{label} unavailable for {whom}{_text(period['period'])}: {note}",
            "Missing evidence is not a clean result."]


def _plural(count: int, word: str) -> str:
    return f"{count:,} {word}{'' if count == 1 else 's'}"


def _showing(body: dict) -> list[str]:
    shown, total = len(body["dealers"]), body["dealer_count"]
    return [f"Showing {shown:,} of {total:,}."] if total > shown else []


def _render_activation_exceptions(measure: dict, dealer_id: str | None) -> list[str]:
    """Each flagged dealer's findings as the Activation Exceptions view shows them."""
    parts = []
    for period in measure["periods"]:
        month, body = _text(period["period"]), period.get("activation_exceptions")
        if period["status"] == "unavailable":
            parts.extend(_exception_unavailable("Activation exceptions", period, dealer_id))
            continue
        if not body["found"]:
            parts.append(f"Dealer {_text(dealer_id)} has no recorded activations in {month}; check the dealer code.")
            continue
        if not body["dealer_count"]:
            subject = f"Dealer {_text(dealer_id)} has no activation exception" if dealer_id else "No activation exceptions"
            parts.append(f"{subject} for {month} under the existing "
                         "exception rules. This does not certify every record as correct.")
            continue
        if dealer_id:
            parts.append(f"Activation exceptions for dealer {_text(dealer_id)}, {month}: "
                         f"{_plural(body['finding_count'], 'finding')}.")
        else:
            parts.append(f"Activation exceptions for {month}: {_plural(body['dealer_count'], 'dealer')}, "
                         f"{_plural(body['finding_count'], 'finding')}.")
            parts.append("By finding: " + "; ".join(
                f"{_text(e['label'])} ({_text(e['severity'])}): {_plural(e['dealer_count'], 'dealer')}"
                for e in body["by_finding"]) + ".")
        lines = ["| Dealer | Highest severity | Findings | Activations | Zero-commission activations |",
                 "| --- | --- | --- | --- | --- |"]
        for d in body["dealers"]:
            lines.append(f"| {_text(d['dealer_name'])} ({_text(d['dealer_id'])}) | "
                         f"{_text(d['findings'][0]['severity'])} | "
                         f"{'; '.join(_text(f['label']) for f in d['findings'])} | "
                         f"{d['activation_count']:,} | {d['zero_commission_count']:,} |")
        parts.append("\n".join(lines))
        parts.extend(_showing(body))
        if not dealer_id:
            parts.append("Ordered by highest finding severity, then dealer code.")
        parts.append("Findings come from the existing activation exception rules; they flag "
                     f"{'an account' if dealer_id else 'accounts'} to inspect and do not establish a cause.")
    sources = dict.fromkeys(_text(period["source"]) for period in measure["periods"])
    parts.append(f"Source: {', '.join(sources)}.")
    return parts


def _render_payment_exceptions(measure: dict, dealer_id: str | None) -> list[str]:
    """Settlement records not fully paid, as the Payments Exceptions view shows them."""
    parts = []
    for period in measure["periods"]:
        month, body = _text(period["period"]), period.get("payment_exceptions")
        if period["status"] == "unavailable":
            parts.extend(_exception_unavailable("Payment exceptions", period, dealer_id))
            continue
        if not body["found"]:
            parts.append(f"Dealer {_text(dealer_id)} has no payment record for {month}; check the dealer code.")
            continue
        if not body["dealer_count"]:
            if dealer_id:
                parts.append(f"Dealer {_text(dealer_id)} has no payment exception for {month}; "
                             f"the recorded payment status is {_text(body['dealer_status'])}.")
            else:
                parts.append(f"No payment exceptions for {month}: no settlement record is disputed, "
                             "partially paid or pending.")
            continue
        outstanding = _number(body["outstanding_ngn"], "ngn")
        if dealer_id:
            parts.append(f"Payment exceptions for dealer {_text(dealer_id)}, {month}: "
                         f"{_plural(body['dealer_count'], 'exception')}, {outstanding} outstanding.")
        else:
            parts.append(f"Payment exceptions for {month}: {_plural(body['dealer_count'], 'dealer')}, "
                         f"{outstanding} outstanding.")
            parts.append("By payment status: " + "; ".join(
                f"{_text(s['status'])} {s['dealer_count']:,}" for s in body["status_counts"]) + ".")
        lines = ["| Dealer | Payment status | Commission owed | Amount settled | Outstanding | Source flag |",
                 "| --- | --- | --- | --- | --- | --- |"]
        for d in body["dealers"]:
            flag = _text(d["exception_flag"]) if d["exception_flag"] else "—"
            lines.append(f"| {_text(d['dealer_name'])} ({_text(d['dealer_id'])}) | {_text(d['payment_status'])} | "
                         f"{_number(d['commission_owed'], 'ngn')} | {_number(d['amount_paid'], 'ngn')} | "
                         f"{_number(d['amount_unpaid'], 'ngn')} | {flag} |")
        parts.append("\n".join(lines))
        parts.extend(_showing(body))
        if not dealer_id:
            parts.append("Ordered by outstanding amount, largest first, then dealer code. The outstanding "
                         f"total covers all {body['dealer_count']:,} dealers, not only those shown.")
        parts.append("Payment exceptions are settlement records that are not fully paid: "
                     f"{', '.join(map(_text, EXCEPTION_STATUSES[:-1]))} or {_text(EXCEPTION_STATUSES[-1])}, "
                     "as on the Payments Exceptions view.")
    sources = dict.fromkeys(_text(period["source"]) for period in measure["periods"])
    parts.append(f"Source: {', '.join(sources)}.")
    return parts


_QUEUE_MODULES = tuple(ASSURANCE_REGISTRY)


def _validate_queue(period: dict) -> None:
    """Queue evidence is the Overview queue filtered and bounded; reject malformed shapes."""
    try:
        _check_queue(period)
    except (KeyError, TypeError, AttributeError) as exc:
        raise ValueError("Incomplete investigation queue evidence") from exc


def _check_queue(period: dict) -> None:
    body = period.get("queue")
    if period["status"] == "unavailable":
        if body is not None:
            raise ValueError("Unavailable queue evidence cannot carry a queue")
        return
    if not isinstance(body, dict):
        raise ValueError("Available queue evidence requires a queue")
    severity, modules, limit = body["severity"], body["modules"], body["limit"]
    if severity is not None and severity not in _PRIORITY_SEVERITIES:
        raise ValueError("Unsupported queue severity filter")
    if (not isinstance(modules, list) or len(set(modules)) != len(modules)
            or any(module not in _QUEUE_MODULES for module in modules)):
        raise ValueError("Queue module filter must be distinct assurance modules")
    if not _is_count(limit) or not 1 <= limit <= QUEUE_MAX_LIMIT:
        raise ValueError("Queue limit out of bounds")
    size, count, dealers = body["queue_size"], body["match_count"], body["dealers"]
    if (not _is_count(size) or not _is_count(count) or count > size or not isinstance(dealers, list)
            or (not severity and not modules and count != size)):
        raise ValueError("Queue counts are inconsistent")
    if len(dealers) != min(count, limit) or period["truncated"] != (count > len(dealers)):
        raise ValueError("A queue listing shows every match up to the limit")
    if len(period["rows"]) != len(dealers):
        raise ValueError("Queue rows must be one per listed dealer")
    unchecked = body["unchecked_modules"]
    if not isinstance(unchecked, list) or any(module not in _QUEUE_MODULES for module in unchecked):
        raise ValueError("Unchecked modules must be assurance modules")
    previous = 0
    for dealer in dealers:
        rank = dealer["rank"]
        if not _is_count(rank) or not previous < rank <= size:
            raise ValueError("Queue ranks must rise within the full queue")
        previous = rank
        if not isinstance(dealer["dealer_id"], str) or not isinstance(dealer["dealer_name"], str):
            raise ValueError("Queue dealers require a code and name")
        if dealer["severity"] not in _PRIORITY_SEVERITIES or (severity and dealer["severity"] != severity):
            raise ValueError("Queue dealer severity does not match the filter")
        listed = dealer["modules"]
        if (not isinstance(listed, list) or not listed or any(m not in _QUEUE_MODULES for m in listed)
                or not set(modules) <= set(listed) or dealer["lead_module"] not in listed
                or not isinstance(dealer["lead_type"], str)):
            raise ValueError("Queue dealer modules do not match the filter")
        amount = dealer["amount_outstanding"]
        if amount is not None and (not _is_amount(amount) or _cents(amount) < 0):
            raise ValueError("Amount outstanding must be a nonnegative amount")
    outstanding, paid = body["outstanding_ngn"], body["payment_dealer_count"]
    if "payment" in unchecked:
        if outstanding is not None or paid is not None:
            raise ValueError("An unchecked payment module has no outstanding total")
        return
    if not _is_amount(outstanding) or _cents(outstanding) < 0 or not _is_count(paid) or paid > count:
        raise ValueError("Queue outstanding total is inconsistent")
    if len(dealers) == count:
        amounts = [d["amount_outstanding"] for d in dealers if d["amount_outstanding"] is not None]
        if paid != len(amounts) or sum(map(_cents, amounts)) != _cents(outstanding):
            raise ValueError("Outstanding total is not the sum of the matching dealers")


def _check_queue_request(request: dict, body: dict) -> None:
    """The evidence must carry exactly the filters the scope asked for."""
    limit = request.get("limit")
    if (body["severity"] != request.get("queue_severity")
            or body["modules"] != list(request.get("queue_modules") or [])
            or body["limit"] != (QUEUE_DEFAULT_LIMIT if limit is None else limit)):
        raise ValueError("Queue evidence filters do not match the request")


def _module_list(modules: list) -> str:
    names = [_text(module) for module in modules]
    return names[0] if len(names) == 1 else f"{', '.join(names[:-1])} and {names[-1]}"


def _queue_filter(body: dict, plural: bool) -> str:
    """The filter as a verb phrase, e.g. "match HIGH severity with findings in payment"."""
    severity, modules = body["severity"], body["modules"]
    findings = f"findings in {_module_list(modules)}" if modules else ""
    if severity:
        return (f"{'match' if plural else 'matches'} {_text(severity)} severity"
                + (f" with {findings}" if findings else ""))
    return f"{'have' if plural else 'has'} {findings}"


def _render_queue(measure: dict, dealer_id: str | None) -> list[str]:
    """The month's investigation queue in its own order; missing evidence is never an empty queue."""
    parts = []
    for period in measure["periods"]:
        month, body = _text(period["period"]), period.get("queue")
        if period["status"] == "unavailable":
            note = _text(period.get("note") or "the investigation queue could not be read.")
            parts.append(f"Investigation queue unavailable for {month}: {note}")
            parts.append("Missing evidence is not an empty queue.")
            continue
        filtered = bool(body["severity"] or body["modules"])
        size, count, dealers = body["queue_size"], body["match_count"], body["dealers"]
        if not count:
            if filtered:
                parts.append(f"No dealers in the {month} investigation queue {_queue_filter(body, True)} "
                             f"(queue of {_plural(size, 'dealer')}).")
            else:
                parts.append(f"No dealers are in the {month} investigation queue.")
        else:
            matched = _plural(count, "dealer") + (f" {_queue_filter(body, count != 1)}" if filtered else "")
            context = f" (of {size:,} in the queue)" if filtered else ""
            showing = (f"showing the top {len(dealers):,}" if count > len(dealers)
                       else "showing it" if count == 1 else f"showing all {count:,}")
            parts.append(f"Investigation queue for {month}: {matched}{context}; {showing}.")
            payment_unchecked = "payment" in body["unchecked_modules"]
            lines = ["| Rank | Dealer | Severity | Lead finding | Modules | Amount outstanding |",
                     "| --- | --- | --- | --- | --- | --- |"]
            for d in dealers:
                amount = d["amount_outstanding"]
                shown = ("Unavailable" if payment_unchecked else "No payment record" if amount is None
                         else _number(amount, "ngn"))
                lines.append(f"| {d['rank']:,} | {_text(d['dealer_name'])} ({_text(d['dealer_id'])}) | "
                             f"{_text(d['severity'])} | {_text(d['lead_module'].capitalize())} · "
                             f"{_text(d['lead_type'])} | "
                             f"{', '.join(_text(m.capitalize()) for m in d['modules'])} | {shown} |")
            parts.append("\n".join(lines))
            if count > len(dealers):
                parts.append(f"Showing {len(dealers):,} of {count:,} matching dealers.")
            if payment_unchecked:
                parts.append("Amount outstanding unavailable: the payment module could not be checked.")
            else:
                kind = "matching dealer" if filtered else "dealer in the queue"
                whom = f"the 1 {kind}" if count == 1 else (
                    f"all {count:,} {'matching dealers' if filtered else 'dealers in the queue'}")
                parts.append(f"Amount outstanding across {whom}: {_number(body['outstanding_ngn'], 'ngn')} "
                             f"(counting only the {_plural(body['payment_dealer_count'], 'dealer')} "
                             "with a payment record).")
            parts.append("Queue order: severity, then amount outstanding (largest first).")
        if body["unchecked_modules"]:
            parts.append(f"Not checked: {', '.join(map(_text, body['unchecked_modules']))}; "
                         "the queue may be incomplete.")
    sources = dict.fromkeys(_text(period["source"]) for period in measure["periods"])
    parts.append(f"Source: {', '.join(sources)}.")
    return parts


# Standalone measures: each period carries one payload key that only its
# measure may use. measure -> (payload key, validate(period), render(measure, dealer_id)).
_STANDALONE = {
    "investigation_priority": ("priority", _validate_priority, _render_priority),
    "dealer_statement": ("statement", _validate_statement, _render_statement),
    "verification_outcome": ("verification", _validate_verification, _render_verification),
    "commission_variance": ("variance", _validate_variance, _render_variance),
    "data_coverage": ("coverage", _validate_coverage, _render_coverage),
    "activation_exceptions": ("activation_exceptions", _validate_activation_exceptions,
                              _render_activation_exceptions),
    "payment_exceptions": ("payment_exceptions", _validate_payment_exceptions, _render_payment_exceptions),
    "investigation_queue": ("queue", _validate_queue, _render_queue),
}
