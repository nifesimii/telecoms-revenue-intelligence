// What a draft costs, from the server's catalogue and quantity limit. Amounts are exact kobo.

import { quantityError } from './salesFormChecks.js';

export function draftPricing(catalogue, maxQuantity) {
  const productByCode = (code) => catalogue.find((product) => product.code === code);
  const errorInQuantity = (quantity) => quantityError(quantity, maxQuantity);
  const lineTotalMinor = (line) => (errorInQuantity(line.quantity) ? null : Number(line.quantity) * productByCode(line.product_code).price_minor);
  // Null while any line is invalid: a partial total would misstate the draft.
  const draftTotalMinor = (draft) => {
    let total = 0;
    for (const line of draft.lines) {
      const lineTotal = lineTotalMinor(line);
      if (lineTotal === null) return null;
      total += lineTotal;
    }
    return total;
  };
  return { catalogue, productByCode, quantityError: errorInQuantity, lineTotalMinor, draftTotalMinor };
}
