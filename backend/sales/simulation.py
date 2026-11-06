"""Fictional Partner Sales simulation (docs/adr/0002-partner-sales-two-logins.md).

Holds partner orders, invoices and collections in process memory, seeded at startup, so
every session sees the same records and a restart returns to the seed. It relies
on the single-worker deployment. Nothing here reads or writes a financial source,
and amounts are exact integers in kobo.
"""
from __future__ import annotations

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
# clear of its account, 296065. Built through the same rules as an issued order, with
# no order behind them, so the waiting order stays SIM-ORD-0001.
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

# Waits for Finance at first login. Its account, 295083, shares a name with 205044 and
# is not the presentation's own account, 296065.
_EXAMPLE_ORDER = {"account_code": "295083", "lines": [{"product_code": "FBB-MIFI", "quantity": "3"}, {"product_code": "RCC-0200", "quantity": "50"}]}

MAX_QUANTITY = 1_000_000
UNPAID, PARTIALLY_PAID, PAID = STATUSES = ["Unpaid", "Partially paid", "Paid"]
SUBMITTED, ISSUED, REJECTED = ORDER_STATUSES = ["Submitted", "Issued", "Rejected"]
_PARTNERS_BY_CODE = {partner["code"]: partner for partner in PARTNERS}
_PRODUCTS_BY_CODE = {product["code"]: product for product in CATALOGUE}


class SalesRuleError(ValueError):
    """The action breaks a simulation rule and changed nothing."""


class SalesNotFound(LookupError):
    """The record does not exist."""


class SalesConflict(Exception):
    """The caller holds an older copy of a draft order, a decided order, or a record from
    before a reset that now shares its reference with another. Changed nothing."""


class RecordHandle(NamedTuple):
    """What a caller holds of an order or invoice when asking to change it."""

    reference: str
    token: str


def _new_token() -> str:
    """Identifies one exact record, and one saved copy of a draft order. References restart
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


def _period_of(iso_date: str) -> str:
    return iso_date[:7].replace("-", "")


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


def _require_partner(account_code: str | None) -> dict:
    partner = _PARTNERS_BY_CODE.get(account_code)
    if partner is None:
        raise SalesNotFound
    return partner


def _require_catalogue_lines(lines: list[dict]) -> None:
    codes = [line["product_code"] for line in lines]
    if len(set(codes)) != len(codes) or any(code not in _PRODUCTS_BY_CODE for code in codes):
        raise SalesRuleError("Draft lines must name different catalogue products.")


def _priced(lines: list[dict]) -> list[dict]:
    """Copies catalogue facts onto the lines so nothing later can reprice them."""
    return [{**_line_view(line), "quantity": int(line["quantity"]), "line_total_minor": _line_total(line)} for line in lines]


def _order_draft_view(draft: dict) -> dict:
    return {"token": draft["token"], "lines": [{"product_code": line["product_code"], "quantity": line["quantity"]} for line in draft["lines"]]}


def _order_view(order: dict) -> dict:
    """What the partner sees, including Finance's decision once there is one."""
    return {
        "reference": order["reference"], "status": order["status"], "account": _PARTNERS_BY_CODE[order["account_code"]],
        "currency": "NGN", "lines": order["lines"], "total_minor": order["total_minor"],
        "invoice": order["invoice"], "rejection_reason": order["rejection_reason"],
    }


def _finance_order_view(order: dict) -> dict:
    """Finance's view, whose token a decision must send."""
    return {**_order_view(order), "token": order["token"]}


def _invoice(reference: str, token: str, account_code: str, issue_date: str, due_date: str, lines: list[dict]) -> dict:
    """A frozen invoice from priced lines. Its month is its issue date's."""
    return {
        "reference": reference, "token": token, "seller": "MTN", "buyer": _PARTNERS_BY_CODE[account_code],
        "period": _period_of(issue_date), "issue_date": issue_date, "due_date": due_date,
        "currency": "NGN", "total_minor": sum(line["line_total_minor"] for line in lines), "lines": lines,
    }


