// Phase 2 panel — Activation Intelligence.
// Period selector lives in the global header (PeriodProvider). This panel
// owns only the "compare against" prior-period dropdown for the variance tab.

import { useEffect, useMemo, useState } from 'react';
import {
  getActivationSummary,
  getActivationVariance,
  getActivationExceptions,
} from '../../api/client.js';
import { usePeriod } from '../../context/PeriodContext.jsx';
import { formatPeriod } from '../../lib/format.js';
import { exportCsv } from '../../lib/csv.js';
import ActivationSummaryTable from './ActivationSummaryTable.jsx';
import ActivationVarianceTable from './ActivationVarianceTable.jsx';
import ActivationExceptionsTable from './ActivationExceptionsTable.jsx';

const TABS = [
  { id: 'summary', label: 'Summary' },
  { id: 'variance', label: 'Variance' },
  { id: 'exceptions', label: 'Exceptions' },
];

// Column descriptors per tab — keep these next to the table components so
// the export matches what the user sees on screen.
const CSV_COLUMNS = {
  summary: [
    { key: 'dealer_id',                       header: 'Dealer ID' },
    { key: 'dealer_name',                     header: 'Dealer Name' },
    { key: 'account_profile_class',           header: 'Profile Class' },
    { key: 'activation_count',                header: 'Total Activations' },
    { key: 'qualified_activation_count',      header: 'Qualified' },
    { key: 'non_qualified_activation_count',  header: 'Unqualified' },
    { key: 'qualification_rate_pct',          header: 'Qualification Rate %' },
    { key: 'activation_commission_amount',    header: 'Commission (NGN)' },
  ],
  variance: [
    { key: 'dealer_id',                  header: 'Dealer ID' },
    { key: 'dealer_name',                header: 'Dealer Name' },
    { key: 'activation_count_a',         header: 'Activations (period A)' },
    { key: 'activation_count_b',         header: 'Activations (period B)' },
    { key: 'delta_activations',          header: 'Δ Activations' },
    { key: 'delta_commission_ngn',       header: 'Δ Commission (NGN)' },
    { key: 'delta_qualification_rate',   header: 'Δ Qual Rate %' },
  ],
  exceptions: [
    { key: 'dealer_id',                       header: 'Dealer ID' },
    { key: 'dealer_name',                     header: 'Dealer Name' },
    { key: 'account_profile_class',           header: 'Profile Class' },
    { key: 'exception_type',                  header: 'Exception' },
    { key: 'activation_count',                header: 'Total Activations' },
    { key: 'qualified_activation_count',      header: 'Qualified' },
    { key: 'qualification_rate_pct',          header: 'Qualification Rate %' },
    { key: 'activation_commission_amount',    header: 'Commission (NGN)' },
  ],
};

