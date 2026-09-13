import { useEffect, useRef, useState } from 'react';
import { keepPreviousData, useQuery, useQueryClient } from '@tanstack/react-query';
import { getPayments, getPaymentPosition, getPaymentExport, getPaymentAnalytics } from '../../api/client.js';
import { usePeriod } from '../../context/PeriodContext.jsx';
import { formatPeriod } from '../../lib/format.js';
import { downloadCsv } from '../../lib/csv.js';
import useDebouncedValue from '../../hooks/useDebouncedValue.js';
import PaginationControls from '../shared/PaginationControls.jsx';
import PaymentCoverageCard from './PaymentCoverageCard.jsx';
import PaymentSummaryTable from './PaymentSummaryTable.jsx';
import PaymentDetail from './PaymentDetail.jsx';
import PaymentComparison from './PaymentComparison.jsx';
import PartnerHealthScorecard from './PartnerHealthScorecard.jsx';
import './payment.css';

const VIEWS = [['exceptions', 'Exceptions'], ['all', 'All Payments'], ['comparison', 'Period comparison'], ['health', 'Health']];
const DEFAULTS = { search: '', status: '', sort_by: 'amount_unpaid', sort_direction: 'desc', limit: 25, offset: 0 };

export default function PaymentIntelligencePanel(props) {
  const { period, loading, error } = usePeriod();
  const initialPeriod = useRef(null);
  const navigationConsumed = useRef(false);
  const [view, setView] = useState(props.navigation?.tab === 'variance' ? 'comparison' : props.navigation?.tab || 'exceptions');
  if (period && !initialPeriod.current) initialPeriod.current = period;
  if (initialPeriod.current && period !== initialPeriod.current) navigationConsumed.current = true;
  if (!period) return <p className="p-6" role="status">{error ? 'Reporting periods unavailable. Reload to retry.' : loading ? 'Loading reporting periods…' : 'No reporting periods available.'}</p>;
  return <PaymentWorkspace key={period} period={period} {...props} view={view} setView={setView} navigation={!navigationConsumed.current ? props.navigation : undefined} />;
}

