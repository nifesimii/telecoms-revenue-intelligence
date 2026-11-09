"""Fictional Partner Sales simulation routes. They change only the simulation and
never touch a financial source."""
from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from pydantic import BaseModel, Field, StrictInt

from backend.auth import access
from backend.sales.simulation import CATALOGUE, MAX_QUANTITY, PARTNERS, STATUSES, RecordHandle, SalesConflict, SalesNotFound, SalesRuleError, simulation
from backend.sales import statements

router = APIRouter(prefix="/partner-sales", tags=["partner-sales"])

PERIOD_PATTERN = r"^[0-9]{4}(0[1-9]|1[0-2])$"
Period = Annotated[str, Query(pattern=PERIOD_PATTERN)]
Limit = Annotated[int, Query(ge=1, le=100)]
Offset = Annotated[int, Query(ge=0)]
Token = Annotated[str, Field(min_length=1, max_length=64)]


class DraftLine(BaseModel):
    product_code: str = Field(max_length=40)
    quantity: str = Field(max_length=20)


class NewCollection(BaseModel):
    token: Token
    action_id: str = Field(min_length=1, max_length=100)
    date: str = Field(max_length=20)
    amount_minor: StrictInt


def _run(action):
    try:
        return action()
    except SalesNotFound:
        raise HTTPException(status_code=404, detail="Not found in this simulation.") from None
    except SalesConflict:
        raise HTTPException(status_code=409, detail="This changed elsewhere or the simulation was reset.") from None
    except SalesRuleError as error:
        raise HTTPException(status_code=422, detail=str(error)) from None


@router.get("/reference")
def reference() -> dict:
    return {"partners": PARTNERS, "catalogue": CATALOGUE, "max_quantity": MAX_QUANTITY, "statuses": STATUSES}


@router.get("/status")
def status() -> dict:
    return simulation.status()


@router.post("/reset")
def reset() -> dict:
    return simulation.reset()


@router.get("/records")
def records(mon_period: Period, search: str = Query("", max_length=200), status: str = Query("", max_length=20), limit: Limit = 25, offset: Offset = 0) -> dict:
    return simulation.records(mon_period, search, status, limit, offset)


@router.get("/period-summary")
def period_summary(mon_period: Period) -> dict:
    return simulation.period_summary(mon_period)


@router.get("/partners")
def partner_accounts(search: str = Query("", max_length=200), limit: Limit = 25, offset: Offset = 0) -> dict:
    return simulation.partner_accounts(search, limit, offset)


@router.get("/invoices/{reference}")
def invoice_detail(reference: str, limit: Limit = 25, offset: Offset = 0) -> dict:
    return _run(lambda: simulation.invoice_detail(reference, limit, offset))


@router.post("/invoices/{reference}/collections")
def record_collection(reference: str, body: NewCollection) -> dict:
    return _run(lambda: simulation.record_collection(body.action_id, RecordHandle(reference, body.token), body.date, body.amount_minor))


@router.get("/partners/{account_code}/obligations")
def obligations(account_code: str, limit: Limit = 25, offset: Offset = 0) -> dict:
    return _run(lambda: simulation.obligations(account_code, limit, offset))


@router.get("/partners/{account_code}/statement")
def statement(account_code: str, mon_period: Period) -> dict:
    """One exact account's fictional commission statement. A month without one is null, not zero."""
    return {"statement": _run(lambda: statements.statement_for(account_code, mon_period))}


# A partner's own ordering. The account is the session's, and no route accepts one.

def _own_account(request: Request) -> str | None:
    return access.current_principal(request).account_code


OwnAccount = Annotated[str | None, Depends(_own_account)]


class OrderDraftChange(BaseModel):
    token: Token
    lines: list[DraftLine] = Field(max_length=len(CATALOGUE))


class OrderSubmission(BaseModel):
    token: Token
    action_id: str = Field(min_length=1, max_length=100)


@router.get("/my/reference")
def own_reference(account_code: OwnAccount) -> dict:
    return {**_run(lambda: simulation.ordering_reference(account_code)), "statement_periods": statements.statement_periods(account_code)}


@router.get("/my/draft")
def own_draft(account_code: OwnAccount) -> dict:
    return {"draft": _run(lambda: simulation.order_draft(account_code))}


@router.post("/my/draft")
def create_own_draft(account_code: OwnAccount) -> dict:
    return _run(lambda: simulation.create_order_draft(account_code))


@router.put("/my/draft")
def update_own_draft(body: OrderDraftChange, account_code: OwnAccount) -> dict:
    lines = [line.model_dump() for line in body.lines]
    return _run(lambda: simulation.update_order_draft(account_code, body.token, lines))


@router.delete("/my/draft", status_code=204)
def delete_own_draft(token: Annotated[str, Query(min_length=1, max_length=64)], account_code: OwnAccount) -> None:
    _run(lambda: simulation.delete_order_draft(account_code, token))


@router.post("/my/draft/submit")
def submit_own_draft(body: OrderSubmission, account_code: OwnAccount) -> dict:
    return _run(lambda: simulation.submit_order(account_code, body.action_id, body.token))


@router.get("/my/orders")
def own_orders(account_code: OwnAccount, limit: Limit = 25, offset: Offset = 0) -> dict:
    return _run(lambda: simulation.orders(account_code, limit, offset))


@router.get("/my/orders/{reference}")
def own_order(reference: str, account_code: OwnAccount) -> dict:
    return _run(lambda: simulation.order(account_code, reference))


# A partner's own invoices and collections, read-only: recording a collection is Finance's.

@router.get("/my/invoices")
def own_invoices(account_code: OwnAccount, status: str = Query("", max_length=20), limit: Limit = 25, offset: Offset = 0) -> dict:
    return _run(lambda: simulation.own_invoices(account_code, status, limit, offset))


@router.get("/my/invoices/{reference}")
def own_invoice(reference: str, account_code: OwnAccount, limit: Limit = 25, offset: Offset = 0) -> dict:
    return _run(lambda: simulation.own_invoice(account_code, reference, limit, offset))


@router.get("/my/statement")
def own_statement(mon_period: Period, account_code: OwnAccount) -> dict:
    return {"statement": _run(lambda: statements.own_statement(account_code, mon_period))}


# Finance's review of submitted partner orders.

class OrderIssue(BaseModel):
    token: Token
    issue_date: str = Field(max_length=20)
    due_date: str = Field(max_length=20)


class OrderRejection(BaseModel):
    token: Token
    reason: str = Field(max_length=500)


@router.get("/orders")
def review_queue(limit: Limit = 25, offset: Offset = 0) -> dict:
    return simulation.review_queue(limit, offset)


@router.post("/orders/{reference}/issue")
def issue_order(reference: str, body: OrderIssue) -> dict:
    return _run(lambda: simulation.issue_order(RecordHandle(reference, body.token), body.issue_date, body.due_date))


@router.post("/orders/{reference}/reject")
def reject_order(reference: str, body: OrderRejection) -> dict:
    return _run(lambda: simulation.reject_order(RecordHandle(reference, body.token), body.reason))
