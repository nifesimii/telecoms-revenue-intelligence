import { useQuery } from '@tanstack/react-query';
import { getAuditTrail, getDealerVerification, getDealerStatement } from '../../api/client.js';
import { formatNGN, formatPeriod } from '../../lib/format.js';

export const AUDIT_MODULE = { commission: 'zero_commission', inventory: 'inventory_mismatch' };

export default function DealerEvidence({ finding, period, onClose, onNavigate }) {
  const subject = finding.product_code ? `${finding.dealer_id}:${finding.product_code}` : finding.dealer_id;
  const audit = AUDIT_MODULE[finding.module];
  const query = useQuery({ queryKey: ['overview-evidence', period, finding.module, subject],
    queryFn: ({ signal }) => audit ? getAuditTrail(subject, audit, period, signal)
      : finding.module === 'payment' ? getDealerStatement(finding.dealer_id, period)
        : getDealerVerification(finding.dealer_id, period, signal),
    retry: false });
  const data = query.data;
  const source = String(data?.payment_source || '').toLowerCase();
  const sourceLabel = { apdp: 'APDP payments', simulated: 'Synthetic payments', ifs: 'IFS invoice evidence' }[source]
    || (source ? `Source: ${data.payment_source}` : 'Source not recorded');
  const missing = query.error?.response?.status === 404;
  return <section className="mt-4 rounded-md border border-gray-200 bg-gray-50 p-4" aria-label={`${finding.module} evidence for dealer ${finding.dealer_id}`}>
    <div className="flex justify-between items-start gap-3">
      <div><h4 className="text-sm font-semibold capitalize">{finding.module} evidence · {formatPeriod(period)}</h4>
        <p className="text-xs text-gray-500 mt-1">Dealer {finding.dealer_id}{finding.product_code ? ` · Product ${finding.product_code}` : ''}</p></div>
      <button className="text-sm underline" onClick={onClose}>Close evidence</button>
    </div>
    {query.isPending && <p role="status" className="mt-3 text-sm">Loading dealer evidence…</p>}
    {query.isError && <p role="status" className="mt-3 text-sm text-amber-900">
      {missing ? 'No saved evidence is available for this subject and period.' : 'Evidence source unavailable. This is not a verification result.'}
      {!missing && <button className="ml-2 underline" onClick={() => query.refetch()}>Retry</button>}
    </p>}
    {data && audit && <>
      <p className="mt-3 text-sm font-medium">Saved conclusion: {data.conclusion?.replaceAll('_', ' ').toLowerCase()}</p>
      <p className="mt-1 text-xs text-gray-500">Persisted audit evidence{data.generated_at ? ` · ${new Date(data.generated_at).toLocaleString()}` : ''} · {sourceLabel}. This may precede the current assessment.</p>
      <ol className="mt-3 space-y-3">{(Array.isArray(data.steps) ? data.steps : []).map((step) => <li key={step.step}>
        <p className="text-sm font-medium">{step.step}. {step.name?.replaceAll('_', ' ')}</p>
        <p className="text-sm text-gray-600 mt-1">{step.result}</p>
        {step.caveat && <p className="text-sm text-amber-900 mt-1">Caveat: {step.caveat}</p>}
      </li>)}</ol>
    </>}
    {data && finding.module === 'activation' && <>
      <dl className="grid sm:grid-cols-3 gap-3 mt-3 text-sm">
        <div><dt className="text-gray-500">Activations</dt><dd className="font-semibold">{data.activation_count}</dd></div>
        <div><dt className="text-gray-500">Qualified</dt><dd className="font-semibold">{data.qualified_activation_count}</dd></div>
        <div><dt className="text-gray-500">Zero commission</dt><dd className="font-semibold">{data.zero_commission_count}</dd></div>
      </dl>
      <p className="text-sm text-gray-600 mt-3">{finding.description}</p>
      <p className="text-xs text-gray-500 mt-2">Activation records provide the count and qualification context; no eligibility audit conclusion is inferred.</p>
    </>}
    {data && finding.module === 'payment' && <>
      <dl className="grid sm:grid-cols-2 gap-3 mt-3 text-sm">
        <div><dt className="text-gray-500">Activation entitlement</dt><dd className="font-semibold">{formatNGN(data.position.expected_ngn)}</dd></div>
        <div><dt className="text-gray-500">Amount settled</dt><dd className="font-semibold">{formatNGN(data.position.paid_ngn)}</dd></div>
      </dl>
      <p className="text-sm text-gray-600 mt-3">Statement position: {data.position.headline?.replaceAll('_', ' ').toLowerCase()} · {data.payment.data_source === 'apdp' ? 'APDP' : 'Synthetic payments'}</p>
      <p className="text-xs text-gray-500 mt-2">Entitlement is from activation records; the queue uses the payment source’s recorded outstanding balance.</p>
    </>}
    {audit && <button className="text-sm underline mt-4" onClick={() => onNavigate('audit', { module: audit, search: subject, subject })}>Open this audit in workspace →</button>}
    {!audit && <button className="text-sm underline mt-4" onClick={() => onNavigate(finding.module, { tab: 'exceptions', search: finding.dealer_id })}>Open dealer in {finding.module} workspace →</button>}
  </section>;
}