function PaymentWorkspace({ period, navigation, onNavigate, view, setView }) {
  const client = useQueryClient();
  const { periods } = usePeriod();
  const earlier = periods.filter((p) => p < period).sort().reverse();
  const [selectedComparison, setComparison] = useState(() => navigation?.prior_period === '' || earlier.includes(navigation?.prior_period) ? navigation.prior_period : null);
  const comparison = selectedComparison ?? earlier[0] ?? '';
  const [filters, setFilters] = useState({ ...DEFAULTS, search: navigation?.search || '' });
  const [selected, setSelected] = useState(navigation?.dealer_id || null);
  const [exporting, setExporting] = useState(false);
  const [exportError, setExportError] = useState('');
  const exportController = useRef(null);
  const heading = useRef(null);
  const rowRefs = useRef({});
  const returnFocus = useRef(null);
  const search = useDebouncedValue(filters.search);
  const main = view === 'exceptions' || view === 'all';
  const params = { mon_period: period, search, payment_status: filters.status || (view === 'exceptions' ? 'DISPUTED,PARTIALLY_PAID,PENDING' : undefined), sort_by: filters.sort_by, sort_direction: filters.sort_direction, limit: filters.limit, offset: filters.offset };
  const accounts = useQuery({ queryKey: ['payments-page', params], queryFn: ({ signal }) => getPayments(params, signal), placeholderData: keepPreviousData, enabled: main });
  const position = useQuery({ queryKey: ['payment-position', period], queryFn: ({ signal }) => getPaymentPosition(period, signal), enabled: !main });
  const prior = useQuery({ queryKey: ['payment-position', comparison], queryFn: ({ signal }) => getPaymentPosition(comparison, signal), enabled: Boolean(comparison) });
  const analyticsParams = { mon_period: period, prior_period: comparison || undefined, view, search, limit: filters.limit, offset: filters.offset };
  const analytics = useQuery({ queryKey: ['payment-analytics', analyticsParams], queryFn: ({ signal }) => getPaymentAnalytics(analyticsParams, signal), enabled: !main && (view !== 'comparison' || Boolean(comparison)) });
  const query = main ? accounts : analytics;
  const summaryQuery = main ? accounts : position;
  const summary = summaryQuery.isError ? null : summaryQuery.data;
  const busy = query.isFetching || search !== filters.search;
  const noComparison = view === 'comparison' && !comparison;
  const data = query.isError || busy ? null : query.data;
  useEffect(() => () => exportController.current?.abort(), []);
  useEffect(() => {
    if (!selected && returnFocus.current && !busy) {
      (rowRefs.current[returnFocus.current] || heading.current)?.focus();
      returnFocus.current = null;
    }
  }, [selected, busy]);
  function update(patch) { setFilters((current) => ({ ...current, ...patch, offset: 0 })); setExportError(''); }
  function changeView(next) { setView(next); update({ status: '' }); }
  function back() { returnFocus.current = selected; setSelected(null); }
  async function exportMatching() {
    const controller = new AbortController();
    exportController.current = controller;
    setExporting(true); setExportError('');
    try {
      const csv = await getPaymentExport({ ...params, limit: undefined, offset: undefined }, controller.signal);
      if (!controller.signal.aborted) downloadCsv(csv, `payment-accounts-${period}.csv`);
    } catch (error) { if (!controller.signal.aborted) setExportError('Matching-account export failed. Retry export.'); }
    finally { if (!controller.signal.aborted) setExporting(false); }
  }
  async function refresh() {
    await Promise.all([
      client.invalidateQueries({ queryKey: ['payment-account', period] }),
      client.invalidateQueries({ queryKey: ['dealer-verification', period] }),
      summaryQuery.refetch(),
      comparison ? prior.refetch() : Promise.resolve(),
      !main && !noComparison ? analytics.refetch() : Promise.resolve(),
    ]);
  }
  return <main className="overview commission-workspace payment-workspace h-full overflow-y-auto bg-gray-50" aria-label="Payment intelligence">
    <div className="mx-auto max-w-7xl p-4 sm:p-6 lg:p-8 space-y-6">
      <header className="flex flex-wrap justify-between items-start gap-4">
        <div><p className="text-xs font-semibold tracking-widest uppercase text-gray-500">Finance & revenue assurance</p><h1 className="text-2xl font-semibold tracking-tight mt-1">Payment Intelligence</h1><p className="text-sm text-gray-600 mt-2">Review recorded commissions, settlements and outstanding balances by dealer.</p></div>
        <div className="flex flex-wrap items-center gap-3"><button className="overview-button" disabled={busy || summaryQuery.isFetching} onClick={refresh}>Refresh</button>{main && !selected && <button className="overview-button" disabled={busy || accounts.isError || !accounts.data || exporting} onClick={exportMatching}>{exporting ? 'Exporting matching accounts…' : 'Export matching accounts'}</button>}</div>
      </header>
      <label className="text-sm flex flex-wrap items-center gap-3">Compare {formatPeriod(period)} with <select className="overview-select" value={comparison} onChange={(e) => { setComparison(e.target.value); update({}); }}><option value="">No comparison</option>{earlier.map((p) => <option key={p} value={p}>{formatPeriod(p)}</option>)}</select></label>
      {exportError && <p role="alert" className="overview-notice text-red-800">{exportError}</p>}
      {summaryQuery.isError && <p role="alert" className="overview-notice text-red-800">Full-period payment figures could not be refreshed. <button className="underline" onClick={() => summaryQuery.refetch()}>Retry summary</button></p>}
      {summaryQuery.isFetching && summary && <p role="status" className="text-sm text-gray-600">Refreshing full-period figures; displayed values are from the last successful retrieval.</p>}
      {summary && <p className="overview-notice text-sm text-gray-600">{summary.data_source === 'APDP' ? 'APDP payment source selected. Production provenance has not been established.' : 'Simulated payment source: synthetic settlement figures for demonstration.'} · {formatPeriod(period)} · Retrieved {new Date(summary.generated_at || summaryQuery.dataUpdatedAt).toLocaleString()}. Retrieval time is not source freshness.</p>}
      {!selected && <>
        <PaymentCoverageCard data={summary} loading={summaryQuery.isFetching} prior={prior.data} comparison={comparison} comparisonError={prior.isError || prior.isFetching} />
        {comparison && prior.isError && <p role="alert" className="overview-notice">Comparison totals unavailable. <button className="underline" onClick={() => prior.refetch()}>Retry comparison totals</button></p>}
        <section className="overview-surface overflow-hidden" aria-label="Payment account workspace">
          <div className="p-5 space-y-5">
            <div className="flex flex-wrap gap-2" role="group" aria-label="Payment views">{VIEWS.map(([id, label]) => <button key={id} className={`overview-button ${view === id ? 'overview-primary' : ''}`} aria-pressed={view === id} onClick={() => changeView(id)}>{label}</button>)}</div>
            <h2 ref={heading} tabIndex={-1} className="text-lg font-semibold">{VIEWS.find(([id]) => id === view)?.[1]} · {formatPeriod(period)}</h2>
            <div className="flex flex-wrap gap-3 items-end">
              <label className="text-sm text-gray-600 min-w-0">Dealer search<input type="search" maxLength={100} className="overview-select block mt-2 w-full" value={filters.search} onChange={(e) => update({ search: e.target.value })} placeholder="Dealer name or exact code" /></label>
              {main && <><label className="text-sm text-gray-600">Payment status<select className="overview-select block mt-2" value={filters.status} onChange={(e) => update({ status: e.target.value })}><option value="">{view === 'exceptions' ? 'All exception statuses' : 'All statuses'}</option>{(view === 'all' ? ['FULLY_PAID', 'PARTIALLY_PAID', 'DISPUTED', 'PENDING'] : ['PARTIALLY_PAID', 'DISPUTED', 'PENDING']).map((s) => <option key={s} value={s}>{s.replaceAll('_', ' ').toLowerCase()}</option>)}</select></label>
                <label className="text-sm text-gray-600">Sort by<select className="overview-select block mt-2" value={filters.sort_by} onChange={(e) => update({ sort_by: e.target.value })}>{[['amount_unpaid', 'Outstanding'], ['commission_owed', 'Commission owed'], ['amount_paid', 'Amount settled'], ['dealer_name', 'Dealer name'], ['payment_status', 'Payment status']].map(([v, label]) => <option key={v} value={v}>{label}</option>)}</select></label>
                <label className="text-sm text-gray-600">Order<select className="overview-select block mt-2" value={filters.sort_direction} onChange={(e) => update({ sort_direction: e.target.value })}><option value="desc">Descending</option><option value="asc">Ascending</option></select></label></>}
              <button className="overview-button" onClick={() => setFilters({ ...DEFAULTS })}>Reset filters</button>
            </div>
            <p className="text-sm text-gray-600" role="status">{noComparison ? 'Choose a comparison period to see shared accounts.' : busy ? 'Loading matching accounts…' : query.isError ? 'Account results unavailable.' : `${data?.pagination.total ?? 0} matching accounts${filters.search ? ` for “${filters.search}”` : ''}.`}</p>
          </div>
          {query.isError && !noComparison && <p role="alert" className="p-5 text-red-800">Account results could not be loaded. <button className="underline" onClick={() => query.refetch()}>Retry accounts</button></p>}
          {busy && !noComparison && <div className="p-5 space-y-3" aria-busy="true">{[1, 2, 3].map((i) => <div key={i} className="h-14 bg-gray-100 animate-pulse rounded" />)}</div>}
          {data && !noComparison && (data.items.length ? <>
            {main && <PaymentSummaryTable rows={data.items} rowRefs={rowRefs} period={period} onSelect={setSelected} />}
            {view === 'comparison' && <PaymentComparison rows={data.items} period={period} comparison={comparison} rowRefs={rowRefs} onSelect={setSelected} />}
            {view === 'health' && <PartnerHealthScorecard rows={data.items} rowRefs={rowRefs} onSelect={setSelected} />}
          </> : <p className="p-5 text-sm" role="status">{filters.search || filters.status ? 'No matching accounts. Adjust the search or payment status, or Reset filters above.' : main && data.record_count === 0 ? 'No payment source records for this period.' : view === 'exceptions' ? 'No outstanding payment exceptions recorded for this period.' : view === 'comparison' ? 'No accounts recorded in both selected periods.' : 'No accounts recorded for this view.'}</p>)}
          {data && !noComparison && <div className="payment-pagination p-5 border-t border-gray-200"><PaginationControls pagination={data.pagination} pageSize={filters.limit} onOffsetChange={(offset) => setFilters((f) => ({ ...f, offset }))} onPageSizeChange={(limit) => update({ limit })} /></div>}
        </section>
      </>}
      {selected && <PaymentDetail key={`${selected}:${comparison}`} dealerId={selected} period={period} comparison={comparison} onBack={back} onNavigate={onNavigate} />}
    </div>
  </main>;
}
