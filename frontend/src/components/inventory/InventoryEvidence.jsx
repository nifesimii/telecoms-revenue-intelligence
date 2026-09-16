import { useQuery } from '@tanstack/react-query';
import { getAuditTrail } from '../../api/client.js';
import { formatPeriod } from '../../lib/format.js';

const CONCLUSIONS = {
  RECONCILED: 'Saved verification: reconciled',
  INSUFFICIENT_DATA: 'Verification inconclusive',
  EXCESS_ACTIVATION: 'Saved verification: excess activation',
};
const STEPS = {
  prior_period_stock: 'Prior-period stock carryover',
  product_alias_reconciliation: 'Product-code aliases',
  upstream_completeness: 'Invoice coverage',
};

export default function InventoryEvidence({ subject, period }) {
  const query = useQuery({
    queryKey: ['inventory-evidence', period, subject],
    queryFn: ({ signal }) => getAuditTrail(subject, 'inventory_mismatch', period, signal),
    retry: false,
  });
  const data = query.data;
  const missing = query.error?.response?.status === 404;
  const matches = data?.partner_code === subject && data?.mon_period === period;
  return <section className="overview-surface p-5 sm:p-6" aria-labelledby="inventory-evidence-heading" aria-busy={query.isFetching}>
    <div className="flex flex-wrap justify-between items-center gap-3">
      <h3 id="inventory-evidence-heading" className="font-semibold">Saved Inventory verification</h3>
      <button className="overview-button" onClick={() => query.refetch()} disabled={query.isFetching}>Refresh evidence</button>
    </div>
    <p className="text-sm text-gray-600 mt-2">Dealer-product {subject} · {formatPeriod(period)}. Reads an existing trail; no new verification is run.</p>
    {query.isFetching && <p role="status" className="mt-4 text-sm">{data ? 'Refreshing saved evidence…' : 'Loading saved evidence…'}</p>}
    {query.isError && <p role={missing ? 'status' : 'alert'} className="mt-4 text-sm text-amber-900">
      {missing ? 'No saved verification available for this dealer-product and period.' : 'Saved evidence could not be loaded. No verification result can be established.'}
      {!missing && <button className="ml-2 underline" onClick={() => query.refetch()}>Retry evidence</button>}
    </p>}
    {data && !query.isError && !matches && <p role="alert" className="mt-4 text-sm text-red-800">The saved evidence does not match this dealer-product and period. Refresh evidence to retry.</p>}
    {matches && !query.isError && <>
      <p className="mt-5 text-lg font-semibold">{CONCLUSIONS[data.conclusion] || 'Saved conclusion unavailable'}</p>
      <p className="text-sm text-gray-600 mt-2">Recorded confidence: {data.confidence || 'Unavailable'} · {data.payment_source === 'ifs' ? 'IFS invoice evidence' : 'Source not established'}{data.generated_at ? ` · Saved ${new Date(data.generated_at).toLocaleString()}` : ' · Save time unavailable'}</p>
      <p className="text-sm text-gray-600 mt-2">This saved assessment may precede the current comparison. It does not establish commission on excess units.</p>
      <ol className="mt-5 space-y-5">{(data.steps || []).map((step) => <li key={step.step} className="border-l-2 border-gray-200 pl-4">
        <h4 className="text-sm font-semibold">{step.step}. {STEPS[step.name] || step.name?.replaceAll('_', ' ')}</h4>
        <p className="mt-1 text-sm text-gray-600">{step.checked}</p>
        <p className="mt-2 text-sm">{step.result}</p>
        {step.caveat && <p className="mt-2 text-sm text-amber-900">Caveat: {step.caveat}</p>}
      </li>)}</ol>
    </>}
    <aside className="mt-5 border-t border-gray-200 pt-4 text-sm text-gray-600">
      <h4 className="font-semibold text-gray-800">Limits of the saved checks</h4>
      <p className="mt-2">Carryover and alias checks can miss products with purchases but no activations. The current coverage check establishes that invoice data exists, not that the reporting period is complete. Read these limitations even when recorded confidence is HIGH.</p>
    </aside>
  </section>;
}
