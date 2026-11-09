"""Scope stays visible even when Claude uses the recorded name or data is missing."""
from backend.tests.test_narrative import compose, provider


def test_named_answer_keeps_exact_account_and_period_in_supporting_evidence():
    client, _ = provider(lambda payload, attempt: 'The recorded dealer had activations.')
    answer = compose(client)
    assert 'Account: 296065.' in answer.split('### Verification evidence')[1]
    assert 'Periods: 202606.' in answer


def test_missing_source_keeps_scope_without_inventing_a_tool_call():
    client, _ = provider(lambda payload, attempt: 'Activation records are unavailable for the selected month.')
    answer = compose(client, evidence={'status':'unavailable'}, tools_called=[],
                     validated_context='Activation records are unavailable.')
    details = answer.split('### Verification evidence')[1]
    assert 'Account: 296065.' in details and 'Periods: 202606.' in details
    assert 'Tools:' not in details


def test_provenance_preserves_punctuation_and_leading_zeroes_in_account():
    client, _ = provider(lambda payload, attempt: 'Records are available.')
    answer = compose(client, scope={'kind': 'measure', 'dealer_id': '001.23', 'periods': ['202606']}, evidence={'dealer_id': '001.23'})
    assert 'Account: 001.23.' in answer
