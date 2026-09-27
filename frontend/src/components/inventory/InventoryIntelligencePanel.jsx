import { useEffect, useRef, useState } from 'react';
import { useQuery } from '@tanstack/react-query';
import { getInventoryComparisonPage } from '../../api/client.js';
import { usePeriod } from '../../context/PeriodContext.jsx';
import { formatPeriod } from '../../lib/format.js';
import useDebouncedValue from '../../hooks/useDebouncedValue.js';
import InventoryComparisonTable from './InventoryComparisonTable.jsx';
import InventorySummary from './InventorySummary.jsx';
import InventoryFilters from './InventoryFilters.jsx';
import InventoryDetail from './InventoryDetail.jsx';
import DataCoverageTicketModal from './DataCoverageTicketModal.jsx';
import { subjectFor } from './inventoryPresentation.js';

const DEFAULT_FILTERS = { view: 'exceptions', search: '', finding: '', sort_by: 'inventory_gap', sort_direction: 'desc', limit: 25, offset: 0 };

export default function InventoryIntelligencePanel(props) {
  const { period, loading, error } = usePeriod();
  if (!period) return <p className="p-6" role="status">{error ? 'Reporting periods unavailable. Reload to retry.' : loading ? 'Loading reporting periods…' : 'No reporting periods available.'}</p>;
  return <InventoryWorkspace key={period} period={period} {...props} />;
}

