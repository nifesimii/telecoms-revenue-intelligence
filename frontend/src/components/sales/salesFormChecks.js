// Partner Sales form checks. The server owns the simulation (see
// docs/adr/0002-partner-sales-two-logins.md) and decides every action; these only
// explain a problem before it is sent.

import { formatCount, formatDate, formatMinorNGN } from '../../lib/format.js';

// The dates in a YYYYMM reporting month, as date-only strings.
export function issueDateRange(period) {
  const [year, month] = [period.slice(0, 4), period.slice(4, 6)];
  const lastDay = new Date(Date.UTC(Number(year), Number(month), 0)).getUTCDate();
  return { min: `${year}-${month}-01`, max: `${year}-${month}-${String(lastDay).padStart(2, '0')}` };
}

// Quantities stay as typed so an invalid edit remains visible and correctable.
export function quantityError(quantity, maxQuantity) {
  if (!/^\d+$/.test(quantity) || Number(quantity) < 1) return 'Enter a positive whole number.';
  if (Number(quantity) > maxQuantity) return `Enter ${formatCount(maxQuantity)} or fewer.`;
  return null;
}

// A date input yields five-digit years unless capped, and those do not compare
// correctly as strings.
const isDate = (value) => /^\d{4}-\d{2}-\d{2}$/.test(value) && new Date(`${value}T00:00:00Z`).toISOString().slice(0, 10) === value;

// Date-only values compare correctly as strings and never shift across time zones.
const inMonth = (date, period) => date.slice(0, 7) === `${period.slice(0, 4)}-${period.slice(4, 6)}`;

// Issuing a partner order sets both dates. The invoice's month is its issue date's, so
// keeping that in the selected month keeps the invoice in the list being reviewed.
export function orderIssueErrors({ issueDate, dueDate }, period, periodLabel) {
  return {
    issueDate: !isDate(issueDate) ? 'Enter a valid issue date.' : inMonth(issueDate, period) ? null : `Choose a date in ${periodLabel}.`,
    dueDate: isDate(dueDate) && !(isDate(issueDate) && dueDate < issueDate) ? null : 'Enter a due date on or after the issue date.',
  };
}

export const rejectionError = (reason) => (reason.trim() ? null : 'Enter a reason for the partner.');

// Exact kobo from typed text, never through a fractional number. Null when the
// text is not a money amount, which includes any sign. Here because the check below
// must judge exactly the amount the form then sends.
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
