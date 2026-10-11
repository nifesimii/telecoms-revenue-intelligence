"""Public regressions for population overclaims observed in real-provider answers."""
from backend.agent.agent import run_agent
from backend.tests.test_agent import _run, evidence_period, install_scope_provider, measure_scope


def test_zero_commission_subset_cannot_be_described_as_the_dealers_whole_month(monkeypatch):
    candidate = ('Dealer 296065 earned zero commission in 202606 because all 50 activations '
                 'failed to earn commission: 48 records had a product lookup miss in the '
                 'calculation-month USP snapshot, and 2 records had activation outside '
                 'the invoice-to-activation eligibility window.')
    install_scope_provider(monkeypatch, measure_scope('zero_commission_count', dealer_id='296065',
        periods=['202606'], operation='explain'), answer=candidate)
    result = _run(run_agent('Why does dealer 296065 have zero commission in June 2026?'))
    assert 'Dealer 296065 earned zero commission' not in result['response']
    assert 'all 50 activations' not in result['response']
    assert evidence_period(result)['total'] == 50
    investigation = result['raw_data']['measure_evidence']['explanations'][0]['investigation']
    assert investigation['total_records'] == 50
    assert [cause['count'] for cause in investigation['causes']] == [48, 2]


def test_product_with_flat_volume_prevents_claim_that_every_tier_increased(monkeypatch):
    candidate = ("Dealer 74050's activation commission increased NGN 51,331.98 from 202605 "
                 'to 202606 due to higher qualified activation volume across all '
                 'commission-bearing product tiers.')
    install_scope_provider(monkeypatch, measure_scope('commission_variance', dealer_id='74050',
        periods=['202605', '202606'], operation='explain'), answer=candidate)
    result = _run(run_agent("Why did dealer 74050's activation commission change from May to June 2026?"))
    assert 'across all commission-bearing product tiers' not in result['response']
    variance = evidence_period(result)['variance']
    assert variance['totals']['change_ngn'] == 51331.98
    flat = next(row for row in variance['products'] if row['product'] == 'HYNETFLEX_1')
    assert flat['earlier_activations'] == flat['later_activations'] == 8
    assert flat['earlier_ngn'] == flat['later_ngn'] == 26790.72


def test_supported_zero_commission_subset_explanation_is_returned(monkeypatch):
    candidate = ('Dealer 296065 had 50 zero-commission activations in 202606. '
                 'Of those, 48 had a product lookup miss and 2 were outside the eligibility window.')
    install_scope_provider(monkeypatch, measure_scope('zero_commission_count', dealer_id='296065',
        periods=['202606'], operation='explain'), answer=candidate)
    result = _run(run_agent('Why did these records earn no commission?'))
    assert result['response'].startswith('Dealer 296065 had 50 zero-commission activations')
    assert '48 had a product lookup miss' in result['response']
    assert '2 were outside the eligibility window' in result['response']
    assert evidence_period(result)['total'] == 50


def test_relative_clause_can_identify_the_zero_commission_subset(monkeypatch):
    candidate = 'Dealer 296065 had 50 activations in 202606 that earned zero commission.'
    install_scope_provider(monkeypatch, measure_scope('zero_commission_count', dealer_id='296065',
        periods=['202606'], operation='explain'), answer=candidate)
    result = _run(run_agent('Why did these records earn no commission?'))
    assert result['response'].startswith('Dealer 296065 had 50 activations in June 2026 that earned zero commission.')


def test_zero_commission_on_explicit_records_is_a_supported_subset(monkeypatch):
    candidate = 'Dealer 296065 earned zero commission in 202606 on 50 activation records.'
    install_scope_provider(monkeypatch, measure_scope('zero_commission_count', dealer_id='296065',
        periods=['202606'], operation='explain'), answer=candidate)
    result = _run(run_agent('Why did these records earn no commission?'))
    assert result['response'].startswith('Dealer 296065 earned zero commission in June 2026 on 50 activation records.')


