// Activation summary table — one row per dealer for the selected month.
// Columns: Rank | Dealer | Class | Total Acts | Qualified | Non-Qual | Rate % | Commission
// Rate % cell traffic-light: green (>=80), amber (50-79), red (<50).

import { formatNGN } from '../../lib/format.js';
import HelpIcon, { QUALIFICATION_HELP } from '../shared/HelpIcon.jsx';

function rateTone(pct) {
  const v = Number(pct);
  if (!isFinite(v)) return 'text-gray-400';
  if (v >= 80) return 'text-emerald-700 bg-emerald-50';
  if (v >= 50) return 'text-amber-700 bg-amber-50';
  return 'text-red-700 bg-red-50';
}

export default function ActivationSummaryTable({ rows = [], loading = false }) {
  if (loading) {
    return (
      <div className="p-4 text-sm text-gray-500 italic">
        Loading activation summary…
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
            <th className="border-b border-gray-200 px-2 py-1.5 text-left font-semibold w-10">
              #
            </th>
            <th className="border-b border-gray-200 px-2 py-1.5 text-left font-semibold">
              Dealer
            </th>
            <th className="border-b border-gray-200 px-2 py-1.5 text-left font-semibold">
              Class
            </th>
            <th className="border-b border-gray-200 px-2 py-1.5 text-right font-semibold">
              Total
            </th>
            <th className="border-b border-gray-200 px-2 py-1.5 text-right font-semibold">
              <span className="inline-flex items-center justify-end">
                Qualified
                <HelpIcon label="What is a qualified activation?">{QUALIFICATION_HELP}</HelpIcon>
              </span>
            </th>
            <th className="border-b border-gray-200 px-2 py-1.5 text-right font-semibold">
              <span className="inline-flex items-center justify-end">
                Non-Qual
                <HelpIcon label="What is an unqualified activation?">{QUALIFICATION_HELP}</HelpIcon>
              </span>
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
              key={r.dealer_id || i}
              className="hover:bg-gray-50 border-b border-gray-100 last:border-b-0"
            >
              <td className="px-2 py-1.5 text-gray-400 tabular-nums">{i + 1}</td>
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
              <td className="px-2 py-1.5 text-right tabular-nums text-gray-800">
                {r.activation_count}
              </td>
              <td className="px-2 py-1.5 text-right tabular-nums text-gray-700">
                {r.qualified_activation_count}
              </td>
              <td className="px-2 py-1.5 text-right tabular-nums text-gray-700">
                {r.non_qualified_activation_count}
              </td>
              <td className="px-2 py-1.5 text-right">
                <span
                  className={`inline-block px-2 py-0.5 rounded text-[11px] font-semibold tabular-nums ${rateTone(
                    r.qualification_rate_pct,
                  )}`}
                >
                  {Number(r.qualification_rate_pct).toFixed(2)}%
                </span>
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
