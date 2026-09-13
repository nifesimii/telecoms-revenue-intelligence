import { formatNGN, formatNGNDelta, formatPeriod } from '../../lib/format.js';

export default function FinancialPosition({ payment, prior, comparison, comparisons, setComparison, onNavigate }) {
  if (!payment || payment.record_count === 0) return <section className="overview-surface p-6" aria-label="Financial position">
    <h2 className="text-lg font-semibold">Financial position unavailable</h2>
    <p className="mt-2 text-sm text-gray-600">{payment ? 'No payment records are available for this period.' : 'The payment source could not be reached. Refresh to retry.'} Missing data is not a zero balance.</p>
  </section>;
  const previous = prior.data?.record_count > 0 && prior.data.data_source === payment.data_source ? prior.data : null;
  const delta = previous ? payment.total_amount_unpaid - previous.total_amount_unpaid : null;
  const coverageDelta = previous ? payment.payment_coverage_pct - previous.payment_coverage_pct : null;
  const exceptions = payment.disputed_count + payment.partially_paid_count + payment.pending_count;
  return <section className="overview-surface overflow-hidden" aria-labelledby="position-title">
    <div className="px-5 py-4 sm:px-6 border-b border-gray-200 flex flex-wrap justify-between gap-3 items-center">
      <h2 id="position-title" className="font-semibold">Financial position</h2>
      <span className="text-xs font-medium bg-amber-50 border border-amber-200 rounded px-2 py-1">
        {payment.data_source === 'APDP' ? 'Payment source · APDP' : 'Demo · Synthetic payments'}
      </span>
    </div>
    <div className="grid grid-cols-1 lg:grid-cols-[1.1fr_1fr]">
      <div className="p-5 sm:p-6 bg-yellow-50/50 lg:border-r border-gray-200">
        <p className="text-sm text-gray-600">Outstanding to partners</p>
        <p className="overview-headline mt-2 font-semibold tracking-tight tabular-nums">{formatNGN(payment.total_amount_unpaid)}</p>
        <p className="mt-3 text-sm text-gray-600">Recorded commission less settlement, across {payment.record_count.toLocaleString()} dealer accounts.</p>
        <div className="mt-5 flex flex-wrap gap-3 items-center">
          <button className="overview-button overview-primary" onClick={() => onNavigate('payment', { tab: 'exceptions', search: '' })}>Review {exceptions.toLocaleString()} payment exceptions →</button>
          <span className="text-sm text-gray-600">{payment.disputed_count} disputed</span>
        </div>
      </div>
      <div className="p-5 sm:p-6">
        <dl className="grid sm:grid-cols-2 gap-5">
          <div><dt className="text-sm text-gray-500">Commission owed</dt><dd className="overview-amount mt-1 font-semibold tabular-nums">{formatNGN(payment.total_commission_owed)}</dd></div>
          <div><dt className="text-sm text-gray-500">Amount settled</dt><dd className="overview-amount mt-1 font-semibold tabular-nums">{formatNGN(payment.total_amount_paid)}</dd></div>
        </dl>
        <div className="mt-6 flex justify-between gap-2 text-sm"><span className="text-gray-600">Settlement coverage</span><span className="font-semibold">{payment.payment_coverage_pct.toFixed(1)}%</span></div>
        <progress className="overview-progress mt-2 w-full" max="100" value={Math.min(100, Math.max(0, payment.payment_coverage_pct))} aria-label="Settlement coverage" />
        <p className="mt-3 text-xs text-gray-500">Payment-source commission; ORSC subscription revenue is separate. Outstanding is not automatically a confirmed underpayment.</p>
      </div>
    </div>
    <div className="px-5 py-4 sm:px-6 border-t border-gray-200 flex flex-wrap gap-x-6 gap-y-3 items-center text-sm">
      <label className="flex items-center gap-2 text-gray-600">Compare with
        <select className="overview-select" value={comparison} onChange={(e) => setComparison(e.target.value)}>
          <option value="">No comparison</option>
          {comparisons.map((p) => <option key={p} value={p}>{formatPeriod(p)}</option>)}
        </select>
      </label>
      {comparison && prior.isPending ? <span role="status">Loading comparison…</span> : comparison && prior.isError ? <span className="text-amber-800">Comparison unavailable <button className="underline" onClick={() => prior.refetch()}>Retry</button></span> : previous ? <>
        <span><span className="text-gray-500">Outstanding </span><strong className={delta > 0 ? 'text-red-700' : 'text-gray-800'}>{formatNGNDelta(delta)}</strong></span>
        <span><span className="text-gray-500">Coverage </span><strong>{coverageDelta > 0 ? '+' : ''}{coverageDelta.toFixed(1)} pp</strong></span>
        <span><span className="text-gray-500">Disputed </span><strong>{payment.disputed_count - previous.disputed_count > 0 ? '+' : ''}{payment.disputed_count - previous.disputed_count}</strong></span>
      </> : <span className="text-gray-500">{comparisons.length ? 'No comparable payment data selected.' : 'No earlier period available.'}</span>}
    </div>
  </section>;
}
