"""Read-time wording overlays; source records and compatibility keys stay intact."""
from copy import deepcopy

from backend.terminology import normalize_generated_prose

# Only these audit-owned fields are generated prose. Product codes, source
# identifiers, user notes and other evidence must never be rewritten.
_DETAIL_PROSE = frozenset({'basis', 'note', 'limitation', 'limitations', 'explanation'})


def present_saved_trail(trail):
    presented = deepcopy(trail)
    for step in presented.get('steps') or []:
        for field in ('result', 'checked', 'caveat'):
            if isinstance(step.get(field), str):
                step['presentation_' + field] = normalize_generated_prose(step[field])
        detail = deepcopy(step.get('detail') or {})
        for key in _DETAIL_PROSE & detail.keys():
            value = detail[key]
            if isinstance(value, str):
                detail[key] = normalize_generated_prose(value)
            elif isinstance(value, list):
                detail[key] = [normalize_generated_prose(item) if isinstance(item, str) else item for item in value]
        step['presentation_detail'] = detail
    return presented