def _newest_first(records: list[dict]) -> list[dict]:
    """References are unique, so this is a total order."""
    return sorted(records, key=lambda record: (record["date"], _sequence_of(record["reference"])), reverse=True)


def _outstanding(records: list[dict]) -> int:
    return sum(record["outstanding_minor"] for record in records)


def _latest_activity(records: list[dict]) -> str:
    return max((record["as_of"] for record in records), default="")


def _without(record: dict, field: str) -> dict:
    return {key: value for key, value in record.items() if key != field}


def _summary(records: list[dict]) -> dict:
    """Describes the whole matching set, whichever page is returned."""
    return {"count": len(records), "outstanding_minor": _outstanding(records), "as_of": _latest_activity(records)}


class SalesSimulation:
    def __init__(self) -> None:
        self._lock = threading.RLock()
        self._seed()

    def _empty(self) -> None:
        self._next_sequence = 1
        self._next_collection_sequence = 1
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
            invoice = self._issue(example["account_code"], example["issue_date"], example["due_date"], _priced(example["lines"]))
            if "collection" in example:
                self.record_collection(
                    f"seed-{invoice['reference']}", RecordHandle(invoice["reference"], invoice["token"]),
                    example["collection"]["date"], example["collection"]["amount_minor"],
                )
        code = _EXAMPLE_ORDER["account_code"]
        draft = self.create_order_draft(code)
        draft = self.update_order_draft(code, draft["token"], _EXAMPLE_ORDER["lines"])
        self.submit_order(code, "seed-order", draft["token"])

    def reset(self) -> dict:
        with self._lock:
            self._seed()
            return self.status()

    def status(self) -> dict:
        with self._lock:
            return {
                "invoices": len(self._invoices), "collections": len(self._collections),
                "orders": len(self._orders), "next_invoice_reference": _invoice_reference(self._next_sequence),
            }

    def _issue(self, account_code: str, issue_date: str, due_date: str, lines: list[dict], order_reference: str | None = None) -> dict:
        """The one way an invoice comes into being. Changes nothing unless the dates are valid."""
        if not _is_date(issue_date):
            raise SalesRuleError("Enter a valid issue date.")
        if not _is_date(due_date) or due_date < issue_date:
            raise SalesRuleError("Enter a due date on or after the issue date.")
        invoice = {**_invoice(_invoice_reference(self._next_sequence), _new_token(), account_code, issue_date, due_date, lines), "order_reference": order_reference}
        self._next_sequence += 1
        self._invoices.append(invoice)
        return invoice

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
            "reference": invoice["reference"], "status": balance["status"], "partner": invoice["buyer"],
            "date": invoice["issue_date"], "amount_minor": invoice["total_minor"],
            "outstanding_minor": balance["outstanding_minor"], "as_of": balance["as_of"], "period": invoice["period"],
        }

    def records(self, period: str, search: str, status: str, limit: int, offset: int) -> dict:
        """Invoices by issue month. The summary describes the whole matching set,
        whichever page is returned."""
        term = search.strip().lower()
        with self._lock:
            everything = [self._invoice_record(invoice) for invoice in self._invoices]
        matching = _newest_first([
            record for record in everything
            if record["period"] == period
            and (not status or record["status"] == status)
            and (term in record["partner"]["code"] or term in record["partner"]["name"].lower())
        ])
        return {**_page(matching, limit, offset), "summary": _summary(matching)}

    def _detail(self, invoice: dict | None, limit: int, offset: int) -> dict:
        if invoice is None:
            raise SalesNotFound
        balance = self._balance(invoice)
        history = balance.pop("history")
        return {"invoice": invoice, "balance": balance, "collections": _page(history, limit, offset)}

    def invoice_detail(self, reference: str, limit: int, offset: int) -> dict:
        with self._lock:
            return self._detail(self._invoice(reference), limit, offset)

    def _account_records(self, account_code: str) -> list[dict]:
        """One exact account's invoices from every issue month, newest first."""
        with self._lock:
            return _newest_first([self._invoice_record(invoice) for invoice in self._invoices if invoice["buyer"]["code"] == account_code])

    def obligations(self, account_code: str, limit: int, offset: int) -> dict:
        """One exact account across every month, up to its latest simulated activity."""
        if account_code not in _PARTNERS_BY_CODE:
            raise SalesNotFound
        invoices = self._account_records(account_code)
        return {
            "invoices": _page(invoices, limit, offset),
            "outstanding_minor": _outstanding(invoices), "as_of": _latest_activity(invoices),
        }

    # A partner's own ordering. The account always comes from the caller's login, and
    # another account's records behave exactly as if they did not exist.

    def ordering_reference(self, account_code: str) -> dict:
        """What a partner may see: their own account, never the other partners."""
        return {"account": _require_partner(account_code), "catalogue": CATALOGUE, "max_quantity": MAX_QUANTITY, "statuses": ORDER_STATUSES, "invoice_statuses": STATUSES}

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
            lines = _priced(draft["lines"])
            order = {
                "reference": _order_reference(self._next_order_sequence), "token": _new_token(), "action_id": action_id, "account_code": code,
                "status": SUBMITTED, "invoice": None, "rejection_reason": None,
                "lines": lines, "total_minor": sum(line["line_total_minor"] for line in lines),
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

    def own_invoices(self, account_code: str, status: str, limit: int, offset: int) -> dict:
        """A partner's invoices from every issue month, newest first."""
        records = self._account_records(_require_partner(account_code)["code"])
        matching = [record for record in records if not status or record["status"] == status]
        return {**_page(matching, limit, offset), "summary": _summary(matching)}

    def own_invoice(self, account_code: str, reference: str, limit: int, offset: int) -> dict:
        """Read-only: without the invoice's token or Finance's action ids, the partner holds
        nothing a change could send."""
        code = _require_partner(account_code)["code"]
        with self._lock:
            invoice = self._invoice(reference)
            detail = self._detail(invoice if invoice and invoice["buyer"]["code"] == code else None, limit, offset)
        collections = detail["collections"]
        return {
            **detail,
            "invoice": _without(detail["invoice"], "token"),
            "collections": {**collections, "items": [_without(item, "action_id") for item in collections["items"]]},
        }

    # Finance's review of submitted orders, across every partner.

    def review_queue(self, limit: int, offset: int) -> dict:
        """Orders awaiting a decision, oldest first, so the longest waiting leads."""
        with self._lock:
            waiting = [_finance_order_view(order) for order in self._orders if order["status"] == SUBMITTED]
        return _page(waiting, limit, offset)

    def _undecided(self, held: RecordHandle) -> dict:
        """A decided order stays decided, so a second decision is a conflict."""
        order = _require_held(next((order for order in self._orders if order["reference"] == held.reference), None), held.token)
        if order["status"] != SUBMITTED:
            raise SalesConflict
        return order

    def issue_order(self, held: RecordHandle, issue_date: str, due_date: str) -> dict:
        """Issues exactly the submitted lines and total as a new invoice."""
        with self._lock:
            order = self._undecided(held)
            invoice = self._issue(order["account_code"], issue_date, due_date, order["lines"], order_reference=order["reference"])
            order.update(status=ISSUED, invoice={"reference": invoice["reference"], "issue_date": issue_date, "due_date": due_date})
            return invoice

    def reject_order(self, held: RecordHandle, reason: str) -> dict:
        """Final: the partner starts a new draft rather than resubmitting."""
        with self._lock:
            order = self._undecided(held)
            if not reason.strip():
                raise SalesRuleError("Enter a reason for the partner.")
            order.update(status=REJECTED, rejection_reason=reason.strip())
            return _finance_order_view(order)


simulation = SalesSimulation()
