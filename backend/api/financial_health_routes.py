"""Read-only synthetic financial statements, isolated from live financial data."""
from typing import Literal
from fastapi import APIRouter, HTTPException, Query
from backend.db.financial_health import get_report, list_dealers

router = APIRouter(prefix='/financial-health', tags=['Synthetic financial health'])
PERIOD_PATTERN = r'^\d{4}(0[1-9]|1[0-2])$'


@router.get('')
def collection(
    mon_period: str = Query(..., pattern=PERIOD_PATTERN),
    search: str = Query('', max_length=200),
    sort_by: Literal['dealer_name', 'revenue', 'net_profit'] = 'dealer_name',
    direction: Literal['asc', 'desc'] = 'asc',
    limit: int = Query(25, ge=1, le=100),
    offset: int = Query(0, ge=0),
) -> dict:
    return list_dealers(mon_period, search, sort_by, direction, limit, offset)


@router.get('/{dealer_id}')
def detail(dealer_id: str, mon_period: str = Query(..., pattern=PERIOD_PATTERN)) -> dict:
    report = get_report(dealer_id, mon_period)
    if report is None:
        raise HTTPException(404, 'No synthetic statement exists for this dealer and month.')
    return report
