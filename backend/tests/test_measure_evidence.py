"""Evidence projections exercise the real sample query boundary."""
import csv
import pytest

from backend import config
from backend.db.measure_evidence import _MEASURES, collect_measure_evidence, collect_dealer_codes
from backend.db import queries, financial_health


@pytest.fixture(autouse=True)
def sample_mode(monkeypatch):
    monkeypatch.setattr(config, 'USE_SAMPLE_DATA', True)


def request(measures, periods=None, dealer_id='296065', **kwargs):
    return collect_measure_evidence(dict(dict(measures=measures, periods=periods or ['202606'],
                                        dealer_id=dealer_id, operation='total',
                                        breakdown='dealer'), **kwargs))


def test_subscription_statement_projects_only_requested_recorded_amount():
    result = request(['subscription_commission'])
    measure, = result['measures']
    period, = measure['periods']
    assert period['total'] == 3050.0
    assert period['status'] == 'available'
    assert period['source'] == 'Subscription records · subscription statements'
    assert set(period['rows'][0]) == {'dealer_id', 'dealer_name', 'dimension', 'value'}
    assert period['rows'][0]['value'] == 3050.0


@pytest.mark.parametrize('measure', ['activation_count', 'activation_commission',
    'zero_commission_count', 'subscription_revenue', 'subscription_commission',
    'subscription_settled', 'subscription_outstanding', 'payment_paid',
    'payment_owed', 'payment_outstanding'])
def test_missing_period_and_missing_dealer_never_become_zero(measure):
    for result in (request([measure], ['202612']), request([measure], dealer_id='missing')):
        period = result['measures'][0]['periods'][0]
        assert period['status'] == 'unavailable'
        assert period['total'] is None
        assert period['rows'] == []


@pytest.mark.parametrize('measure', ['retail_sales_units', 'retail_sales_value', 'dealer_purchases'])
def test_unsupported_measures_do_not_substitute_available_activity(measure):
    period = request([measure])['measures'][0]['periods'][0]
    assert period['status'] == 'unavailable'
    assert period['total'] is None
    assert period['tool'] is None
    assert period['note']


def test_projection_retains_coverage_and_complete_total_beyond_bounded_rows():
    result = request(['activation_count'], ['202606', '202607'], dealer_id=None)
    available, missing = result['measures'][0]['periods']
    assert available['total_rows'] > 100
    assert available['truncated'] is True
    assert len(available['rows']) == 100
    assert available['total'] > sum(r['value'] for r in available['rows'])
    assert available['source'] == 'Activation records'
    assert missing['total'] is None


@pytest.mark.parametrize('measure', ['activation_qualified_count', 'activation_unqualified_count',
                                    'payment_status', 'financial_revenue', 'financial_net_profit'])
def test_additional_requested_measures_have_scoped_evidence(measure):
    result = request([measure], dealer_id=None)
    period = result['measures'][0]['periods'][0]
    assert period['status'] == 'available'
    assert period['rows']
    assert period['source']


def test_unsupported_filter_never_silently_returns_unfiltered_total():
    period = request(['subscription_revenue'], filter='disputed')['measures'][0]['periods'][0]
    assert period['status'] == 'unavailable'
    assert 'filter' in period['note'].lower()


def test_disputed_status_filter_is_applied_before_projection():
    period = request(['payment_status'], dealer_id=None, filter='disputed')['measures'][0]['periods'][0]
    assert period['status'] == 'available'
    assert {row['value'] for row in period['rows']} == {'DISPUTED'}
    assert period['total'] is None


def test_inventory_measure_reports_missing_evidence_instead_of_unknown_as_zero():
    result = request(['inventory_gap', 'inventory_recorded_purchases'], dealer_id=None)
    for measure in result['measures']:
        period = measure['periods'][0]
        assert period['status'] == 'unavailable'
        assert period['total'] is None
        assert 'complete' in period['note']


def test_coverage_checks_requested_source_file_even_when_query_cache_is_warm(monkeypatch, tmp_path):
    request(['activation_count'])
    paths = dict(config.SAMPLE_DATA_PATHS)
    paths['fbb_comm_dev_act'] = {'202606': tmp_path / 'absent.csv'}
    monkeypatch.setattr(config, 'SAMPLE_DATA_PATHS', paths)
    period = request(['activation_count'])['measures'][0]['periods'][0]
    assert period['status'] == 'unavailable'


def test_orsc_source_name_differs_from_activation_for_march():
    measures = request(['activation_count', 'subscription_revenue'], ['202603'])['measures']
    assert measures[0]['periods'][0]['source'] == 'Activation records'
    assert measures[1]['periods'][0]['source'] == 'Subscription records'


_DEMO_WORDS = ('synthetic', 'simulated', 'sample', 'demo', 'fictional')