def test_supported_partial_product_increase_and_flat_tier_are_returned(monkeypatch):
    candidate = ('Commission increased by NGN 51,331.98 for dealer 74050 from 202605 to 202606. '
                 'MIFI_1 contributed NGN 33,906.87; HYNETFLEX_1 remained flat.')
    install_scope_provider(monkeypatch, measure_scope('commission_variance', dealer_id='74050',
        periods=['202605', '202606'], operation='explain'), answer=candidate)
    result = _run(run_agent('Which products explain the change?'))
    assert result['response'].startswith('Commission increased by NGN 51,331.98')
    assert 'MIFI_1 contributed NGN 33,906.87' in result['response']
    assert 'HYNETFLEX_1 remained flat.' in result['response']
    variance = evidence_period(result)['variance']
    assert variance['totals']['change_ngn'] == 51331.98


def test_volume_growth_is_not_rejected_because_commission_decreased():
    from backend.tests.test_narrative import compose, provider
    client, _ = provider(lambda payload, attempt: 'Higher activations across all products.')
    answer = compose(client, evidence={'products': [{'earlier_activations': 1,
        'later_activations': 2, 'change_ngn': -10}]}, validated_context='')
    assert answer.startswith('Higher activations across all products.')


def test_smaller_product_increase_cannot_be_called_the_largest_contributor(monkeypatch):
    candidate = ('The largest contributor was MIFI_1, which added NGN 13,813.91. '
                 '5G ROUTER contributed NGN 16,431.62.')
    install_scope_provider(monkeypatch, measure_scope('commission_variance', dealer_id='296065',
        periods=['202605', '202606'], operation='explain'), answer=candidate)
    result = _run(run_agent('Why did commission change for dealer 296065 between May and June 2026?'))
    assert 'The largest contributor was MIFI_1' not in result['response']
    products = evidence_period(result)['variance']['products']
    largest = max(products, key=lambda product: product['change_ngn'])
    assert largest['product'] == '5G ROUTER' and largest['change_ngn'] == 16431.62
    assert next(p for p in products if p['product'] == 'MIFI_1')['change_ngn'] == 13813.91


def test_accepted_activation_count_does_not_reintroduce_prior_commission_figures(monkeypatch):
    candidate = ('Stone Light Networks recorded 887 activations in 202606, '
                 'earning NGN 1,267,922.85 in activation commission.')
    calls, _ = install_scope_provider(monkeypatch, measure_scope('activation_count', periods=['202606']),
                                     answer=candidate)
    history = [{'role': 'user', 'content': 'What are my customer sales?'},
               {'role': 'assistant', 'content': 'Customer sales evidence is unavailable. I can show recorded activations if you want. Earlier recorded activation commission was NGN 1,267,922.85.'}]
    result = _run(run_agent('Yes, show recorded activations instead.', history,
        reporting_period='202606', investigation_context='Selected exact dealer account 74050; Commission workspace.'))
    assert 'NGN' not in result['response']
    assert evidence_period(result)['total'] == 887
    import json
    payload = json.loads(calls[1]['messages'][-1]['content'])
    assert not any(f.get('unit') == 'ngn' or str(f['display']).startswith('NGN') for f in payload['facts'])
    assert [m['measure'] for m in payload['evidence']['measure_evidence']['measures']] == ['activation_count']


def test_true_largest_product_contributor_is_returned(monkeypatch):
    candidate = ('The largest contributor was 5G ROUTER, which added NGN 16,431.62. '
                 'MIFI_1 contributed NGN 13,813.91.')
    install_scope_provider(monkeypatch, measure_scope('commission_variance', dealer_id='296065',
        periods=['202605', '202606'], operation='explain'), answer=candidate)
    result = _run(run_agent('Which product contributed most to the commission increase?'))
    assert result['response'].startswith('The largest contributor was 5G ROUTER, which added NGN 16,431.62.')
    assert 'MIFI_1 contributed NGN 13,813.91.' in result['response']
    products = evidence_period(result)['variance']['products']
    assert max(products, key=lambda product: product['change_ngn'])['product'] == '5G ROUTER'


