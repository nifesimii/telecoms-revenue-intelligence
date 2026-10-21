"""Bounded affected-account discovery from a single existing summary read."""
from backend.db import queries
from backend.db.connection import execute_query


def discover_zero_commission(period: str, *, limit: int = 20, offset: int = 0) -> dict:
    import re
    if not re.fullmatch(r'\d{4}(0[1-9]|1[0-2])', period) or not 1 <= limit <= 100 or offset < 0:
        raise ValueError('Invalid discovery scope')
    result = dict(status='unavailable', period=period, workspace='commission',
                  ranking='zero_commission_count_desc_dealer_id_asc', total_count=None,
                  items=[], limit=limit, offset=offset, has_more=False, tools=[])
    try:
        if not queries.has_source_period('fbb_comm_dev_act', period):
            return result
        result['tools'] = ['get_dealer_summary']
        frame = execute_query('get_dealer_summary', {'mon_period': period, 'distributor_code': None})
        if frame.empty:
            return result
        items = []
        seen = set()
        for row in frame.to_dict(orient='records'):
            code = row['dealer_id']
            count = row['zero_commission_count']
            if not isinstance(code, str) or not code.strip() or code in seen or count < 0 or int(count) != count:
                return result
            seen.add(code)
            if count > 0:
                items.append(dict(dealer_id=code, dealer_name=str(row['dealer_name']),
                                  zero_commission_count=int(count)))
        items.sort(key=lambda item: (-item['zero_commission_count'], item['dealer_id']))
        return {**result, 'status': 'available', 'total_count': len(items),
                'items': items[offset:offset + limit], 'has_more': offset + limit < len(items)}
    except Exception:
        return result
