// Partner Sales display helpers and form checks. The server owns the simulation
// (see docs/adr/0002-partner-sales-two-logins.md) and decides every action; these
// checks only explain a problem before it is sent. Amounts are exact kobo.

import { formatCount, formatDate, formatMinorNGN } from '../../lib/format.js';

export const partnerLabel = (partner) => `${partner.name} · Account ${partner.code}`;
export const quantityLabel = (quantity, unit) => `${formatCount(quantity)} ${unit}${quantity === 1 ? '' : 's'}`;
export const partnerMatches = (partner, term) => partner.code.includes(term) || partner.name.toLowerCase().includes(term);

const MAX_QUANTITY = 1000000;

// Last day of a YYYYMM reporting month, as a date-only string.
export function lastDayOf(period) {
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

export const lineTotalMinor = (line, product) => (quantityError(line.quantity) ? null : Number(line.quantity) * product.price_minor);

// Null while any line is invalid: a partial total would misstate the draft.
export function draftTotalMinor(draft, productByCode) {
  let total = 0;
  for (const line of draft.lines) {
    const lineTotal = lineTotalMinor(line, productByCode(line.product_code));
    if (lineTotal === null) return null;
    total += lineTotal;
  }
  return total;
}

// A date input yields five-digit years unless capped, and those do not compare
// correctly as strings.
const isDate = (value) => /^\d{4}-\d{2}-\d{2}$/.test(value) && new Date(`${value}T00:00:00Z`).toISOString().slice(0, 10) === value;

// Date-only values compare correctly as strings and never shift across time zones.
const inMonth = (date, period) => date.slice(0, 7) === `${period.slice(0, 4)}-${period.slice(4, 6)}`;

export function issueDateError(draft, periodLabel) {
  if (!draft.issue_date) return 'Enter an intended issue date.';
  return isDate(draft.issue_date) && inMonth(draft.issue_date, draft.period) ? null : `Choose a date in ${periodLabel}.`;
}

export function dueDateError(draft) {
  if (!draft.due_date) return null;
  if (!isDate(draft.due_date)) return 'Enter a valid due date.';
  return draft.issue_date && draft.due_date < draft.issue_date ? 'Due date cannot be before the issue date.' : null;
}

// The list row that opens an invoice, where focus returns after its detail closes.
export const invoiceOpenerId = (reference) => `sales-open-${reference}`;

// Exact kobo from typed text, never through a fractional number. Null when the
// text is not a money amount, which includes any sign.
export function parseAmountMinor(text) {
  const match = /^(\d+|\d{1,3}(?:,\d{3})+)(?:\.(\d{1,2}))?$/.exec(text.trim());
  return match ? Number(match[1].replaceAll(',', '')) * 100 + Number((match[2] ?? '').padEnd(2, '0')) : null;
}

export function collectionErrors(invoice, outstandingMinor, { date, amount }) {
  const amountMinor = parseAmountMinor(amount);
  return {
    date: !date ? 'Enter a collection date.' : !isDate(date) ? 'Enter a valid collection date.' : date < invoice.issue_date ? `A collection cannot be dated before the issue date, ${formatDate(invoice.issue_date)}.` : null,
    amount: !amountMinor ? 'Enter a positive NGN amount with at most two decimal places.' : amountMinor > outstandingMinor ? `Enter ${formatMinorNGN(outstandingMinor)} or less, the outstanding balance.` : null,
  };
}

export const STATUSES = ['Draft', 'Unpaid', 'Partially paid', 'Paid'];
