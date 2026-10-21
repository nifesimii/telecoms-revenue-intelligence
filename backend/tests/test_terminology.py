"""Compatibility presentation: generated prose changes; recorded values do not."""
from backend.terminology import normalize_generated_prose


def test_historical_prose_preserves_quoted_evidence_code_and_price_semantics():
    text = ('USP snapshot miss; calculation-month USP snapshot; USP missing. '
            'Unit Selling Price NGN 12,558.14; unit_selling_price; USP_SNAPSHOT_MISS; '
            'development.usp_dimension; "USP snapshot miss"; `USP`;\n'
            '> USP snapshot miss\n```\nUSP snapshot miss\n```')
    expected = ('Product not matched to commission rate card; calculation-month commission rate card snapshot; '
                'Missing partner classification. Unit Selling Price NGN 12,558.14; unit_selling_price; '
                'USP_SNAPSHOT_MISS; development.usp_dimension; "USP snapshot miss"; `USP`;\n'
                '> USP snapshot miss\n```\nUSP snapshot miss\n```')
    assert normalize_generated_prose(text) == expected
    assert normalize_generated_prose(expected) == expected


def test_only_domain_phrases_change_and_markdown_code_and_quotes_are_preserved():
    text = ('Marketing USP is not a commission concept. USP rate card; in the USP; '
            'USP lookup; against USP.\n\n'
            '~~~text\nUSP snapshot miss\n~~~\n\n'
            '    USP snapshot miss\n\n'
            '“USP snapshot\nmiss”\n\n'
            '```text\nUSP snapshot miss')
    expected = ('Marketing USP is not a commission concept. commission rate card; in the commission rate card; '
                'commission rate card lookup; against the commission rate card.\n\n'
                '~~~text\nUSP snapshot miss\n~~~\n\n'
                '    USP snapshot miss\n\n'
                '“USP snapshot\nmiss”\n\n'
                '```text\nUSP snapshot miss')
    assert normalize_generated_prose(text) == expected


def test_multiline_quotes_and_exact_backtick_spans_preserve_source_words():
    protected = (
        'The dealer said "First line\nUSP snapshot miss". '
        "They also said 'First line\nUSP snapshot miss'. "
        'Example: ``first ` USP snapshot miss`` and `first `` USP snapshot miss`. '
        'Longer span: ``first ``` USP snapshot miss``.'
    )
    text = protected + ' USP snapshot miss.'
    assert normalize_generated_prose(text) == protected + ' Product not matched to commission rate card.'


def test_fences_close_only_on_the_same_character_with_sufficient_length():
    for opener, interior, closer in [
        ('````', '```', '````'),
        ('~~~', '```', '~~~~'),
        ('````', '~~~', '`````'),
    ]:
        protected = f'{opener}text\n{interior}\nUSP snapshot miss\n{closer}\n'
        assert normalize_generated_prose(protected + 'USP snapshot miss') == (
            protected + 'Product not matched to commission rate card')
    unclosed = '````text\n```\nUSP snapshot miss'
    assert normalize_generated_prose(unclosed) == unclosed
