import { useEffect, useRef } from 'react';
import { useQuery } from '@tanstack/react-query';
import { getAuditEvidence } from '../../api/client.js';
import { label, measureLabel, measureValue, savedTime, qualifications, detailText, downloadEvidence } from './auditPresentation.js';

export default function AuditEvidence({ subject, trailId, module, period, onBack }) {
  const heading = useRef(null);
  useEffect(() => { heading.current?.focus(); }, [subject, module, period]);
  const query = useQuery({ queryKey: ['audit-evidence', module, period, subject, trailId], queryFn: ({ signal }) => getAuditEvidence(subject, module, period, signal, trailId), retry: false });
  const data = query.data;
  const missing = query.error?.response?.status === 404;
  const matches = data?.partner_code === subject && data?.module === module && data?.mon_period === period && (!trailId || String(data?.trail_id) === String(trailId));
  return <section className="overview-surface p-5 sm:p-6" aria-busy={query.isFetching}>
    <div className="flex flex-wrap justify-between gap-3">
      <button className="overview-button" onClick={onBack}>Back to results</button>
      <button className="overview-button" disabled={query.isFetching} onClick={() => query.refetch()}>Refresh saved evidence</button>
    </div>
    <h2 ref={heading} tabIndex={-1} className="text-xl font-semibold mt-5 break-words">Saved evidence · {subject}</h2>
    {query.isFetching && <p role="status" className="mt-4">Loading saved evidence…</p>}
    {query.isError && <div role={missing ? 'status' : 'alert'} className="overview-notice mt-4">
      <p>{missing ? 'No saved evidence for this exact subject, module and period.' : 'Saved evidence could not be read. No result can be established from this failed read.'}</p>
      <button className="overview-button mt-3" onClick={() => query.refetch()}>Retry evidence</button>
    </div>}
    {data && !query.isError && !matches && <p role="alert">The saved evidence does not match this subject, module and period. Refresh to retry.</p>}
    {matches && !query.isError && <>
      <div className="mt-5 border-b border-gray-200 pb-5">
        <p className="text-sm text-gray-600 break-words">{data.dealer_name} {data.product_name ? `· ${data.product_name} (${data.product_code})` : ''}</p>
        <h3 className="text-lg font-semibold mt-2">Recorded conclusion: {label(data.conclusion)}</h3>
        <p className="text-sm text-gray-600 mt-2">Recorded confidence: {label(data.confidence)} · {data.caveat_steps.length ? `${data.caveat_steps.length} recorded caveat steps` : 'No recorded caveats'}</p>
        {qualifications(data).map((note, i) => <p key={i} className="mt-3 text-sm text-amber-900">{note}</p>)}
      </div>
      <h3 className="font-semibold mt-5">Supporting measures</h3>
      <dl className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-4 mt-3">{Object.entries(data.measures || {}).map(([key, value]) => <div key={key}><dt className="text-sm text-gray-600">{measureLabel(key)}</dt><dd className="font-semibold tabular-nums mt-1">{measureValue(key, value)}</dd></div>)}</dl>
      <h3 className="font-semibold mt-6">Checks and explanations</h3>
      <ol className="mt-4 space-y-5">{(data.steps || []).map((step) => <li key={step.step} className="border-l-2 border-gray-200 pl-4">
        <h4 className="font-semibold">{step.step}. {label(step.name)}</h4>
        <p className="text-xs text-gray-500 mt-1">Recorded check: {step.passed ? 'passed' : 'did not pass'}</p>
        <p className="text-sm text-gray-600 mt-2">{step.checked}</p>
        <p className="text-sm mt-2">{step.presentation_result || step.result}</p>
        {step.presentation_qualification && <div className="text-sm text-amber-900 mt-2"><p>{step.presentation_qualification}</p><details className="mt-2"><summary className="cursor-pointer">Original recorded wording</summary><p>{step.result}</p></details></div>}
        {step.caveat && <p className="text-sm text-amber-900 mt-2">Recorded caveat: {step.caveat}</p>}
        {step.detail?.note && <p className="text-sm text-amber-900 mt-2">Recorded limitation: {step.detail.note}</p>}
        {step.detail && <details className="text-sm mt-2"><summary className="cursor-pointer">Supporting detail for {label(step.name)}</summary><pre className="whitespace-pre-wrap break-words font-sans mt-2 text-gray-600">{detailText(step.detail)}</pre></details>}
      </li>)}</ol>
      <div className="mt-6 pt-5 border-t border-gray-200 text-sm text-gray-600 break-words">
        <h3 className="font-semibold text-gray-900">Provenance</h3>
        <p className="mt-2">Reporting period: {data.mon_period} · Saved: {savedTime(data.generated_at)}</p>
        <p className="mt-2">Saved source: {data.payment_source || 'Unavailable'} · Pipeline version: {data.pipeline_version || 'Unavailable'}</p>
        <p className="mt-2">Run reference: {data.run_id || 'Unavailable'} · Trail: {data.trail_id || 'Unavailable'}</p>
        <p className="mt-2">Save and retrieval times do not establish source freshness. Earlier trail versions are not retained.</p>
        <button className="overview-button mt-4" onClick={() => downloadEvidence(data)} disabled={query.isFetching}>Download evidence report</button>
      </div>
    </>}
  </section>;
}
