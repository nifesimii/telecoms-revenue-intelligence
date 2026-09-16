"""Bounded commission reads, separate from agent and payment workflows."""
import csv
import io
import logging
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import Response

from backend.api.commission_schemas import CommissionDetail, CommissionPage, ZeroRecordPage
from backend.db import commission_workspace as workspace, queries
from backend.db.connection import execute_query

router = APIRouter(prefix='/commissions', tags=['Commission workspace'])
logger = logging.getLogger(__name__)


def public_source(source: str) -> str:
    return source.replace('ORSC', 'subscription commission')


def selection(
    mon_period: str = Query(..., pattern=r'^\d{6}$'),
    prior_period: str | None = Query(None, pattern=r'^\d{6}$'),
    stream: Literal['activation', 'orsc'] = 'activation',
) -> dict:
    periods = queries.get_available_periods()
    if mon_period not in periods or (prior_period and prior_period not in periods):
        raise HTTPException(404, 'Reporting period not available')
    if prior_period and prior_period >= mon_period:
        raise HTTPException(422, 'Comparison period must precede reporting period')
    return {'period': mon_period, 'prior_period': prior_period, 'stream': stream}


def filtered_collection(
    context: dict = Depends(selection),
    search: str = Query('', max_length=100),
    partner_class: str = Query('', max_length=100),
    status: Literal['all', 'with_zero', 'all_zero'] = 'all',
    sort_by: Literal['amount_ngn', 'dealer_name', 'delta_ngn', 'record_count', 'zero_count'] = 'amount_ngn',
    direction: Literal['asc', 'desc'] = 'desc',
) -> dict:
    try:
        data = workspace.collection(**context, search=search, partner_class=partner_class,
                                    status=status, sort_by=sort_by, direction=direction)
        return {**data, 'source': public_source(data['source'])}
    except Exception:
        logger.exception('Commission collection unavailable')
        raise HTTPException(503, 'Commission source unavailable. Retry later.') from None


@router.get('', response_model=CommissionPage)
def accounts(data: dict = Depends(filtered_collection),
             limit: int = Query(25, ge=1, le=100), offset: int = Query(0, ge=0)):
    return {**data, 'items': data['items'][offset:offset + limit], 'limit': limit, 'offset': offset}


@router.get('/export')
def export_accounts(data: dict = Depends(filtered_collection)):
    fields = ['mon_period', 'prior_period', 'stream', 'source', 'dealer_id', 'dealer_name',
              'account_profile_class', 'amount_ngn', 'prior_amount_ngn', 'delta_ngn',
              'delta_pct', 'record_count', 'zero_count', 'amount_basis']
    output = io.StringIO()
    writer = csv.DictWriter(output, fieldnames=fields)
    writer.writeheader()
    for row in data['items']:
        record = {key: row.get(key, data.get(key, '')) for key in fields}
        if data['stream'] == 'orsc':
            record['stream'] = 'Subscription commission'
        record['amount_basis'] = ('Recorded subscription revenue; not confirmed commission payable'
                                  if data['stream'] == 'orsc' else 'Recorded activation commission')
        record['source'] = public_source(record['source'])
        for key, value in record.items():
            if isinstance(value, str) and value.lstrip().startswith(('=', '+', '-', '@')):
                record[key] = "'" + value
        writer.writerow(record)
    stream_name = 'subscription' if data['stream'] == 'orsc' else data['stream']
    return Response(output.getvalue(), media_type='text/csv', headers={
        'Content-Disposition': f'attachment; filename="commission_{stream_name}_{data["mon_period"]}.csv"'})


@router.get('/{dealer_id}/detail', response_model=CommissionDetail)
def account_detail(dealer_id: str, context: dict = Depends(selection)):
    try:
        data = workspace.detail(**context, dealer_id=dealer_id)
    except Exception:
        logger.exception('Commission account unavailable')
        raise HTTPException(503, 'Commission evidence unavailable. Retry later.') from None
    if data is None:
        raise HTTPException(404, 'No account records for this stream and period')
    return {**data, 'source': public_source(data['source'])}


@router.get('/{dealer_id}/zero-records', response_model=ZeroRecordPage)
def zero_records(dealer_id: str, context: dict = Depends(selection),
                 limit: int = Query(25, ge=1, le=100), offset: int = Query(0, ge=0)):
    if context['stream'] != 'activation':
        raise HTTPException(422, 'Raw zero-commission evidence is activation-only')
    try:
        frame = execute_query('get_zero_commission_records',
                              {'mon_period': context['period'], 'distributor_code': dealer_id})
        # Nulls stay null; dates and identifiers have a stable string representation.
        frame = frame.sort_values(['first_activation_date', 'imei', 'product_code'], kind='stable')
        records = frame.iloc[offset:offset + limit].astype(object).where(frame.notna(), None).to_dict(orient='records')
        for record in records:
            for key in ('imei', 'product_code', 'product_name', 'invoice_date', 'first_activation_date'):
                if record.get(key) is not None:
                    record[key] = str(record[key])
    except Exception:
        logger.exception('Zero-commission records unavailable')
        raise HTTPException(503, 'Zero-commission evidence unavailable. Retry later.') from None
    return {'mon_period': context['period'], 'dealer_id': dealer_id, **workspace.provenance(),
            'items': records, 'total': len(frame), 'limit': limit, 'offset': offset}
