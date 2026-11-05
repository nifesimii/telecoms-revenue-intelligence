"""Fictional Partner Sales simulation (docs/adr/0002-partner-sales-two-logins.md).

Holds drafts, invoices and collections in process memory, seeded at startup, so
every session sees the same records and a restart returns to the seed. It relies
on the single-worker deployment. Nothing here reads or writes a financial source,
and amounts are exact integers in kobo.
"""
from __future__ import annotations

import calendar
import re
import threading
from datetime import date

PARTNERS = [
    {"code": "296065", "name": "River Isle Ventures"},
    {"code": "353072", "name": "River Isle Ventures"},
    {"code": "74050", "name": "Stone Light Networks"},
    {"code": "98052", "name": "Ember Hill Networks"},
    {"code": "205044", "name": "Sunset Crest Communications"},
    {"code": "295083", "name": "Sunset Crest Communications"},
]

# Prices are fixed demo values in kobo, never MTN price lists.
CATALOGUE = [
    {"code": "FBB-5G-ROUTER", "description": "Fictional 5G FBB router", "unit": "device", "price_minor": 5000000},
    {"code": "FBB-4G-ROUTER", "description": "Fictional 4G FBB router", "unit": "device", "price_minor": 3500000},
    {"code": "FBB-MIFI", "description": "Fictional portable FBB MiFi", "unit": "device", "price_minor": 3333333},
    {"code": "RCC-0100", "description": "Fictional NGN 100 physical recharge card", "unit": "card", "price_minor": 10000},
    {"code": "RCC-0200", "description": "Fictional NGN 200 physical recharge card", "unit": "card", "price_minor": 20000},
    {"code": "RCC-0500", "description": "Fictional NGN 500 physical recharge card", "unit": "card", "price_minor": 50000},
]

# One example of each status, dated before the presentation's own invoice and
# clear of its account, 296065. Built through the same rules as any other invoice.
_EXAMPLE_INVOICES = [
    {"partner_code": "205044", "issue_date": "2026-05-05", "due_date": "2026-06-04",
     "lines": [{"product_code": "FBB-4G-ROUTER", "quantity": "1"}, {"product_code": "RCC-0500", "quantity": "50"}],
     "collection": {"date": "2026-05-18", "amount_minor": 6000000}},
    {"partner_code": "98052", "issue_date": "2026-05-08", "due_date": "2026-06-07",
     "lines": [{"product_code": "FBB-5G-ROUTER", "quantity": "2"}, {"product_code": "RCC-0200", "quantity": "100"}],
     "collection": {"date": "2026-05-20", "amount_minor": 4500000}},
    {"partner_code": "74050", "issue_date": "2026-05-12", "due_date": "2026-06-11",
     "lines": [{"product_code": "FBB-4G-ROUTER", "quantity": "3"}]},
]

_MAX_QUANTITY = 1_000_000
_PARTNERS_BY_CODE = {partner["code"]: partner for partner in PARTNERS}
_PRODUCTS_BY_CODE = {product["code"]: product for product in CATALOGUE}


class SalesRuleError(ValueError):
    """The action breaks a simulation rule and changed nothing."""


class SalesNotFound(LookupError):
    """The record does not exist."""


def _is_date(value: str) -> bool:
    if not re.fullmatch(r"[0-9]{4}-[0-9]{2}-[0-9]{2}", value):
        return False
    try:
        date.fromisoformat(value)
    except ValueError:
        return False
    return True


def _quantity_is_valid(quantity: str) -> bool:
    return re.fullmatch(r"[0-9]+", quantity) is not None and 1 <= int(quantity) <= _MAX_QUANTITY


def _sequence_of(reference: str) -> int:
    return int(reference.rsplit("-", 1)[1])


def _invoice_reference(sequence: int) -> str:
    return f"SIM-INV-{sequence:04d}"


def _collection_reference(sequence: int) -> str:
    return f"SIM-PAY-{sequence:04d}"


