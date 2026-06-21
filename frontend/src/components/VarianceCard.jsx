// Month-on-month variance card for a single dealer.
//
// Props:
//   dealer_name:     string
//   current_period:  string (YYYYMM)
//   prior_period:    string (YYYYMM)
//   delta_ngn:       number
//   delta_pct:       number (optional)
//
// Visuals:
//   delta > 0 → green up arrow
//   delta < 0 → red down arrow
//   delta === 0 → grey em dash

import { formatNGN, formatPeriod } from '../lib/format.js';

function UpArrow() {
  return (
    <svg viewBox="0 0 20 20" fill="currentColor" className="w-4 h-4">
      <path
        fillRule="evenodd"
        d="M10 17a.75.75 0 01-.75-.75V5.66l-3.97 3.97a.75.75 0 01-1.06-1.06l5.25-5.25a.75.75 0 011.06 0l5.25 5.25a.75.75 0 11-1.06 1.06L10.75 5.66v10.59A.75.75 0 0110 17z"
        clipRule="evenodd"
      />
    </svg>
  );
}

function DownArrow() {
  return (
    <svg viewBox="0 0 20 20" fill="currentColor" className="w-4 h-4">
      <path
        fillRule="evenodd"
        d="M10 3a.75.75 0 01.75.75v10.59l3.97-3.97a.75.75 0 111.06 1.06l-5.25 5.25a.75.75 0 01-1.06 0l-5.25-5.25a.75.75 0 111.06-1.06l3.97 3.97V3.75A.75.75 0 0110 3z"
        clipRule="evenodd"
      />
    </svg>
  );
}

export default function VarianceCard({
  dealer_name,
  current_period,
  prior_period,
  delta_ngn,
  delta_pct,
}) {
  const value = Number(delta_ngn) || 0;
  const positive = value > 0;
  const negative = value < 0;

  const tone = positive
    ? 'text-emerald-600 bg-emerald-50 border-emerald-200'
    : negative
      ? 'text-red-600 bg-red-50 border-red-200'
      : 'text-gray-500 bg-gray-50 border-gray-200';

  const arrow = positive ? <UpArrow /> : negative ? <DownArrow /> : <span>—</span>;
  const pct =
    delta_pct === undefined || delta_pct === null
      ? null
      : `${value >= 0 ? '+' : '−'}${Math.abs(Number(delta_pct)).toFixed(1)}%`;

  return (
    <div className="border border-gray-200 rounded-lg p-3 bg-white shadow-sm">
      {dealer_name && (
        <div
          className="text-xs text-gray-500 truncate"
          title={dealer_name}
        >
          {dealer_name}
        </div>
      )}
      <div className="mt-1 flex items-center gap-2">
        <div
          className={`flex items-center gap-1 px-2 py-1 rounded-md border text-sm font-semibold ${tone}`}
        >
          {arrow}
          <span className="tabular-nums">
            {formatNGN(Math.abs(value))}
          </span>
          {pct && <span className="text-xs font-normal opacity-80">({pct})</span>}
        </div>
      </div>
      <div className="mt-2 text-[11px] text-gray-500">
        <span className="font-medium text-gray-700">{formatPeriod(current_period)}</span>
        <span className="mx-1">vs</span>
        <span>{formatPeriod(prior_period)}</span>
      </div>
    </div>
  );
}
