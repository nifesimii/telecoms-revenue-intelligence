// Standalone dealer commission summary table — sidebar / modal friendly.
//
// Columns: Rank | Dealer Name | Partner Class | Activations | Commission | Zero-Comm
// Sortable by Commission (descending by default) — click the header to toggle.
// Zero-Commission Count > 0 renders in amber with a warning glyph.

import { useMemo, useState } from 'react';
import { formatNGN } from '../lib/format.js';

function WarningIcon() {
  return (
    <svg
      viewBox="0 0 20 20"
      fill="currentColor"
      aria-hidden="true"
      className="inline-block w-3 h-3 mr-1"
    >
      <path
        fillRule="evenodd"
        d="M8.485 2.495c.673-1.167 2.357-1.167 3.03 0l6.28 10.875c.673 1.167-.17 2.63-1.516 2.63H3.72c-1.347 0-2.189-1.463-1.515-2.63L8.485 2.495zM10 5a.75.75 0 01.75.75v3.5a.75.75 0 01-1.5 0v-3.5A.75.75 0 0110 5zm0 9a1 1 0 100-2 1 1 0 000 2z"
        clipRule="evenodd"
      />
    </svg>
  );
}

function SortArrow({ direction }) {
  // direction: 'desc' | 'asc'
  return (
    <span className="ml-1 text-[10px]">
      {direction === 'desc' ? '▼' : '▲'}
    </span>
  );
}

export default function DealerSummaryTable({ dealers = [], loading = false, onDealerClick }) {
  const [sortDir, setSortDir] = useState('desc');

  const sorted = useMemo(() => {
    const arr = [...dealers];
    arr.sort((a, b) => {
      const av = Number(a.total_commission_ngn) || 0;
      const bv = Number(b.total_commission_ngn) || 0;
      return sortDir === 'desc' ? bv - av : av - bv;
    });
    return arr;
  }, [dealers, sortDir]);

  if (loading) {
    return (
      <div className="p-3 text-xs text-gray-500 italic">Loading dealers…</div>
    );
  }

  if (!sorted.length) {
    return (
      <div className="p-3 text-xs text-gray-500 italic">
        No dealers to display.
      </div>
    );
  }

  return (
    <div className="overflow-auto">
      <table className="w-full text-xs border-collapse">
        <thead className="sticky top-0 bg-gray-50 z-10">
          <tr className="text-gray-600">
            <th className="border-b border-gray-200 px-2 py-1.5 text-left font-semibold w-7">
              #
            </th>
            <th className="border-b border-gray-200 px-2 py-1.5 text-left font-semibold">
              Dealer
            </th>
            <th className="border-b border-gray-200 px-2 py-1.5 text-right font-semibold w-10">
              Act.
            </th>
            <th
              className="border-b border-gray-200 px-2 py-1.5 text-right font-semibold cursor-pointer select-none hover:bg-gray-100"
              onClick={() =>
                setSortDir((d) => (d === 'desc' ? 'asc' : 'desc'))
              }
              title="Sort by Commission"
            >
              Comm.
              <SortArrow direction={sortDir} />
            </th>
            <th className="border-b border-gray-200 px-2 py-1.5 text-right font-semibold w-10">
              Zero
            </th>
          </tr>
        </thead>
        <tbody>
          {sorted.map((d, i) => (
            <tr
              key={d.dealer_id || i}
              onClick={onDealerClick ? () => onDealerClick(d) : undefined}
              className={`border-b border-gray-100 last:border-b-0 align-top ${
                onDealerClick
                  ? 'hover:bg-yellow-50 cursor-pointer'
                  : 'hover:bg-gray-50'
              }`}
              title={onDealerClick ? 'Click to template a question about this dealer' : undefined}
            >
              <td className="px-2 py-1.5 text-gray-400 tabular-nums">{i + 1}</td>
              <td className="px-2 py-1.5">
                <div className="text-gray-800" title={d.dealer_name}>
                  {d.dealer_name}
                </div>
                <div
                  className="text-[10px] uppercase tracking-wide text-gray-400"
                  title={d.account_profile_class}
                >
                  {d.account_profile_class}
                </div>
              </td>
              <td className="px-2 py-1.5 text-right tabular-nums text-gray-700">
                {d.total_activations}
              </td>
              <td className="px-2 py-1.5 text-right tabular-nums font-semibold text-gray-900">
                {formatNGN(d.total_commission_ngn)}
              </td>
              <td className="px-2 py-1.5 text-right tabular-nums">
                {Number(d.zero_commission_count) > 0 ? (
                  <span className="text-amber-600 font-medium whitespace-nowrap">
                    <WarningIcon />
                    {d.zero_commission_count}
                  </span>
                ) : (
                  <span className="text-gray-400">0</span>
                )}
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
