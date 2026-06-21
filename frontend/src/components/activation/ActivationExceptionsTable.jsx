// Activation exceptions table — one row per (dealer, exception_type).
// Exception type rendered as a coloured badge:
//   ALL_UNQUALIFIED       → red
//   HIGH_UNQUALIFIED_RATE → amber
//   UNUSUAL_VOLUME        → blue  (NOT red — investigation, not fraud)

import { formatNGN } from '../../lib/format.js';

const BADGE_STYLE = {
  ALL_UNQUALIFIED: 'bg-red-100 text-red-800 border-red-200',
  HIGH_UNQUALIFIED_RATE: 'bg-amber-100 text-amber-800 border-amber-200',
  UNUSUAL_VOLUME: 'bg-blue-100 text-blue-800 border-blue-200',
};

const BADGE_TOOLTIP = {
  ALL_UNQUALIFIED:
    'Activations recorded but zero commission — likely USP snapshot miss.',
  HIGH_UNQUALIFIED_RATE:
    'More than 50% of activations did not earn commission.',
  UNUSUAL_VOLUME:
    'High volume vs peers. Requires investigation.',
};

function ExceptionBadge({ type }) {
  const style = BADGE_STYLE[type] || 'bg-gray-100 text-gray-700 border-gray-200';
  const tooltip = BADGE_TOOLTIP[type] || '';
  return (
    <span
      className={`inline-block px-2 py-0.5 text-[10px] font-semibold uppercase tracking-wide border rounded-full ${style}`}
      title={tooltip}
    >
      {type}
    </span>
  );
}

export default function ActivationExceptionsTable({ rows = [], loading = false }) {
  if (loading) {
    return (
      <div className="p-4 text-sm text-gray-500 italic">
        Loading exceptions…
      </div>
    );
  }
  if (!rows.length) {
    return (
      <div className="p-4 text-sm text-gray-500 italic">No flagged dealers.</div>
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
              Class
            </th>
            <th className="border-b border-gray-200 px-2 py-1.5 text-left font-semibold">
              Exception
            </th>
            <th className="border-b border-gray-200 px-2 py-1.5 text-right font-semibold">
              Activations
            </th>
            <th className="border-b border-gray-200 px-2 py-1.5 text-right font-semibold">
              Qualified
            </th>
            <th className="border-b border-gray-200 px-2 py-1.5 text-right font-semibold">
              Rate %
            </th>
            <th className="border-b border-gray-200 px-2 py-1.5 text-right font-semibold">
              Commission
            </th>
          </tr>
        </thead>
        <tbody>
          {rows.map((r, i) => (
            <tr
              key={`${r.dealer_id}-${r.exception_type}-${i}`}
              className="hover:bg-gray-50 border-b border-gray-100 last:border-b-0"
            >
              <td
                className="px-2 py-1.5 text-gray-800 truncate max-w-[220px]"
                title={r.dealer_name}
              >
                {r.dealer_name}
              </td>
              <td
                className="px-2 py-1.5 text-gray-500 truncate max-w-[140px]"
                title={r.account_profile_class}
              >
                {r.account_profile_class || '—'}
              </td>
              <td className="px-2 py-1.5">
                <ExceptionBadge type={r.exception_type} />
              </td>
              <td className="px-2 py-1.5 text-right tabular-nums text-gray-800">
                {r.activation_count}
              </td>
              <td className="px-2 py-1.5 text-right tabular-nums text-gray-700">
                {r.qualified_activation_count}
              </td>
              <td className="px-2 py-1.5 text-right tabular-nums text-gray-700">
                {Number(r.qualification_rate_pct).toFixed(2)}%
              </td>
              <td className="px-2 py-1.5 text-right tabular-nums font-semibold text-gray-900">
                {formatNGN(r.activation_commission_amount)}
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
