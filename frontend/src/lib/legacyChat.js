// Frozen templates emitted by CommissionAssistant before storage version 2.
// These are migration signatures, not the current investigation instructions.
const ordinaryTails = new Map([
  ['Activation commission.', 'activation'],
  ['Payment settlement investigation. Use recorded payment and commission evidence; do not infer causes from aggregate differences.', 'payment'],
  ['Subscription review: subscription revenue is separate from recorded upstream subscription commission, settlement and outstanding amounts. Use get_orsc_summary for available evidence. Do not infer a commission rate or eligibility policy; the actual calculation policy has not been supplied. Missing commission evidence is unavailable, not zero.', 'orsc'],
]);

function generatedScope(prefix) {
  const ordinary = prefix.match(/^Reporting period (\d{6})\. (?:Comparison period (\d{6})\.|No comparison period selected\.) (?:Exact dealer account code ([^\s()]+) \([^\r\n]+\); do not combine other accounts with the same name\.|Portfolio-level investigation\.) (.+)$/);
  if (ordinary) {
    const [, period, comparison, dealer, tail] = ordinary;
    const stream = ordinaryTails.get(tail);
    return stream ? `${period}.${comparison || 'none'}.${stream}.${dealer || 'all'}` : null;
  }
  const inventory = prefix.match(/^Inventory investigation for reporting period (\d{6}), exact dealer ([^\s()]+) \([^\r\n]+\), product ([^\s()]+) \([^\r\n]+\)\. Use only this dealer\/product scope\. Confirm invoice coverage, purchase window and documented Inventory KB explanations; missing evidence does not prove missing purchases or commission owed\. (?:Purchase scenario: [^\r\n]+; scenario purchase quantities are not verified operational evidence\.|Synthetic scenario: [^\r\n]+; fictional purchase evidence is not verified operational evidence\.)?$/);
  if (inventory) return `inventory.${inventory[1]}.${inventory[2]}.${inventory[3]}`;
  const finding = prefix.match(/^Findings investigation for reporting period (\d{6})\. Exact dealer account code ([^\s()]+) \([^\r\n]+\); do not combine other accounts with the same name\. Finding module ([a-z_]+), type ([A-Z_]+)\.(?: Exact product code ([^\s]+)\.)? Use the evidence and documented rules; distinguish missing evidence from confirmed discrepancies\.$/);
  if (finding) return `findings.${JSON.stringify([...finding.slice(1, 5), finding[5] || null])}`;
  return null;
}

function normalizeText(text, scope) {
  if (typeof text !== 'string' || !scope) return text;
  const boundary = text.indexOf('\n\n');
  if (boundary < 0) return text;
  const question = text.slice(boundary + 2);
  // A complete generated prefix, matching the persisted account/period/product
  // scope, and a nonempty question are all required. Never trim user prose.
  return question.trim() && generatedScope(text.slice(0, boundary)) === scope ? question : text;
}

export function normalizeLegacyMessages(messages, scope) {
  return messages.map((message) => {
    if (message.role === 'user') return { ...message, content: normalizeText(message.content, scope) };
    if (message.role === 'assistant' && message.request) {
      return { ...message, request: { ...message.request, text: normalizeText(message.request.text, scope) } };
    }
    return message;
  });
}
