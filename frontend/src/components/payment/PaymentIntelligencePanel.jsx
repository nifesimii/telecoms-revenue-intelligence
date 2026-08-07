// Phase 4 panel — Payment Intelligence.
// PaymentCoverageCard at top + tabbed table (Exceptions | All | Variance).
// Period comes from the global PeriodProvider.

import { useEffect, useMemo, useState } from 'react';
import {
  getPaymentSummary,
  getPaymentExceptions,
  getPaymentVariance,
} from '../../api/client.js';
import { usePeriod } from '../../context/PeriodContext.jsx';
import { formatNGN, formatPeriod } from '../../lib/format.js';
import PaymentCoverageCard from './PaymentCoverageCard.jsx';
import PaymentSummaryTable from './PaymentSummaryTable.jsx';
import PaymentExceptionsTable from './PaymentExceptionsTable.jsx';

const TABS = [
  { id: 'exceptions', label: 'Exceptions' },
  { id: 'all', label: 'All Payments' },
  { id: 'variance', label: 'Variance' },
];

function VarianceTable({ rows = [], loading }) {
  if (loading) {
    return <div className="p-4 text-sm text-gray-500 italic">Loading variance…</div>;
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
              Paid {formatPeriod(rows[0]?.period_a)}
            </th>
            <th className="border-b border-gray-200 px-2 py-1.5 text-right font-semibold">
              Paid {formatPeriod(rows[0]?.period_b)}
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
                  {formatNGN(r.amount_paid_a)}
                </td>
                <td className="px-2 py-1.5 text-right tabular-nums text-gray-800">
                  {formatNGN(r.amount_paid_b)}
                </td>
                <td className={`px-2 py-1.5 text-right tabular-nums font-semibold ${tone}`}>
                  {delta > 0 ? '+' : delta < 0 ? '−' : ''}
                  {formatNGN(Math.abs(delta))}
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

export default function PaymentIntelligencePanel({ onAsk } = {}) {
  const { periods, period, priorPeriod } = usePeriod();
  const [activeTab, setActiveTab] = useState('exceptions');

  const [coverage, setCoverage] = useState(null);
  const [allRows, setAllRows] = useState([]);
  const [exceptions, setExceptions] = useState([]);
  const [variance, setVariance] = useState([]);

  const [loading, setLoading] = useState(false);
  const [error, setError] = useState(null);

  // Client-side dealer filter — persists across all three sub-tabs so
  // tracking one dealer's payment story (exception → summary row →
  // MoM change) doesn't need re-typing the query.
  const [dealerQuery, setDealerQuery] = useState('');
  const matchesDealer = (row) => {
    const q = dealerQuery.trim().toLowerCase();
    if (!q) return true;
    return String(row.dealer_id || '').toLowerCase().includes(q)
      || String(row.dealer_name || '').toLowerCase().includes(q);
  };
  const filteredAll        = useMemo(() => allRows.filter(matchesDealer),    [allRows, dealerQuery]);
  const filteredExceptions = useMemo(() => exceptions.filter(matchesDealer), [exceptions, dealerQuery]);
  const filteredVariance   = useMemo(() => variance.filter(matchesDealer),   [variance, dealerQuery]);

  useEffect(() => {
    if (!period) return;
    let cancelled = false;
    setLoading(true);
    setError(null);
    Promise.all([getPaymentSummary(period), getPaymentExceptions(period)])
      .then(([summary, exc]) => {
        if (cancelled) return;
        setCoverage(summary);
        setAllRows(summary?.records || []);
        setExceptions(Array.isArray(exc) ? exc : []);
      })
      .catch((e) => {
        if (!cancelled) setError(e?.response?.data?.detail || e?.message || String(e));
      })
      .finally(() => !cancelled && setLoading(false));
    return () => {
      cancelled = true;
    };
  }, [period]);

  useEffect(() => {
    if (activeTab !== 'variance') return;
    if (!period || !priorPeriod) return;
    let cancelled = false;
    getPaymentVariance(priorPeriod, period)
      .then((rows) => !cancelled && setVariance(Array.isArray(rows) ? rows : []))
      .catch(() => !cancelled && setVariance([]));
    return () => {
      cancelled = true;
    };
  }, [activeTab, period, priorPeriod, periods]);

  return (
    <div className="h-full flex flex-col bg-gray-50 text-gray-800">
      <div className="px-5 py-3 bg-white border-b border-gray-200 flex flex-wrap items-end gap-4">
        <div className="text-sm font-semibold text-gray-800">
          Payment Intelligence
          <span className="ml-2 text-xs font-normal text-gray-500">
            · {formatPeriod(period) || '—'}
          </span>
        </div>
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

      {coverage?.data_source === 'APDP' ? (
        <div className="mx-5 mt-4 bg-emerald-50 border border-emerald-200 rounded-lg px-4 py-2 text-xs text-emerald-800 flex items-start gap-2">
          <span className="font-semibold uppercase tracking-wide bg-emerald-200 text-emerald-900 rounded px-1.5 py-0.5">
            Live · APDP
          </span>
          <span>
            Reconciliation sourced from APDP's <code>normalized.partner_settlements</code> view.
            Sales captured, expected commission, settled amount, and variance are derived from
            real dealer / commission / settlement events.
          </span>
        </div>
      ) : (
        <div className="mx-5 mt-4 bg-amber-50 border border-amber-200 rounded-lg px-4 py-2 text-xs text-amber-800 flex items-start gap-2">
          <span className="font-semibold uppercase tracking-wide bg-amber-200 text-amber-900 rounded px-1.5 py-0.5">
            Simulated
          </span>
          <span>
            Payment data is simulated from real commission and exception records.
            Live Oracle AP / APDP integration pending — set{' '}
            <code>PAYMENT_SOURCE=apdp</code> when ready.
          </span>
        </div>
      )}

      {error && (
        <div className="mx-5 mt-3 text-xs text-red-600 bg-red-50 border border-red-200 rounded-md px-3 py-2">
          {error}
        </div>
      )}

      <div className="flex-1 min-h-0 p-5 flex flex-col gap-4 overflow-hidden">
        <div className="shrink-0">
          <PaymentCoverageCard data={coverage} loading={loading} />
        </div>

        <div className="flex-1 min-h-[360px] bg-white border border-gray-200 rounded-lg shadow-sm overflow-hidden flex flex-col">
          <div className="px-3 py-2 border-b border-gray-100 text-[11px] text-gray-500 shrink-0 flex items-center justify-between">
            <span>
              {activeTab === 'exceptions' && (
                <>
                  {filteredExceptions.length.toLocaleString()} exception{filteredExceptions.length === 1 ? '' : 's'}
                  {dealerQuery && filteredExceptions.length !== exceptions.length && ` (of ${exceptions.length.toLocaleString()})`}
                </>
              )}
              {activeTab === 'all' && (
                <>
                  {filteredAll.length.toLocaleString()} dealer{filteredAll.length === 1 ? '' : 's'}
                  {dealerQuery && filteredAll.length !== allRows.length && ` (of ${allRows.length.toLocaleString()})`}
                </>
              )}
              {activeTab === 'variance' && (
                <>
                  {filteredVariance.length.toLocaleString()} dealer{filteredVariance.length === 1 ? '' : 's'} present in both periods
                  {dealerQuery && filteredVariance.length !== variance.length && ` (of ${variance.length.toLocaleString()})`}
                </>
              )}
            </span>
            {coverage?.data_source === 'APDP' ? (
              <span className="text-emerald-700 font-semibold">[APDP]</span>
            ) : (
              <span className="text-amber-700 font-semibold">[SIMULATED]</span>
            )}
          </div>
          <div className="flex-1 min-h-0">
            {activeTab === 'exceptions' && (
              <PaymentExceptionsTable
                rows={filteredExceptions}
                loading={loading}
                period={period}
                onAsk={onAsk}
              />
            )}
            {activeTab === 'all' && (
              <PaymentSummaryTable rows={filteredAll} loading={loading} />
            )}
            {activeTab === 'variance' && (
              <VarianceTable rows={filteredVariance} loading={false} />
            )}
          </div>
        </div>
      </div>
    </div>
  );
}