def test_smaller_tier_cannot_be_called_the_largest_absolute_increase(monkeypatch):
    candidate = ('The MIFI_1 tier contributed the largest absolute increase at NGN 13,813.91, '
                 'growing from 230 to 241 activations, and the 5G ROUTER tier added NGN 16,431.62 '
                 'with an increase from 58 to 60 activations.')
    install_scope_provider(monkeypatch, measure_scope('commission_variance', dealer_id='296065',
        periods=['202605', '202606'], operation='explain'), answer=candidate)
    result = _run(run_agent('Why did commission change for dealer 296065 between May and June 2026?'))
    assert 'MIFI_1 tier contributed the largest absolute increase' not in result['response']
    products = evidence_period(result)['variance']['products']
    largest = max(products, key=lambda product: abs(product['change_ngn']))
    assert largest['product'] == '5G ROUTER' and largest['change_ngn'] == 16431.62


def test_final_model_receives_computed_largest_positive_product_without_changing_raw_evidence(monkeypatch):
    calls, _ = install_scope_provider(monkeypatch, measure_scope('commission_variance', dealer_id='296065',
        periods=['202605', '202606'], operation='explain'),
        answer='5G ROUTER contributed the largest increase at NGN 16,431.62.')
    result = _run(run_agent('Which product contributed most to the increase?'))
    import json
    payload = json.loads(calls[1]['messages'][-1]['content'])
    variance = payload['evidence']['measure_evidence']['measures'][0]['periods'][0]['variance']
    assert variance['largest_positive_product_contribution'] == {
        'product': '5G ROUTER', 'change_ngn': '16431.62'}
    raw_variance = evidence_period(result)['variance']
    assert 'largest_positive_product_contribution' not in raw_variance
    assert len(raw_variance['products']) == len(variance['products'])
    assert raw_variance['totals']['change_ngn'] == 39873.42
    assert result['response'].startswith('5G ROUTER contributed the largest increase at NGN 16,431.62.')


def test_honest_denial_of_smaller_product_as_largest_is_allowed(monkeypatch):
    candidate = ('MIFI_1 was not the largest contributor. '
                 '5G ROUTER contributed the largest increase at NGN 16,431.62.')
    install_scope_provider(monkeypatch, measure_scope('commission_variance', dealer_id='296065',
        periods=['202605', '202606'], operation='explain'), answer=candidate)
    result = _run(run_agent('Was MIFI_1 the largest contributor?'))
    assert result['response'].startswith(candidate)
    assert evidence_period(result)['variance']['totals']['change_ngn'] == 39873.42


def test_product_contributions_do_not_establish_a_higher_value_mix(monkeypatch):
    candidate = ('Dealer 74050 activation commission increased by NGN 51,331.98 '
                 'because additional activations concentrated in higher-value products. '
                 'MIFI_1 contributed NGN 33,906.87.')
    install_scope_provider(monkeypatch, measure_scope('commission_variance', dealer_id='74050',
        periods=['202605', '202606'], operation='explain'), answer=candidate)
    result = _run(run_agent('Why did activation commission change?'))
    assert 'additional activations concentrated in higher-value products' not in result['response']
    variance = evidence_period(result)['variance']
    assert variance['totals']['change_ngn'] == 51331.98
    assert next(p for p in variance['products'] if p['product'] == 'MIFI_1')['change_ngn'] == 33906.87


def test_positive_commission_does_not_mean_every_denomination_increased(monkeypatch):
    candidate = ('All product denominations with positive commission increased: '
                 '5G ROUTER added NGN 8,215.81, HYNETFLEX contributed NGN 6,697.68, '
                 'and MIFI added NGN 2,511.62.')
    install_scope_provider(monkeypatch, measure_scope('commission_variance', dealer_id='74050',
        periods=['202605', '202606'], operation='explain'), answer=candidate)
    result = _run(run_agent('Did every commission-bearing product increase?'))
    assert 'All product denominations with positive commission increased' not in result['response']
    flat = next(p for p in evidence_period(result)['variance']['products'] if p['product'] == 'HYNETFLEX_1')
    assert flat['earlier_ngn'] == flat['later_ngn'] == 26790.72


