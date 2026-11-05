"""Fictional Partner Sales simulation routes. They change only the simulation and
never touch a financial source."""
from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel, Field, StrictInt

from backend.sales.simulation import CATALOGUE, MAX_QUANTITY, PARTNERS, STATUSES, RecordHandle, SalesConflict, SalesNotFound, SalesRuleError, simulation

router = APIRouter(prefix="/partner-sales", tags=["partner-sales"])

PERIOD_PATTERN = r"^[0-9]{4}(0[1-9]|1[0-2])$"
Period = Annotated[str, Query(pattern=PERIOD_PATTERN)]
Limit = Annotated[int, Query(ge=1, le=100)]
Offset = Annotated[int, Query(ge=0)]
Token = Annotated[str, Field(min_length=1, max_length=64)]


class NewDraft(BaseModel):
    account_code: str = Field(max_length=20)
    mon_period: str = Field(pattern=PERIOD_PATTERN)


class DraftLine(BaseModel):
    product_code: str = Field(max_length=40)
    quantity: str = Field(max_length=20)


class DraftChange(BaseModel):
    token: Token
    issue_date: str = Field(max_length=20)
    due_date: str = Field(max_length=20)
    lines: list[DraftLine] = Field(max_length=len(CATALOGUE))


class IssueRequest(BaseModel):
    token: Token


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


@router.get("/drafts")
def draft_for(account_code: str, mon_period: Period) -> dict:
    return {"draft": simulation.draft_for(account_code, mon_period)}


@router.post("/drafts")
def create_draft(body: NewDraft) -> dict:
    return _run(lambda: simulation.create_draft(body.account_code, body.mon_period))


@router.put("/drafts/{reference}")
def update_draft(reference: str, body: DraftChange) -> dict:
    lines = [line.model_dump() for line in body.lines]
    return _run(lambda: simulation.update_draft(RecordHandle(reference, body.token), body.issue_date, body.due_date, lines))


@router.post("/drafts/{reference}/issue")
def issue_draft(reference: str, body: IssueRequest) -> dict:
    return _run(lambda: simulation.issue(RecordHandle(reference, body.token)))


@router.get("/invoices/{reference}")
def invoice_detail(reference: str, limit: Limit = 25, offset: Offset = 0) -> dict:
    return _run(lambda: simulation.invoice_detail(reference, limit, offset))


@router.post("/invoices/{reference}/collections")
def record_collection(reference: str, body: NewCollection) -> dict:
    return _run(lambda: simulation.record_collection(body.action_id, RecordHandle(reference, body.token), body.date, body.amount_minor))


@router.get("/partners/{account_code}/obligations")
def obligations(account_code: str, limit: Limit = 25, offset: Offset = 0) -> dict:
    return _run(lambda: simulation.obligations(account_code, limit, offset))
