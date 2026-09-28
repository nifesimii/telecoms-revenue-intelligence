"""Read-only subscription workspace; bounded evidence and filtered export."""
import csv
import io
import logging
from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import Response
from backend.api.subscription_schemas import (
    SubscriptionPage, SubscriptionDetail, DevicePage, DealerSort, DeviceSort,
    Direction, PaymentFilter, ReasonFilter,
)
from backend.db import subscription_workspace as workspace

router = APIRouter(prefix='/subscriptions', tags=['Subscription commission'])
logger = logging.getLogger(__name__)


def period_selection(mon_period: str = Query(..., pattern=r'^\d{6}$')):
    try:
        workspace.validate_period(mon_period)
    except ValueError:
        raise HTTPException(422, 'Expected a valid reporting month YYYYMM') from None
    return mon_period


def filters(search: str = Query('', max_length=100), payment_status: PaymentFilter = 'all',
            sort_by: DealerSort = 'simulated_commission_ngn', direction: Direction = 'desc'):
    return dict(search=search, payment_status=payment_status, sort_by=sort_by, direction=direction)


def read(operation, *args, **kwargs):
    try:
        return operation(*args, **kwargs)
    except Exception:
        logger.exception('Subscription evidence unavailable')
        raise HTTPException(503, 'Subscription source unavailable. Retry later.') from None


@router.get('', response_model=SubscriptionPage)
def collection(period: str = Depends(period_selection), selection: dict = Depends(filters),
               limit: int = Query(25, ge=1, le=100), offset: int = Query(0, ge=0)):
    return read(workspace.page, period, limit=limit, offset=offset, **selection)


@router.get('/export')
def export(period: str = Depends(period_selection), selection: dict = Depends(filters)):
    data = read(workspace.collection, period, **selection)
    fields = ['mon_period', 'source', 'synthetic', 'policy_label', 'evidence_as_of', 'commission_available',
              'dealer_id', 'dealer_name', 'account_profile_class', 'device_count', *workspace.AMOUNTS,
              'payment_status', 'unknown_commission_count', 'reason_counts']
    output = io.StringIO()
    writer = csv.DictWriter(output, fieldnames=fields)
    writer.writeheader()
    for row in data['items']:
        record = {key: row.get(key, data.get(key)) for key in fields}
        for key, value in record.items():
            if isinstance(value, str) and value.lstrip().startswith(('=', '+', '-', '@')):
                record[key] = "'" + value
        writer.writerow(record)
    return Response(output.getvalue(), media_type='text/csv', headers={
        'Content-Disposition': f'attachment; filename="subscription_commission_{period}.csv"',
        'X-Data-Source': 'synthetic' if data['synthetic'] else 'revenue-only',
    })


@router.get('/{dealer_id}/detail', response_model=SubscriptionDetail)
def detail(dealer_id: str, period: str = Depends(period_selection)):
    result = read(workspace.detail, period, dealer_id)
    if result is None:
        raise HTTPException(404, 'No subscription records for this dealer and period')
    return result


@router.get('/{dealer_id}/devices', response_model=DevicePage)
def devices(dealer_id: str, period: str = Depends(period_selection),
            limit: int = Query(25, ge=1, le=100), offset: int = Query(0, ge=0),
            reason: ReasonFilter = 'all', search: str = Query('', max_length=100),
            sort_by: DeviceSort = 'imei', direction: Direction = 'asc'):
    return read(workspace.devices, period, dealer_id, limit=limit, offset=offset,
                reason=reason, search=search, sort_by=sort_by, direction=direction)
