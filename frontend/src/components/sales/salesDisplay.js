// Partner Sales labels and messages.

import { formatCount } from '../../lib/format.js';

export const partnerLabel = (partner) => `${partner.name} · Account ${partner.code}`;
export const quantityLabel = (quantity, unit) => `${formatCount(quantity)} ${unit}${quantity === 1 ? '' : 's'}`;

// The list row that opens an invoice, where focus returns after its detail closes.
export const invoiceOpenerId = (reference) => `sales-open-${reference}`;

// A refusal means the server would not touch a record that changed elsewhere or is
// gone, so nothing was overwritten. Anything else gets a message to show.
export function describeFailure(error, fallback) {
  const { status, data } = error.response ?? {};
  if ([404, 409].includes(status)) return { refused: true };
  return { refused: false, message: status === 422 && typeof data?.detail === 'string' ? data.detail : fallback };
}