export default function ActivationIntelligencePanel() {
  const { periods, period, priorPeriod, setPriorPeriod } = usePeriod();
  const [activeTab, setActiveTab] = useState('summary');

  const [summary, setSummary] = useState([]);
  const [variance, setVariance] = useState([]);
  const [exceptions, setExceptions] = useState([]);

  const [loading, setLoading] = useState(false);
  const [error, setError] = useState(null);

  // Client-side dealer filter — applies across all three sub-tabs so the
  // search sticks when the user switches Summary ↔ Variance ↔ Exceptions
  // for the same dealer. Case-insensitive substring on dealer_id OR
  // dealer_name; rows are already loaded so this is a pure display filter.
  const [dealerQuery, setDealerQuery] = useState('');

  const matchesDealer = (row) => {
    const q = dealerQuery.trim().toLowerCase();
    if (!q) return true;
    return String(row.dealer_id || '').toLowerCase().includes(q)
      || String(row.dealer_name || '').toLowerCase().includes(q);
  };

  const filteredSummary    = useMemo(() => summary.filter(matchesDealer),    [summary, dealerQuery]);
  const filteredVariance   = useMemo(() => variance.filter(matchesDealer),   [variance, dealerQuery]);
  const filteredExceptions = useMemo(() => exceptions.filter(matchesDealer), [exceptions, dealerQuery]);

  // Prefetch all three datasets in parallel so tab switching is instant.
  // activeTab is intentionally NOT a dependency — it's a display toggle,
  // not a data trigger. Variance re-fetches when priorPeriod changes.
  useEffect(() => {
    if (!period) return;
    let cancelled = false;
    setLoading(true);
    setError(null);
    const prior = priorPeriod || period;
    Promise.all([
      getActivationSummary(period).catch(() => []),
      getActivationVariance(prior, period).catch(() => []),
      getActivationExceptions(period).catch(() => []),
    ])
      .then(([s, v, e]) => {
        if (cancelled) return;
        setSummary(Array.isArray(s) ? s : []);
        setVariance(Array.isArray(v) ? v : []);
        setExceptions(Array.isArray(e) ? e : []);
      })
      .catch((e) => {
        if (!cancelled) setError(e?.response?.data?.detail || e?.message || String(e));
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, [period, priorPeriod]);

  const exceptionCounts = useMemo(() => {
    const counts = { ALL_UNQUALIFIED: 0, HIGH_UNQUALIFIED_RATE: 0, UNUSUAL_VOLUME: 0 };
    for (const e of filteredExceptions) counts[e.exception_type] = (counts[e.exception_type] || 0) + 1;
    return counts;
  }, [filteredExceptions]);

  return (
    <div className="h-full flex flex-col bg-gray-50 text-gray-800">
      <div className="px-5 py-3 bg-white border-b border-gray-200 flex flex-wrap items-end gap-4">
        <div className="text-sm font-semibold text-gray-800">
          Activation Intelligence
          <span className="ml-2 text-xs font-normal text-gray-500">
            · {formatPeriod(period) || '—'}
          </span>
        </div>

        {activeTab === 'variance' && (
          <div>
            <label className="block text-[11px] uppercase tracking-wide text-gray-500 mb-1">
              Compare against
            </label>
            <select
              value={priorPeriod}
              onChange={(e) => setPriorPeriod(e.target.value)}
              className="text-sm border border-gray-300 rounded-md px-2 py-1.5 bg-white focus:outline-none focus:ring-2 focus:ring-mtn-yellow focus:border-mtn-yellow"
            >
              {periods.map((p) => (
                <option key={p} value={p}>
                  {formatPeriod(p)}
                </option>
              ))}
            </select>
          </div>
        )}

        <div>
          <label className="block text-[11px] uppercase tracking-wide text-gray-500 mb-1">
            Dealer search
          </label>
          <input
            type="search"
            value={dealerQuery}
            onChange={(e) => setDealerQuery(e.target.value)}
            placeholder="code or name…"
            className="text-sm border border-gray-300 rounded-md px-2 py-1.5 bg-white focus:outline-none focus:ring-2 focus:ring-mtn-yellow focus:border-mtn-yellow w-52"
          />
        </div>

        <div className="flex-1" />

        <button
          onClick={() => {
            // Export what the user actually sees — the filtered rows.
            const rows = activeTab === 'summary' ? filteredSummary
              : activeTab === 'variance' ? filteredVariance
              : filteredExceptions;
            if (!rows.length) return;
            const filename = `activation_${activeTab}_${period || 'all'}.csv`;
            exportCsv(CSV_COLUMNS[activeTab], rows, filename);
          }}
          disabled={
            (activeTab === 'summary' && !filteredSummary.length) ||
            (activeTab === 'variance' && !filteredVariance.length) ||
            (activeTab === 'exceptions' && !filteredExceptions.length)
          }
          className="text-xs text-gray-700 hover:text-gray-900 font-medium border border-gray-200 rounded-md px-2 py-1 hover:bg-yellow-50 hover:border-mtn-yellow transition disabled:opacity-40 disabled:hover:bg-white disabled:hover:border-gray-200"
          title="Download the current tab as CSV"
        >
          ⬇ Export CSV
        </button>

        <div className="flex items-center gap-1 bg-gray-100 rounded-lg p-1">
          {TABS.map((t) => (
            <button
              key={t.id}
              onClick={() => setActiveTab(t.id)}
              className={`px-3 py-1.5 text-sm rounded-md transition ${
                activeTab === t.id
                  ? 'bg-white text-gray-900 shadow-sm font-semibold'
                  : 'text-gray-600 hover:text-gray-900'
              }`}
            >
              {t.label}
            </button>
          ))}
        </div>
      </div>

      <div className="px-5 py-3 bg-white border-b border-gray-100 flex flex-wrap items-center gap-6 text-xs">
        {activeTab === 'summary' && filteredSummary.length > 0 && (
          <>
            <Stat label="Dealers" value={filteredSummary.length.toLocaleString()} />
            <Stat
              label="Total activations"
              value={filteredSummary
                .reduce((a, b) => a + (b.activation_count || 0), 0)
                .toLocaleString()}
            />
            <Stat
              label="Qualified"
              value={filteredSummary
                .reduce((a, b) => a + (b.qualified_activation_count || 0), 0)
                .toLocaleString()}
            />
            <Stat
              label="Non-qualified"
              value={filteredSummary
                .reduce((a, b) => a + (b.non_qualified_activation_count || 0), 0)
                .toLocaleString()}
              tone="text-amber-600"
            />
          </>
        )}
        {activeTab === 'variance' && filteredVariance.length > 0 && (
          <>
            <Stat label="Dealers in both" value={filteredVariance.length.toLocaleString()} />
            <Stat
              label="Growing"
              value={filteredVariance.filter((r) => r.delta_activations > 0).length}
              tone="text-emerald-600"
            />
            <Stat
              label="Declining"
              value={filteredVariance.filter((r) => r.delta_activations < 0).length}
              tone="text-red-600"
            />
          </>
        )}
        {activeTab === 'exceptions' && filteredExceptions.length > 0 && (
          <>
            <Stat label="ALL_UNQUALIFIED" value={exceptionCounts.ALL_UNQUALIFIED} tone="text-red-600" />
            <Stat label="HIGH_UNQUALIFIED_RATE" value={exceptionCounts.HIGH_UNQUALIFIED_RATE} tone="text-amber-600" />
            <Stat label="UNUSUAL_VOLUME" value={exceptionCounts.UNUSUAL_VOLUME} tone="text-blue-600" />
          </>
        )}
      </div>

      {error && (
        <div className="mx-5 mt-3 text-xs text-red-600 bg-red-50 border border-red-200 rounded-md px-3 py-2">
          {error}
        </div>
      )}

      <div className="flex-1 min-h-0 p-5 flex flex-col overflow-hidden">
        <div className="flex-1 min-h-0 bg-white border border-gray-200 rounded-lg shadow-sm overflow-hidden flex flex-col">
          <div className="px-3 py-2 border-b border-gray-100 text-[11px] text-gray-500 shrink-0">
            {activeTab === 'summary' && (
              <>
                {filteredSummary.length.toLocaleString()} dealer{filteredSummary.length === 1 ? '' : 's'}
                {dealerQuery && filteredSummary.length !== summary.length && ` (of ${summary.length.toLocaleString()})`}
              </>
            )}
            {activeTab === 'variance' && (
              <>
                {filteredVariance.length.toLocaleString()} dealer{filteredVariance.length === 1 ? '' : 's'} present in both periods
                {dealerQuery && filteredVariance.length !== variance.length && ` (of ${variance.length.toLocaleString()})`}
              </>
            )}
            {activeTab === 'exceptions' && (
              <>
                {filteredExceptions.length.toLocaleString()} exception{filteredExceptions.length === 1 ? '' : 's'}
                {dealerQuery && filteredExceptions.length !== exceptions.length && ` (of ${exceptions.length.toLocaleString()})`}
              </>
            )}
          </div>
          <div className="flex-1 min-h-0 relative">
            <div className={activeTab === 'summary' ? 'h-full' : 'hidden'}>
              <ActivationSummaryTable rows={filteredSummary} loading={loading} />
            </div>
            <div className={activeTab === 'variance' ? 'h-full' : 'hidden'}>
              <ActivationVarianceTable rows={filteredVariance} loading={loading} />
            </div>
            <div className={activeTab === 'exceptions' ? 'h-full' : 'hidden'}>
              <ActivationExceptionsTable rows={filteredExceptions} loading={loading} />
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}

function Stat({ label, value, tone = 'text-gray-900' }) {
  return (
    <div className="flex flex-col">
      <span className="text-[10px] uppercase tracking-wide text-gray-500">{label}</span>
      <span className={`text-sm font-semibold tabular-nums ${tone}`}>{value}</span>
    </div>
  );
}
