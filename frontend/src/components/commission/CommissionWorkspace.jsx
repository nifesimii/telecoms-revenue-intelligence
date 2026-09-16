import { useEffect, useRef, useState } from 'react';
import { keepPreviousData, useQuery } from '@tanstack/react-query';
import { usePeriod } from '../../context/PeriodContext.jsx';
import { getCommissionAccounts, getCommissionDetail, getCommissionExport } from '../../api/client.js';
import { formatPeriod } from '../../lib/format.js';
import { downloadCsv } from '../../lib/csv.js';
import useDebouncedValue from '../../hooks/useDebouncedValue.js';
import CommissionSummary from './CommissionSummary.jsx';
import CommissionAccounts from './CommissionAccounts.jsx';
import CommissionDetail from './CommissionDetail.jsx';
import CommissionAssistant from './CommissionAssistant.jsx';

export default function CommissionWorkspace(props) {
  const { period, error, loading } = usePeriod();
  const [stream, setStream] = useState('activation');
  if (!period) return <p className="p-6" role="status">{error ? 'Reporting periods unavailable. Reload to retry.' : loading ? 'Loading reporting periods…' : 'No reporting periods available.'}</p>;
  return <PeriodWorkspace key={period} period={period} stream={stream} setStream={setStream} {...props} />;
}

function PeriodWorkspace({ period, stream, setStream, ...props }) {
  const { periods } = usePeriod();
  const earlier = periods.filter((p) => p < period).sort().reverse();
  const requestedComparison = props.navigation?.prior_period;
  const [selectedComparison, setComparison] = useState(
    requestedComparison === '' || earlier.includes(requestedComparison) ? requestedComparison : null,
  );
  const comparison = selectedComparison ?? earlier[0] ?? '';
  return <main className="overview commission-workspace h-full overflow-y-auto bg-gray-50" aria-label="Commission intelligence">
    <div className="mx-auto max-w-7xl p-4 sm:p-6 lg:p-8 space-y-6">
      <header className="flex flex-wrap justify-between items-start gap-4">
        <div><p className="text-xs font-semibold tracking-widest uppercase text-gray-500">Finance & revenue assurance</p>
          <h1 className="text-2xl font-semibold tracking-tight mt-1">Commission Intelligence</h1>
          <p className="text-sm text-gray-600 mt-2">Understand the figure. Investigate the difference. Follow the evidence.</p></div>
        <label className="text-sm text-gray-600 flex flex-wrap items-center gap-3">Compare {formatPeriod(period)} with
          <select className="overview-select" value={comparison} onChange={(e) => setComparison(e.target.value)}>
            <option value="">No comparison</option>{earlier.map((p) => <option key={p} value={p}>{formatPeriod(p)}</option>)}
          </select>
        </label>
      </header>
      <div className="flex flex-wrap gap-2" role="group" aria-label="Commission revenue stream">
        {[['activation', 'Activation commission'], ['orsc', 'Subscription commission']].map(([value, label]) => <button key={value} className={`overview-button ${stream === value ? 'overview-primary' : ''}`} aria-pressed={stream === value} onClick={() => setStream(value)}>{label}</button>)}
      </div>
      <AccountWorkspace key={`${stream}:${comparison}`} period={period} comparison={comparison} stream={stream} {...props} />
    </div>
  </main>;
}

const DEFAULT_FILTERS = { search: '', partner_class: '', status: 'all', sort_by: 'amount_ngn', direction: 'desc', limit: 25, offset: 0 };