function InventoryWorkspace({ period, navigation, onAsk }) {
  const [filters, setFilters] = useState(() => ({ ...DEFAULT_FILTERS, search: navigation?.search || '' }));
  const [selected, setSelected] = useState(null);
  const [ticketOpen, setTicketOpen] = useState(false);
  const rowRefs = useRef({});
  const returnFocus = useRef(null);
  const listHeading = useRef(null);
  const search = useDebouncedValue(filters.search);
  const includeWithin = filters.view === 'within';
  const params = {
    mon_period: period, search: search || undefined,
    finding_type: includeWithin ? 'WITHIN_ALLOCATION' : filters.view === 'coverage' ? 'NO_INVOICE_RECORD' : filters.finding || undefined,
    include_within_allocation: includeWithin,
    sort_by: filters.sort_by, sort_direction: filters.sort_direction,
    limit: filters.limit, offset: filters.offset,
  };
  const query = useQuery({ queryKey: ['inventory-page', params], queryFn: ({ signal }) => getInventoryComparisonPage(params, signal), enabled: !selected });
  // Never label a previous search/page/period payload as the new selection.
  const data = search === filters.search ? query.data : undefined;
  const busy = query.isFetching || search !== filters.search;
  useEffect(() => {
    if (!selected && returnFocus.current && !busy) {
      const rowButton = rowRefs.current[returnFocus.current];
      (rowButton && !rowButton.disabled ? rowButton : listHeading.current)?.focus();
      returnFocus.current = null;
    }
  }, [selected, busy]);
  function updateFilter(key, value) {
    setFilters((current) => key === 'reset' ? { ...DEFAULT_FILTERS } : {
      ...current, [key]: value, offset: 0,
      ...(key === 'view' ? { finding: '', sort_by: value === 'coverage' ? 'activation_count' : 'inventory_gap', sort_direction: 'desc' } : {}),
    });
  }
  const pagination = data?.pagination;
  return <main className="overview commission-workspace h-full overflow-y-auto bg-gray-50" aria-label="Inventory intelligence">
    <div className="mx-auto max-w-7xl p-4 sm:p-6 lg:p-8 space-y-6">
      <header className="flex flex-wrap items-start justify-between gap-4">
        <div><p className="text-xs font-semibold tracking-widest uppercase text-gray-500">Finance & revenue assurance</p>
          <h1 className="text-2xl font-semibold tracking-tight mt-1">Inventory Intelligence</h1>
          <p className="text-sm text-gray-600 mt-2">Compare reported activations with recorded IFS purchases by dealer and product.</p>
          <p className="text-sm text-gray-600 mt-2">Reporting period · {formatPeriod(period)}</p>
        </div>
        {!selected && <div className="flex flex-wrap gap-2"><button className="overview-button" onClick={() => query.refetch()} disabled={busy}>Refresh</button>
          <button className="overview-button" onClick={() => setTicketOpen(true)}>Prepare coverage ticket</button></div>}
      </header>
      <aside className="rounded-lg border border-blue-200 bg-blue-50 p-4 text-sm text-blue-900" aria-label="Invoice coverage limitation">
        <p className="font-semibold">Invoice coverage is limited</p>
        <p className="mt-1">The reporting period selects activations. Purchases use the available invoice dataset; a matching invoice window and complete period coverage are not established. Treat excess quantities as observations requiring investigation.</p>
        {data?.source_note && <p className="mt-2">{data.source_note}</p>}
      </aside>
      {selected ? <InventoryDetail row={selected.row} period={period} retrievedAt={selected.retrievedAt} onAsk={onAsk}
        onTicket={() => setTicketOpen(true)} onBack={() => { returnFocus.current = subjectFor(selected.row); setSelected(null); }} /> : <>
        <InventoryFilters filters={filters} onChange={updateFilter} />
        {query.isError && <p role="alert" className="overview-notice text-red-800">Inventory comparison unavailable. {data ? 'The figures below are the last successful result for these filters and have not been refreshed.' : 'No inventory position can be established.'} <button className="underline" onClick={() => query.refetch()}>Retry</button></p>}
        {busy && <p role="status" className="text-sm text-gray-600">{data ? 'Refreshing this comparison…' : 'Loading matching comparisons…'}</p>}
        {!data && busy && <div aria-hidden="true" className="space-y-4 animate-pulse"><div className="h-40 rounded-lg bg-gray-200" /><div className="h-64 rounded-lg bg-gray-200" /></div>}
        {data && <>
          <InventorySummary summary={data.summary} view={filters.view} />
          <section className="overview-surface overflow-hidden" aria-labelledby="inventory-comparisons-heading">
            <div className="p-5 border-b border-gray-200"><h2 ref={listHeading} tabIndex={-1} id="inventory-comparisons-heading" className="font-semibold">Dealer-product comparisons</h2>
              <p className="text-sm text-gray-600 mt-2" role="status">{pagination.total.toLocaleString()} matching combinations · {filters.view === 'coverage' ? 'Invoice coverage gaps' : includeWithin ? 'Within recorded purchases' : 'Needs investigation'}</p>
              <p className="text-xs text-gray-500 mt-2">Excess = activations minus recorded purchases. Unknown quantities show —. Negative differences are not stock balances.</p>
            </div>
            {data.items.length ? <InventoryComparisonTable rows={data.items} busy={busy || query.isError} rowRefs={rowRefs}
              onSelect={(row) => setSelected({ row, retrievedAt: query.dataUpdatedAt })} />
              : <div className="p-6 text-sm" role="status"><p className="font-semibold">No matching comparisons</p><p className="text-gray-600 mt-2">No dealer-product rows match this view and search. This does not establish complete invoice coverage.</p><button className="overview-button mt-4" onClick={() => updateFilter('reset')}>Reset filters</button></div>}
            <div className="p-4 flex flex-wrap items-center justify-between gap-3 border-t border-gray-200 text-sm text-gray-600">
              <span>{pagination.total ? pagination.offset + 1 : 0}–{pagination.offset + pagination.returned} of {pagination.total.toLocaleString()}</span>
              <div className="flex flex-wrap items-center gap-3">
                <label>Rows per page <select className="overview-select ml-2" value={filters.limit} onChange={(e) => updateFilter('limit', Number(e.target.value))} disabled={busy}>
                  {[25, 50, 100].map((size) => <option key={size} value={size}>{size}</option>)}
                </select></label>
                <button className="overview-button" disabled={busy || query.isError || !pagination.offset} onClick={() => setFilters((f) => ({ ...f, offset: Math.max(0, f.offset - f.limit) }))}>Previous</button>
                <button className="overview-button" disabled={busy || query.isError || !pagination.has_more} onClick={() => setFilters((f) => ({ ...f, offset: f.offset + f.limit }))}>Next</button>
              </div>
            </div>
          </section>
          <p className="text-xs text-gray-500">Comparison retrieved {new Date(query.dataUpdatedAt).toLocaleString()} · Retrieval time does not establish source freshness.</p>
        </>}
      </>}
      {ticketOpen && <DataCoverageTicketModal period={period} open onClose={() => setTicketOpen(false)} />}
    </div>
  </main>;
}
