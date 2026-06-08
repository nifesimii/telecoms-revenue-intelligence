// Phase 4 panel — Payment Intelligence.
// PaymentCoverageCard at top + tabbed table (Exceptions | All | Variance).

import { useEffect, useState } from 'react';
import {
  getPeriods,
  getPaymentSummary,
  getPaymentExceptions,
  getPaymentVariance,
} from '../../api/client.js';
import PaymentCoverageCard from './PaymentCoverageCard.jsx';
import PaymentSummaryTable from './PaymentSummaryTable.jsx';
import PaymentExceptionsTable from './PaymentExceptionsTable.jsx';

const TABS = [
  { id: 'exceptions', label: 'Exceptions' },
  { id: 'all', label: 'All Payments' },
  { id: 'variance', label: 'Variance' },
];

function fmtNaira(n) {
  const v = Number(n) || 0;
  return (
    '₦' +
    v.toLocaleString('en-NG', {
      minimumFractionDigits: 2,
      maximumFractionDigits: 2,
    })
  );
}

function VarianceTable({ rows = [], loading }) {
  if (loading) {
    return (
      <div className="p-4 text-sm text-gray-500 italic">Loading variance…</div>
    );
  }
  if (!rows.length) {
    return <div className="p-4 text-sm text-gray-500 italic">No data.</div>;
  }
  return (
    <div className="overflow-auto h-full">
      <table className="w-full text-xs border-collapse">
        <thead className="sticky top-0 bg-gray-50 z-10">
          <tr className="text-gray-600">
            <th className="border-b border-gray-200 px-2 py-1.5 text-left font-semibold">
              Dealer
            </th>
            <th className="border-b border-gray-200 px-2 py-1.5 text-right font-semibold">
              Paid {rows[0]?.period_a}
            </th>
            <th className="border-b border-gray-200 px-2 py-1.5 text-right font-semibold">
              Paid {rows[0]?.period_b}
            </th>
            <th className="border-b border-gray-200 px-2 py-1.5 text-right font-semibold">
              Δ Paid
            </th>
            <th className="border-b border-gray-200 px-2 py-1.5 text-left font-semibold">
              Status A → B
            </th>
            <th className="border-b border-gray-200 px-2 py-1.5 text-center font-semibold">
              Changed
            </th>
          </tr>
        </thead>
        <tbody>
          {rows.map((r, i) => {
            const delta = Number(r.delta_paid) || 0;
            const tone = delta > 0 ? 'text-emerald-700' : delta < 0 ? 'text-red-700' : 'text-gray-500';
            return (
              <tr
                key={`${r.dealer_id}-${i}`}
                className="hover:bg-gray-50 border-b border-gray-100 last:border-b-0"
              >
                <td
                  className="px-2 py-1.5 text-gray-800 truncate max-w-[220px]"
                  title={r.dealer_name}
                >
                  {r.dealer_name}
                </td>
                <td className="px-2 py-1.5 text-right tabular-nums text-gray-700">
                  {fmtNaira(r.amount_paid_a)}
                </td>
                <td className="px-2 py-1.5 text-right tabular-nums text-gray-800">
                  {fmtNaira(r.amount_paid_b)}
                </td>
                <td className={`px-2 py-1.5 text-right tabular-nums font-semibold ${tone}`}>
                  {delta > 0 ? '+' : delta < 0 ? '−' : ''}
                  {fmtNaira(Math.abs(delta))}
                </td>
                <td className="px-2 py-1.5 text-[11px] text-gray-600">
                  {r.payment_status_a} → {r.payment_status_b}
                </td>
                <td className="px-2 py-1.5 text-center text-[10px]">
                  {r.status_changed ? (
                    <span className="text-amber-700 font-semibold">YES</span>
                  ) : (
                    <span className="text-gray-400">—</span>
                  )}
                </td>
              </tr>
            );
          })}
        </tbody>
      </table>
    </div>
  );
}

