"""Bounded top-dealer commission answers use ranked rows, not portfolio totals."""
import re
from copy import deepcopy

from backend.agent.measure_response import render_measure_response
from backend.agent.tool_executor import execute_measure_request


def request(limit=1):
    return dict(measures=['activation_commission'], periods=['202606'], dealer_id=None,
                operation='breakdown', breakdown='dealer', limit=limit)


def plain(value):
    return re.sub(r'\\(.)', r'\1', value)


def test_top_sample_dealer_is_headline_and_only_requested_row():
    plan = request()
    payload = execute_measure_request(plan)
    before = deepcopy(payload)
    answer = plain(render_measure_response(plan, payload))
    assert 'NGN 1,267,922.85' in answer.split('\n\n')[0]
    assert '74050' in answer.split('\n\n')[0]
    assert len([line for line in answer.splitlines() if line.startswith('|')]) == 3
    assert 'Covered periods: 202606' in answer and 'Source:' in answer
    assert payload == before


def test_ranking_ties_use_dealer_code_and_limit_selected_sum():
    plan = request(2)
    payload = execute_measure_request(plan)
    period = payload['measures'][0]['periods'][0]
    period.update(rows=[dict(dealer_id=code, dealer_name=code, dimension=None, value=value)
                        for code, value in [('Z', 12), ('B', 15), ('A', 15)]],
                  total=42, total_rows=3, truncated=False)
    answer = plain(render_measure_response(plan, payload))
    assert 'NGN 30.00' in answer.split('\n\n')[0]
    assert 'NGN 42.00' not in answer
    assert answer.index('A (A)') < answer.index('B (B)')
    assert 'Z (Z)' not in answer


def test_ranked_total_provenance_does_not_claim_to_cover_entire_portfolio():
    plan = request(2)
    payload = execute_measure_request(plan)
    period = payload['measures'][0]['periods'][0]
    assert period['truncated']
    answer = plain(render_measure_response(plan, payload))
    assert 'any total includes all matching records' not in answer
    assert 'Showing the first 100 evidence rows' not in answer
    assert 'The headline amount covers only the displayed dealers.' in answer
    assert 'no completeness claim beyond the supplied dataset' in answer
    assert 'Source:' in answer and 'Covered periods: 202606' in answer
