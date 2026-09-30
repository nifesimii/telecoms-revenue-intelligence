import useQuery from '../../hooks/useWorkspaceQuery.js';

import { getAuditModules, getAuditBreakdown } from '../../api/client.js';
import { openEvidence } from './InvestigationQueue.jsx';

function AuditCoverage({ module, period, onNavigate }) {
  const query = useQuery({ queryKey: ['audit-breakdown', module.name, period],
    queryFn: () => getAuditBreakdown(module.name, period) });
  const rows = query.data || [];
  const total = rows.reduce((sum, row) => sum + row.n, 0);
  const insufficient = rows.filter((r) => r.conclusion === 'INSUFFICIENT_DATA').reduce((sum, r) => sum + r.n, 0);
  return <li className="py-3 border-b border-gray-100 last:border-0">
    <button className="text-sm font-medium text-left hover:underline" onClick={() => onNavigate('audit', { module: module.name, search: '' })}>{module.label} →</button>
    <p className="mt-1 text-xs text-gray-600">
      {query.isPending ? 'Loading audit coverage…' : query.isError ? 'Audit source unavailable' : total ? `${total.toLocaleString()} persisted trails` : 'No saved trails for this period'}
    </p>
    {query.isError && <button className="text-xs underline mt-1" onClick={() => query.refetch()}>Retry audit coverage</button>}
    {insufficient > 0 && <p className="text-xs text-amber-800 mt-1">{insufficient.toLocaleString()} with insufficient evidence</p>}
  </li>;
}

export default function OverviewCoverage({ period, data, onNavigate }) {
  const registry = useQuery({ queryKey: ['audit-modules'], queryFn: getAuditModules });
  const missing = data.modules.reduce((n, m) => n + m.missing_invoice_count, 0);
  return <aside className="space-y-5" aria-label="Assurance and evidence coverage">
    {missing > 0 && <section className="rounded-lg border border-amber-200 bg-amber-50 p-5">
      <h2 className="font-semibold text-sm text-amber-900">Evidence gap</h2>
      <p className="text-2xl font-semibold mt-2 tabular-nums">{missing.toLocaleString()}</p>
      <p className="text-sm text-amber-900 mt-1">Dealer-product combinations have no invoice record in the available window.</p>
      <p className="text-xs text-amber-900 mt-3">Missing evidence is not a confirmed inventory discrepancy.</p>
      <button className="text-sm underline mt-4" onClick={() => onNavigate('inventory', { search: '' })}>Inspect inventory coverage →</button>
    </section>}
    <section className="overview-surface p-5">
      <h2 className="font-semibold">Assurance checks</h2>
      <p className="text-xs text-gray-500 mt-1">Full-period finding counts</p>
      <ul className="mt-3 divide-y divide-gray-100">{data.modules.map((m) => <li key={m.module} className="py-3">
        <div className="flex justify-between items-center gap-2">
          <button className="text-sm capitalize font-medium hover:underline" onClick={() => openEvidence(onNavigate, m.module)}>{m.module} →</button>
          <span className="text-sm tabular-nums font-semibold">{m.status === 'UNAVAILABLE' ? '—' : m.finding_count.toLocaleString()}</span>
        </div>
        <p className="text-xs mt-1 text-gray-500">{m.status === 'UNAVAILABLE' ? 'Source unavailable' : m.status === 'NOT_IMPLEMENTED' ? 'Not yet available' : m.status === 'NO_DATA' ? 'No source records' : m.finding_count ? `${m.high_count} high · ${m.medium_count} medium · ${m.low_count} low` : 'No findings from these checks'}</p>
      </li>)}</ul>
    </section>
    <section className="overview-surface p-5">
      <h2 className="font-semibold">Audit evidence</h2>
      <p className="text-xs text-gray-500 mt-1">Saved verification chains; opening a trail does not run a new audit.</p>
      {registry.isPending ? <p role="status" className="text-sm mt-3">Loading modules…</p> : registry.isError ? <p role="alert" className="text-sm mt-3">Audit registry unavailable. <button className="underline" onClick={() => registry.refetch()}>Retry</button></p> : <ul className="mt-2">{registry.data.map((m) => <AuditCoverage key={m.name} module={m} period={period} onNavigate={onNavigate} />)}</ul>}
    </section>
  </aside>;
}