def test_model_receives_complete_product_growth_flags_without_changing_raw_evidence(monkeypatch):
    calls, _ = install_scope_provider(monkeypatch, measure_scope('commission_variance', dealer_id='74050',
        periods=['202605', '202606'], operation='explain'),
        answer='MIFI_1 contributed NGN 33,906.87, while HYNETFLEX_1 remained flat.')
    result = _run(run_agent('Did every commission-bearing product increase?'))
    import json
    payload = json.loads(calls[1]['messages'][-1]['content'])
    variance = payload['evidence']['measure_evidence']['measures'][0]['periods'][0]['variance']
    assert variance['all_product_commissions_increased'] is False
    assert variance['all_product_activation_counts_increased'] is False
    raw = evidence_period(result)['variance']
    assert 'all_product_commissions_increased' not in raw
    assert 'all_product_activation_counts_increased' not in raw
    from decimal import Decimal
    assert [(p['product'], Decimal(str(p['change_ngn']))) for p in raw['products']] == [(p['product'], Decimal(p['change_ngn'])) for p in variance['products']]
    assert all('prepared' not in p for p in raw['products'])
    assert result['response'].startswith('MIFI_1 contributed NGN 33,906.87, while HYNETFLEX_1 remained flat.')


def test_zero_product_delta_cannot_be_described_as_unchanged_commission_level(monkeypatch):
    install_scope_provider(monkeypatch, measure_scope('commission_variance', dealer_id='74050',
        periods=['202605', '202606'], operation='explain'),
        answer='HYNETFLEX_1 remained unchanged at NGN 0.00.')
    result = _run(run_agent('What changed for HYNETFLEX_1?'))
    assert 'HYNETFLEX_1 remained unchanged at NGN 0.00' not in result['response']
    flat = next(p for p in evidence_period(result)['variance']['products'] if p['product'] == 'HYNETFLEX_1')
    assert flat['earlier_ngn'] == flat['later_ngn'] == 26790.72
    assert flat['change_ngn'] == 0


def test_unchanged_product_commission_can_name_its_actual_level(monkeypatch):
    answer = 'HYNETFLEX_1 remained unchanged at NGN 26,790.72.'
    install_scope_provider(monkeypatch, measure_scope('commission_variance', dealer_id='74050',
        periods=['202605', '202606'], operation='explain'), answer=answer)
    result = _run(run_agent('What changed for HYNETFLEX_1?'))
    assert result['response'].startswith(answer)
    flat = next(p for p in evidence_period(result)['variance']['products'] if p['product'] == 'HYNETFLEX_1')
    assert flat['earlier_ngn'] == flat['later_ngn'] == 26790.72


def test_total_activation_counts_cannot_be_called_qualified(monkeypatch):
    answer = 'Qualified activation volume grew from 846 to 887 devices.'
    install_scope_provider(monkeypatch, measure_scope('commission_variance', dealer_id='74050',
        periods=['202605', '202606'], operation='explain'), answer=answer)
    result = _run(run_agent('Why did dealer 74050 activation commission change?'))
    assert answer not in result['response']
    totals = evidence_period(result)['variance']['totals']
    assert totals['earlier_activations'] == 846 and totals['later_activations'] == 887


def test_total_activation_counts_can_be_described_as_total_volume(monkeypatch):
    answer = 'Total activation volume grew from 846 to 887 devices.'
    install_scope_provider(monkeypatch, measure_scope('commission_variance', dealer_id='74050',
        periods=['202605', '202606'], operation='explain'), answer=answer)
    result = _run(run_agent('How did total activation volume change?'))
    assert result['response'].startswith(answer)
    totals = evidence_period(result)['variance']['totals']
    assert totals['earlier_activations'] == 846 and totals['later_activations'] == 887
