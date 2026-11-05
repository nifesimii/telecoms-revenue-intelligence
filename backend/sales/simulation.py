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
import uuid
from datetime import date
from typing import NamedTuple

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
    {"account_code": "205044", "issue_date": "2026-05-05", "due_date": "2026-06-04",
     "lines": [{"product_code": "FBB-4G-ROUTER", "quantity": "1"}, {"product_code": "RCC-0500", "quantity": "50"}],
     "collection": {"date": "2026-05-18", "amount_minor": 6000000}},
    {"account_code": "98052", "issue_date": "2026-05-08", "due_date": "2026-06-07",
     "lines": [{"product_code": "FBB-5G-ROUTER", "quantity": "2"}, {"product_code": "RCC-0200", "quantity": "100"}],
     "collection": {"date": "2026-05-20", "amount_minor": 4500000}},
    {"account_code": "74050", "issue_date": "2026-05-12", "due_date": "2026-06-11",
     "lines": [{"product_code": "FBB-4G-ROUTER", "quantity": "3"}]},
]

MAX_QUANTITY = 1_000_000
_MAX_DRAFTS_LISTED = 100
DRAFT, UNPAID, PARTIALLY_PAID, PAID = STATUSES = ["Draft", "Unpaid", "Partially paid", "Paid"]
# Finance's decisions on an order follow in #11.
SUBMITTED, = ORDER_STATUSES = ["Submitted"]
_PARTNERS_BY_CODE = {partner["code"]: partner for partner in PARTNERS}
_PRODUCTS_BY_CODE = {product["code"]: product for product in CATALOGUE}


class SalesRuleError(ValueError):
    """The action breaks a simulation rule and changed nothing."""


class SalesNotFound(LookupError):
    """The record does not exist."""


class SalesConflict(Exception):
    """The caller holds an older copy of a draft, or a record from before a reset that
    now shares its reference with another. Changed nothing."""


class RecordHandle(NamedTuple):
    """What a caller holds of a draft or invoice when asking to change it."""

    reference: str
    token: str


def _new_token() -> str:
    """Identifies one exact record, and one saved copy of a draft. References restart
    after a reset; this never repeats."""
    return uuid.uuid4().hex


def _require_held(record: dict | None, token: str) -> dict:
    if record is None:
        raise SalesNotFound
    if record["token"] != token:
        raise SalesConflict
    return record


def _is_date(value: str) -> bool:
    if not re.fullmatch(r"[0-9]{4}-[0-9]{2}-[0-9]{2}", value):
        return False
    try:
        date.fromisoformat(value)
    except ValueError:
        return False
    return True


def _quantity_is_valid(quantity: str) -> bool:
    return re.fullmatch(r"[0-9]+", quantity) is not None and 1 <= int(quantity) <= MAX_QUANTITY


def _sequence_of(reference: str) -> int:
    return int(reference.rsplit("-", 1)[1])


def _invoice_reference(sequence: int) -> str:
    return f"SIM-INV-{sequence:04d}"


def _collection_reference(sequence: int) -> str:
    return f"SIM-PAY-{sequence:04d}"


def _order_reference(sequence: int) -> str:
    return f"SIM-ORD-{sequence:04d}"


def _last_day_of(period: str) -> str:
    year, month = int(period[:4]), int(period[4:6])
    return f"{period[:4]}-{period[4:6]}-{calendar.monthrange(year, month)[1]:02d}"


def _period_of(iso_date: str) -> str:
    return iso_date[:7].replace("-", "")


def _draft_key(account_code: str, period: str) -> str:
    return f"{account_code}|{period}"


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


def _line_total(line: dict) -> int:
    return int(line["quantity"]) * _PRODUCTS_BY_CODE[line["product_code"]]["price_minor"]


def _draft_total(draft: dict) -> int | None:
    """None while any line is invalid: a partial total would misstate the draft."""
    if not all(_quantity_is_valid(line["quantity"]) for line in draft["lines"]):
        return None
    return sum(_line_total(line) for line in draft["lines"])


