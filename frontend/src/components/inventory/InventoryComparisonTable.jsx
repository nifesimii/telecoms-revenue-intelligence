import { COMPARISON_STATUS, columnsFor, gapPercent, gapUnits, subjectFor, units } from './inventoryPresentation.js';

export function ComparisonStatus({ type }) {
  const status = COMPARISON_STATUS[type];
  return <span className={`inline-block rounded-md border px-2 py-1 text-xs font-medium ${status?.tone || 'bg-gray-50 text-gray-700 border-gray-200'}`}>
    {status?.label || 'Comparison unavailable'}
  </span>;
}

function cell(id, row, { busy, onSelect, rowRefs }) {
  switch (id) {
    case 'subject': return <th key={id} scope="row" className="text-left min-w-56 w-72 max-w-xs">
      <p className="break-words"><span className="font-semibold">{row.dealer_name || 'Dealer name unavailable'}</span> <span className="text-xs text-gray-500 tabular-nums">{row.dealer_id}</span></p>
      <p className="mt-1 break-words"><span className="text-sm text-gray-700">{row.product_name || 'Product name unavailable'}</span> <span className="text-xs text-gray-500">{row.product_code}</span>
        {row.scenario_id && <> <span className="inline-block rounded border border-gray-300 px-1.5 text-xs text-gray-700 bg-gray-50">{row.scenario_label}</span></>}</p>
    </th>;
    case 'purchases': return <td key={id} className="text-right tabular-nums">{units(row.total_units_purchased)}{row.total_units_purchased == null && <span className="block text-xs text-gray-500 mt-1">Not recorded</span>}</td>;
    case 'activations': return <td key={id} className="text-right tabular-nums">{units(row.activation_count)}</td>;
    case 'excess': return <td key={id} className="text-right tabular-nums font-semibold">{gapUnits(row.inventory_gap)}</td>;
    case 'excess_pct': return <td key={id} className="text-right tabular-nums">{gapPercent(row.gap_pct)}</td>;
    case 'comparison': return <td key={id}><ComparisonStatus type={row.finding_type} />{row.finding_type === 'CONFIRMED_MISMATCH' && <p className="text-xs text-gray-600 mt-2">Requires investigation</p>}</td>;
    case 'evidence': return <td key={id}><button ref={(node) => { rowRefs.current[subjectFor(row)] = node; }}
      className="overview-button whitespace-nowrap" disabled={busy} onClick={() => onSelect(row)}
      aria-label={`View evidence for dealer ${row.dealer_id}, product ${row.product_code}`}>View evidence</button></td>;
    default: return null;
  }
}

export default function InventoryComparisonTable({ rows, view, busy, onSelect, rowRefs }) {
  const columns = columnsFor(view);
  return <div className="overflow-auto max-h-[70vh]" tabIndex={0} role="region" aria-label="Inventory comparison table" aria-busy={busy}>
    <table className="commission-table inventory-table w-full text-sm">
      <caption className="sr-only">One row per dealer and product. Quantities compare reporting-period activations with available invoice records.</caption>
      <thead className="sticky top-0 z-10"><tr>
        {columns.map((c) => <th key={c.id} scope="col" className={c.numeric ? 'text-right' : 'text-left'}>{c.label}</th>)}
      </tr></thead>
      <tbody>{rows.map((row) => <tr key={subjectFor(row)}>{columns.map((c) => cell(c.id, row, { busy, onSelect, rowRefs }))}</tr>)}</tbody>
    </table>
  </div>;
}
