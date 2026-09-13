import { useEffect, useRef, useState } from 'react';
import { keepPreviousData, useQuery } from '@tanstack/react-query';
import { getActivationAccounts, getActivationExport } from '../../api/client.js';
import { usePeriod } from '../../context/PeriodContext.jsx';
import { formatPeriod } from '../../lib/format.js';
import { downloadCsv } from '../../lib/csv.js';
import useDebouncedValue from '../../hooks/useDebouncedValue.js';
import ActivationSummary from './ActivationSummary.jsx';
import ActivationAccounts from './ActivationAccounts.jsx';
import ActivationDetail from './ActivationDetail.jsx';
import { VIEWS } from './ActivationFilters.jsx';

const DEFAULT_FILTERS = { view: 'accounts', search: '', partner_class: '', finding: 'all', sort_by: 'activation_count', direction: 'desc', limit: 25, offset: 0 };
const navigationView = (tab) => tab === 'variance' ? 'comparison' : VIEWS.some(([id]) => id === tab) ? tab : 'accounts';

export default function ActivationIntelligencePanel(props) {
  const { period, error, loading } = usePeriod();
  const initialPeriod = useRef(null);
  const navigationConsumed = useRef(false);
  if (period && !initialPeriod.current) initialPeriod.current = period;
  if (initialPeriod.current && period !== initialPeriod.current) navigationConsumed.current = true;
  if (!period) return <p className="p-6" role="status">{error ? 'Reporting periods unavailable. Reload to retry.' : loading ? 'Loading reporting periods…' : 'No reporting periods available.'}</p>;
  return <ActivationWorkspace key={period} period={period} {...props} navigation={!navigationConsumed.current ? props.navigation : undefined} />;
}