@pytest.mark.parametrize('measure', list(_MEASURES))
def test_atlas_evidence_names_sources_without_demo_labels(measure):
    dealer = '74050' if measure.startswith('financial_') else '296065'
    result = request([measure], ['202603', '202606'], dealer_id=dealer)
    text = repr(result).lower()
    assert not [word for word in _DEMO_WORDS if word in text]
    assert all(period['source'] for period in result['measures'][0]['periods'])


def test_dealer_without_financial_statement_is_named_and_offers_alternatives():
    period = request(['financial_statements'], dealer_id='296065',
                     line_ids=['sales_revenue'])['measures'][0]['periods'][0]
    assert period['status'] == 'unavailable'
    assert period['rows'] == [] and period['total'] is None
    assert 'No financial statement on record for account 296065.' in period['note']
    assert 'activations or commission' in period['note']


def test_sales_revenue_selects_only_the_income_statement_line():
    period = request(['financial_statements'], dealer_id='74050',
                     line_ids=['sales_revenue'])['measures'][0]['periods'][0]
    assert period['status'] == 'available'
    assert [row['dimension'] for row in period['rows']] == ['Income statement: Sales revenue']


def test_commission_product_breakdown_is_recorded_denomination_evidence():
    period = request(['activation_commission'], breakdown='product')['measures'][0]['periods'][0]
    assert period['status'] == 'available'
    assert all(row['dimension'] for row in period['rows'])
    assert period['total'] == pytest.approx(sum(row['value'] for row in period['rows']))


def test_financial_statements_keep_line_items_without_nonsense_grand_total():
    period = request(['financial_statements'], dealer_id=None)['measures'][0]['periods'][0]
    assert period['status'] == 'available'
    assert period['total'] is None
    assert all(row['dimension'] for row in period['rows'])
    assert period['source'] == 'Whole-business financial statements · includes non-MTN activity'


@pytest.mark.parametrize(('measure', 'aggregation'), [
    ('inventory_gap', 'snapshot'), ('inventory_recorded_purchases', 'snapshot'),
    ('financial_statements', 'none'), ('payment_status', 'none'),
    ('activation_count', 'sum'), ('subscription_revenue', 'sum')])
def test_measure_declares_which_cross_period_aggregation_is_valid(measure, aggregation):
    assert request([measure])['measures'][0]['aggregation'] == aggregation


def test_unattributed_commission_remains_in_recorded_total_and_breakdown(tmp_path, monkeypatch):
    path = tmp_path / 'activation.csv'
    path.write_text('mon_period,distributor_code,distributor_name,account_profile_class,commission_rate,product_denomination\n'
                    '202606,123,Example Dealer,DEALER,100,Router\n'
                    '202606,123,Example Dealer,DEALER,50,\n')
    monkeypatch.setattr(config, 'SAMPLE_DATA_PATHS', {'fbb_comm_dev_act': {'202606': path}})
    queries._clear_csv_cache()
    try:
        period = request(['activation_commission'], dealer_id='123', breakdown='product')['measures'][0]['periods'][0]
        assert period['status'] == 'available'
        assert period['total'] == 150.0
        assert {row['dimension']: row['value'] for row in period['rows']} == {
            'Router': 100.0, 'Unattributed denomination': 50.0}
    finally:
        queries._clear_csv_cache()


def test_unavailable_measure_does_not_require_fabricated_period():
    result = collect_measure_evidence({'measures': ['retail_sales_units'], 'periods': []})
    assert result['requested_periods'] == []
    measure, = result['measures']
    assert measure['periods'] == []
    assert 'transactions' in measure['note']
    with pytest.raises(ValueError, match='require requested periods'):
        collect_measure_evidence({'measures': ['activation_count'], 'periods': []})


def test_inventory_scenario_rows_carry_no_demo_label_and_notes_are_bounded(tmp_path, monkeypatch):
    with config.SAMPLE_DATA_PATHS['fbb_comm_dev_act']['202606'].open(newline='') as handle:
        reader = csv.DictReader(handle)
        columns = reader.fieldnames
        row = next(r for r in reader if r['distributor_code'] == '74050' and r['product_code'] == '1283279')
    path = tmp_path / 'activation.csv'
    with path.open('w', newline='') as handle:
        writer = csv.DictWriter(handle, fieldnames=columns)
        writer.writeheader()
        writer.writerow(row)
    monkeypatch.setattr(config, 'SAMPLE_DATA_PATHS', {**config.SAMPLE_DATA_PATHS, 'fbb_comm_dev_act': {'202606': path}})
    queries._clear_csv_cache()
    try:
        period = request(['inventory_gap'], dealer_id='74050')['measures'][0]['periods'][0]
        assert period['status'] == 'available'
        assert period['source'] == 'Inventory comparison records · purchase scenarios'
        assert 'synthetic' not in period['rows'][0]['dimension'].lower()
        assert len(period['note']) < 500
        assert 'do not sum across months' in period['note']
    finally:
        queries._clear_csv_cache()