function AccountWorkspace({ period, comparison, stream, pendingPrompt, onPromptConsumed, onNavigate, navigation }) {
  const [filters, setFilters] = useState(() => ({ ...DEFAULT_FILTERS, search: navigation?.search || navigation?.dealer_id || '' }));
  const [selected, setSelected] = useState(null);
  const [showAssistant, setShowAssistant] = useState(Boolean(pendingPrompt));
  const [exporting, setExporting] = useState(false);
  const [exportError, setExportError] = useState('');
  const rowRefs = useRef({});
  const listHeading = useRef(null);
  const returnFocus = useRef(null);
  const navigationConsumed = useRef(false);
  const search = useDebouncedValue(filters.search);
  const params = { ...filters, search, mon_period: period, prior_period: comparison || undefined, stream };
  const query = useQuery({ queryKey: ['commission-accounts', params],
    queryFn: ({ signal }) => getCommissionAccounts(params, signal), placeholderData: keepPreviousData });
  const data = query.data;
  const busy = query.isFetching || search !== filters.search;
  const detailParams = { mon_period: period, prior_period: comparison || undefined, stream };
  const navigationQuery = useQuery({
    queryKey: ['commission-detail', navigation?.dealer_id, detailParams],
    queryFn: ({ signal }) => getCommissionDetail(navigation.dealer_id, detailParams, signal),
    enabled: Boolean(navigation?.dealer_id && !navigationConsumed.current),
  });
  useEffect(() => {
    if (navigationConsumed.current || !navigation?.dealer_id || !navigationQuery.data || navigationQuery.isError) return;
    setSelected(navigationQuery.data.account);
    navigationConsumed.current = true;
  }, [navigationQuery.data, navigationQuery.isError, navigation]);
  useEffect(() => {
    if (pendingPrompt) { setSelected(null); setShowAssistant(true); }
  }, [pendingPrompt]);
  useEffect(() => {
    if (!selected && returnFocus.current) {
      (rowRefs.current[returnFocus.current] || listHeading.current)?.focus();
      returnFocus.current = null;
    }
  }, [selected]);
  function updateFilter(key, value) {
    setFilters((current) => key === 'reset' ? DEFAULT_FILTERS : { ...current, [key]: value, offset: 0 });
  }
  function back() { returnFocus.current = selected.dealer_id; setSelected(null); }
  async function exportMatching() {
    setExporting(true); setExportError('');
    try { downloadCsv(await getCommissionExport(params), `commission_${stream === 'orsc' ? 'subscription' : stream}_${period}_matching_accounts.csv`); }
    catch { setExportError('The matching-account export is unavailable. Please retry.'); }
    finally { setExporting(false); }
  }
  if (selected) return <CommissionDetail account={selected} period={period} comparison={comparison} stream={stream} onBack={back} onNavigate={onNavigate} />;
  return <>
    {navigationQuery.isError && !navigationConsumed.current && <p role="alert" className="overview-notice text-red-800">Requested account unavailable. <button className="underline" onClick={() => navigationQuery.refetch()}>Retry account</button></p>}
    <div className="flex flex-wrap items-center justify-between gap-3">
      <p className="text-sm text-gray-500">{formatPeriod(period)} · {stream === 'orsc' ? 'Subscription commission' : 'Activation commission ledger'}</p>
      <div className="flex flex-wrap gap-2"><button className="overview-button" onClick={() => query.refetch()} disabled={busy}>Refresh</button>
        <button className="overview-button" onClick={exportMatching} disabled={!data || query.isError || busy || exporting}>{exporting ? 'Exporting…' : 'Export matching accounts ↓'}</button>
        <button className="overview-button" aria-expanded={showAssistant} onClick={() => setShowAssistant(!showAssistant)}>{showAssistant ? 'Hide assistant' : 'Ask a question'}</button></div>
    </div>
    {exportError && <p role="alert" className="text-sm text-red-800">{exportError}</p>}
    {showAssistant && <CommissionAssistant key={`${period}:${comparison}:${stream}:all`} period={period} comparison={comparison} stream={stream} prompt={pendingPrompt} onPromptConsumed={onPromptConsumed} />}
    {query.isError && <div role="alert" className="overview-notice text-red-800">Commission data unavailable. {data ? 'The figures below are the last successful result; they have not been refreshed.' : 'No balance can be established.'} <button className="underline" onClick={() => query.refetch()}>Retry</button></div>}
    {!data && query.isPending && <div role="status" aria-label="Loading commission workspace" className="space-y-5 animate-pulse"><div className="h-56 bg-gray-200 rounded-lg" /><div className="h-80 bg-gray-200 rounded-lg" /></div>}
    {data && <>
      <CommissionSummary data={data} onFilter={(status) => updateFilter('status', status)} />
      <CommissionAccounts data={data} busy={busy || query.isError} filters={filters} onFilter={updateFilter} onSelect={setSelected} rowRefs={rowRefs} headingRef={listHeading} onPage={(offset) => setFilters((current) => ({ ...current, offset }))} />
      <footer className="text-xs text-gray-500 flex flex-wrap gap-3 justify-between border-t border-gray-200 pt-4"><span>{data.source} · Retrieved {new Date(data.generated_at).toLocaleString()}</span><span>Amounts follow existing source calculations. No production writes.</span></footer>
    </>}
  </>;
}