function ActivationWorkspace({ period, navigation, onNavigate }) {
  const { periods } = usePeriod();
  const earlier = periods.filter((p) => p < period).sort().reverse();
  const [comparison, setComparison] = useState(() => navigation?.prior_period === '' || earlier.includes(navigation?.prior_period) ? navigation.prior_period : earlier[0] || '');
  const [filters, setFilters] = useState(() => ({ ...DEFAULT_FILTERS, view: navigationView(navigation?.tab), search: navigation?.search || '', sort_by: navigation?.tab === 'exceptions' ? 'severity' : 'activation_count' }));
  const [selected, setSelected] = useState(() => navigation?.dealer_id ? { dealer_id: navigation.dealer_id, dealer_name: navigation.dealer_name || `Account ${navigation.dealer_id}` } : null);
  const workspaceRef = useRef(null);
  const [exporting, setExporting] = useState(false);
  const [exportError, setExportError] = useState('');
  const rowRefs = useRef({});
  const returnFocus = useRef(null);
  const previousNavigation = useRef(navigation);
  const search = useDebouncedValue(filters.search);
  const params = { ...filters, search, mon_period: period, prior_period: comparison || undefined };
  const query = useQuery({ queryKey: ['activation-accounts', params], queryFn: ({ signal }) => getActivationAccounts(params, signal), placeholderData: keepPreviousData });
  const data = query.data;
  const busy = query.isFetching || search !== filters.search;
  useEffect(() => {
    if (navigation === previousNavigation.current) return;
    previousNavigation.current = navigation;
    if (!navigation) return;
    setSelected(null);
    setFilters({ ...DEFAULT_FILTERS, view: navigationView(navigation.tab), search: navigation.search || '', sort_by: navigation.tab === 'exceptions' ? 'severity' : 'activation_count' });
    if (navigation.prior_period === '' || earlier.includes(navigation.prior_period)) setComparison(navigation.prior_period);
  }, [navigation, earlier]);
  useEffect(() => {
    if (!selected && returnFocus.current && !busy) {
      (rowRefs.current[returnFocus.current] || workspaceRef.current)?.focus();
      returnFocus.current = null;
    }
  }, [selected, busy]);
  function updateFilter(key, value) {
    setExportError('');
    setFilters((current) => key === 'reset' ? { ...DEFAULT_FILTERS, view: current.view, sort_by: current.view === 'exceptions' ? 'severity' : 'activation_count' } : { ...current, [key]: value, offset: 0, ...(key === 'view' ? { sort_by: value === 'exceptions' ? 'severity' : 'activation_count', direction: 'desc' } : {}) });
  }
  function changeComparison(value) { setComparison(value); setSelected(null); setFilters((current) => ({ ...current, offset: 0 })); setExportError(''); }
  async function exportMatching() {
    setExporting(true); setExportError('');
    try { downloadCsv(await getActivationExport(params), `activation_${filters.view}_${period}_matching_accounts.csv`); }
    catch { setExportError('The matching-account export is unavailable. Please retry.'); }
    finally { setExporting(false); }
  }
  return <main ref={workspaceRef} tabIndex={-1} className="overview commission-workspace h-full overflow-y-auto bg-gray-50" aria-label="Activation intelligence">
    <div className="mx-auto max-w-7xl p-4 sm:p-6 lg:p-8 space-y-6">
      <header className="flex flex-wrap justify-between items-start gap-4"><div><p className="text-xs font-semibold tracking-widest uppercase text-gray-500">Finance & revenue assurance</p><h1 className="text-2xl font-semibold tracking-tight mt-1">Activation Intelligence</h1><p className="text-sm text-gray-600 mt-2">Track activation volume. Understand qualification. Investigate the evidence.</p></div>
        <label className="text-sm text-gray-600 flex flex-wrap items-center gap-3">Compare {formatPeriod(period)} with<select className="overview-select max-w-full" value={comparison} onChange={(e) => changeComparison(e.target.value)}><option value="">No comparison</option>{earlier.map((p) => <option key={p} value={p}>{formatPeriod(p)}</option>)}</select></label>
      </header>
      {selected ? <ActivationDetail key={`${selected.dealer_id}:${comparison}`} account={selected} period={period} comparison={comparison} onBack={() => { returnFocus.current = selected.dealer_id; setSelected(null); }} onNavigate={onNavigate} /> : <>
        <div className="flex flex-wrap justify-between gap-3"><p className="text-sm text-gray-500">{formatPeriod(period)} · Activation volume and qualification</p><div className="flex flex-wrap gap-2"><button className="overview-button" onClick={() => query.refetch()} disabled={busy}>Refresh</button><button className="overview-button" onClick={exportMatching} disabled={!data || busy || query.isError || exporting}>{exporting ? 'Exporting…' : 'Export matching accounts ↓'}</button></div></div>
        {exportError && <p role="alert" className="text-sm text-red-800">{exportError}</p>}
        {query.isError && <div role="alert" className="overview-notice text-red-800">Activation data unavailable. {data ? 'Figures below are the last successful result and have not been refreshed.' : 'No activation position can be established.'} <button className="underline" onClick={() => query.refetch()}>Retry</button></div>}
        {data && <ActivationSummary summary={data.summary} onFilter={(finding) => { updateFilter('view', 'accounts'); updateFilter('finding', finding); }} />}
        <div className="flex flex-wrap gap-2" role="group" aria-label="Activation views">{VIEWS.map(([id, label]) => <button key={id} className={`overview-button ${filters.view === id ? 'overview-primary' : ''}`} aria-pressed={filters.view === id} onClick={() => updateFilter('view', id)}>{label}</button>)}</div>
        {!data && query.isPending && <div role="status" aria-label="Loading activation workspace" className="space-y-5 animate-pulse">{!data && <div className="h-56 bg-gray-200 rounded-lg" />}<div className="h-80 bg-gray-200 rounded-lg" /></div>}
        {data && <ActivationAccounts data={data} busy={busy || query.isError} filters={filters} onFilter={updateFilter} onSelect={setSelected} rowRefs={rowRefs} onPage={(offset) => setFilters((current) => ({ ...current, offset }))} />}
        {data && <footer className="text-xs text-gray-500 flex flex-wrap gap-3 justify-between border-t border-gray-200 pt-4"><span>{data.source} · Retrieved {new Date(data.generated_at).toLocaleString()}</span><span>Recorded figures follow existing source calculations.</span></footer>}
      </>}
    </div>
  </main>;
}