def _draft_view(draft: dict) -> dict:
    return {
        "reference": draft["reference"], "token": draft["token"], "account_code": draft["account_code"], "period": draft["period"],
        "issue_date": draft["issue_date"], "due_date": draft["due_date"],
        "lines": [{"product_code": line["product_code"], "quantity": line["quantity"]} for line in draft["lines"]],
    }


def _draft_record(draft: dict) -> dict:
    return {
        "reference": draft["reference"], "status": DRAFT, "is_draft": True, "partner": _PARTNERS_BY_CODE[draft["account_code"]],
        "date": draft["issue_date"], "amount_minor": _draft_total(draft), "period": draft["period"],
    }


def _require_partner(account_code: str | None) -> dict:
    partner = _PARTNERS_BY_CODE.get(account_code)
    if partner is None:
        raise SalesNotFound
    return partner


def _require_catalogue_lines(lines: list[dict]) -> None:
    codes = [line["product_code"] for line in lines]
    if len(set(codes)) != len(codes) or any(code not in _PRODUCTS_BY_CODE for code in codes):
        raise SalesRuleError("Draft lines must name different catalogue products.")


def _order_draft_view(draft: dict) -> dict:
    return {"token": draft["token"], "lines": [{"product_code": line["product_code"], "quantity": line["quantity"]} for line in draft["lines"]]}


def _order_view(order: dict) -> dict:
    return {
        "reference": order["reference"], "status": SUBMITTED, "account": _PARTNERS_BY_CODE[order["account_code"]],
        "currency": "NGN", "lines": order["lines"], "total_minor": order["total_minor"],
    }


def _newest_first(records: list[dict]) -> list[dict]:
    """References are unique, so this is a total order."""
    return sorted(records, key=lambda record: (record["date"], _sequence_of(record["reference"])), reverse=True)