def test_identity_lookup_preserves_raw_codes_and_coverage_without_measure_fields():
    result = collect_dealer_codes({'dealer_name': financial_health.DEALERS[0]['dealer_name'], 'periods': []})
    assert result['rows']
    assert result['data_source'] == 'SAMPLE'
    assert result['coverage_by_source']
    assert result['page_size'] == 100
    assert set(result['rows'][0]) == {'dealer_id', 'recorded_names', 'first_observed_period', 'last_observed_period', 'sources'}


def test_identity_lookup_does_not_broaden_gapped_requested_months():
    with pytest.raises(ValueError, match='contiguous'):
        collect_dealer_codes({'dealer_name': 'Example Dealer', 'periods': ['202601', '202603']})


def test_financial_kpis_preserve_missing_schedule_and_source_units():
    dealer = next(d for d in financial_health.DEALERS if d['scenario_id'] == 'missing_schedule')
    measure, = request(['financial_kpis'], dealer_id=dealer['dealer_id'])['measures']
    assert measure['aggregation'] == 'none'
    assert measure['unit'] == 'text'
    period, = measure['periods']
    values = {row['dimension']: row['value'] for row in period['rows']}
    assert values['Debt-service coverage'] == 'unavailable: Repayment schedule unavailable.'
    assert '%' in values['Gross profit margin']
    assert values['Operating cash flow'].startswith('NGN ')
    assert period['total'] is None


@pytest.mark.parametrize(('selector', 'expected'), [
    ({'kpi_ids': ['current_ratio']}, ['Current ratio']),
])
def test_financial_kpi_selection_excludes_unrequested_ratios(selector, expected):
    period = request(['financial_kpis'], dealer_id=financial_health.DEALERS[0]['dealer_id'], **selector)['measures'][0]['periods'][0]
    assert [row['dimension'] for row in period['rows']] == expected


def test_cashflow_selection_excludes_other_statements_and_single_line_excludes_other_lines():
    dealer = financial_health.DEALERS[0]['dealer_id']
    period = request(['financial_statements'], dealer_id=dealer, statement_ids=['cashflow'])['measures'][0]['periods'][0]
    assert period['rows'] and all(row['dimension'].startswith('Cash flow statement:') for row in period['rows'])
    period = request(['financial_statements'], dealer_id=dealer, line_ids=['cash'])['measures'][0]['periods'][0]
    assert [row['dimension'] for row in period['rows']] == ['Balance sheet: Cash and bank balances']


@pytest.mark.parametrize('selectors', [{'kpi_ids': ['current_ratio']}, {'line_ids': ['cash']}, {'statement_ids': ['income']}])
def test_selectors_cannot_be_silently_ignored_for_other_measures(selectors):
    with pytest.raises(ValueError, match='selector'):
        request(['activation_count'], **selectors)


def test_explanation_reads_only_bounded_scoped_zero_record_observations():
    result = request(['activation_commission'], dealer_id='296065', operation='explain')
    observation, = result['explanations']
    assert observation['dealer_id'] == '296065'
    assert observation['tool'] == 'get_zero_commission_records'
    assert observation['records_checked'] <= 100
    assert observation['records_with_dates'] <= observation['records_checked']
    assert 'authoritative' in observation['note']
    assert not {'imei', 'unit_selling_price', 'commission_rate'} & observation.keys()
    assert not request(['subscription_revenue'], operation='explain')['explanations']
    assert not request(['activation_commission'], dealer_id=None, operation='explain')['explanations']


def test_explanation_date_coverage_is_bounded_and_does_not_classify_a_cause(tmp_path, monkeypatch):
    path = tmp_path / 'zeros.csv'
    fields = ['mon_period', 'distributor_code', 'distributor_name', 'account_profile_class',
              'commission_rate', 'product_denomination', 'imei', 'product_name', 'product_code',
              'invoice_date', 'first_activation_date', 'unit_selling_price']
    with path.open('w', newline='') as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        for index in range(101):
            writer.writerow(dict(mon_period='202606', distributor_code='123', distributor_name='Example Dealer',
                                 account_profile_class='DEALER', commission_rate=0, product_denomination='Router',
                                 imei=str(index), product_name='Router', product_code='1',
                                 invoice_date='2026-06-01', first_activation_date='2026-06-02', unit_selling_price=1000))
    monkeypatch.setattr(config, 'SAMPLE_DATA_PATHS', {'fbb_comm_dev_act': {'202606': path}})
    queries._clear_csv_cache()
    try:
        observation, = request(['zero_commission_count'], dealer_id='123', operation='explain')['explanations']
        assert observation['records_checked'] == 100
        assert observation['records_with_dates'] == 100
        assert observation['total_records'] == 101
        assert observation['bounded'] is True
        assert 'authoritative eligibility rule' in observation['note']
    finally:
        queries._clear_csv_cache()


def test_invalid_financial_line_selector_is_rejected_before_reading_reports():
    with pytest.raises(ValueError, match='selector'):
        request(['financial_statements'], line_ids=['invented_sales_total'])