def _last_day_of(period: str) -> str:
    year, month = int(period[:4]), int(period[4:6])
    return f"{period[:4]}-{period[4:6]}-{calendar.monthrange(year, month)[1]:02d}"


def _page(items: list, limit: int, offset: int) -> dict:
    """One bounded page. A set that shrinks falls back to its last page."""
    last_page_offset = (max(len(items) - 1, 0) // limit) * limit
    start = min(offset, last_page_offset)
    visible = items[start:start + limit]
    return {
        "items": visible,
        "pagination": {
            "total": len(items), "returned": len(visible), "offset": start, "limit": limit,
            "has_more": start + len(visible) < len(items),
        },
    }


def _line_view(line: dict) -> dict:
    product = _PRODUCTS_BY_CODE[line["product_code"]]
    return {
        "product_code": product["code"], "description": product["description"], "unit": product["unit"],
        "unit_price_minor": product["price_minor"], "quantity": line["quantity"],
    }


def _draft_total(draft: dict) -> int | None:
    """None while any line is invalid: a partial total would misstate the draft."""
    if not all(_quantity_is_valid(line["quantity"]) for line in draft["lines"]):
        return None
    return sum(int(line["quantity"]) * _PRODUCTS_BY_CODE[line["product_code"]]["price_minor"] for line in draft["lines"])


def _draft_view(draft: dict) -> dict:
    return {
        "reference": draft["reference"], "partner_code": draft["partner_code"], "period": draft["period"],
        "issue_date": draft["issue_date"], "due_date": draft["due_date"],
        "lines": [{"product_code": line["product_code"], "quantity": line["quantity"]} for line in draft["lines"]],
    }


def _draft_record(draft: dict) -> dict:
    return {
        "reference": draft["reference"], "status": "Draft", "partner": _PARTNERS_BY_CODE[draft["partner_code"]],
        "date": draft["issue_date"], "amount_minor": _draft_total(draft), "period": draft["period"],
    }


def _newest_first(records: list[dict]) -> list[dict]:
    """References are unique, so this is a total order."""
    return sorted(records, key=lambda record: (record["date"], _sequence_of(record["reference"])), reverse=True)


def _issued(records: list[dict]) -> list[dict]:
    return [record for record in records if record["status"] != "Draft"]


def _outstanding(records: list[dict]) -> int:
    return sum(record["outstanding_minor"] for record in _issued(records))


def _latest_activity(records: list[dict]) -> str:
    return max((record["as_of"] for record in _issued(records)), default="")


class SalesSimulation:
    def __init__(self) -> None:
        self._lock = threading.RLock()
        self._seed()

    def _empty(self) -> None:
        self._next_sequence = 1
        self._next_collection_sequence = 1
        self._drafts: dict[str, dict] = {}
        self._invoices: list[dict] = []
        self._collections: list[dict] = []

    def _seed(self) -> None:
        self._empty()
        for example in _EXAMPLE_INVOICES:
            period = example["issue_date"][:7].replace("-", "")
            draft = self._create_draft(example["partner_code"], period)
            draft.update(issue_date=example["issue_date"], due_date=example["due_date"], lines=example["lines"])
            self._issue(draft["reference"])
            if "collection" in example:
                self._record_collection(
                    f"seed-{draft['reference']}", draft["reference"],
                    example["collection"]["date"], example["collection"]["amount_minor"],
                )

    def load_state(self, state: dict) -> None:
        """Replace all records. Acceptance fixtures only; no route exposes this."""
        with self._lock:
            self._next_sequence = state["next_sequence"]
            self._next_collection_sequence = state["next_collection_sequence"]
            self._drafts = {
                f"{draft['partner_code']}|{draft['period']}": draft for draft in state["drafts"]
            }
            self._invoices = state["invoices"]
            self._collections = state["collections"]

    def reset(self) -> dict:
        with self._lock:
            self._seed()
            return self.status()

    def status(self) -> dict:
        with self._lock:
            return {
                "drafts": len(self._drafts), "invoices": len(self._invoices), "collections": len(self._collections),
                "next_draft_reference": _invoice_reference(self._next_sequence),
            }

    def _create_draft(self, partner_code: str, period: str) -> dict:
        draft = {
            "reference": _invoice_reference(self._next_sequence), "partner_code": partner_code, "period": period,
            "issue_date": _last_day_of(period), "due_date": "", "lines": [],
        }
        self._next_sequence += 1
        self._drafts[f"{partner_code}|{period}"] = draft
        return draft

    def create_draft(self, partner_code: str, period: str) -> dict:
        """Each account has one draft per month, so repeating this returns it."""
        if partner_code not in _PARTNERS_BY_CODE:
            raise SalesNotFound
        with self._lock:
            existing = self._drafts.get(f"{partner_code}|{period}")
            return _draft_view(existing or self._create_draft(partner_code, period))

    def draft_for(self, partner_code: str, period: str) -> dict | None:
        with self._lock:
            draft = self._drafts.get(f"{partner_code}|{period}")
            return _draft_view(draft) if draft else None

    def _draft_by_reference(self, reference: str) -> dict | None:
        return next((draft for draft in self._drafts.values() if draft["reference"] == reference), None)

    def update_draft(self, reference: str, issue_date: str, due_date: str, lines: list[dict]) -> dict:
        """Invalid quantities and dates stay as typed; issuing is what requires them valid."""
        codes = [line["product_code"] for line in lines]
        if len(set(codes)) != len(codes) or any(code not in _PRODUCTS_BY_CODE for code in codes):
            raise SalesRuleError("Draft lines must name different catalogue products.")
        with self._lock:
            draft = self._draft_by_reference(reference)
            if draft is None:
                raise SalesNotFound
            draft.update(issue_date=issue_date, due_date=due_date, lines=lines)
            return _draft_view(draft)

    def _issue(self, reference: str) -> dict:
        draft = self._draft_by_reference(reference)
        if draft is None:
            raise SalesNotFound
        total = _draft_total(draft)
        if not draft["lines"] or total is None:
            raise SalesRuleError("A draft needs at least one line with a valid quantity.")
        if not _is_date(draft["issue_date"]) or draft["issue_date"][:7].replace("-", "") != draft["period"]:
            raise SalesRuleError("The issue date must be in the draft's month.")
        if draft["due_date"] and (not _is_date(draft["due_date"]) or draft["due_date"] < draft["issue_date"]):
            raise SalesRuleError("The due date cannot be before the issue date.")
        # Copies catalogue facts onto the invoice so nothing later can reprice it.
        invoice = {
            "reference": reference, "seller": "MTN", "buyer": _PARTNERS_BY_CODE[draft["partner_code"]],
            "period": draft["period"], "issue_date": draft["issue_date"], "due_date": draft["due_date"],
            "currency": "NGN", "total_minor": total,
            "lines": [
                {**_line_view(line), "quantity": int(line["quantity"]),
                 "line_total_minor": int(line["quantity"]) * _PRODUCTS_BY_CODE[line["product_code"]]["price_minor"]}
                for line in draft["lines"]
            ],
        }
        del self._drafts[f"{draft['partner_code']}|{draft['period']}"]
        self._invoices.append(invoice)
        return invoice

    def issue(self, reference: str) -> dict:
        """Issuing consumes the draft, so repeating the action returns the same invoice."""
        with self._lock:
            existing = self._invoice(reference)
            return existing if existing else self._issue(reference)

    def _invoice(self, reference: str) -> dict | None:
        return next((invoice for invoice in self._invoices if invoice["reference"] == reference), None)

    def _balance(self, invoice: dict) -> dict:
        """Status derives from collections, never stored. Collections run oldest first,
        so each states the balance it left and backdating cannot misorder the history."""
        outstanding = invoice["total_minor"]
        history = []
        ordered = sorted(
            (collection for collection in self._collections if collection["invoice_reference"] == invoice["reference"]),
            key=lambda collection: (collection["date"], _sequence_of(collection["reference"])),
        )
        for collection in ordered:
            outstanding -= collection["amount_minor"]
            history.append({**collection, "outstanding_after_minor": outstanding})
        return {
            "history": history,
            "status": "Unpaid" if not history else "Partially paid" if outstanding else "Paid",
            "outstanding_minor": outstanding,
            "collected_minor": invoice["total_minor"] - outstanding,
            "as_of": history[-1]["date"] if history else invoice["issue_date"],
        }

    def _record_collection(self, action_id: str, invoice_reference: str, collected_on: str, amount_minor: int) -> dict:
        repeated = next((collection for collection in self._collections if collection["action_id"] == action_id), None)
        if repeated:
            return repeated
        invoice = self._invoice(invoice_reference)
        if invoice is None:
            raise SalesNotFound
        if not _is_date(collected_on):
            raise SalesRuleError("Enter a valid collection date.")
        if collected_on < invoice["issue_date"]:
            raise SalesRuleError("A collection cannot be dated before the invoice's issue date.")
        if amount_minor <= 0 or amount_minor > self._balance(invoice)["outstanding_minor"]:
            raise SalesRuleError("A collection must be positive and no more than the outstanding balance.")
        collection = {
            "action_id": action_id, "reference": _collection_reference(self._next_collection_sequence),
            "invoice_reference": invoice_reference, "date": collected_on, "amount_minor": amount_minor,
        }
        self._next_collection_sequence += 1
        self._collections.append(collection)
        return collection

    def record_collection(self, action_id: str, invoice_reference: str, collected_on: str, amount_minor: int) -> dict:
        """Repeating an action returns what it recorded and has no further effect."""
        with self._lock:
            return self._record_collection(action_id, invoice_reference, collected_on, amount_minor)

    def _invoice_record(self, invoice: dict) -> dict:
        balance = self._balance(invoice)
        return {
            "reference": invoice["reference"], "status": balance["status"], "partner": invoice["buyer"],
            "date": invoice["issue_date"], "amount_minor": invoice["total_minor"],
            "outstanding_minor": balance["outstanding_minor"], "as_of": balance["as_of"], "period": invoice["period"],
        }

    def records(self, period: str, search: str, status: str, limit: int, offset: int) -> dict:
        """Invoices by issue month and drafts by intended issue month. The summary
        describes the whole matching set, whichever page is returned."""
        term = search.strip().lower()
        with self._lock:
            everything = [self._invoice_record(invoice) for invoice in self._invoices]
            everything += [_draft_record(draft) for draft in self._drafts.values()]
        matching = _newest_first([
            record for record in everything
            if record["period"] == period
            and (not status or record["status"] == status)
            and (term in record["partner"]["code"] or term in record["partner"]["name"].lower())
        ])
        issued = len(_issued(matching))
        return {
            **_page(matching, limit, offset),
            "summary": {
                "count": len(matching), "issued": issued, "drafts": len(matching) - issued,
                "outstanding_minor": _outstanding(matching), "as_of": _latest_activity(matching),
            },
        }

    def invoice_detail(self, reference: str, limit: int, offset: int) -> dict:
        with self._lock:
            invoice = self._invoice(reference)
            if invoice is None:
                raise SalesNotFound
            balance = self._balance(invoice)
        history = balance.pop("history")
        return {"invoice": invoice, "balance": balance, "collections": _page(history, limit, offset)}

    def obligations(self, partner_code: str, limit: int, offset: int) -> dict:
        """One exact account across every month, up to its latest simulated activity."""
        if partner_code not in _PARTNERS_BY_CODE:
            raise SalesNotFound
        with self._lock:
            invoices = _newest_first([
                self._invoice_record(invoice) for invoice in self._invoices if invoice["buyer"]["code"] == partner_code
            ])
            drafts = _newest_first([
                _draft_record(draft) for draft in self._drafts.values() if draft["partner_code"] == partner_code
            ])
        return {
            "invoices": _page(invoices, limit, offset), "drafts": _page(drafts, limit, 0)["items"],
            "outstanding_minor": _outstanding(invoices), "as_of": _latest_activity(invoices),
        }


simulation = SalesSimulation()
