// Big headline coverage card with four sub-stats.
// Coverage tone:
//   >= 85%  → emerald
//   60-84%  → amber
//   < 60%   → red

import { formatNGN, formatPeriod } from '../../lib/format.js';

function coverageTone(pct) {
  if (pct >= 85) return 'text-emerald-700 bg-emerald-50 border-emerald-200';
  if (pct >= 60) return 'text-amber-700 bg-amber-50 border-amber-200';
  return 'text-red-700 bg-red-50 border-red-200';
}

function SubStat({ label, value, tone = 'text-gray-900' }) {
  return (
    <div className="flex flex-col gap-0.5">
      <span className="text-[10px] uppercase tracking-wide text-gray-500">
        {label}
      </span>
      <span className={`text-base font-semibold tabular-nums ${tone}`}>
        {value}
      </span>
    </div>
  );
}

export default function PaymentCoverageCard({ data, loading }) {
  const pct = Number(data?.payment_coverage_pct) || 0;
  const tone = coverageTone(pct);

  return (
    <div className="bg-white border border-gray-200 rounded-lg shadow-sm p-5 relative overflow-hidden">
      <div className="absolute top-0 left-0 h-full w-1 bg-mtn-yellow" />
      <div className="flex items-start gap-4">
        <div
          className={`px-5 py-4 rounded-lg border ${tone} flex flex-col items-center`}
        >
          <span className="text-[10px] uppercase tracking-wide opacity-80">
            Commission coverage
          </span>
          <span className="text-4xl font-bold tabular-nums">
            {loading ? '…' : `${pct.toFixed(1)}%`}
          </span>
          <span className="text-[10px] uppercase tracking-wide opacity-80">
            for {formatPeriod(data?.period) || '—'}
          </span>
        </div>
        <div className="flex-1 grid grid-cols-2 sm:grid-cols-4 gap-4 pl-4 border-l border-gray-100">
          <SubStat
            label="Total owed"
            value={loading ? '…' : formatNGN(data?.total_commission_owed)}
          />
          <SubStat
            label="Total paid"
            value={loading ? '…' : formatNGN(data?.total_amount_paid)}
            tone="text-emerald-700"
          />
          <SubStat
            label="Outstanding"
            value={loading ? '…' : formatNGN(data?.total_amount_unpaid)}
            tone="text-amber-700"
          />
          <SubStat
            label="Disputed"
            value={loading ? '…' : Number(data?.disputed_count || 0).toLocaleString()}
            tone="text-red-700"
          />
        </div>
        <span className="absolute top-3 right-3 text-[10px] uppercase tracking-wide bg-amber-100 text-amber-800 border border-amber-200 rounded-full px-2 py-0.5 font-semibold">
          SIMULATED DATA
        </span>
      </div>
    </div>
  );
}
