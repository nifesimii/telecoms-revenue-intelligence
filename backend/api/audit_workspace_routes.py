"""Bounded Audit workspace API. Legacy readers remain compatible."""
import csv
import io
import json
import logging
from typing import Any, Literal
from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import Response
from pydantic import BaseModel
from backend.audit.trail import CONCLUSIONS
from backend.db import audit_workspace

router = APIRouter(prefix='/assurance/audit/records')
logger = logging.getLogger(__name__)

class AuditFilters(BaseModel):
    mon_period: str
    module: str
    search: str = ''
    subject: str = ''
    conclusion: str = ''
    confidence: str = ''
    caveats: str = 'all'
    caveat_step: str = ''
    sort_by: str = 'partner_name'
    sort_direction: str = 'asc'


class AuditSummary(BaseModel):
    trail_count: int
    subject_count: int
    dealer_count: int
    caveat_trail_count: int
    breakdown: list[dict[str, Any]]


class AuditPage(BaseModel):
    mon_period: str
    module: str
    retrieved_at: str
    summary: AuditSummary
    filtered_summary: AuditSummary
    items: list[dict[str, Any]]
    pagination: dict[str, int | bool]


def filters(
    mon_period: str = Query(pattern=r'^\d{4}(0[1-9]|1[0-2])$'),
    module: Literal['zero_commission', 'inventory_mismatch', 'eligibility_window', 'payment_reconciliation'] = 'zero_commission',
    search: str = Query(default='', max_length=200), subject: str = Query(default='', max_length=200),
    conclusion: str = '', confidence: Literal['', 'HIGH', 'MEDIUM', 'LOW'] = '',
    caveats: Literal['all', 'with', 'without'] = 'all', caveat_step: str = '',
    sort_by: Literal['partner_name', 'partner_code', 'conclusion', 'confidence', 'generated_at'] = 'partner_name',
    sort_direction: Literal['asc', 'desc'] = 'asc',
):
    if conclusion and conclusion not in CONCLUSIONS:
        raise HTTPException(422, 'Unknown recorded conclusion.')
    if caveat_step:
        from backend.audit.base import get_module
        if caveat_step not in get_module(module).step_names:
            raise HTTPException(422, 'Unknown caveat step for this module.')
    return AuditFilters(mon_period=mon_period, module=module, search=search, subject=subject,
                        conclusion=conclusion, confidence=confidence, caveats=caveats,
                        caveat_step=caveat_step, sort_by=sort_by, sort_direction=sort_direction)


def read_collection(params):
    try:
        return audit_workspace.collection(params)
    except Exception:
        logger.exception('Saved audit collection read failed')
        raise HTTPException(503, 'Saved evidence is unavailable. Please retry.')


@router.get('', response_model=AuditPage)
def records(params: AuditFilters = Depends(filters), limit: int = Query(25, ge=1, le=100), offset: int = Query(0, ge=0)) -> dict:
    result = read_collection(params)
    total = len(result['items'])
    result['items'] = result['items'][offset:offset + limit]
    result['pagination'] = dict(total=total, limit=limit, offset=offset, returned=len(result['items']), has_more=offset + limit < total)
    return result


def csv_value(value):
    if isinstance(value, (dict, list)):
        value = json.dumps(value, ensure_ascii=False, default=str)
    if isinstance(value, str) and value.lstrip().startswith(('=', '+', '-', '@', '\t', '\r', '\n')):
        return "'" + value
    return value


@router.get('/export')
def export_records(params: AuditFilters = Depends(filters)):
    result = read_collection(params)
    fields = [*audit_workspace.FIELDS, 'dealer_id', 'dealer_name', 'product_code', 'product_name', 'measures', 'partial_payment', 'limitations', 'export_filters', 'retrieved_at']
    output = io.StringIO()
    writer = csv.DictWriter(output, fieldnames=fields)
    writer.writeheader()
    for row in result['items']:
        scoped = {**row, 'export_filters': params.model_dump(), 'retrieved_at': result['retrieved_at']}
        writer.writerow({key: csv_value(scoped.get(key)) for key in fields})
    return Response(output.getvalue(), media_type='text/csv', headers={
        'Content-Disposition': f'attachment; filename="audit-{params.module}-{params.mon_period}.csv"'})


@router.get('/{exact_subject}')
def evidence(exact_subject: str, params: AuditFilters = Depends(filters), trail_id: str | None = Query(default=None, pattern=r"^[0-9]+$")) -> dict:
    try:
        result = audit_workspace.detail(exact_subject, params.mon_period, params.module, trail_id)
    except Exception:
        logger.exception('Saved audit evidence read failed')
        raise HTTPException(503, 'Saved evidence is unavailable. Please retry.')
    if result is None:
        raise HTTPException(404, 'No saved evidence for this exact subject, module and period.')
    return result
