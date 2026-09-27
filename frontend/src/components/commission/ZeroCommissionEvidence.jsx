import { useState } from 'react';
import { useQuery } from '@tanstack/react-query';
import { getCommissionZeroRecords, getAuditTrail } from '../../api/client.js';
import PaginationControls from '../shared/PaginationControls.jsx';

export default function ZeroCommissionEvidence({ dealerId, period, onNavigate }) {
  const [offset, setOffset] = useState(0);
  const [limit, setLimit] = useState(25);
  const [showAudit, setShowAudit] = useState(false);
  const query = useQuery({ queryKey: ['commission-zero-records', dealerId, period, offset, limit],
    queryFn: ({ signal }) => getCommissionZeroRecords(dealerId, { mon_period: period, offset, limit }, signal) });
  const data = query.data;
  return <section className="overview-surface overflow-hidden" aria-label="Zero-commission evidence">
    <div className="p-5"><h2 className="font-semibold">Zero-commission source records</h2>
      <p className="text-sm text-gray-600 mt-2">These are raw records, not confirmed root-cause classifications. Missing dates remain unknown; a zero rate alone does not establish an error.</p>
      <p className="text-xs text-gray-500 mt-2">Documented causes: USP snapshot miss, outside the 6-month eligibility window, NULL account profile class, and the known Hynex/Hynex_1 split. Apply only where evidence supports them.</p>
    </div>
    {query.isPending && <p role="status" className="p-5">Loading account evidence…</p>}
    {query.isError && <p role="alert" className="p-5 text-red-800">Source records unavailable. <button className="underline" onClick={() => query.refetch()}>Retry</button></p>}
    {data && <>
      <div className="overflow-x-auto" tabIndex={0} role="region" aria-label="Scrollable zero-commission records"><table className="commission-table w-full text-sm text-left">
        <thead><tr><th>Device / IMEI</th><th>Product</th><th>Invoice date</th><th>First activation</th></tr></thead>
        <tbody>{data.items.map((r, i) => <tr key={`${r.imei}-${offset + i}`}><td className="font-mono text-xs">{r.imei || 'Not recorded'}</td><td>{r.product_name || 'Not recorded'}<div className="text-xs text-gray-500">{r.product_code || 'No product code'}</div></td><td className="whitespace-nowrap">{r.invoice_date || 'Not recorded'}</td><td className="whitespace-nowrap">{r.first_activation_date || 'Not recorded'}</td></tr>)}</tbody>
      </table></div>
      {!data.total && <p className="p-5 text-sm" role="status">No zero-commission records for this account and period.</p>}
      <div className="p-4 commission-pagination"><PaginationControls pagination={{ total: data.total, returned: data.items.length, offset, limit, has_more: offset + data.items.length < data.total }} pageSize={limit} onPageSizeChange={(n) => { setLimit(n); setOffset(0); }} onOffsetChange={setOffset} /></div>
    </>}
    <div className="p-5 border-t border-gray-200">
      <button className="overview-button" aria-expanded={showAudit} onClick={() => setShowAudit(!showAudit)}>{showAudit ? 'Hide saved verification' : 'View saved verification'}</button>
      {showAudit && <SavedVerification dealerId={dealerId} period={period} onNavigate={onNavigate} />}
    </div>
  </section>;
}

function SavedVerification({ dealerId, period, onNavigate }) {
  const query = useQuery({ queryKey: ['commission-saved-audit', dealerId, period], retry: false,
    queryFn: ({ signal }) => getAuditTrail(dealerId, 'zero_commission', period, signal) });
  if (query.isPending) return <p className="mt-3 text-sm" role="status">Loading saved verification…</p>;
  if (query.isError) return <p className="mt-3 text-sm" role="status">{query.error?.response?.status === 404 ? 'No saved verification for this account and period. Opening evidence does not run an audit.' : 'Saved verification unavailable.'}<button className="ml-2 underline" onClick={() => query.refetch()}>Retry</button></p>;
  const data = query.data;
  return <div className="mt-4 text-sm"><h3 className="font-medium">Saved conclusion: {data.conclusion?.replaceAll('_', ' ').toLowerCase()}</h3>
    <p className="mt-1 font-medium">Confidence: {data.confidence || 'Not recorded'}</p>
    <p className="text-xs text-gray-500 mt-2">{data.generated_at ? new Date(data.generated_at).toLocaleString() : 'Date not recorded'} · Payment source: {data.payment_source || 'not recorded'}. Saved evidence may predate the current figures.</p>
    <ol className="mt-4 space-y-3">{(data.steps || []).map((step) => <li key={step.step}><p>{step.step}. {step.result}</p>{step.caveat && <p className="text-amber-900 mt-1">Caveat: {step.caveat}</p>}</li>)}</ol>
    <button className="underline mt-4" onClick={() => onNavigate('audit', { module: 'zero_commission', subject: dealerId, search: dealerId })}>Open this audit in workspace →</button>
  </div>;
}
