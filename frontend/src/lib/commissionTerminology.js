// Presentation aliases only: source keys and stored evidence remain unchanged.
export const RATE_CARD_CAUSE = 'Product not matched to commission rate card';
export const RATE_CARD_EXPLANATION = 'The product could not be matched to the commission rate card for the calculation month, so the applicable commission amount could not be retrieved.';

export const legacyEvidenceLabels = {
  usp_snapshot_miss: RATE_CARD_CAUSE,
  products_missing_from_usp: 'Products not matched to commission rate card',
  usp_snapshot_period: 'Commission rate card snapshot period',
  usp_lookup: 'Commission rate card lookup',
  usp_missing: 'Missing partner classification',
};

function normalizeProse(text) {
  return text
    .replace(/\bUSP missing\b/gi, 'Missing partner classification')
    .replace(/\bUSP snapshot miss(?:es)?\b/gi, RATE_CARD_CAUSE)
    .replace(/\bUSP (?:product )?rate card\b/gi, 'commission rate card')
    .replace(/\bUSP dimension\b/gi, 'commission rate card')
    .replace(/\bUSP (?=snapshot|lookup|coverage|product|mapping|reference|data)/gi, 'commission rate card ')
    .replace(/\b(missing from|against|absent from|in) (?:the )?USP\b/gi, '$1 the commission rate card');
}

// Only known domain phrases are aliases. Keep code, quotations, links and
// identifiers verbatim; a customer's quoted words are not our terminology.
export function commissionTerminology(text) {
  if (typeof text !== 'string') return text;
  const protectedText = /(^[ \t]*(?<fence>`{3,}|~{3,})[^\n]*(?:\n|$)|^[ \t]*>[^\n]*(?:\n(?![ \t]*$)[^\n]*)*(?:\n|$)|^(?: {4}|\t)[^\n]*(?:\n|$)|(?<!`)(?<ticks>`+)(?!`)[\s\S]*?(?<!`)\k<ticks>(?!`)|"[^"]*"|(?<!\w)'[^']*'(?!\w)|“[^”]*”|‘[^’]*’|https?:\/\/\S+|\]\([^)]*\)|\b\w*[_.]\w*\b)/gm;
  let result = '', start = 0, match;
  while ((match = protectedText.exec(text)) !== null) {
    let end = protectedText.lastIndex;
    if (match.groups.fence) {
      // Shorter runs and the other fence character are ordinary code content.
      const fence = match.groups.fence;
      const closing = new RegExp(`^[ \\t]*${fence[0]}{${fence.length},}[ \\t]*(?:\\r?\\n|$)`, 'gm');
      closing.lastIndex = end;
      const close = closing.exec(text);
      end = close ? closing.lastIndex : text.length;
      protectedText.lastIndex = end;
    }
    result += normalizeProse(text.slice(start, match.index)) + text.slice(match.index, end);
    start = end;
  }
  return result + normalizeProse(text.slice(start));
}

export function assistantPresentation(message) {
  return message.role === 'assistant'
    ? { ...message, content: commissionTerminology(message.content) } : message;
}
