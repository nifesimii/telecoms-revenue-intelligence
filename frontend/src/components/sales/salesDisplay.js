// Partner Sales labels and totals. Amounts are exact kobo.

import { formatCount } from '../../lib/format.js';
import { quantityError } from './salesFormChecks.js';

export const partnerLabel = (partner) => `${partner.name} · Account ${partner.code}`;
export const quantityLabel = (quantity, unit) => `${formatCount(quantity)} ${unit}${quantity === 1 ? '' : 's'}`;
export const partnerMatches = (partner, term) => partner.code.includes(term) || partner.name.toLowerCase().includes(term);

export const lineTotalMinor = (line, product, maxQuantity) => (quantityError(line.quantity, maxQuantity) ? null : Number(line.quantity) * product.price_minor);

// Null while any line is invalid: a partial total would misstate the draft.
export function draftTotalMinor(draft, productByCode, maxQuantity) {
  let total = 0;
  for (const line of draft.lines) {
    const lineTotal = lineTotalMinor(line, productByCode(line.product_code), maxQuantity);
    if (lineTotal === null) return null;
    total += lineTotal;
  }
  return total;
}

// The list row that opens an invoice, where focus returns after its detail closes.
export const invoiceOpenerId = (reference) => `sales-open-${reference}`;
