"""Behavior checks for the evidence-only answer boundary; no provider required."""
from copy import deepcopy

import pytest

from backend.agent.measure_response import render_measure_response


def activation_fixture():
    return (
        {"measures": ["activations"], "periods": ["202603"], "dealer_id": "D1", "operation": "total"},
        {"requested_periods": ["202603"], "dealer_id": "D1", "measures": [{
            "measure": "activations", "label": "Recorded activations", "unit": "count",
            "periods": [{"period": "202603", "status": "available", "source": "SAMPLE",
                         "rows": [{"dealer_id": "D1", "dealer_name": "First Dealer", "dimension": None, "value": 12}],
                         "total": 12, "note": "", "tool": "get_activation_summary"}],
        }]},
    )


def test_requested_activation_total_has_context_and_provenance_only():
    request, evidence = activation_fixture()
    answer = render_measure_response(request, evidence)
    assert "Recorded activations: 12" in answer
    assert "D1" in answer and "202603" in answer and "SAMPLE" in answer
    assert r"get\_activation\_summary" not in answer
    assert "commission" not in answer.lower()
    assert "sales" not in answer.lower()


def test_partial_year_keeps_missing_months_distinct_from_recorded_zero():
    request, evidence = activation_fixture()
    request["periods"] = [f"2026{month:02}" for month in range(1, 13)]
    evidence["requested_periods"] = request["periods"]
    evidence["measures"][0]["periods"].append({
        "period": "202604", "status": "available", "source": "SAMPLE",
        "rows": [], "total": 0, "note": "", "tool": "get_activation_summary",
    })
    evidence["measures"][0]["periods"].append({
        "period": "202605", "status": "unavailable", "source": "SAMPLE",
        "rows": [], "total": None, "note": "No source records.", "tool": "get_activation_summary",
    })
    answer = render_measure_response(request, evidence)
    assert "Partial total" in answer and "12" in answer
    assert "Covered periods: 202603, 202604" in answer
    assert "Unavailable periods: 202601, 202602, 202605" in answer
    assert "202612" in answer and "not zero" in answer
    assert "No source records" in answer


@pytest.mark.parametrize("mutation", [
    "measure", "period", "requested_periods", "dealer", "row_dealer", "nan", "infinity", "duplicate_period", "duplicate_measure",
])
def test_rejects_evidence_outside_request_or_nonfinite_numbers(mutation):
    request, evidence = activation_fixture()
    measure = evidence["measures"][0]
    period = measure["periods"][0]
    if mutation == "measure":
        measure["measure"] = "commission"
    elif mutation == "period":
        period["period"] = "202604"
    elif mutation == "requested_periods":
        evidence["requested_periods"] = ["202604"]
    elif mutation == "dealer":
        evidence["dealer_id"] = "D2"
    elif mutation == "row_dealer":
        period["rows"][0]["dealer_id"] = "D2"
    elif mutation == "nan":
        period["rows"][0]["value"] = float("nan")
    elif mutation == "infinity":
        period["total"] = float("inf")
    elif mutation == "duplicate_period":
        measure["periods"].append(deepcopy(period))
    else:
        evidence["measures"].append(deepcopy(measure))
    with pytest.raises(ValueError):
        render_measure_response(request, evidence)


def test_explanation_compares_requested_amounts_without_claiming_causation():
    request, evidence = activation_fixture()
    request.update(measures=["activation_commission"], periods=["202602", "202603"], operation="explain")
    evidence["requested_periods"] = request["periods"]
    measure = evidence["measures"][0]
    measure.update(measure="activation_commission", label="Activation commission", unit="ngn")
    prior = deepcopy(measure["periods"][0])
    prior.update(period="202602", total=1200)
    prior["rows"][0]["value"] = 1200
    measure["periods"][0]["total"] = 900
    measure["periods"][0]["rows"][0]["value"] = 900
    measure["periods"].insert(0, prior)
    answer = render_measure_response(request, evidence)
    assert "202602: NGN 1,200.00" in answer
    assert "202603: NGN 900.00" in answer
    assert "Change (202603 − 202602): NGN -300.00" in answer
    assert "unverified" in answer and "source records" in answer
    assert "USP snapshot miss" not in answer
    assert "NGN 2,100.00" not in answer


