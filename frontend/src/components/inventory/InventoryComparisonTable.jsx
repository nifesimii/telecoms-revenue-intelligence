// Inventory comparison table — one row per (dealer, product) combination.
//
// Visual cues:
//   * CONFIRMED_MISMATCH   → amber left border, red gap_pct text if >= 100%
//   * NO_INVOICE_RECORD    → blue left border, italicised note
//   * WITHIN_ALLOCATION    → green left border
//
// Tooltip on the finding type badge describes what each label means.

const BADGE_STYLE = {
  CONFIRMED_MISMATCH: 'bg-amber-100 text-amber-800 border-amber-200',
  NO_INVOICE_RECORD: 'bg-blue-100 text-blue-800 border-blue-200',
  WITHIN_ALLOCATION: 'bg-emerald-100 text-emerald-800 border-emerald-200',
};

const BORDER_STYLE = {
  CONFIRMED_MISMATCH: 'border-l-4 border-l-amber-400',
  NO_INVOICE_RECORD: 'border-l-4 border-l-blue-400',
  WITHIN_ALLOCATION: 'border-l-4 border-l-emerald-400',
};

const BADGE_TOOLTIP = {
  CONFIRMED_MISMATCH:
    'IFS invoice records exist AND activations exceed purchased units. Requires investigation.',
  NO_INVOICE_RECORD:
    'Activations exist but no IFS invoice record was found in the available window. NOT a confirmed mismatch.',
  WITHIN_ALLOCATION:
    'Activations are within the dealer’s purchased unit count.',
};

function fmtUnits(v) {
  if (v === null || v === undefined) return '—';
  const n = Number(v);
  if (!isFinite(n)) return '—';
  return Number.isInteger(n) ? n.toLocaleString() : n.toFixed(2);
}

function fmtGap(v) {
  if (v === null || v === undefined) return '—';
  const n = Number(v);
  if (!isFinite(n)) return '—';
  const sign = n > 0 ? '+' : n < 0 ? '−' : '';
  return `${sign}${Math.abs(n).toFixed(0)}`;
}

function gapPctTone(v, finding) {
  if (finding === 'WITHIN_ALLOCATION') return 'text-gray-400';
  if (v === null || v === undefined) return 'text-gray-400';
  const n = Number(v);
  if (n >= 100) return 'text-red-700 font-semibold';
  if (n >= 50) return 'text-amber-700 font-semibold';
  return 'text-gray-600';
}

function FindingBadge({ type }) {
  const style =
    BADGE_STYLE[type] || 'bg-gray-100 text-gray-700 border-gray-200';
  return (
    <span
      className={`inline-block px-2 py-0.5 text-[10px] font-semibold uppercase tracking-wide border rounded-full ${style}`}
      title={BADGE_TOOLTIP[type] || ''}
    >
      {type}
    </span>
  );
}

export default function InventoryComparisonTable({
  rows = [],
  loading = false,
}) {
  if (loading) {
    return (
      <div className="p-4 text-sm text-gray-500 italic">
        Loading inventory comparison…
      </div>
    );
  }
  if (!rows.length) {
    return (
      <div className="p-4 text-sm text-gray-500 italic">No data.</div>
    );
  }

  return (
    <div className="overflow-auto h-full">
      <table className="w-full text-xs border-collapse">
        <thead className="sticky top-0 bg-gray-50 z-10">
          <tr className="text-gray-600">
            <th className="border-b border-gray-200 px-2 py-1.5 text-left font-semibold">
              Dealer
            </th>
            <th className="border-b border-gray-200 px-2 py-1.5 text-left font-semibold">
              Product
            </th>
            <th className="border-b border-gray-200 px-2 py-1.5 text-right font-semibold">
              Purchased
            </th>
            <th className="border-b border-gray-200 px-2 py-1.5 text-right font-semibold">
              Activations
            </th>
            <th className="border-b border-gray-200 px-2 py-1.5 text-right font-semibold">
              Gap
            </th>
            <th className="border-b border-gray-200 px-2 py-1.5 text-right font-semibold">
              Gap %
            </th>
            <th className="border-b border-gray-200 px-2 py-1.5 text-left font-semibold">
              Finding
            </th>
            <th className="border-b border-gray-200 px-2 py-1.5 text-left font-semibold">
              Note
            </th>
          </tr>
        </thead>
        <tbody>
          {rows.map((r, i) => {
            const isNoInvoice = r.finding_type === 'NO_INVOICE_RECORD';
            return (
              <tr
                key={`${r.dealer_id}-${r.product_code}-${i}`}
                className={`hover:bg-gray-50 border-b border-gray-100 last:border-b-0 ${
                  BORDER_STYLE[r.finding_type] || ''
                }`}
              >
                <td
                  className="px-2 py-1.5 text-gray-800 truncate max-w-[200px]"
                  title={r.dealer_name}
                >
                  {r.dealer_name}
                </td>
                <td
                  className="px-2 py-1.5 text-gray-600 truncate max-w-[120px]"
                  title={r.product_name}
                >
                  {r.product_code}
                </td>
                <td className="px-2 py-1.5 text-right tabular-nums text-gray-700">
                  {fmtUnits(r.total_units_purchased)}
                </td>
                <td className="px-2 py-1.5 text-right tabular-nums text-gray-800">
                  {r.activation_count}
                </td>
                <td className="px-2 py-1.5 text-right tabular-nums text-gray-700">
                  {fmtGap(r.inventory_gap)}
                </td>
                <td
                  className={`px-2 py-1.5 text-right tabular-nums ${gapPctTone(
                    r.gap_pct,
                    r.finding_type,
                  )}`}
                >
                  {r.gap_pct === null || r.gap_pct === undefined
                    ? '—'
                    : `${Number(r.gap_pct).toFixed(1)}%`}
                </td>
                <td className="px-2 py-1.5">
                  <FindingBadge type={r.finding_type} />
                </td>
                <td
                  className={`px-2 py-1.5 text-[11px] max-w-[260px] ${
                    isNoInvoice ? 'italic text-blue-700' : 'text-gray-500'
                  }`}
                  title={r.data_coverage_note}
                >
                  {r.data_coverage_note}
                </td>
              </tr>
            );
          })}
        </tbody>
      </table>
    </div>
  );
}
