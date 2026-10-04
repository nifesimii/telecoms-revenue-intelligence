"""Readable commission terminology; source and persisted identifiers stay stable."""
import re

RATE_CARD_MISS_LABEL = 'Product not matched to commission rate card'
RATE_CARD_MISS_EXPLANATION = (
    'The product could not be matched to the commission rate card for the calculation '
    'month, so the applicable commission amount could not be retrieved.'
)

# Generated prose only. Preserve citations, code, quoted source text and links.
_PROTECTED = re.compile(
    r'^[ \t]*(?P<fence>`{3,}|~{3,})[^\n]*(?:\n|$)|'
    r'^[ \t]*>[^\n]*(?:\n(?![ \t]*$)[^\n]*)*(?:\n|$)|'
    r'^(?: {4}|\t)[^\n]*(?:\n|$)|'
    r'(?<!`)(?P<ticks>`+)(?!`)[\s\S]*?(?<!`)(?P=ticks)(?!`)|'
    r'"[^"]*"|“[^”]*”|(?<!\w)\'[^\']+\'(?!\w)|‘[^’]*’|'
    r'https?://\S+|\[[^\]\n]*\]\([^\)\n]*\)|\b\w*[_.]\w*\b', re.M
)


def normalize_generated_prose(text: str) -> str:
    """Overlay legacy application/assistant prose without changing stored evidence.

    Callers must select generated prose fields, never user-authored text or raw
    structured evidence. Word boundaries deliberately exclude compatibility keys.
    """
    if not isinstance(text, str):
        return text

    def replace(part):
        part = re.sub(r'\bUSP snapshot miss(?:es)?\b', RATE_CARD_MISS_LABEL, part, flags=re.I)
        part = re.sub(r'\bUSP missing\b', 'Missing partner classification', part, flags=re.I)
        part = re.sub(r'\bUSP (?:(?:product )?rate card|dimension)\b', 'commission rate card', part, flags=re.I)
        part = re.sub(r'\bUSP (?=snapshot|lookup|coverage|product|mapping|reference|data)', 'commission rate card ', part, flags=re.I)
        return re.sub(r'\b(missing from|against|absent from|in)(?: the)? USP\b',
                      r'\1 the commission rate card', part, flags=re.I)

    pieces, end = [], 0
    while match := _PROTECTED.search(text, end):
        protected_end = match.end()
        if fence := match.group('fence'):
            # Markdown permits a longer closer, but never a shorter run or a
            # different fence character. An unclosed fence protects through EOF.
            closer = re.compile(
                rf'^[ \t]*{re.escape(fence[0])}{{{len(fence)},}}[ \t]*(?:\n|$)', re.M
            ).search(text, protected_end)
            protected_end = closer.end() if closer else len(text)
        pieces.extend((replace(text[end:match.start()]), text[match.start():protected_end]))
        end = protected_end
    pieces.append(replace(text[end:]))
    return ''.join(pieces)