def test_comparison_with_missing_evidence_does_not_invent_a_delta():
    request, evidence = activation_fixture()
    request.update(periods=["202602", "202603"], operation="compare")
    evidence["requested_periods"] = request["periods"]
    answer = render_measure_response(request, evidence)
    assert "Comparison unavailable" in answer
    assert "Change (" not in answer


def test_breakdown_is_bounded_escaped_and_keeps_whole_evidence_total():
    request, evidence = activation_fixture()
    request.update(operation="breakdown", breakdown="product")
    period = evidence["measures"][0]["periods"][0]
    period.update(total=150, total_rows=150, truncated=True)
    period["rows"] = [{"dealer_id": "D1", "dealer_name": "Dealer | <img>",
                       "dimension": f"Product {n} [link](https://bad)", "value": 1} for n in range(150)]
    answer = render_measure_response(request, evidence)
    assert "Recorded activations: 150" in answer
    assert "Product 99" in answer and "Product 100" not in answer
    assert "truncated" in answer.lower()
    assert r"Dealer \| &lt;img&gt;" in answer
    assert r"\[link\]\(https://bad\)" in answer


def test_multiple_requested_measures_include_text_status_without_numeric_sum():
    request, evidence = activation_fixture()
    request["measures"].append("payment_status")
    evidence["measures"].append({
        "measure": "payment_status", "label": "Payment status", "unit": "text",
        "periods": [{"period": "202603", "status": "available", "source": "SIMULATED",
                     "rows": [{"dealer_id": "D1", "dealer_name": "First Dealer", "dimension": None, "value": "PARTIALLY_PAID"}],
                     "total": None, "note": "", "tool": "get_payment_summary"}],
    })
    answer = render_measure_response(request, evidence)
    assert "Recorded activations: 12" in answer
    assert "Payment status" in answer and r"PARTIALLY\_PAID" in answer
    assert "SIMULATED" in answer
    assert "Payment status: unavailable" not in answer


def test_zero_is_available_and_null_is_unavailable_without_fabricating_amount():
    request, evidence = activation_fixture()
    period = evidence["measures"][0]["periods"][0]
    period["total"] = 0
    period["rows"][0]["value"] = 0
    assert "Recorded activations: 0" in render_measure_response(request, evidence)
    period["total"] = None
    period["rows"][0]["value"] = None
    answer = render_measure_response(request, evidence)
    assert "Recorded activations: unavailable" in answer
    assert "Recorded activations: 0" not in answer


def test_month_breakdown_uses_aggregates_and_marks_missing_months():
    request, evidence = activation_fixture()
    request.update(operation="breakdown", breakdown="month", periods=["202603", "202604"])
    evidence["requested_periods"] = request["periods"]
    period = evidence["measures"][0]["periods"][0]
    period["rows"] = []
    answer = render_measure_response(request, evidence)
    assert "| 202603 | 12 |" in answer
    assert "| 202604 | Unavailable |" in answer


def test_breakdown_does_not_claim_empty_rows_are_complete_detail():
    request, evidence = activation_fixture()
    request.update(operation="breakdown", breakdown="product")
    evidence["measures"][0]["periods"][0]["rows"] = []
    answer = render_measure_response(request, evidence)
    assert "Requested breakdown unavailable" in answer
    assert "Recorded activations: 12" in answer


@pytest.mark.parametrize("bad_value", [{"commission": 900}, ["PAID"], 900, True])
def test_text_evidence_requires_a_text_scalar(bad_value):
    request, evidence = activation_fixture()
    measure = evidence["measures"][0]
    measure["unit"] = "text"
    measure["periods"][0]["total"] = None
    measure["periods"][0]["rows"][0]["value"] = bad_value
    with pytest.raises(ValueError):
        render_measure_response(request, evidence)


def test_snapshot_months_are_never_added_as_purchases():
    request, evidence = activation_fixture()
    request.update(measures=['inventory_recorded_purchases'], periods=['202603', '202604'])
    evidence['requested_periods'] = request['periods']
    measure = evidence['measures'][0]
    measure.update(measure='inventory_recorded_purchases', label='Recorded purchases for compared products', aggregation='snapshot')
    later = deepcopy(measure['periods'][0])
    later.update(period='202604', total=18)
    later['rows'][0]['value'] = 18
    measure['periods'].append(later)
    answer = render_measure_response(request, evidence)
    assert '202603: 12' in answer and '202604: 18' in answer
    assert ': 30' not in answer
    request['operation'] = 'compare'
    answer = render_measure_response(request, evidence)
    assert 'Snapshot change (202604 − 202603): 6' in answer


