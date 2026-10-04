"""Knowledge-source monetary units survive the public answer composer."""
import pytest
from backend.agent import prompts
from backend.agent.measure_scope import MeasureScope, knowledge_response
from backend.tests.test_narrative import compose, provider


@pytest.mark.parametrize('quote', [
    '₦8,215.81 (approximately 12% of unit price), not 10%',
    '| 5G ROUTER            | 68,465.12                | 8,215.81              | TOZED ROUMOD4393, ZTE MC888D 5G CPE, HUAWEI ROUWIR4332      |',
])
def test_kb_currency_is_formatted_as_ngn_without_changing_percentages(quote):
    scope = MeasureScope(kind='knowledge', knowledge_quote=quote)
    context = knowledge_response(scope, prompts.KB_CONTENT, sample_mode=True)
    def answer(payload, attempt):
        rate = next(f for f in payload['facts'] if '8,215.81' in str(f['value']))
        assert rate['display'] == 'NGN 8,215.81'
        if '12%' in context:
            percent = next(f for f in payload['facts'] if f['value'] == '12%')
            assert percent['display'] == '12%'
            standard = next(f for f in payload['facts'] if f['value'] == '10%')
            assert standard['display'] == '10%'
        return 'The documented activation commission is {{' + rate['id'] + '}}.'
    client, calls = provider(answer)
    result = compose(client, scope=scope.model_dump(), evidence={}, tools_called=[], validated_context=context)
    assert result == 'The documented activation commission is NGN 8,215.81.'
    assert len(calls) == 1


def test_currency_table_units_do_not_change_adjacent_counts_or_identifiers():
    context = '| Product code | Unit selling price (₦) | Commission (NGN) | Count |\n| --- | --- | --- | --- |\n| 1283280 | 50,000 | 5,000 | 20 |'
    def answer(payload, attempt):
        facts = payload['facts']
        assert next(f for f in facts if f['value'] == '50,000')['display'] == 'NGN 50,000.00'
        assert next(f for f in facts if f['value'] == '5,000')['display'] == 'NGN 5,000.00'
        assert next(f for f in facts if f['value'] == '20')['display'] == '20'
        assert next(f for f in facts if f['value'] == '1283280')['display'] == '1283280'
        return 'The table distinguishes recorded currency amounts from quantities.'
    client, _ = provider(answer)
    assert compose(client, scope={'kind':'knowledge'}, evidence={}, tools_called=[], validated_context=context)
