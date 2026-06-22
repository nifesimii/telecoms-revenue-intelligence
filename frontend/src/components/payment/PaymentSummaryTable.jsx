// Payment summary table — one row per dealer. All four statuses possible.
// Status badge colours:
//   FULLY_PAID     → green
//   PARTIALLY_PAID → amber
//   DISPUTED       → red
//   PENDING        → grey
//
// When the row carries APDP reconciliation enrichment (data_source==="APDP"),
// extra columns are rendered: Sales captured, Variance, Reconciliation status.

import { formatNGN } from '../../lib/format.js';

const STATUS_TONE = {
  FULLY_PAID: 'bg-emerald-100 text-emerald-800 border-emerald-200',
  PARTIALLY_PAID: 'bg-amber-100 text-amber-800 border-amber-200',
  DISPUTED: 'bg-red-100 text-red-800 border-red-200',
  PENDING: 'bg-gray-100 text-gray-700 border-gray-200',
};

const RECON_TONE = {
  RECONCILED: 'bg-emerald-100 text-emerald-800 border-emerald-200',
  PARTIALLY_PAID: 'bg-amber-100 text-amber-800 border-amber-200',
  AMOUNT_MISMATCH: 'bg-amber-100 text-amber-800 border-amber-200',
  DISPUTED: 'bg-red-100 text-red-800 border-red-200',
  STATEMENT_WITHOUT_PAYMENT: 'bg-blue-100 text-blue-800 border-blue-200',
  SALES_WITHOUT_STATEMENT: 'bg-purple-100 text-purple-800 border-purple-200',
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

function ReconBadge({ status }) {
  if (!status) return null;
  const tone = RECON_TONE[status] || RECON_TONE.RECONCILED;
  return (
    <span
      className={`inline-block px-1.5 py-0 text-[9px] font-semibold uppercase tracking-wide border rounded ${tone}`}
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

  // Detect source from the first row (all rows in a request share data_source).
  const isApdp = rows[0]?.data_source === 'APDP';

  return (
    <div className="overflow-auto h-full">
      {isApdp ? (
        <div className="px-3 py-2 text-[10px] uppercase tracking-wide text-emerald-700 bg-emerald-50 border-b border-emerald-200 font-semibold sticky top-0 z-20">
          APDP data — reconciled from normalized.partner_settlements
        </div>
      ) : (
        <div className="px-3 py-2 text-[10px] uppercase tracking-wide text-amber-700 bg-amber-50 border-b border-amber-200 font-semibold sticky top-0 z-20">
          SIMULATED data — generated from real commission and exception records
        </div>
      )}
      <table className="w-full text-xs border-collapse">
        <thead className="sticky top-[33px] bg-gray-50 z-10">
          <tr className="text-gray-600">
            <th className="border-b border-gray-200 px-2 py-1.5 text-left font-semibold">Dealer</th>
            {!isApdp && (
              <th className="border-b border-gray-200 px-2 py-1.5 text-left font-semibold">Class</th>
            )}
            {isApdp && (
              <th className="border-b border-gray-200 px-2 py-1.5 text-right font-semibold" title="Consumer sales captured (Flow A)">Sales</th>
            )}
            <th className="border-b border-gray-200 px-2 py-1.5 text-right font-semibold">Owed</th>
            <th className="border-b border-gray-200 px-2 py-1.5 text-right font-semibold">Paid</th>
            <th className="border-b border-gray-200 px-2 py-1.5 text-right font-semibold">Outstanding</th>
            {isApdp && (
              <th className="border-b border-gray-200 px-2 py-1.5 text-right font-semibold" title="Settled − Owed (signed)">Variance</th>
            )}
            <th className="border-b border-gray-200 px-2 py-1.5 text-left font-semibold">Status</th>
            {isApdp ? (
              <th className="border-b border-gray-200 px-2 py-1.5 text-left font-semibold">Reconciliation</th>
            ) : (
              <>
                <th className="border-b border-gray-200 px-2 py-1.5 text-left font-semibold">Channel</th>
                <th className="border-b border-gray-200 px-2 py-1.5 text-left font-semibold">Pay date</th>
              </>
            )}
          </tr>
        </thead>
        <tbody>
          {sorted.map((r, i) => {
            const variance = Number(r.payment_variance_ngn ?? 0);
            const varTone =
              variance === 0
                ? 'text-gray-500'
                : variance > 0
                  ? 'text-emerald-700'
                  : 'text-red-700';
            return (
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
                {!isApdp && (
                  <td className="px-2 py-1.5 text-gray-500 truncate max-w-[130px]">
                    {r.account_profile_class || '—'}
                  </td>
                )}
                {isApdp && (
                  <td className="px-2 py-1.5 text-right tabular-nums text-gray-600" title={`${r.sale_count ?? 0} consumer transactions`}>
                    {formatNGN(r.total_sales_ngn)}
                  </td>
                )}
                <td className="px-2 py-1.5 text-right tabular-nums text-gray-700">
                  {formatNGN(r.commission_owed)}
                </td>
                <td className="px-2 py-1.5 text-right tabular-nums text-emerald-700">
                  {formatNGN(r.amount_paid)}
                </td>
                <td className="px-2 py-1.5 text-right tabular-nums font-semibold text-gray-900">
                  {formatNGN(r.amount_unpaid)}
                </td>
                {isApdp && (
                  <td className={`px-2 py-1.5 text-right tabular-nums font-semibold ${varTone}`}>
                    {variance > 0 ? '+' : variance < 0 ? '−' : ''}
                    {formatNGN(Math.abs(variance))}
                  </td>
                )}
                <td className="px-2 py-1.5">
                  <StatusBadge status={r.payment_status} />
                </td>
                {isApdp ? (
                  <td className="px-2 py-1.5">
                    <ReconBadge status={r.reconciliation_status} />
                  </td>
                ) : (
                  <>
                    <td className="px-2 py-1.5 text-[11px] text-gray-500">
                      {r.payment_channel || '—'}
                    </td>
                    <td className="px-2 py-1.5 text-[11px] tabular-nums text-gray-600">
                      {r.payment_date || '—'}
                    </td>
                  </>
                )}
              </tr>
            );
          })}
        </tbody>
      </table>
    </div>
  );
}
