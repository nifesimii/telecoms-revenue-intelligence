// A frozen order's lines and its total, which comes from the server or the pricing
// the preview was built from, never from adding up what is shown.

import { formatMinorNGN } from '../../lib/format.js';
import { quantityLabel } from './salesDisplay.js';

export default function OrderLines({ caption, lines, totalMinor }) {
  return <table className="sales-table mt-5">
    <caption className="sr-only">{caption}</caption>
    <thead><tr><th scope="col">Product</th><th scope="col" className="sales-amount hidden sm:table-cell">Quantity</th><th scope="col" className="sales-amount hidden sm:table-cell">Unit price</th><th scope="col" className="sales-amount">Line total</th></tr></thead>
    <tbody>{lines.map((line) => <tr key={line.product_code}>
      <th scope="row"><span className="block font-semibold">{line.product_code}</span> <span className="block">{line.description}</span>
        <span className="block sm:hidden text-gray-600 mt-1">{quantityLabel(line.quantity, line.unit)} × {formatMinorNGN(line.unit_price_minor)}</span></th>
      <td className="sales-amount hidden sm:table-cell">{quantityLabel(line.quantity, line.unit)}</td>
      <td className="sales-amount hidden sm:table-cell">{formatMinorNGN(line.unit_price_minor)}</td>
      <td className="sales-amount">{formatMinorNGN(line.line_total_minor)}</td>
    </tr>)}</tbody>
    <tfoot><tr><th scope="row">Total</th><td className="hidden sm:table-cell" /><td className="hidden sm:table-cell" /><td className="sales-amount">{formatMinorNGN(totalMinor)}</td></tr></tfoot>
  </table>;
}
