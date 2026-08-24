import { useState } from 'react';
import { formatNGN } from '../../lib/format.js';
import DealerStatementModal from '../DealerStatementModal.jsx';

const BAND_STYLES = {
  HEALTHY: 'bg-emerald-100 text-emerald-800 border border-emerald-200',
  WATCH: 'bg-amber-100 text-amber-800 border border-amber-200',
  'AT RISK': 'bg-red-100 text-red-800 border border-red-200',
};

const BAND_ROW = {
  HEALTHY: '',
  WATCH: 'bg-amber-50/40',
  'AT RISK': 'bg-red-50/40',
};

function Delta({ value }) {
  if (value === null || value === undefined) return <span className="text-gray-300">—</span>;
  const n = Number(value);
  if (n > 0) return <span className="text-emerald-600 font-semibold">▲ {n.toFixed(1)}%</span>;
  if (n < 0) return <span className="text-red-600 font-semibold">▼ {Math.abs(n).toFixed(1)}%</span>;
  return <span className="text-gray-400">—</span>;
}

export default function PartnerHealthScorecard({ rows = [], loading, period }) {
  const [statementDealer, setStatementDealer] = useState(null);
  const [dealerQuery, setDealerQuery] = useState('');

  const filtered = rows.filter((r) => {
    const q = dealerQuery.trim().toLowerCase();
    if (!q) return true;
    return (
      String(r.dealer_id).toLowerCase().includes(q) ||
      String(r.dealer_name).toLowerCase().includes(q)
    );
  });

  const counts = { HEALTHY: 0, WATCH: 0, 'AT RISK': 0 };
  rows.forEach((r) => { if (counts[r.health_band] !== undefined) counts[r.health_band]++; });

  if (loading) {
    return <div className="p-4 text-sm text-gray-500 italic">Loading health scorecard…</div>;
  }

  return (
    <div className="h-full flex flex-col overflow-hidden">
      {/* Summary pills */}
      <div className="px-3 py-2 border-b border-gray-100 flex items-center gap-3 shrink-0 flex-wrap">
        <span className="text-[11px] text-gray-500 font-medium">Portfolio:</span>
        <span className="text-[11px] px-2 py-0.5 rounded-full bg-emerald-100 text-emerald-800 font-semibold border border-emerald-200">
          {counts.HEALTHY} Healthy
        </span>
        <span className="text-[11px] px-2 py-0.5 rounded-full bg-amber-100 text-amber-800 font-semibold border border-amber-200">
          {counts.WATCH} Watch
        </span>
        <span className="text-[11px] px-2 py-0.5 rounded-full bg-red-100 text-red-800 font-semibold border border-red-200">
          {counts['AT RISK']} At Risk
        </span>
        <div className="flex-1" />
        <input
          type="search"
          value={dealerQuery}
          onChange={(e) => setDealerQuery(e.target.value)}
          placeholder="filter dealer…"
          className="text-xs border border-gray-300 rounded px-2 py-1 bg-white focus:outline-none focus:ring-2 focus:ring-mtn-yellow w-40"
        />
      </div>

      {/* Table */}
      <div className="flex-1 overflow-auto">
        <table className="w-full text-xs border-collapse">
          <thead className="sticky top-0 bg-gray-50 z-10">
            <tr className="text-gray-600">
              <th className="border-b border-gray-200 px-2 py-1.5 text-left font-semibold">Dealer</th>
              <th className="border-b border-gray-200 px-2 py-1.5 text-center font-semibold">Score</th>
              <th className="border-b border-gray-200 px-2 py-1.5 text-right font-semibold">Settlement %</th>
              <th className="border-b border-gray-200 px-2 py-1.5 text-right font-semibold">MoM Δ</th>
              <th className="border-b border-gray-200 px-2 py-1.5 text-right font-semibold">Yield %</th>
              <th className="border-b border-gray-200 px-2 py-1.5 text-right font-semibold">Zero Comm %</th>
              <th className="border-b border-gray-200 px-2 py-1.5 text-right font-semibold">Outstanding</th>
              <th className="border-b border-gray-200 px-2 py-1.5 text-center font-semibold">Flag</th>
              <th className="border-b border-gray-200 px-2 py-1.5 text-center font-semibold"></th>
            </tr>
          </thead>
          <tbody>
            {filtered.length === 0 && (
              <tr>
                <td colSpan={9} className="px-3 py-4 text-center text-gray-400 italic">
                  No dealers match.
                </td>
              </tr>
            )}
            {filtered.map((r, i) => (
              <tr
                key={`${r.dealer_id}-${i}`}
                className={`border-b border-gray-100 last:border-b-0 hover:brightness-95 transition ${BAND_ROW[r.health_band] || ''}`}
              >
                <td className="px-2 py-1.5 text-gray-800 truncate max-w-[200px]" title={r.dealer_name}>
                  <div className="truncate">{r.dealer_name}</div>
                  <div className="text-[10px] text-gray-400">{r.dealer_id}</div>
                </td>
                <td className="px-2 py-1.5 text-center">
                  <span className={`inline-block text-[10px] font-bold px-2 py-0.5 rounded-full ${BAND_STYLES[r.health_band] || ''}`}>
                    {r.health_score}
                  </span>
                </td>
                <td className="px-2 py-1.5 text-right tabular-nums text-gray-700">
                  {Number(r.settlement_rate_pct).toFixed(1)}%
                </td>
                <td className="px-2 py-1.5 text-right tabular-nums">
                  <Delta value={r.settlement_rate_delta} />
                </td>
                <td className="px-2 py-1.5 text-right tabular-nums text-gray-700">
                  {Number(r.commission_yield_pct).toFixed(1)}%
                </td>
                <td className="px-2 py-1.5 text-right tabular-nums text-gray-700">
                  {Number(r.zero_commission_rate_pct).toFixed(1)}%
                </td>
                <td className="px-2 py-1.5 text-right tabular-nums text-gray-800 font-medium">
                  {formatNGN(r.outstanding_ngn)}
                </td>
                <td className="px-2 py-1.5 text-center">
                  {r.dispute_flag ? (
                    <span className="text-[10px] font-semibold text-red-700 bg-red-100 rounded px-1.5 py-0.5">DISPUTE</span>
                  ) : (
                    <span className="text-gray-300 text-[10px]">—</span>
                  )}
                </td>
                <td className="px-2 py-1.5 text-center">
                  <button
                    onClick={() => setStatementDealer({ id: r.dealer_id, name: r.dealer_name })}
                    className="text-[10px] text-gray-700 hover:text-gray-900 font-medium border border-gray-200 rounded px-1.5 py-0.5 hover:bg-yellow-50 hover:border-mtn-yellow transition"
                  >
                    Statement
                  </button>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      <DealerStatementModal
        open={!!statementDealer}
        onClose={() => setStatementDealer(null)}
        dealerId={statementDealer?.id}
        dealerName={statementDealer?.name}
        period={period}
      />
    </div>
  );
}
