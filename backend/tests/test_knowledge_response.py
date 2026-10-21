"""Policy excerpts retain their source context and unresolved policy boundaries."""
from pathlib import Path
from types import SimpleNamespace

import pytest

from backend.agent.knowledge_response import knowledge_response


KB = (Path(__file__).parents[1] / 'knowledge_base' / 'fbb_commission_kb.md').read_text()


def answer(quote, kb=KB):
    return knowledge_response(SimpleNamespace(knowledge_quote=quote), kb)


@pytest.mark.parametrize('quote', [
    '6 months back from the reporting period', '180-day window', 'POLICY_MET',
])
def test_eligibility_fragments_cannot_strip_the_policy_limitation(quote):
    result = answer(quote)
    assert 'Finance must confirm' in result
    assert 'reporting month' in result
    assert 'invoice-to-activation' in result


def test_a_fragment_retains_the_source_paragraphs_qualifying_sentence():
    paragraph = 'An observed mismatch requires investigation. Missing evidence does not establish its cause.'
    assert answer('An observed mismatch requires investigation.', paragraph) == 'Documented policy:\n\n' + paragraph


def test_5g_rate_card_paragraph_is_unchanged_and_has_no_unrelated_limitation():
    paragraph = next(p for p in KB.split('\n\n') if p.startswith('The MIFI / HYNETFLEX'))
    assert answer(paragraph) == 'Documented policy:\n\n' + paragraph


def test_the_four_causes_have_one_exact_quoteable_source_paragraph():
    paragraph = next((p for p in KB.split('\n\n') if p.startswith('The four documented candidate causes')), '')
    assert paragraph
    result = answer(paragraph)
    for cause in ['Product not matched to commission rate card', 'eligibility window', 'NULL `account_profile_class`', 'Hynex / Hynex_1']:
        assert cause in result
    assert 'unverified' in result


@pytest.mark.parametrize('quote', [None, '', 'Dealer 74050 earned NGN 900,000.00.'])
def test_non_source_quotes_are_rejected(quote):
    with pytest.raises(ValueError):
        answer(quote)


def test_every_output_paragraph_comes_from_the_kb():
    for quote in ['POLICY_MET', 'Product not matched to commission rate card', '5G ROUTER']:
        result = answer(quote).removeprefix('Documented policy:\n\n')
        assert all(paragraph in KB for paragraph in result.split('\n\n'))


def test_a_selected_section_heading_includes_its_explanatory_paragraph():
    result = answer('### Four documented zero-commission causes')
    assert 'Product not matched to commission rate card' in result
    assert 'cause remains unverified' in result


def test_missing_eligibility_limitation_fails_closed():
    with pytest.raises(ValueError, match='limitation is missing'):
        answer('180-day window', 'A historical check uses a 180-day window.')


@pytest.mark.parametrize('quote', ['REGEXP_REPLACE', 'substring(imei'])
def test_internal_query_expression_returns_a_grounded_capability_boundary(quote):
    result = answer(quote)
    assert 'does not expose raw SQL' in result
    assert quote not in result
    assert 'error retrieving' not in result


def test_explicit_business_owner_excerpt_remains_supported():
    assert 'Victor Ugboajah' in answer('Report Owner / Business Reporter')


@pytest.mark.parametrize('quote', [
    'Actual subscription eligibility is',
    '**lending_decision**',
    '**subscription_policy**',
])
def test_other_eligibility_topics_do_not_add_activation_window_policy(quote):
    result = answer(quote)
    assert 'Finance must confirm the authoritative date anchor' not in result
    assert 'invoice-to-activation 180-day window' not in result


def test_one_commission_definition_does_not_expand_to_the_other_list_item():
    result = answer('a one-time commission paid to a partner')
    assert 'Finance must confirm' in result
    assert '**Subscription commission**' not in result


@pytest.mark.parametrize('topic, required', [
    ('zero_commission_causes', ['Product not matched to commission rate card', 'NULL `account_profile_class`', 'Hynex / Hynex_1', 'unverified']),
    ('activation_eligibility', ['Finance must confirm', 'reporting month', 'invoice-to-activation']),
])
def test_named_policy_topics_select_exact_source_without_model_transcription(topic, required):
    result = knowledge_response(SimpleNamespace(knowledge_topic=topic, knowledge_quote=None), KB)
    assert all(text in result for text in required)
    assert all(paragraph in KB for paragraph in result.removeprefix('Documented policy:\n\n').split('\n\n'))


@pytest.mark.parametrize('topic, quote', [
    ('unknown', None), ('activation_eligibility', 'POLICY_MET'),
])
def test_named_policy_topics_cannot_guess_or_coexist_with_a_quote(topic, quote):
    with pytest.raises(ValueError):
        knowledge_response(SimpleNamespace(knowledge_topic=topic, knowledge_quote=quote), KB)
