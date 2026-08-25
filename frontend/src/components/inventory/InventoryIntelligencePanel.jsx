// Phase 3 panel — Inventory Intelligence.
//
// Summary cards on top (CONFIRMED_MISMATCH / NO_INVOICE_RECORD / WITHIN_ALLOCATION)
// + a single table below. Toggle to include WITHIN_ALLOCATION rows.
// Period comes from the global PeriodProvider.

import { useEffect, useMemo, useState } from 'react';
import { getInventoryComparisonPage } from '../../api/client.js';
import { usePeriod } from '../../context/PeriodContext.jsx';
import { formatPeriod } from '../../lib/format.js';
import InventoryComparisonTable from './InventoryComparisonTable.jsx';
import DataCoverageTicketModal from './DataCoverageTicketModal.jsx';
import PaginationControls from '../shared/PaginationControls.jsx';
import useDebouncedValue from '../../hooks/useDebouncedValue.js';
import { useQueryClient } from '@tanstack/react-query';

function SummaryCard({ label, count, sub, tone, accent }) {
  return (
    <div className="bg-white border border-gray-200 rounded-lg shadow-sm p-4 relative overflow-hidden">
      <div className={`absolute top-0 left-0 h-full w-1 ${accent}`} />
      <div className="text-[11px] uppercase tracking-wide text-gray-500">{label}</div>
      <div className={`mt-1 text-2xl font-bold tabular-nums ${tone}`}>{count}</div>
      {sub && <div className="mt-1 text-[11px] text-gray-500 leading-snug">{sub}</div>}
    </div>
  );
}

export default function InventoryIntelligencePanel({ onAsk } = {}) {
  const queryClient = useQueryClient();
  const { period } = usePeriod();
  const [includeWithin, setIncludeWithin] = useState(false);
  const [rows, setRows] = useState([]);
  const [pagination, setPagination] = useState(null);
  const [summary, setSummary] = useState(null);
  const [offset, setOffset] = useState(0);
  const [pageSize, setPageSize] = useState(50);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState(null);
  const [ticketOpen, setTicketOpen] = useState(false);

  // Client-side substring filter — searches dealer AND product fields
  // (both are meaningful here; e.g. "hynex" to isolate the alias split).
  const [query, setQuery] = useState('');
  const debouncedQuery = useDebouncedValue(query);

  useEffect(() => {
    if (!period) return;
    setLoading(true);
    setError(null);
    const params = {
      mon_period: period,
      include_within_allocation: includeWithin,
      search: debouncedQuery || undefined,
      limit: pageSize,
      offset,
      sort_by: 'activation_count',
      sort_direction: 'desc',
    };
    let active = true;
    queryClient.fetchQuery({
      queryKey: ['inventory-page', params],
      queryFn: ({ signal }) => getInventoryComparisonPage(params, signal),
    })
      .then((data) => {
        if (!active) return;
        setRows(Array.isArray(data?.items) ? data.items : []);
        setPagination(data?.pagination || null);
        setSummary(data?.summary || null);
      })
      .catch((e) => {
        if (active && e?.code !== 'ERR_CANCELED') setError(e?.response?.data?.detail || e?.message || String(e));
      })
      .finally(() => { if (active) setLoading(false); });
    return () => { active = false; };
  }, [period, includeWithin, debouncedQuery, pageSize, offset, queryClient]);

  useEffect(() => { setOffset(0); }, [period, includeWithin, debouncedQuery, pageSize]);

  // Summary cards reflect the filtered view — "confirmed mismatches on
  // Hynex products" is a natural drill-down to want cards for.
  const counts = useMemo(() => {
    if (summary) return {
      CONFIRMED_MISMATCH: summary.confirmed_mismatch_count,
      NO_INVOICE_RECORD: summary.no_invoice_record_count,
      WITHIN_ALLOCATION: summary.within_allocation_count,
      total_gap_units: summary.total_gap_units,
    };
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
  }, [rows, summary]);

  return (
    <div className="h-full flex flex-col bg-gray-50 text-gray-800">
      <div className="px-5 py-3 bg-white border-b border-gray-200 flex flex-wrap items-end gap-4">
        <div className="text-sm font-semibold text-gray-800">
          Inventory Intelligence
          <span className="ml-2 text-xs font-normal text-gray-500">
            · {formatPeriod(period) || '—'}
          </span>
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
        <div>
          <label className="block text-[11px] uppercase tracking-wide text-gray-500 mb-1">
            Search
          </label>
          <input
            type="search"
            value={query}
            onChange={(e) => setQuery(e.target.value)}
            placeholder="dealer or product…"
            className="text-sm border border-gray-300 rounded-md px-2 py-1.5 bg-white focus:outline-none focus:ring-2 focus:ring-mtn-yellow focus:border-mtn-yellow w-52"
          />
        </div>
        <div className="flex-1" />
        <button
          onClick={() => setTicketOpen(true)}
          disabled={!period}
          className="text-xs text-gray-700 hover:text-gray-900 font-medium border border-gray-200 rounded-md px-2 py-1 hover:bg-yellow-50 hover:border-mtn-yellow transition disabled:opacity-40"
          title="Compile a ServiceNow ticket draft for dealers with IFS / USP data coverage gaps"
        >
          ⚠ Raise data coverage ticket
        </button>
        <div className="text-[11px] text-gray-500">Activations vs IFS purchases</div>
      </div>

      <DataCoverageTicketModal
        period={period}
        open={ticketOpen}
        onClose={() => setTicketOpen(false)}
      />

      {error && (
        <div className="mx-5 mt-3 text-xs text-red-600 bg-red-50 border border-red-200 rounded-md px-3 py-2">
          {error}
        </div>
      )}

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
            count={includeWithin ? counts.WITHIN_ALLOCATION : '—'}
            sub={
              includeWithin
                ? 'Activations covered by purchased units'
                : 'Enable the toggle above to load these rows'
            }
            tone="text-emerald-700"
            accent="bg-emerald-400"
          />
        </div>

        <div className="flex-1 min-h-[360px] bg-white border border-gray-200 rounded-lg shadow-sm overflow-hidden flex flex-col">
          <div className="px-3 py-2 border-b border-gray-100 text-[11px] text-gray-500 shrink-0">
            <div className="flex items-center justify-between gap-3">
              <span>{pagination?.total?.toLocaleString() || 0} matching records</span>
              <PaginationControls
                pagination={pagination}
                pageSize={pageSize}
                onOffsetChange={setOffset}
                onPageSizeChange={setPageSize}
              />
            </div>
          </div>
          <div className="flex-1 min-h-0">
            <InventoryComparisonTable
              rows={rows}
              loading={loading}
              period={period}
              onAsk={onAsk}
            />
          </div>
        </div>
      </div>
    </div>
  );
}
