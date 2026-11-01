// Fictional Partner Sales seed data. Browser-only presentation simulation (see
// docs/adr/0001-partner-sales-presentation-boundary.md): nothing here is read
// from, or written to, a financial source.

import { formatCount } from '../../lib/format.js';

// Sample dealer identities. Same-name accounts stay separate; the account code
// is the identity.
export const PARTNERS = [
  { code: '296065', name: 'River Isle Ventures' },
  { code: '353072', name: 'River Isle Ventures' },
  { code: '74050', name: 'Stone Light Networks' },
  { code: '98052', name: 'Ember Hill Networks' },
  { code: '205044', name: 'Sunset Crest Communications' },
  { code: '295083', name: 'Sunset Crest Communications' },
];

// Bounded catalogue. Prices are fixed demo values in kobo, never MTN price lists.
export const CATALOGUE = [
  { code: 'FBB-5G-ROUTER', description: 'Fictional 5G FBB router', unit: 'device', priceMinor: 5000000 },
  { code: 'FBB-4G-ROUTER', description: 'Fictional 4G FBB router', unit: 'device', priceMinor: 3500000 },
  { code: 'FBB-MIFI', description: 'Fictional portable FBB MiFi', unit: 'device', priceMinor: 3333333 },
  { code: 'RCC-0100', description: 'Fictional NGN 100 physical recharge card', unit: 'card', priceMinor: 10000 },
  { code: 'RCC-0200', description: 'Fictional NGN 200 physical recharge card', unit: 'card', priceMinor: 20000 },
  { code: 'RCC-0500', description: 'Fictional NGN 500 physical recharge card', unit: 'card', priceMinor: 50000 },
];
export const productByCode = (code) => CATALOGUE.find((product) => product.code === code);

// Keeps every line and draft total well inside Number.MAX_SAFE_INTEGER kobo.
const MAX_QUANTITY = 1000000;

export const draftKey = (partnerCode, period) => `${partnerCode}|${period}`;

// Last day of a YYYYMM reporting month, as a date-only string.
export function defaultIssueDate(period) {
  const year = Number(period.slice(0, 4));
  const month = Number(period.slice(4, 6));
  const day = new Date(Date.UTC(year, month, 0)).getUTCDate();
  return `${period.slice(0, 4)}-${period.slice(4, 6)}-${String(day).padStart(2, '0')}`;
}

// Quantities stay as typed so an invalid edit remains visible and correctable.
export function quantityError(quantity) {
  if (!/^\d+$/.test(quantity) || Number(quantity) < 1) return 'Enter a positive whole number.';
  if (Number(quantity) > MAX_QUANTITY) return `Enter ${formatCount(MAX_QUANTITY)} or fewer.`;
  return null;
}

export function lineTotalMinor(line) {
  return quantityError(line.quantity) ? null : Number(line.quantity) * productByCode(line.productCode).priceMinor;
}

// Null while any line is invalid: a partial total would misstate the draft.
export function draftTotalMinor(draft) {
  let total = 0;
  for (const line of draft.lines) {
    const lineTotal = lineTotalMinor(line);
    if (lineTotal === null) return null;
    total += lineTotal;
  }
  return total;
}

export const referenceFor = (sequence) => `SIM-INV-${String(sequence).padStart(4, '0')}`;

// Date-only values compare correctly as strings and never shift across time zones.
const inMonth = (date, period) => date.slice(0, 7) === `${period.slice(0, 4)}-${period.slice(4, 6)}`;

export function issueDateError(draft, periodLabel) {
  if (!draft.issueDate) return 'Enter an intended issue date.';
  return inMonth(draft.issueDate, draft.period) ? null : `Choose a date in ${periodLabel}.`;
}

export function dueDateError(draft) {
  return draft.dueDate && draft.issueDate && draft.dueDate < draft.issueDate ? 'Due date cannot be before the issue date.' : null;
}
