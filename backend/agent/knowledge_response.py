"""Render exact KB excerpts with their paragraph context and policy limitations."""
from __future__ import annotations

import re


_ELIGIBILITY = re.compile(
    r'eligibility[- ]window|180[- ]day|(?:6|six)[- ]months?|'
    r'invoice[-→ ](?:to[- ])?activation|POLICY_MET|POLICY_VIOLATED|MIXED_ATTRIBUTION', re.I)
_LIMITATION_HEADING = '### Eligibility policy limitation'
_DEMO_HEADING = '### Demo eligibility policy'
_TOPIC_HEADINGS = {
    'zero_commission_causes': '### Four documented zero-commission causes',
    'activation_eligibility': _LIMITATION_HEADING,
}
# Recognize the executable excerpts present in the core KB, plus SQL fences and
# statement forms. This is an output guard, not a semantic SQL parser.
_QUERY_EXPRESSION = re.compile(
    r'```(?:sql|presto)\b|\b(?:REGEXP_REPLACE|substring)\s*\(|'
    r'\bCAST\s+(?:\([^)]*\)\s*)?AS\b|\bSELECT\b[\s\S]*?\bFROM\b|'
    r'\b(?:INSERT\s+INTO|DELETE\s+FROM|DROP\s+TABLE|CREATE\s+TABLE)\b', re.I)


def _section_paragraph(kb: str, heading: str, label: str) -> str:
    marker = heading + '\n\n'
    if marker not in kb:
        raise ValueError(f'{label} is missing from the core KB')
    paragraph = kb.split(marker, 1)[1].split('\n\n', 1)[0].strip()
    if not paragraph or paragraph.startswith('#'):
        raise ValueError(f'{label} has no explanatory paragraph')
    return paragraph


def eligibility_limitation(kb: str) -> str:
    """Read the limitation from the KB; never supply a business rule in code."""
    return _section_paragraph(kb, _LIMITATION_HEADING, 'Eligibility policy limitation')


def eligibility_policy(kb: str, sample_mode: bool) -> str:
    """Select the applicable KB policy without promoting demo assumptions to live rules."""
    if not sample_mode:
        return eligibility_limitation(kb)
    return _section_paragraph(kb, _DEMO_HEADING, 'Demo eligibility policy')


def eligibility_evidence_note(kb: str) -> str:
    return _section_paragraph(kb, '### Eligibility evidence interpretation', 'Eligibility evidence interpretation')


def knowledge_response(scope, kb: str, *, sample_mode: bool = False) -> str:
    """Only exact source text crosses this boundary, with qualifying context intact."""
    quote = scope.knowledge_quote
    topic = getattr(scope, 'knowledge_topic', None)
    if topic is not None:
        if quote is not None or topic not in _TOPIC_HEADINGS:
            raise ValueError('Knowledge requires a supported topic or quote, not both')
        heading = _DEMO_HEADING if sample_mode and topic == 'activation_eligibility' else _TOPIC_HEADINGS[topic]
        quote = _section_paragraph(kb, heading, 'Named policy section')
    if not isinstance(quote, str) or not quote.strip() or quote not in kb:
        raise ValueError('Knowledge excerpt is not present in the core KB')
    start = kb.index(quote)
    end = start + len(quote)
    # Expand short fragments to complete Markdown blocks. This preserves a
    # qualifying sentence, a numbered item, or a table's headers and units.
    paragraphs = list(re.finditer(r'\S(?:[^\n]|\n(?![ \t]*\n|\d+\.\s))*', kb))
    selected = [index for index, match in enumerate(paragraphs)
                if match.start() < end and match.end() > start]
    if selected and paragraphs[selected[-1]].group().startswith('#'):
        # A section title alone is not an explanation. Include its immediate
        # source paragraph; do not synthesize prose to fill the gap.
        following = selected[-1] + 1
        if following < len(paragraphs) and not paragraphs[following].group().startswith('#'):
            selected.append(following)
    blocks = [paragraphs[index].group().strip() for index in selected]
    if not blocks:
        raise ValueError('Knowledge excerpt has no source paragraph')
    if any(_QUERY_EXPRESSION.search(block) for block in blocks):
        boundary = next((p.group().strip() for p in paragraphs
                         if p.group().startswith('**capability** — ')), None)
        if boundary is None:
            raise ValueError('Core KB has no capability boundary for technical excerpts')
        return 'Documented policy:\n\n' + boundary.removeprefix('**capability** — ')
    if any(_ELIGIBILITY.search(block) for block in blocks):
        limitation = eligibility_policy(kb, sample_mode)
        if limitation not in blocks:
            blocks.append(limitation)
    return 'Documented policy:\n\n' + '\n\n'.join(blocks)