def test_financial_statement_rows_are_available_without_an_additive_total():
    request, evidence = activation_fixture()
    request['measures'] = ['financial_statements']
    measure = evidence['measures'][0]
    measure.update(measure='financial_statements', label='Synthetic financial statements', unit='ngn', aggregation='none')
    period = measure['periods'][0]
    period.update(total=None, source='SYNTHETIC', rows=[
        {'dealer_id': 'D1', 'dimension': 'Revenue', 'value': 1200},
        {'dealer_id': 'D1', 'dimension': 'Net profit', 'value': 200}])
    answer = render_measure_response(request, evidence)
    assert 'Revenue | NGN 1,200.00' in answer
    assert 'Net profit | NGN 200.00' in answer
    assert 'NGN 1,400.00' not in answer
    assert 'unavailable' not in answer.lower()
    assert 'SYNTHETIC' in answer


def test_product_explanation_shows_period_details_and_aggregate_delta():
    request, evidence = activation_fixture()
    request.update(operation='explain', breakdown='product', periods=['202603', '202604'])
    evidence['requested_periods'] = request['periods']
    measure = evidence['measures'][0]
    measure['periods'][0]['rows'][0]['dimension'] = 'Hynex'
    later = deepcopy(measure['periods'][0])
    later.update(period='202604', total=18)
    later['rows'][0]['value'] = 18
    measure['periods'].append(later)
    answer = render_measure_response(request, evidence)
    assert '| 202603 | First Dealer (D1) | Hynex | 12 |' in answer
    assert '| 202604 | First Dealer (D1) | Hynex | 18 |' in answer
    assert 'Change (202604 − 202603): 6' in answer


def test_repeated_provenance_is_consolidated_and_tool_names_stay_internal():
    request, evidence = activation_fixture()
    request['periods'] = ['202603', '202604']
    evidence['requested_periods'] = request['periods']
    measure = evidence['measures'][0]
    measure['periods'][0]['note'] = 'Fictional evidence.'
    later = deepcopy(measure['periods'][0])
    later['period'] = '202604'
    measure['periods'].append(later)
    answer = render_measure_response(request, evidence)
    assert answer.count('Source: SAMPLE') == 1
    assert answer.count('Fictional evidence') == 1
    assert 'get' not in answer
    assert 'Periods: 202603, 202604' in answer


def test_periodless_unavailable_measure_retains_missing_evidence_explanation():
    request = {'measures': ['retail_sales_value'], 'periods': [], 'dealer_id': None}
    evidence = {'requested_periods': [], 'dealer_id': None, 'measures': [{
        'measure': 'retail_sales_value', 'label': 'Customer sales value', 'unit': 'ngn',
        'periods': [], 'note': 'Actual customer transactions and returns are required.'}]}
    answer = render_measure_response(request, evidence)
    assert 'Customer sales value: unavailable' in answer
    assert 'Actual customer transactions and returns are required' in answer
    assert '2026' not in answer


@pytest.mark.parametrize('mutation', ['nonfinite', 'wrong_dealer', 'text_number'])
def test_nonadditive_financial_rows_still_require_valid_scoped_numbers(mutation):
    request, evidence = activation_fixture()
    measure = evidence['measures'][0]
    measure.update(aggregation='none', unit='ngn')
    period = measure['periods'][0]
    period['total'] = None
    if mutation == 'nonfinite':
        period['rows'][0]['value'] = float('nan')
    elif mutation == 'wrong_dealer':
        period['rows'][0]['dealer_id'] = 'D2'
    else:
        period['rows'][0]['value'] = '1200'
    with pytest.raises(ValueError):
        render_measure_response(request, evidence)


