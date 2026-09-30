import { useWorkspaceActive } from '../../context/WorkspaceActivityContext.jsx';
import useQuery from '../../hooks/useWorkspaceQuery.js';
import { useEffect, useRef, useState } from 'react';
import { useQueryClient } from '@tanstack/react-query';
import { usePeriod } from '../../context/PeriodContext.jsx';
import { formatPeriod } from '../../lib/format.js';
import { downloadCsv } from '../../lib/csv.js';
import useDebouncedValue from '../../hooks/useDebouncedValue.js';
import { getAuditModules, getAuditRecords, getAuditExport } from '../../api/client.js';
import useAuditReplacement from './useAuditReplacement.js';
import AuditEvidence from './AuditEvidence.jsx';
import AuditResults, { AuditSummary } from './AuditResults.jsx';
import { label } from './auditPresentation.js';

const DEFAULTS = { search: '', conclusion: '', confidence: '', caveats: 'all', caveat_step: '', sort_by: 'partner_name', sort_direction: 'asc', limit: 25, offset: 0 };
export default function AuditTrailPanel(props) {
  const { period, loading, error } = usePeriod();
  const [module, setModule] = useState(props.navigation?.module || 'zero_commission');
  if (loading || !period) return <p className="p-6" role="status">{error ? 'Reporting periods unavailable. Reload to retry.' : loading ? 'Loading reporting periods…' : 'No reporting periods available.'}</p>;
  return <AuditWorkspace period={period} module={module} setModule={setModule} {...props} />;
}
function AuditWorkspace({ period, module, setModule, navigation, onReturn }) {
  const active = useWorkspaceActive();
  const [filters, setFilters] = useState(() => ({ ...DEFAULTS, search: navigation?.subject ? '' : navigation?.search || '' }));
  const [subject, setSubject] = useState(navigation?.subject || '');
  const [selectedTrail, setTrailId] = useState(null);
  const trailId = selectedTrail?.period === period ? selectedTrail.id : null;
  const [notice, setNotice] = useState('');
  const { replacement, run: runReplacement } = useAuditReplacement();
  const running = replacement?.status === 'pending';
  const [exporting, setExporting] = useState(false);
  const runScope = `${module}:${period}`;
  const [acknowledgement, setAcknowledgement] = useState({ scope: runScope, checked: false });
  // Reset before committing a new scope, including when returning to an earlier
  // month. Consent for one replacement must never enable another replacement.
  if (acknowledgement.scope !== runScope) setAcknowledgement({ scope: runScope, checked: false });
  const runAcknowledged = acknowledgement.scope === runScope && acknowledgement.checked;
  const setRunAcknowledged = (checked) => setAcknowledgement({ scope: runScope, checked });
  const rows = useRef({});
  const returnFocus = useRef('');
  const heading = useRef(null);
  const queryClient = useQueryClient();
  const search = useDebouncedValue(filters.search);
  useEffect(() => { setFilters((current) => ({ ...current, offset: 0 })); }, [period]);
  const params = { ...filters, search, mon_period: period, module };
  const registry = useQuery({ queryKey: ['audit-modules'], queryFn: getAuditModules });
  const query = useQuery({ queryKey: ['audit-records', params], queryFn: ({ signal }) => getAuditRecords(params, signal), enabled: !subject, retry: false });
  const invalidOffset = query.data && filters.offset > 0 && filters.offset >= query.data.pagination.total;
  const data = search === filters.search && !query.isError && !invalidOffset ? query.data : undefined;
  const busy = query.isFetching || search !== filters.search || Boolean(invalidOffset);
  const activeModule = registry.data?.find((item) => item.name === module);
  useEffect(() => {
    if (active && invalidOffset) {
      // The cached first page may predate the shrink and still be considered
      // fresh. Refetch it when recovering instead of restoring stale totals.
      queryClient.invalidateQueries({ queryKey: ['audit-records', { ...params, offset: 0 }], exact: true });
      setFilters((current) => ({ ...current, offset: 0 }));
    }
  }, [active, invalidOffset, queryClient, params]);
  useEffect(() => {
    if (!subject && returnFocus.current && !busy) {
      (rows.current[returnFocus.current] || heading.current)?.focus();
      returnFocus.current = '';
    }
  }, [subject, busy]);
  function update(key, value) { setFilters((current) => ({ ...current, [key]: value, offset: 0 })); setNotice(''); }
  function changeModule(value) { setModule(value); setSubject(''); setTrailId(null); setFilters({ ...DEFAULTS }); setNotice(''); setRunAcknowledged(false); }
  async function exportMatches() {
    setExporting(true); setNotice('');
    try { downloadCsv(await getAuditExport(params), `audit-${module}-${period}-matching.csv`); }
    catch { setNotice('Export failed. Retry when saved evidence is available.'); }
    finally { setExporting(false); }
  }
  async function run() {
    if (!runAcknowledged || running) return;
    setRunAcknowledged(false); setNotice('');
    await runReplacement(module, period);
  }
  return <main className="overview commission-workspace h-full overflow-y-auto bg-gray-50" aria-label="Audit Trails">
    <div className="mx-auto max-w-7xl p-4 sm:p-6 lg:p-8 space-y-6">
      <header className="flex flex-wrap justify-between items-start gap-4">
        <div><p className="text-xs font-semibold tracking-widest uppercase text-gray-500">Finance & revenue assurance</p>
          <h1 className="text-2xl font-semibold tracking-tight mt-1">Audit Trails</h1>
          <p className="text-sm text-gray-600 mt-2">Inspect what was checked, what saved evidence supports, and what remains uncertain.</p>
          <p className="text-sm text-gray-600 mt-2">Reporting period · {formatPeriod(period)} · {activeModule?.label || label(module)}</p>
        </div>
        <div className="flex flex-wrap gap-2">{onReturn && <button className="overview-button" onClick={onReturn}>Return to investigation</button>}
          {!subject && <><button className="overview-button" disabled={busy || running} onClick={() => query.refetch()}>Refresh saved evidence</button><button className="overview-button" disabled={!data || busy || exporting || running} onClick={exportMatches}>{exporting ? 'Exporting…' : 'Export all matching results'}</button></>}
        </div>
      </header>
      {replacement && <p role="status" className="overview-notice">
        Replacement assessment · {label(replacement.module)} · {formatPeriod(replacement.period)} ({replacement.period}):{' '}
        {running ? 'Running; additional replacement runs are disabled until this request finishes.'
          : replacement.status === 'success'
            ? `Run ${replacement.result.run_id}: ${replacement.result.trail_count} saved trails. Previous trails for this module and period were replaced.`
            : 'The run did not return a successful result; its outcome is unknown. Refresh saved evidence for this module and period to inspect the current saved state before retrying.'}
      </p>}
      {subject ? <AuditEvidence subject={subject} trailId={trailId} module={module} period={period} onBack={() => { returnFocus.current = trailId || subject; setSubject(''); setTrailId(null); }} /> : <>
        {data && <AuditSummary summary={data.summary} filtered={data.filtered_summary} />}
        <section className="overview-surface p-5 sm:p-6" aria-label="Audit filters">
          <div className="grid grid-cols-1 gap-5 sm:grid-cols-3 sm:gap-6">
            <label className="text-sm flex min-w-0 flex-col gap-2">Module<select className="overview-select min-h-11 w-full" value={module} disabled={running} onChange={(e) => changeModule(e.target.value)}>{(registry.data || [{ name: module, label: label(module) }]).map((item) => <option key={item.name} value={item.name}>{item.label}</option>)}</select></label>
            <label className="text-sm flex min-w-0 flex-col gap-2 sm:col-span-2">Dealer or product search<input type="search" className="overview-select min-h-11 w-full" value={filters.search} onChange={(e) => update('search', e.target.value)} placeholder="Name or code" /></label>
          </div>
          <div className="mt-6 grid grid-cols-1 gap-5 sm:grid-cols-2 sm:gap-6 lg:grid-cols-4">
            <label className="text-sm flex min-w-0 flex-col gap-2">Recorded conclusion<select className="overview-select min-h-11 w-full" value={filters.conclusion} onChange={(e) => update('conclusion', e.target.value)}><option value="">All conclusions</option>{[...new Set(query.data?.summary.breakdown.map((item) => item.conclusion) || [])].map((value) => <option key={value} value={value}>{label(value)}</option>)}</select></label>
            <label className="text-sm flex min-w-0 flex-col gap-2">Recorded confidence<select className="overview-select min-h-11 w-full" value={filters.confidence} onChange={(e) => update('confidence', e.target.value)}><option value="">All confidence levels</option>{['HIGH', 'MEDIUM', 'LOW'].map((value) => <option key={value} value={value}>{label(value)}</option>)}</select></label>
            <label className="text-sm flex min-w-0 flex-col gap-2">Recorded caveats<select className="overview-select min-h-11 w-full" value={filters.caveats} onChange={(e) => update('caveats', e.target.value)}><option value="all">All trails</option><option value="with">With recorded caveats</option><option value="without">No recorded caveats</option></select></label>
            <label className="text-sm flex min-w-0 flex-col gap-2">Caveat step<select className="overview-select min-h-11 w-full" value={filters.caveat_step} onChange={(e) => update('caveat_step', e.target.value)}><option value="">All steps</option>{(activeModule?.step_names || []).map((value) => <option key={value} value={value}>{label(value)}</option>)}</select></label>
          </div>
          <div className="mt-6 flex flex-col gap-5 border-t border-gray-200 pt-5 sm:flex-row sm:items-end sm:gap-6">
            <label className="text-sm flex min-w-0 flex-col gap-2 sm:w-52">Sort by<select className="overview-select min-h-11 w-full" value={filters.sort_by} onChange={(e) => update('sort_by', e.target.value)}>{['partner_name', 'partner_code', 'conclusion', 'confidence', 'generated_at'].map((value) => <option key={value} value={value}>{value === 'generated_at' ? 'Saved time' : label(value)}</option>)}</select></label>
            <label className="text-sm flex min-w-0 flex-col gap-2 sm:w-44">Sort direction<select className="overview-select min-h-11 w-full" value={filters.sort_direction} onChange={(e) => update('sort_direction', e.target.value)}><option value="asc">Ascending</option><option value="desc">Descending</option></select></label>
            <button className="overview-button min-h-11 self-start sm:ml-auto sm:self-end" onClick={() => setFilters({ ...DEFAULTS })}>Reset filters</button>
          </div>
          {registry.isError && <p role="alert" className="mt-3 text-sm">Module choices unavailable. <button className="underline" onClick={() => registry.refetch()}>Retry modules</button></p>}
        </section>
        {query.isError && <div role="alert" className="overview-notice">Saved evidence could not be read. This does not mean there are no saved trails. <button className="underline" onClick={() => query.refetch()}>Retry saved evidence</button></div>}
        {busy && <p role="status">Loading matching saved assessments…</p>}
        {data && <section className="overview-surface overflow-hidden">
          <div className="p-5 border-b border-gray-200"><h2 ref={heading} tabIndex={-1} className="font-semibold">Saved assessments</h2><p className="text-sm text-gray-600 mt-2">{data.pagination.total.toLocaleString()} matching trails</p></div>
          {data.items.length ? <AuditResults rows={data.items} rowRefs={rows} onSelect={(row) => { setSubject(row.partner_code); setTrailId({ id: row.trail_id, period }); }} busy={busy || running} /> : <div className="p-6" role="status"><h3 className="font-semibold">{data.summary.trail_count ? 'No matching saved trails' : 'No saved evidence for this module and period'}</h3><p className="text-sm text-gray-600 mt-2">{data.summary.trail_count ? 'Change or reset filters to see other saved assessments.' : 'This does not establish whether payments or exceptions exist, or whether an audit has ever run.'}</p>{data.summary.trail_count > 0 && <button className="overview-button mt-4" onClick={() => setFilters({ ...DEFAULTS })}>Reset filters</button>}</div>}
          <div className="p-4 border-t border-gray-200 flex flex-wrap justify-between items-center gap-3 text-sm">
            <span>{data.pagination.total ? filters.offset + 1 : 0}–{filters.offset + data.items.length} of {data.pagination.total.toLocaleString()}</span>
            <div className="flex flex-wrap items-center gap-3"><label>Rows per page <select className="overview-select" value={filters.limit} onChange={(e) => update('limit', Number(e.target.value))}>{[25, 50, 100].map((n) => <option key={n}>{n}</option>)}</select></label><button className="overview-button" disabled={busy || !filters.offset} onClick={() => setFilters((f) => ({ ...f, offset: Math.max(0, f.offset - f.limit) }))}>Previous</button><button className="overview-button" disabled={busy || !data.pagination.has_more} onClick={() => setFilters((f) => ({ ...f, offset: f.offset + f.limit }))}>Next</button></div>
          </div>
        </section>}
        {data && <p className="text-xs text-gray-500">Retrieved {new Date(data.retrieved_at).toLocaleString()}. Save/retrieval time is not source freshness.</p>}
        <details className="text-sm text-gray-600"><summary className="cursor-pointer">Run a new assessment</summary><p className="mt-3">Running {activeModule?.label || label(module)} for {formatPeriod(period)} replaces all saved trails for this module and period. Earlier versions are not retained. Refresh only reads saved evidence.</p><label className="flex gap-2 items-start mt-3"><input type="checkbox" checked={runAcknowledged} disabled={running} onChange={(e) => setRunAcknowledged(e.target.checked)} />I understand this replaces the saved module/period evidence.</label><button className="overview-button mt-3" disabled={running || !runAcknowledged} onClick={run}>{running ? 'Running…' : 'Run and replace saved trails'}</button></details>
      </>}
      {notice && <p role="status" className="overview-notice">{notice}</p>}
    </div>
  </main>;
}
