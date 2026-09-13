"""Bounded activation accounts and evidence, preserving legacy activation APIs."""
import csv
import io
import logging
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import Response

from backend.api.activation_workspace_schemas import (
    ActivationDetail, ActivationFindingFilter, ActivationPage, ActivationSort, ActivationView,
)
from backend.db import activation_workspace as workspace, queries

router = APIRouter(prefix='/activations/accounts', tags=['Activation workspace'])
logger = logging.getLogger(__name__)


def selection(
    mon_period: str = Query(..., pattern=r'^\d{4}(0[1-9]|1[0-2])$'),
    prior_period: str | None = Query(None, pattern=r'^\d{4}(0[1-9]|1[0-2])$'),
) -> dict:
    if prior_period and prior_period >= mon_period:
        raise HTTPException(422, 'Comparison period must precede reporting period')
    try:
        periods = queries.get_available_periods()
    except Exception:
        logger.exception('Activation reporting periods unavailable')
        raise HTTPException(503, 'Activation source unavailable. Retry later.') from None
    if mon_period not in periods or (prior_period and prior_period not in periods):
        raise HTTPException(404, 'Reporting period not available')
    return {'period': mon_period, 'prior_period': prior_period}


def filtered_collection(
    context: dict = Depends(selection),
    view: ActivationView = 'accounts',
    search: str = Query('', max_length=100),
    partner_class: str = Query('', max_length=100),
    finding: ActivationFindingFilter = 'all',
    sort_by: ActivationSort = 'activation_count',
    direction: Literal['asc', 'desc'] = 'desc',
) -> dict:
    try:
        return workspace.collection(**context, view=view, search=search,
                                    partner_class=partner_class, finding=finding,
                                    sort_by=sort_by, direction=direction)
    except Exception:
        logger.exception('Activation collection unavailable')
        raise HTTPException(503, 'Activation source unavailable. Retry later.') from None


@router.get('', response_model=ActivationPage)
def accounts(data: dict = Depends(filtered_collection),
             limit: int = Query(25, ge=1, le=100), offset: int = Query(0, ge=0)):
    return {**data, 'items': data['items'][offset:offset + limit], 'limit': limit, 'offset': offset}


@router.get('/export')
def export_accounts(data: dict = Depends(filtered_collection)):
    fields = [
        'mon_period', 'prior_period', 'view', 'source', 'generated_at',
        'dealer_id', 'dealer_name', 'account_profile_class', 'report_month',
        'activation_count', 'qualified_activation_count', 'non_qualified_activation_count',
        'qualification_rate_pct', 'activation_commission_amount',
        'prior_activation_count', 'prior_qualification_rate_pct', 'prior_commission_amount',
        'delta_activations', 'delta_qualification_rate', 'delta_commission_ngn', 'findings',
    ]
    output = io.StringIO()
    writer = csv.DictWriter(output, fieldnames=fields)
    writer.writeheader()
    for row in data['items']:
        record = {key: row.get(key, data.get(key, '')) for key in fields}
        record['findings'] = '; '.join(
            f'{f["label"]} ({f["severity"]}): {f["recommended_action"]}' for f in row['findings'])
        for key, value in record.items():
            if isinstance(value, str) and value.lstrip().startswith(('=', '+', '-', '@')):
                record[key] = "'" + value
        writer.writerow(record)
    return Response(output.getvalue(), media_type='text/csv', headers={
        'Content-Disposition': f'attachment; filename="activation_{data["view"]}_{data["mon_period"]}.csv"'})


@router.get('/{dealer_id}/detail', response_model=ActivationDetail)
def account_detail(dealer_id: str, context: dict = Depends(selection)):
    try:
        data = workspace.detail(**context, dealer_id=dealer_id)
    except Exception:
        logger.exception('Activation account unavailable')
        raise HTTPException(503, 'Activation source unavailable. Retry later.') from None
    if data is None:
        raise HTTPException(404, 'No activation records for this account and period')
    return data