def test_dealer_code_lookup_renders_bounded_identity_and_source_coverage_only():
    from backend.agent.measure_response import render_dealer_codes
    evidence = {
        'rows': [{'dealer_id': '0012', 'recorded_names': ['Acme | <Dealer>'],
                  'first_observed_period': '202601', 'last_observed_period': '202603',
                  'sources': ['fbb_comm_dev_act'], 'commission': 999999}],
        'total_codes': 2, 'page': 1, 'page_size': 1, 'has_more': True,
        'data_source': 'SAMPLE',
        'coverage_by_source': {'fbb_comm_dev_act': ['202601', '202603'], 'fbb_comm_orsc': []},
        'association_note': 'Recorded name-code associations only; not verified branches or legal entities. First/last observations do not prove continuity.',
    }
    answer = render_dealer_codes(evidence)
    assert '| 0012 | Acme \\| &lt;Dealer&gt; | 202601 | 202603 |' in answer
    assert 'partial' in answer.lower() and '2' in answer
    assert 'Source: Recorded dealer records.' in answer and 'coverage is limited' in answer.lower()
    assert 'sample' not in answer.lower()
    assert 'Activation records: 202601, 202603' in answer
    assert 'Subscription records: no covered months' in answer
    assert 'not verified branches or legal entities' in answer
    assert '999999' not in answer and 'commission' not in answer.lower()
    evidence['rows'] *= 101
    assert render_dealer_codes(evidence).count('| 0012 |') == 100


def test_explanation_reports_checked_records_without_inventing_cause():
    request, evidence = activation_fixture()
    request.update(operation='explain', measures=['activation_commission'])
    evidence['measures'][0].update(measure='activation_commission', label='Activation commission', unit='ngn')
    evidence['explanations'] = [{
        'period': '202603', 'dealer_id': 'D1', 'records_checked': 8,
        'records_with_dates': 6, 'total_records': 18, 'source': 'SAMPLE',
        'tool': 'get_zero_commission_records', 'status': 'available',
        'note': 'Historical USP, profile and denomination evidence and an authoritative eligibility-window rule are needed to establish the cause.'}]
    answer = render_measure_response(request, evidence)
    assert '8 of 18' in answer and '6' in answer
    assert 'Historical USP' in answer
    assert 'requires supporting source records' not in answer
    assert 'unverified' in answer
    assert 'get_zero' not in answer


@pytest.mark.parametrize('mutation', ['period', 'dealer', 'operation', 'measure'])
def test_explanation_evidence_cannot_escape_requested_scope(mutation):
    request, evidence = activation_fixture()
    request.update(operation='explain', measures=['activation_commission'])
    evidence['measures'][0]['measure'] = 'activation_commission'
    evidence['explanations'] = [{
        'period': '202603', 'dealer_id': 'D1', 'records_checked': 8,
        'records_with_dates': 6, 'total_records': 18, 'source': 'SAMPLE',
        'status': 'available', 'note': 'Unverified.'}]
    if mutation == 'period':
        evidence['explanations'][0]['period'] = '202602'
    elif mutation == 'dealer':
        evidence['explanations'][0]['dealer_id'] = 'D2'
    elif mutation == 'operation':
        request['operation'] = 'total'
    else:
        request['measures'] = ['activation_count']
        evidence['measures'][0]['measure'] = 'activation_count'
    with pytest.raises(ValueError):
        render_measure_response(request, evidence)


def test_breakdown_distinguishes_codes_with_the_same_recorded_name():
    request, evidence = activation_fixture()
    request.update(dealer_id=None, operation='breakdown')
    evidence['dealer_id'] = None
    period = evidence['measures'][0]['periods'][0]
    period['rows'].append({'dealer_id': 'D2', 'dealer_name': 'First Dealer', 'value': 0})
    answer = render_measure_response(request, evidence)
    assert 'First Dealer (D1)' in answer and 'First Dealer (D2)' in answer


def priority_fixture(period_evidence):
    request = {"measures": ["investigation_priority"], "periods": ["202606"], "dealer_id": "296065",
               "operation": "total"}
    evidence = {"requested_periods": ["202606"], "dealer_id": "296065", "explanations": [], "measures": [{
        "measure": "investigation_priority", "label": "Investigation priority", "unit": "text",
        "aggregation": "none", "note": "", "periods": [period_evidence]}]}
    return request, evidence


def queue_period(**priority):
    from backend.tests.test_measure_scope import fake_priority_evidence
    period = fake_priority_evidence("202606", "296065")
    period["priority"].update(priority)
    return period


