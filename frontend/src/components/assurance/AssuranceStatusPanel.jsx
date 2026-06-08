// Read-only assurance dashboard.
//
// 2x2 grid of module cards. Each implemented module shows:
//   * module name
//   * status badge (PASS / FLAG)
//   * one-line summary
//   * counts by severity (HIGH / MEDIUM / LOW)
// Each stub module is greyed out with a "Phase X — Coming Soon" label.

import { useEffect, useMemo, useState } from 'react';
import { getPeriods, getAssuranceStatus } from '../../api/client.js';

const STATUS_TONE = {
  PASS: 'bg-emerald-100 text-emerald-800 border-emerald-200',
  FLAG: 'bg-amber-100 text-amber-800 border-amber-200',
  FAIL: 'bg-red-100 text-red-800 border-red-200',
  NOT_IMPLEMENTED: 'bg-gray-100 text-gray-500 border-gray-200',
};

function StatusBadge({ status }) {
  const tone = STATUS_TONE[status] || STATUS_TONE.NOT_IMPLEMENTED;
  return (
    <span
      className={`inline-block px-2 py-0.5 text-[10px] font-semibold uppercase tracking-wide border rounded-full ${tone}`}
    >
      {status}
    </span>
  );
}

function SeverityChip({ label, value, tone }) {
  return (
    <div className="flex flex-col items-center">
      <span className={`text-base font-bold tabular-nums ${tone}`}>
        {value ?? 0}
      </span>
      <span className="text-[10px] uppercase tracking-wide text-gray-500">
        {label}
      </span>
    </div>
  );
}

function ImplementedCard({ module }) {
  return (
    <div className="bg-white border border-gray-200 rounded-lg shadow-sm p-5 relative overflow-hidden">
      <div className="absolute top-0 left-0 h-full w-1 bg-mtn-yellow" />
      <div className="flex items-start justify-between gap-3">
        <div>
          <div className="text-[11px] uppercase tracking-wide text-gray-500">
            Phase {module.phase}
          </div>
          <h3 className="text-base font-semibold capitalize text-gray-900 mt-0.5">
            {module.module} assurance
          </h3>
        </div>
        <StatusBadge status={module.status} />
      </div>
      <p className="mt-3 text-sm text-gray-700 leading-snug">
        {module.summary}
      </p>
      <div className="mt-4 grid grid-cols-3 gap-3 pt-3 border-t border-gray-100">
        <SeverityChip label="High" value={module.high_count} tone="text-red-600" />
        <SeverityChip
          label="Medium"
          value={module.medium_count}
          tone="text-amber-600"
        />
        <SeverityChip label="Low" value={module.low_count} tone="text-blue-600" />
      </div>
    </div>
  );
}

function StubCard({ module }) {
  return (
    <div className="bg-gray-50 border border-dashed border-gray-300 rounded-lg p-5 relative">
      <div className="flex items-start justify-between gap-3">
        <div>
          <div className="text-[11px] uppercase tracking-wide text-gray-400">
            Phase {module.phase}
          </div>
          <h3 className="text-base font-semibold capitalize text-gray-400 mt-0.5">
            {module.module} assurance
          </h3>
        </div>
        <span className="text-[10px] uppercase tracking-wide text-gray-400 border border-gray-300 rounded-full px-2 py-0.5">
          Coming soon
        </span>
      </div>
      <p className="mt-3 text-sm text-gray-500 leading-snug italic">
        {module.summary}
      </p>
      <div className="mt-4 pt-3 border-t border-gray-200 text-[11px] text-gray-400">
        Phase {module.phase} — implementation pending
      </div>
    </div>
  );
}

export default function AssuranceStatusPanel() {
  const [periods, setPeriods] = useState([]);
  const [period, setPeriod] = useState('');
  const [payload, setPayload] = useState(null);
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
        if (ps.length) setPeriod(ps[0]);
      })
      .catch((e) => !cancelled && setError(String(e?.message || e)));
    return () => {
      cancelled = true;
    };
  }, []);

  // Refetch assurance status whenever the period changes.
  useEffect(() => {
    if (!period) return;
    let cancelled = false;
    setLoading(true);
    setError(null);
    getAssuranceStatus(period)
      .then((data) => !cancelled && setPayload(data))
      .catch((e) => {
        if (!cancelled)
          setError(e?.response?.data?.detail || e?.message || String(e));
      })
      .finally(() => !cancelled && setLoading(false));
    return () => {
      cancelled = true;
    };
  }, [period]);

  const modules = useMemo(() => payload?.modules || [], [payload]);

  return (
    <div className="h-full flex flex-col bg-gray-50 text-gray-800">
      {/* Sub-header */}
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
        <div className="flex-1" />
        <div className="text-[11px] text-gray-500">
          Assurance Layer (Phase 2 scaffolding) ·{' '}
          {modules.length} modules registered
        </div>
      </div>

      {error && (
        <div className="mx-5 mt-3 text-xs text-red-600 bg-red-50 border border-red-200 rounded-md px-3 py-2">
          {error}
        </div>
      )}

      <div className="flex-1 overflow-auto p-5">
        {loading && !modules.length ? (
          <div className="text-sm text-gray-500 italic">
            Loading assurance status…
          </div>
        ) : (
          <div className="grid grid-cols-1 md:grid-cols-2 gap-4 max-w-5xl">
            {modules.map((m) =>
              m.implemented ? (
                <ImplementedCard key={m.module} module={m} />
              ) : (
                <StubCard key={m.module} module={m} />
              ),
            )}
          </div>
        )}
      </div>
    </div>
  );
}
