"""Render requested measures from application-owned evidence, without model prose."""
from __future__ import annotations

from decimal import Decimal
from html import escape
import re

_MAX_RENDERED_ROWS = 100


def _text(value: object) -> str:
    text = escape(str(value), quote=False).replace("\n", " ").replace("\r", " ")
    return re.sub(r"([\\`*_{}\[\]()#+.!|>~-])", r"\\\1", text)


def _number(value: object, unit: str) -> str:
    amount = Decimal(str(value))
    if unit == "ngn":
        return f"NGN {amount:,.2f}"
    return f"{amount:,f}".rstrip("0").rstrip(".") if amount % 1 else f"{amount:,.0f}"


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
    parts.append(f"Source: {_text(source)}." + (' Sample data; coverage is limited to supplied records.' if source.upper() == 'SAMPLE' else ''))
    source_labels = {'fbb_comm_dev_act': 'Activation records', 'fbb_comm_orsc': 'Subscription records'}
    for source_name, periods in evidence.get('coverage_by_source', {}).items():
        label = source_labels.get(source_name, 'Other source records')
        parts.append(f"{label}: {', '.join(map(_text, periods)) if periods else 'no covered months'}.")
    if evidence.get('association_note'):
        parts.append(_text(evidence['association_note']))
    return '\n\n'.join(parts)
