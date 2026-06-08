// Phase 2 panel — Activation Intelligence.
// Period selector + 3 tabs (Summary | Variance | Exceptions) backed by the
// three Phase 2 endpoints. Standalone — no agent loop, no chat.

import { useEffect, useMemo, useState } from 'react';
import {
  getPeriods,
  getActivationSummary,
  getActivationVariance,
  getActivationExceptions,
} from '../../api/client.js';
import ActivationSummaryTable from './ActivationSummaryTable.jsx';
import ActivationVarianceTable from './ActivationVarianceTable.jsx';
import ActivationExceptionsTable from './ActivationExceptionsTable.jsx';

const TABS = [
  { id: 'summary', label: 'Summary' },
  { id: 'variance', label: 'Variance' },
  { id: 'exceptions', label: 'Exceptions' },
];

export default function ActivationIntelligencePanel() {
  const [periods, setPeriods] = useState([]);
  const [period, setPeriod] = useState('');
  const [priorPeriod, setPriorPeriod] = useState('');
  const [activeTab, setActiveTab] = useState('summary');

  const [summary, setSummary] = useState([]);
  const [variance, setVariance] = useState([]);
  const [exceptions, setExceptions] = useState([]);

  const [loading, setLoading] = useState(false);
  const [error, setError] = useState(null);

  // Load periods once on mount.
  useEffect(() => {
    let cancelled = false;
    getPeriods()
      .then((data) => {
        if (cancelled) return;
        const ps = data.periods || [];
        setPeriods(ps);
        if (ps.length) {
          setPeriod(ps[0]);
          setPriorPeriod(ps[1] || ps[0]);
        }
      })
      .catch((e) => !cancelled && setError(String(e?.message || e)));
    return () => {
      cancelled = true;
    };
  }, []);

  // Refetch the active tab's data whenever the period(s) change.
  useEffect(() => {
    if (!period) return;
    let cancelled = false;
    setLoading(true);
    setError(null);

    const work = async () => {
      try {
        if (activeTab === 'summary') {
          const data = await getActivationSummary(period);
          if (!cancelled) setSummary(Array.isArray(data) ? data : []);
        } else if (activeTab === 'variance') {
          const a = priorPeriod || period;
          const data = await getActivationVariance(a, period);
          if (!cancelled) setVariance(Array.isArray(data) ? data : []);
        } else if (activeTab === 'exceptions') {
          const data = await getActivationExceptions(period);
          if (!cancelled) setExceptions(Array.isArray(data) ? data : []);
        }
      } catch (e) {
        if (!cancelled) setError(e?.response?.data?.detail || e?.message || String(e));
      } finally {
        if (!cancelled) setLoading(false);
      }
    };
    work();
    return () => {
      cancelled = true;
    };
  }, [period, priorPeriod, activeTab]);

  const exceptionCounts = useMemo(() => {
    const counts = { ALL_UNQUALIFIED: 0, HIGH_UNQUALIFIED_RATE: 0, UNUSUAL_VOLUME: 0 };
    for (const e of exceptions) counts[e.exception_type] = (counts[e.exception_type] || 0) + 1;
    return counts;
  }, [exceptions]);

  return (
    <div className="h-full flex flex-col bg-gray-50 text-gray-800">
      {/* Sub-header: period selectors + tab strip */}
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
                  {p}
                </option>
              ))}
            </select>
          </div>
        )}

        <div className="flex-1" />

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

      {/* Stats strip — gives a one-glance summary of the current period */}
      <div className="px-5 py-3 bg-white border-b border-gray-100 flex flex-wrap items-center gap-6 text-xs">
        {activeTab === 'summary' && summary.length > 0 && (
          <>
            <Stat label="Dealers" value={summary.length.toLocaleString()} />
            <Stat
              label="Total activations"
              value={summary
                .reduce((a, b) => a + (b.activation_count || 0), 0)
                .toLocaleString()}
            />
            <Stat
              label="Qualified"
              value={summary
                .reduce((a, b) => a + (b.qualified_activation_count || 0), 0)
                .toLocaleString()}
            />
            <Stat
              label="Non-qualified"
              value={summary
                .reduce((a, b) => a + (b.non_qualified_activation_count || 0), 0)
                .toLocaleString()}
              tone="text-amber-600"
            />
          </>
        )}
        {activeTab === 'variance' && variance.length > 0 && (
          <>
            <Stat
              label="Dealers in both"
              value={variance.length.toLocaleString()}
            />
            <Stat
              label="Growing"
              value={variance.filter((r) => r.delta_activations > 0).length}
              tone="text-emerald-600"
            />
            <Stat
              label="Declining"
              value={variance.filter((r) => r.delta_activations < 0).length}
              tone="text-red-600"
            />
          </>
        )}
        {activeTab === 'exceptions' && exceptions.length > 0 && (
          <>
            <Stat
              label="ALL_UNQUALIFIED"
              value={exceptionCounts.ALL_UNQUALIFIED}
              tone="text-red-600"
            />
            <Stat
              label="HIGH_UNQUALIFIED_RATE"
              value={exceptionCounts.HIGH_UNQUALIFIED_RATE}
              tone="text-amber-600"
            />
            <Stat
              label="UNUSUAL_VOLUME"
              value={exceptionCounts.UNUSUAL_VOLUME}
              tone="text-blue-600"
            />
          </>
        )}
      </div>

      {error && (
        <div className="mx-5 mt-3 text-xs text-red-600 bg-red-50 border border-red-200 rounded-md px-3 py-2">
          {error}
        </div>
      )}

      <div className="flex-1 overflow-auto p-5">
        <div className="bg-white border border-gray-200 rounded-lg shadow-sm overflow-hidden">
          {activeTab === 'summary' && (
            <ActivationSummaryTable rows={summary} loading={loading} />
          )}
          {activeTab === 'variance' && (
            <ActivationVarianceTable rows={variance} loading={loading} />
          )}
          {activeTab === 'exceptions' && (
            <ActivationExceptionsTable rows={exceptions} loading={loading} />
          )}
        </div>
      </div>
    </div>
  );
}

function Stat({ label, value, tone = 'text-gray-900' }) {
  return (
    <div className="flex flex-col">
      <span className="text-[10px] uppercase tracking-wide text-gray-500">
        {label}
      </span>
      <span className={`text-sm font-semibold tabular-nums ${tone}`}>
        {value}
      </span>
    </div>
  );
}