def test_priority_states_overall_and_commission_priority_with_every_finding():
    answer = render_measure_response(*priority_fixture(queue_period()))
    lines = answer.split("\n\n")
    assert lines[0] == ("Investigation priority for dealer 296065, 202606: HIGH — rank 1 of 922 "
                        "in the investigation queue.")
    assert "Overall priority is set by the payment finding (COMMISSION\\_DISPUTE)." in answer
    assert "Commission-module priority: MEDIUM (ZERO\\_COMMISSION\\_ACTIVATION)." in answer
    table = next(part for part in lines if part.startswith("| Module | Severity | Finding | Detail |"))
    rows = table.splitlines()[2:]
    assert [row.split(" | ")[0] for row in rows] == ["| Payment", "| Inventory", "| Commission", "| Activation"]
    assert "| Payment | HIGH | COMMISSION\\_DISPUTE | NGN 594,652\\.08 outstanding · disputed |" in table
    assert "110\\.0% excess" in table
    assert "Queue order: severity, then amount outstanding (largest first)." in answer
    assert lines[-1] == "Source: Investigation queue."
    assert "Not checked" not in answer
    assert "knowledge base defines no" not in answer


def test_priority_without_commission_finding_or_unchecked_commission_module():
    no_finding = render_measure_response(*priority_fixture(queue_period(commission=None)))
    assert "Commission-module priority: no commission finding this month." in no_finding
    unchecked = render_measure_response(*priority_fixture(queue_period(
        commission=None, commission_module_status="UNAVAILABLE", unchecked_modules=["commission", "inventory"])))
    assert "Commission-module priority: commission module could not be checked." in unchecked
    assert "Not checked: commission, inventory; the queue may be incomplete." in unchecked


def test_priority_reports_dealer_outside_the_queue_with_queue_size():
    from backend.tests.test_measure_scope import fake_priority_evidence
    period = fake_priority_evidence("202606", "777")
    request, evidence = priority_fixture(period)
    request["dealer_id"] = evidence["dealer_id"] = "777"
    answer = render_measure_response(request, evidence)
    assert answer.startswith("Dealer 777 is not in the investigation queue for 202606 (queue of 922 dealers).")
    assert "| Module |" not in answer
    assert answer.endswith("Source: Investigation queue.")


def test_unavailable_priority_is_never_low():
    from backend.tests.test_measure_scope import fake_priority_evidence
    request, evidence = priority_fixture(fake_priority_evidence("202606", None))
    answer = render_measure_response(request, evidence)
    assert answer.startswith("Investigation priority unavailable for 202606: The investigation queue is unavailable")
    assert "Missing evidence is not a low priority." in answer
    assert "LOW" not in answer and "rank" not in answer
    assert "not in the investigation queue" not in answer


def test_priority_answers_carry_no_demo_wording():
    from backend.tests.test_measure_scope import fake_priority_evidence
    unavailable = fake_priority_evidence("202606", None)
    outside = fake_priority_evidence("202606", "296065")
    outside["priority"].update(in_queue=False, severity=None, rank=None, findings=[], finding_count=0,
                               lead_module=None, lead_type=None, commission=None)
    outside["rows"] = []
    for case in (queue_period(), queue_period(commission=None, unchecked_modules=["payment"]), unavailable, outside):
        answer = render_measure_response(*priority_fixture(case)).lower()
        assert not any(word in answer for word in ("synthetic", "simulated", "sample", "demo"))


@pytest.mark.parametrize("change", [
    {"rank": 923}, {"rank": 0}, {"in_queue": "yes"}, {"severity": "CRITICAL"},
    {"findings": [{"module": "payment", "severity": "HIGH", "type": 1, "description": "x"}]},
    {"finding_count": 1}, {"unchecked_modules": "commission"}, {"queue_size": -1},
    {"findings": None}, {"rank": "1"},
])
def test_priority_evidence_is_validated(change):
    with pytest.raises(ValueError):
        render_measure_response(*priority_fixture(queue_period(**change)))


@pytest.mark.parametrize("missing", ["findings", "finding_count", "queue_size", "rank", "severity"])
def test_incomplete_priority_evidence_is_rejected_not_crashed(missing):
    request, evidence = priority_fixture(queue_period())
    del evidence["measures"][0]["periods"][0]["priority"][missing]
    with pytest.raises(ValueError):
        render_measure_response(request, evidence)


def test_priority_payload_is_rejected_on_other_measures():
    request, evidence = activation_fixture()
    evidence["measures"][0]["periods"][0]["priority"] = queue_period()["priority"]
    with pytest.raises(ValueError):
        render_measure_response(request, evidence)


def test_markdown_in_priority_values_is_escaped():
    period = queue_period(findings=[{"module": "payment", "severity": "HIGH", "type": "X",
                                     "description": "| [link](http://x) `code`"}], finding_count=1)
    answer = render_measure_response(*priority_fixture(period))
    assert "\\| \\[link\\]\\(http://x\\) \\`code\\`" in answer