def _issued(records: list[dict]) -> list[dict]:
    return [record for record in records if record["status"] != DRAFT]


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
        self._next_order_sequence = 1
        # A partner's unsubmitted order, one per account, seen by nobody else.
        self._order_drafts: dict[str, dict] = {}
        # The token each account's last deleted draft had, so only its own retry succeeds.
        self._deleted_order_tokens: dict[str, str] = {}
        self._orders: list[dict] = []

    def _seed(self) -> None:
        self._empty()
        for example in _EXAMPLE_INVOICES:
            draft = self._create_draft(example["account_code"], _period_of(example["issue_date"]))
            draft.update(issue_date=example["issue_date"], due_date=example["due_date"], lines=example["lines"])
            self._issue(draft)
            if "collection" in example:
                self.record_collection(
                    f"seed-{draft['reference']}", RecordHandle(draft["reference"], draft["token"]),
                    example["collection"]["date"], example["collection"]["amount_minor"],
                )

    def reset(self) -> dict:
        with self._lock:
            self._seed()
            return self.status()

    def status(self) -> dict:
        with self._lock:
            return {
                "drafts": len(self._drafts), "invoices": len(self._invoices), "collections": len(self._collections),
                "orders": len(self._orders), "next_draft_reference": _invoice_reference(self._next_sequence),
            }

    def _create_draft(self, account_code: str, period: str) -> dict:
        draft = {
            "reference": _invoice_reference(self._next_sequence), "token": _new_token(), "account_code": account_code, "period": period,
            "issue_date": _last_day_of(period), "due_date": "", "lines": [],
        }
        self._next_sequence += 1
        self._drafts[_draft_key(account_code, period)] = draft
        return draft

    def create_draft(self, account_code: str, period: str) -> dict:
        """Each account has one draft per month, so repeating this returns it."""
        _require_partner(account_code)
        with self._lock:
            existing = self._drafts.get(_draft_key(account_code, period))
            return _draft_view(existing or self._create_draft(account_code, period))

    def draft_for(self, account_code: str, period: str) -> dict | None:
        with self._lock:
            draft = self._drafts.get(_draft_key(account_code, period))
            return _draft_view(draft) if draft else None

    def _draft_by_reference(self, reference: str) -> dict | None:
        return next((draft for draft in self._drafts.values() if draft["reference"] == reference), None)

    def update_draft(self, held: RecordHandle, issue_date: str, due_date: str, lines: list[dict]) -> dict:
        """Invalid quantities and dates stay as typed; issuing is what requires them valid."""
        _require_catalogue_lines(lines)
        with self._lock:
            draft = self._draft_by_reference(held.reference)
            # The same change again means its response was lost, not that the draft moved on.
            if draft and held.token == draft.get("previous_token") and (issue_date, due_date, lines) == (draft["issue_date"], draft["due_date"], draft["lines"]):
                return _draft_view(draft)
            _require_held(draft, held.token)
            draft.update(token=_new_token(), previous_token=held.token, issue_date=issue_date, due_date=due_date, lines=lines)
            return _draft_view(draft)

    def _issue(self, draft: dict) -> dict:
        total = _draft_total(draft)
        if not draft["lines"] or total is None:
            raise SalesRuleError("A draft needs at least one line with a valid quantity.")
        if not _is_date(draft["issue_date"]) or _period_of(draft["issue_date"]) != draft["period"]:
            raise SalesRuleError("The issue date must be in the draft's month.")
        if draft["due_date"] and (not _is_date(draft["due_date"]) or draft["due_date"] < draft["issue_date"]):
            raise SalesRuleError("The due date cannot be before the issue date.")
        # Copies catalogue facts onto the invoice so nothing later can reprice it.
        invoice = {
            "reference": draft["reference"], "token": draft["token"], "seller": "MTN", "buyer": _PARTNERS_BY_CODE[draft["account_code"]],
            "period": draft["period"], "issue_date": draft["issue_date"], "due_date": draft["due_date"],
            "currency": "NGN", "total_minor": total,
            "lines": [
                {**_line_view(line), "quantity": int(line["quantity"]), "line_total_minor": _line_total(line)}
                for line in draft["lines"]
            ],
        }
        del self._drafts[_draft_key(draft["account_code"], draft["period"])]
        self._invoices.append(invoice)
        return invoice

    def issue(self, held: RecordHandle) -> dict:
        """Issuing consumes the draft and the invoice keeps its token, so repeating the
        action returns the same invoice."""
        with self._lock:
            existing = self._invoice(held.reference)
            if existing:
                return _require_held(existing, held.token)
            return self._issue(_require_held(self._draft_by_reference(held.reference), held.token))

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
            "status": UNPAID if not history else PARTIALLY_PAID if outstanding else PAID,
            "outstanding_minor": outstanding,
            "collected_minor": invoice["total_minor"] - outstanding,
            "as_of": history[-1]["date"] if history else invoice["issue_date"],
        }

    def record_collection(self, action_id: str, held: RecordHandle, collected_on: str, amount_minor: int) -> dict:
        """Repeating an action returns what it recorded and has no further effect."""
        with self._lock:
            invoice = _require_held(self._invoice(held.reference), held.token)
            repeated = next((collection for collection in self._collections if collection["action_id"] == action_id), None)
            if repeated:
                return repeated
            if not _is_date(collected_on):
                raise SalesRuleError("Enter a valid collection date.")
            if collected_on < invoice["issue_date"]:
                raise SalesRuleError("A collection cannot be dated before the invoice's issue date.")
            if amount_minor <= 0 or amount_minor > self._balance(invoice)["outstanding_minor"]:
                raise SalesRuleError("A collection must be positive and no more than the outstanding balance.")
            collection = {
                "action_id": action_id, "reference": _collection_reference(self._next_collection_sequence),
                "invoice_reference": held.reference, "date": collected_on, "amount_minor": amount_minor,
            }
            self._next_collection_sequence += 1
            self._collections.append(collection)
            return collection

    def _invoice_record(self, invoice: dict) -> dict:
        balance = self._balance(invoice)
        return {
            "reference": invoice["reference"], "status": balance["status"], "is_draft": False, "partner": invoice["buyer"],
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

    def obligations(self, account_code: str, limit: int, offset: int) -> dict:
        """One exact account across every month, up to its latest simulated activity."""
        if account_code not in _PARTNERS_BY_CODE:
            raise SalesNotFound
        with self._lock:
            invoices = _newest_first([
                self._invoice_record(invoice) for invoice in self._invoices if invoice["buyer"]["code"] == account_code
            ])
            drafts = _newest_first([
                _draft_record(draft) for draft in self._drafts.values() if draft["account_code"] == account_code
            ])
        return {
            "invoices": _page(invoices, limit, offset), "drafts": _page(drafts, _MAX_DRAFTS_LISTED, 0),
            "outstanding_minor": _outstanding(invoices), "as_of": _latest_activity(invoices),
        }

    # A partner's own ordering. The account always comes from the caller's login, and
    # another account's records behave exactly as if they did not exist.

    def ordering_reference(self, account_code: str) -> dict:
        """What a partner may see: their own account, never the other partners."""
        return {"account": _require_partner(account_code), "catalogue": CATALOGUE, "max_quantity": MAX_QUANTITY, "statuses": ORDER_STATUSES}

    def order_draft(self, account_code: str) -> dict | None:
        with self._lock:
            draft = self._order_drafts.get(_require_partner(account_code)["code"])
            return _order_draft_view(draft) if draft else None

    def create_order_draft(self, account_code: str) -> dict:
        """One draft per account, so repeating this returns it."""
        code = _require_partner(account_code)["code"]
        with self._lock:
            draft = self._order_drafts.setdefault(code, {"token": _new_token(), "account_code": code, "lines": []})
            return _order_draft_view(draft)

    def update_order_draft(self, account_code: str, token: str, lines: list[dict]) -> dict:
        """Invalid quantities stay as typed; submitting is what requires them valid."""
        _require_catalogue_lines(lines)
        with self._lock:
            draft = self._order_drafts.get(_require_partner(account_code)["code"])
            # The same change again means its response was lost, not that the draft moved on.
            if draft and token == draft.get("previous_token") and lines == draft["lines"]:
                return _order_draft_view(draft)
            _require_held(draft, token)
            draft.update(token=_new_token(), previous_token=token, lines=lines)
            return _order_draft_view(draft)

    def delete_order_draft(self, account_code: str, token: str) -> None:
        """Retrying a delete whose response was lost succeeds; any other missing draft is refused."""
        code = _require_partner(account_code)["code"]
        with self._lock:
            draft = self._order_drafts.get(code)
            if draft is None and self._deleted_order_tokens.get(code) == token:
                return
            _require_held(draft, token)
            del self._order_drafts[code]
            self._deleted_order_tokens[code] = token

    def submit_order(self, account_code: str, action_id: str, token: str) -> dict:
        """Submitting consumes the draft. Repeating an action returns the order it made."""
        code = _require_partner(account_code)["code"]
        with self._lock:
            repeated = self._own_order(code, "action_id", action_id)
            if repeated:
                return _order_view(repeated)
            draft = _require_held(self._order_drafts.get(code), token)
            if not draft["lines"]:
                raise SalesRuleError("Add at least one product before submitting.")
            if not all(_quantity_is_valid(line["quantity"]) for line in draft["lines"]):
                raise SalesRuleError(f"Every quantity must be a whole number from 1 to {MAX_QUANTITY:,}.")
            order = {
                "reference": _order_reference(self._next_order_sequence), "action_id": action_id, "account_code": code,
                "lines": [{**_line_view(line), "quantity": int(line["quantity"]), "line_total_minor": _line_total(line)} for line in draft["lines"]],
                "total_minor": sum(_line_total(line) for line in draft["lines"]),
            }
            self._next_order_sequence += 1
            del self._order_drafts[code]
            self._orders.append(order)
            return _order_view(order)

    def _own_order(self, code: str, field: str, value: str) -> dict | None:
        return next((order for order in self._orders if order["account_code"] == code and order[field] == value), None)

    def orders(self, account_code: str, limit: int, offset: int) -> dict:
        code = _require_partner(account_code)["code"]
        with self._lock:
            own = [_order_view(order) for order in reversed(self._orders) if order["account_code"] == code]
        return _page(own, limit, offset)

    def order(self, account_code: str, reference: str) -> dict:
        code = _require_partner(account_code)["code"]
        with self._lock:
            found = self._own_order(code, "reference", reference)
            if found is None:
                raise SalesNotFound
            return _order_view(found)


simulation = SalesSimulation()