export default function PaymentIntelligencePanel() {
  const [periods, setPeriods] = useState([]);
  const [period, setPeriod] = useState('');
  const [activeTab, setActiveTab] = useState('exceptions');

  const [coverage, setCoverage] = useState(null);
  const [allRows, setAllRows] = useState([]);
  const [exceptions, setExceptions] = useState([]);
  const [variance, setVariance] = useState([]);

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

  // Fetch coverage card + records for the period.
  useEffect(() => {
    if (!period) return;
    let cancelled = false;
    setLoading(true);
    setError(null);
    Promise.all([
      getPaymentSummary(period),
      getPaymentExceptions(period),
    ])
      .then(([summary, exc]) => {
        if (cancelled) return;
        setCoverage(summary);
        setAllRows(summary?.records || []);
        setExceptions(Array.isArray(exc) ? exc : []);
      })
      .catch((e) => {
        if (!cancelled)
          setError(e?.response?.data?.detail || e?.message || String(e));
      })
      .finally(() => !cancelled && setLoading(false));
    return () => {
      cancelled = true;
    };
  }, [period]);

  // Variance is loaded lazily when its tab is opened.
  useEffect(() => {
    if (activeTab !== 'variance') return;
    if (periods.length < 2) return;
    const prior = periods[1] || periods[0];
    const current = periods[0];
    if (!current || !prior) return;
    let cancelled = false;
    getPaymentVariance(prior, current)
      .then((rows) => !cancelled && setVariance(Array.isArray(rows) ? rows : []))
      .catch(() => !cancelled && setVariance([]));
    return () => {
      cancelled = true;
    };
  }, [activeTab, periods]);

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

      {/* Simulated-data banner — always visible */}
      <div className="mx-5 mt-4 bg-amber-50 border border-amber-200 rounded-lg px-4 py-2 text-xs text-amber-800 flex items-start gap-2">
        <span className="font-semibold uppercase tracking-wide bg-amber-200 text-amber-900 rounded px-1.5 py-0.5">
          Simulated
        </span>
        <span>
          Payment data is simulated from real commission and exception
          records. Live Oracle AP integration pending.
        </span>
      </div>

      {error && (
        <div className="mx-5 mt-3 text-xs text-red-600 bg-red-50 border border-red-200 rounded-md px-3 py-2">
          {error}
        </div>
      )}

      {/* Body: coverage card at natural height + tabbed table card that
          fills remaining space and scrolls internally. ``min-h-0`` is
          essential here — flex children default to ``min-height: auto``. */}
      <div className="flex-1 min-h-0 p-5 flex flex-col gap-4 overflow-hidden">
        <div className="shrink-0">
          <PaymentCoverageCard data={coverage} loading={loading} />
        </div>

        <div className="flex-1 min-h-0 bg-white border border-gray-200 rounded-lg shadow-sm overflow-hidden flex flex-col">
          <div className="px-3 py-2 border-b border-gray-100 text-[11px] text-gray-500 shrink-0 flex items-center justify-between">
            <span>
              {activeTab === 'exceptions' &&
                `${exceptions.length.toLocaleString()} exception${exceptions.length === 1 ? '' : 's'}`}
              {activeTab === 'all' &&
                `${allRows.length.toLocaleString()} dealer${allRows.length === 1 ? '' : 's'}`}
              {activeTab === 'variance' &&
                `${variance.length.toLocaleString()} dealer${variance.length === 1 ? '' : 's'} present in both periods`}
            </span>
            <span className="text-amber-700 font-semibold">[SIMULATED]</span>
          </div>
          <div className="flex-1 min-h-0">
            {activeTab === 'exceptions' && (
              <PaymentExceptionsTable rows={exceptions} loading={loading} />
            )}
            {activeTab === 'all' && (
              <PaymentSummaryTable rows={allRows} loading={loading} />
            )}
            {activeTab === 'variance' && (
              <VarianceTable rows={variance} loading={false} />
            )}
          </div>
        </div>
      </div>
    </div>
  );
}
