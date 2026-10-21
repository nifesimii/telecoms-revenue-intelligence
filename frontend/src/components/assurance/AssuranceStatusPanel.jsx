import useQuery from '../../hooks/useWorkspaceQuery.js';
import { useEffect, useState } from 'react';
import { keepPreviousData, useQueryClient } from '@tanstack/react-query';
import { getOverview, getOverviewExport, getPaymentPosition } from '../../api/client.js';
import { usePeriod } from '../../context/PeriodContext.jsx';
import { formatPeriod } from '../../lib/format.js';
import { downloadCsv } from '../../lib/csv.js';
import useDebouncedValue from '../../hooks/useDebouncedValue.js';
import FinancialPosition from './FinancialPosition.jsx';
import InvestigationQueue from './InvestigationQueue.jsx';
import OverviewCoverage from './OverviewCoverage.jsx';

export default function AssuranceStatusPanel(props) {
  const { period, loading, error } = usePeriod();
  if (loading || !period) return <div className="p-6" role="status">
    {error ? 'Reporting periods unavailable. Reload the page to retry.' : loading ? 'Loading reporting periods…' : 'No reporting periods available.'}
  </div>;
  return <OverviewPeriod period={period} {...props} />;
}

function OverviewPeriod({ period, onNavigate, onAsk }) {
  const queryClient = useQueryClient();
  const { periods } = usePeriod();
  const comparisons = periods.filter((p) => p < period).sort().reverse();
  const [selectedComparison, setComparison] = useState(null);
  const comparison = selectedComparison === '' || comparisons.includes(selectedComparison) ? selectedComparison : comparisons[0] || '';
  const [search, setSearch] = useState('');
  const [severity, setSeverity] = useState('');
  const [module, setModule] = useState('');
  const [offset, setOffset] = useState(0);
  const [evidence, setEvidence] = useState(null);
  const [exporting, setExporting] = useState(false);
  const [exportError, setExportError] = useState('');
  const debouncedSearch = useDebouncedValue(search);
  useEffect(() => { setOffset(0); }, [period]);
  const params = { mon_period: period, limit: 5, offset,
    search: debouncedSearch, severity: severity || undefined, module: module || undefined };
  const query = useQuery({ queryKey: ['overview', params],
    queryFn: ({ signal }) => getOverview(params, signal), placeholderData: keepPreviousData });
  const prior = useQuery({ queryKey: ['payment-position', comparison],
    queryFn: ({ signal }) => getPaymentPosition(comparison, signal), enabled: Boolean(comparison) });
  const data = query.data;
  const updateFilter = (setter) => (value) => { setter(value); setOffset(0); };

  async function exportAll() {
    setExporting(true);
    setExportError('');
    try { downloadCsv(await getOverviewExport(period), `assurance_findings_${period}.csv`); }
    catch { setExportError('The complete export is unavailable. Refresh the overview and try again.'); }
    finally { setExporting(false); }
  }

  return (
    <main className="overview h-full overflow-y-auto bg-gray-50" aria-label="Finance overview">
      <div className="mx-auto max-w-7xl p-4 sm:p-6 lg:p-8 space-y-6">
        <header className="flex flex-wrap items-start justify-between gap-4">
          <div>
            <p className="text-xs font-semibold tracking-widest uppercase text-gray-500">Finance & revenue assurance</p>
            <h1 className="mt-1 text-2xl font-semibold tracking-tight">Overview <span className="text-gray-500 font-normal">/ {formatPeriod(period)}</span></h1>
            <p className="mt-2 text-sm text-gray-600">Your financial position and the partner investigations that need attention.</p>
          </div>
          <div className="flex flex-wrap gap-2">
            <button className="overview-button" onClick={() => { query.refetch(); if (comparison) prior.refetch(); queryClient.invalidateQueries({ queryKey: ['audit-breakdown'] }); }} disabled={query.isFetching}>Refresh</button>
            <button className="overview-button" onClick={exportAll} disabled={!data?.complete || query.isError || exporting}>
              {exporting ? 'Exporting…' : 'Export all findings ↓'}
            </button>
          </div>
        </header>
        {exportError && <p role="alert" className="text-sm text-red-700">{exportError}</p>}
        {query.isError && <div role="alert" className="overview-notice border-red-200 text-red-800">
          Overview could not be refreshed. {data ? 'The figures below are the last successful result for this period.' : 'No totals are available.'}
          <button onClick={() => query.refetch()} className="ml-3 underline">Retry</button>
        </div>}
        {!data && query.isPending && <div role="status" aria-label="Loading overview" className="space-y-6 animate-pulse">
          <div className="h-56 rounded-lg bg-gray-200" /><div className="h-80 rounded-lg bg-gray-200" />
        </div>}
        {data && <>
          {!data.complete && <div role="status" className="overview-notice border-amber-200 text-amber-900">
            Incomplete assessment. Some sources could not be checked; totals and the queue cover available modules only. Full export is disabled.
          </div>}
          <FinancialPosition payment={data.payment} prior={prior} comparison={comparison}
            comparisons={comparisons} setComparison={setComparison} onNavigate={onNavigate} />
          <div className="grid grid-cols-1 xl:grid-cols-[minmax(0,1fr)_18rem] gap-6 items-start">
            <InvestigationQueue evidence={evidence} setEvidence={setEvidence} data={data} busy={query.isFetching || search !== debouncedSearch}
              search={search} setSearch={updateFilter(setSearch)} severity={severity} setSeverity={updateFilter(setSeverity)}
              module={module} setModule={updateFilter(setModule)} offset={offset} setOffset={setOffset}
              onNavigate={onNavigate} onAsk={onAsk} period={period} />
            <OverviewCoverage period={period} data={data} onNavigate={onNavigate} />
          </div>
          <footer className="text-xs text-gray-500 border-t border-gray-200 pt-4 flex flex-wrap justify-between gap-2">
            <span>Assessment refreshed {new Date(data.checked_at).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })} · {formatPeriod(period)}</span>
            <span>Findings flag records for review; they do not establish an amount owed.</span>
          </footer>
        </>}
      </div>
    </main>
  );
}
