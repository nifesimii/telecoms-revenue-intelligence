import { COMPARISON_STATUS, gapPercent, gapUnits, subjectFor, units } from './inventoryPresentation.js';

export function ComparisonStatus({ type }) {
  const status = COMPARISON_STATUS[type];
  return <span className={`inline-block rounded-md border px-2 py-1 text-xs font-medium ${status?.tone || 'bg-gray-50 text-gray-700 border-gray-200'}`}>
    {status?.label || 'Comparison unavailable'}
  </span>;
}

export default function InventoryComparisonTable({ rows, busy, onSelect, rowRefs }) {
  return <div className="overflow-auto max-h-[70vh]" tabIndex={0} role="region" aria-label="Inventory comparison table" aria-busy={busy}>
    <table className="commission-table inventory-table w-full text-sm">
      <caption className="sr-only">One row per dealer and product. Quantities compare reporting-period activations with available invoice records.</caption>
      <thead className="sticky top-0 z-10"><tr>
        {['Dealer / product', 'Recorded purchases', 'Activations', 'Excess units', 'Excess %', 'Comparison', 'Evidence'].map((label, i) =>
          <th key={label} scope="col" className={i > 0 && i < 5 ? 'text-right' : 'text-left'}>{label}</th>)}
      </tr></thead>
      <tbody>{rows.map((row) => <tr key={subjectFor(row)}>
        <th scope="row" className="text-left min-w-56 w-72 max-w-xs">
          <p className="font-semibold break-words">{row.dealer_name || 'Dealer name unavailable'}</p>
          <p className="text-xs text-gray-500 mt-1">Dealer {row.dealer_id}</p>
          <p className="text-sm text-gray-700 mt-3 break-words">{row.product_name || 'Product name unavailable'}</p>
          <p className="text-xs text-gray-500 mt-1">Product {row.product_code}</p>
          {row.scenario_id && <p className="text-xs font-medium text-blue-900 mt-3">{row.scenario_label}</p>}
        </th>
        <td className="text-right tabular-nums">{units(row.total_units_purchased)}{row.total_units_purchased == null && <span className="block text-xs text-gray-500 mt-1">Not recorded</span>}</td>
        <td className="text-right tabular-nums">{units(row.activation_count)}</td>
        <td className="text-right tabular-nums font-semibold">{gapUnits(row.inventory_gap)}</td>
        <td className="text-right tabular-nums">{gapPercent(row.gap_pct)}</td>
        <td><ComparisonStatus type={row.finding_type} />{row.finding_type === 'CONFIRMED_MISMATCH' && <p className="text-xs text-gray-600 mt-2">Requires investigation</p>}</td>
        <td><button ref={(node) => { rowRefs.current[subjectFor(row)] = node; }}
          className="overview-button whitespace-nowrap" disabled={busy} onClick={() => onSelect(row)}
          aria-label={`View evidence for dealer ${row.dealer_id}, product ${row.product_code}`}>View evidence</button></td>
      </tr>)}</tbody>
    </table>
  </div>;
}
