from decimal import Decimal

from backend.agent.answer_preparation import prepare_evidence


def test_decimal_totals_and_missing_periods_are_shared_without_mutating_sources():
    request = {'periods': ['202601', '202602', '202603'], 'operation': 'total'}
    evidence = {'measures': [{'measure': 'activation_commission', 'unit': 'ngn', 'periods': [
        {'period': '202601', 'status': 'available', 'total': 0.1, 'rows': []},
        {'period': '202602', 'status': 'available', 'total': 0.2, 'rows': []},
        {'period': '202603', 'status': 'unavailable', 'total': None, 'rows': []},
    ]}]}
    prepared = prepare_evidence(evidence, request)
    derived = prepared['measures'][0]['prepared']
    assert derived['total'] == Decimal('0.3')
    assert derived['missing_periods'] == ['202603']
    assert prepared['measures'][0]['periods'][2]['total'] is None
    assert 'prepared' not in evidence['measures'][0]


def test_ranked_subtotal_uses_selected_rows_and_stable_ties():
    request = {'periods': ['202601'], 'operation': 'breakdown', 'breakdown': 'dealer', 'limit': 2}
    evidence = {'measures': [{'measure': 'activation_commission', 'unit': 'ngn', 'periods': [
        {'period': '202601', 'status': 'available', 'total': 0.5, 'rows': [
            {'dealer_id': 'C', 'value': 0.1}, {'dealer_id': 'B', 'value': 0.2}, {'dealer_id': 'A', 'value': 0.2}]}]}]}
    derived = prepare_evidence(evidence, request)['measures'][0]['prepared']
    assert [row['dealer_id'] for row in derived['ranked_rows']] == ['A', 'B']
    assert derived['ranked_total'] == Decimal('0.4')


def test_investigation_product_page_contributions_use_decimal_arithmetic():
    evidence = {'investigation': {'status': 'available', 'family': 'commission_variance',
        'variance': {'totals': {'change_ngn': 0.3}}, 'records': [{'change_ngn': 0.1}],
        'zero_investigations': [], 'pagination': {'total': 3, 'offset': 1}}}
    result = prepare_evidence(evidence)['investigation']
    assert result['prepared']['outside_page_change_ngn'] == Decimal('0.2')
    assert result['prepared']['page_start'] == 2
    assert result['prepared']['page_end'] == 2


def test_recorded_zero_supports_comparison_but_unavailable_does_not():
    request = {'periods': ['202601', '202602'], 'operation': 'compare'}
    measure = {'measure': 'paid', 'unit': 'ngn', 'periods': [
        {'period': '202601', 'status': 'available', 'total': 0, 'rows': []},
        {'period': '202602', 'status': 'available', 'total': 0.2, 'rows': []}]}
    assert prepare_evidence({'measures': [measure]}, request)['measures'][0]['prepared']['comparison']['delta'] == Decimal('0.2')
    measure['periods'][0]['status'] = 'unavailable'
    assert prepare_evidence({'measures': [measure]}, request)['measures'][0]['prepared']['comparison'] is None


def test_variance_percentages_are_prepared_once_for_totals_and_product_rows():
    line = {'earlier_ngn': 0.3, 'later_ngn': 0.4, 'change_ngn': 0.1}
    evidence = {'measures': [{'measure': 'commission_variance', 'unit': 'ngn', 'periods': [
        {'period': '202602', 'status': 'available', 'total': None, 'rows': [],
         'variance': {'totals': line, 'products': [{**line, 'product': 'Router'}]}}]}]}
    variance = prepare_evidence(evidence)['measures'][0]['periods'][0]['variance']
    assert variance['totals']['prepared']['change_pct'] == Decimal('33.3')
    assert variance['products'][0]['prepared']['change_pct'] == Decimal('33.3')


def test_product_population_and_page_facts_precede_narrative_bounding():
    products = [{'product': f'P{i}', 'change_ngn': i + 1,
                 'earlier_activations': 1, 'later_activations': 2} for i in range(20)]
    evidence = {'variance': {'products': products}, 'status': 'available',
                'records': [{'imei': str(i)} for i in range(20)],
                'pagination': {'offset': 20, 'total': 50, 'has_more': True}}
    result = prepare_evidence(evidence)
    assert result['variance']['largest_positive_product_contribution'] == {'product': 'P19', 'change_ngn': Decimal(20)}
    assert result['variance']['all_product_commissions_increased'] is True
    assert result['record_page'] == {'first': 21, 'last': 40, 'shown': 20, 'total': 50, 'has_more': True}
