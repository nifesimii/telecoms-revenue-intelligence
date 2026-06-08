// Phase 3 panel — Inventory Intelligence.
//
// Summary cards on top (CONFIRMED_MISMATCH / NO_INVOICE_RECORD / WITHIN_ALLOCATION)
// + a single table below. Toggle to include WITHIN_ALLOCATION rows.
// Reuses the existing period dropdown pattern.

import { useEffect, useMemo, useState } from 'react';
import { getPeriods, getInventoryComparison } from '../../api/client.js';
import InventoryComparisonTable from './InventoryComparisonTable.jsx';

function Stat({ label, value, tone = 'text-gray-900', sub }) {
  return (
    <div className="flex flex-col gap-0.5">
      <span className="text-[10px] uppercase tracking-wide text-gray-500">
        {label}
      </span>
      <span className={`text-base font-semibold tabular-nums ${tone}`}>
        {value}
      </span>
      {sub && <span className="text-[10px] text-gray-500">{sub}</span>}
    </div>
  );
}

function SummaryCard({ label, count, sub, tone, accent }) {
  return (
    <div
      className={`bg-white border border-gray-200 rounded-lg shadow-sm p-4 relative overflow-hidden`}
    >
      <div className={`absolute top-0 left-0 h-full w-1 ${accent}`} />
      <div className="text-[11px] uppercase tracking-wide text-gray-500">
        {label}
      </div>
      <div className={`mt-1 text-2xl font-bold tabular-nums ${tone}`}>
        {count}
      </div>
      {sub && (
        <div className="mt-1 text-[11px] text-gray-500 leading-snug">{sub}</div>
      )}
    </div>
  );
}

export default function InventoryIntelligencePanel() {
  const [periods, setPeriods] = useState([]);
  const [period, setPeriod] = useState('');
  const [includeWithin, setIncludeWithin] = useState(false);
  const [rows, setRows] = useState([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState(null);

  useEffect(() => {
    let cancelled = false;
    getPeriods()
      .then((data) => {
        if (cancelled) return;
        const ps = data.periods || [];
        setPeriods(ps);
        if (ps.length) setPeriod(ps[0]);
      })
      .catch((e) => !cancelled && setError(String(e?.message || e)));
    return () => {
      cancelled = true;
    };
  }, []);

  useEffect(() => {
    if (!period) return;
    let cancelled = false;
    setLoading(true);
    setError(null);
    getInventoryComparison(period, includeWithin)
      .then((data) => !cancelled && setRows(Array.isArray(data) ? data : []))
      .catch((e) => {
        if (!cancelled)
          setError(e?.response?.data?.detail || e?.message || String(e));
      })
      .finally(() => !cancelled && setLoading(false));
    return () => {
      cancelled = true;
    };
  }, [period, includeWithin]);

  const counts = useMemo(() => {
    const c = {
      CONFIRMED_MISMATCH: 0,
      NO_INVOICE_RECORD: 0,
      WITHIN_ALLOCATION: 0,
      total_gap_units: 0,
    };
    for (const r of rows) {
      c[r.finding_type] = (c[r.finding_type] || 0) + 1;
      if (
        r.finding_type === 'CONFIRMED_MISMATCH' &&
        r.inventory_gap !== null &&
        r.inventory_gap !== undefined
      ) {
        c.total_gap_units += Number(r.inventory_gap) || 0;
      }
    }
    return c;
  }, [rows]);

  return (
    <div className="h-full flex flex-col bg-gray-50 text-gray-800">
      <div className="px-5 py-3 bg-white border-b border-gray-200 flex flex-wrap items-end gap-4">
        <div>
          <label className="block text-[11px] uppercase tracking-wide text-gray-500 mb-1">
            Reporting period
          </label>
          <select
            value={period}
            onChange={(e) => setPeriod(e.target.value)}
            className="text-sm border border-gray-300 rounded-md px-2 py-1.5 bg-white focus:outline-none focus:ring-2 focus:ring-mtn-yellow focus:border-mtn-yellow"
          >
            {periods.length === 0 && <option value="">—</option>}
            {periods.map((p) => (
              <option key={p} value={p}>
                {p}
              </option>
            ))}
          </select>
        </div>
        <label className="flex items-center gap-2 text-xs text-gray-600 select-none">
          <input
            type="checkbox"
            checked={includeWithin}
            onChange={(e) => setIncludeWithin(e.target.checked)}
            className="w-4 h-4 accent-mtn-yellow"
          />
          Show WITHIN_ALLOCATION rows
        </label>
        <div className="flex-1" />
        <div className="text-[11px] text-gray-500">
          Phase 3 · activations vs IFS purchases
        </div>
      </div>

      {error && (
        <div className="mx-5 mt-3 text-xs text-red-600 bg-red-50 border border-red-200 rounded-md px-3 py-2">
          {error}
        </div>
      )}

      {/* Body: cards row at natural height + table card that fills remaining
          space and scrolls internally. ``min-h-0`` is essential — flex
          children default to ``min-height: auto`` and won't shrink to fit. */}
      <div className="flex-1 min-h-0 p-5 flex flex-col gap-4 overflow-hidden">
        <div className="shrink-0 grid grid-cols-1 sm:grid-cols-3 gap-4">
          <SummaryCard
            label="Confirmed mismatches"
            count={counts.CONFIRMED_MISMATCH}
            sub={
              counts.CONFIRMED_MISMATCH > 0
                ? `Total excess units: ${counts.total_gap_units.toLocaleString()}`
                : 'No confirmed mismatches'
            }
            tone="text-amber-700"
            accent="bg-amber-400"
          />
          <SummaryCard
            label="No invoice record"
            count={counts.NO_INVOICE_RECORD}
            sub="May reflect purchases outside the available data window. Not a confirmed mismatch."
            tone="text-blue-700"
            accent="bg-blue-400"
          />
          <SummaryCard
            label="Within allocation"
            count={
              includeWithin
                ? counts.WITHIN_ALLOCATION
                : '—'
            }
            sub={
              includeWithin
                ? 'Activations covered by purchased units'
                : 'Enable the toggle above to load these rows'
            }
            tone="text-emerald-700"
            accent="bg-emerald-400"
          />
        </div>

        <div className="flex-1 min-h-0 bg-white border border-gray-200 rounded-lg shadow-sm overflow-hidden flex flex-col">
          <div className="px-3 py-2 border-b border-gray-100 text-[11px] text-gray-500 shrink-0">
            {rows.length.toLocaleString()} record{rows.length === 1 ? '' : 's'}
          </div>
          <div className="flex-1 min-h-0">
            <InventoryComparisonTable rows={rows} loading={loading} />
          </div>
        </div>
      </div>
    </div>
  );
}
