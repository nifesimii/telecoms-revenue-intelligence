// Payment summary table — one row per dealer. All four statuses possible.
// Status badge colours:
//   FULLY_PAID     → green
//   PARTIALLY_PAID → amber
//   DISPUTED       → red
//   PENDING        → grey

import { formatNGN } from '../../lib/format.js';

const STATUS_TONE = {
  FULLY_PAID: 'bg-emerald-100 text-emerald-800 border-emerald-200',
  PARTIALLY_PAID: 'bg-amber-100 text-amber-800 border-amber-200',
  DISPUTED: 'bg-red-100 text-red-800 border-red-200',
  PENDING: 'bg-gray-100 text-gray-700 border-gray-200',
};

function StatusBadge({ status }) {
  const tone = STATUS_TONE[status] || STATUS_TONE.PENDING;
  return (
    <span
      className={`inline-block px-2 py-0.5 text-[10px] font-semibold uppercase tracking-wide border rounded-full ${tone}`}
    >
      {status}
    </span>
  );
}

export default function PaymentSummaryTable({ rows = [], loading = false }) {
  if (loading) {
    return (
      <div className="p-4 text-sm text-gray-500 italic">
        Loading payment data…
      </div>
    );
  }
  if (!rows.length) {
    return <div className="p-4 text-sm text-gray-500 italic">No data.</div>;
  }

  // Sort by amount_unpaid desc by default.
  const sorted = [...rows].sort(
    (a, b) => Number(b.amount_unpaid || 0) - Number(a.amount_unpaid || 0),
  );

  return (
    <div className="overflow-auto h-full">
      <div className="px-3 py-2 text-[10px] uppercase tracking-wide text-amber-700 bg-amber-50 border-b border-amber-200 font-semibold sticky top-0 z-20">
        SIMULATED data — generated from real commission and exception records
      </div>
      <table className="w-full text-xs border-collapse">
        <thead className="sticky top-[33px] bg-gray-50 z-10">
          <tr className="text-gray-600">
            <th className="border-b border-gray-200 px-2 py-1.5 text-left font-semibold">
              Dealer
            </th>
            <th className="border-b border-gray-200 px-2 py-1.5 text-left font-semibold">
              Class
            </th>
            <th className="border-b border-gray-200 px-2 py-1.5 text-right font-semibold">
              Owed
            </th>
            <th className="border-b border-gray-200 px-2 py-1.5 text-right font-semibold">
              Paid
            </th>
            <th className="border-b border-gray-200 px-2 py-1.5 text-right font-semibold">
              Outstanding
            </th>
            <th className="border-b border-gray-200 px-2 py-1.5 text-left font-semibold">
              Status
            </th>
            <th className="border-b border-gray-200 px-2 py-1.5 text-left font-semibold">
              Channel
            </th>
            <th className="border-b border-gray-200 px-2 py-1.5 text-left font-semibold">
              Pay date
            </th>
          </tr>
        </thead>
        <tbody>
          {sorted.map((r, i) => (
            <tr
              key={`${r.distributor_code}-${i}`}
              className="hover:bg-gray-50 border-b border-gray-100 last:border-b-0"
            >
              <td
                className="px-2 py-1.5 text-gray-800 truncate max-w-[200px]"
                title={r.distributor_name}
              >
                {r.distributor_name}
              </td>
              <td className="px-2 py-1.5 text-gray-500 truncate max-w-[130px]">
                {r.account_profile_class || '—'}
              </td>
              <td className="px-2 py-1.5 text-right tabular-nums text-gray-700">
                {formatNGN(r.commission_owed)}
              </td>
              <td className="px-2 py-1.5 text-right tabular-nums text-emerald-700">
                {formatNGN(r.amount_paid)}
              </td>
              <td className="px-2 py-1.5 text-right tabular-nums font-semibold text-gray-900">
                {formatNGN(r.amount_unpaid)}
              </td>
              <td className="px-2 py-1.5">
                <StatusBadge status={r.payment_status} />
              </td>
              <td className="px-2 py-1.5 text-[11px] text-gray-500">
                {r.payment_channel || '—'}
              </td>
              <td className="px-2 py-1.5 text-[11px] tabular-nums text-gray-600">
                {r.payment_date || '—'}
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
