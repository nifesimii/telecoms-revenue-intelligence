import { formatNGN, formatPeriod } from '../../lib/format.js';
import { money, percent } from './paymentPresentation.js';

export default function PaymentCoverageCard({ data, loading, prior, comparison, comparisonError }) {
  if (loading && !data) return <div role="status" className="overview-surface p-6 h-48 animate-pulse bg-gray-100">Loading full-period figures…</div>;
  if (!data) return <p className="overview-notice">Payment totals unavailable. This is not a zero balance.</p>;
  const empty = data.record_count === 0;
  const comparable = !empty && prior?.record_count > 0 && !comparisonError;
  const coverage = data.total_commission_owed > 0 ? data.payment_coverage_pct : null;
  const coverageDelta = comparable && coverage != null && prior.total_commission_owed > 0 ? coverage - prior.payment_coverage_pct : null;
  const change = comparable ? data.total_amount_unpaid - prior.total_amount_unpaid : null;
  return <section className="overview-surface p-5 sm:p-6" aria-label="Full-period payment totals">
    <p className="text-sm text-gray-600">Outstanding to partners · {formatPeriod(data.period)}</p>
    <p className="overview-headline mt-2 font-semibold tabular-nums">{empty ? 'No source records' : money(data.total_amount_unpaid)}</p>
    <p className="text-sm text-gray-600 mt-3">Full-period totals · independent of account search and filters.</p>
    {comparison && <p className="text-sm mt-3">Compared with {formatPeriod(comparison)}: outstanding {change == null ? 'change unavailable' : `${change > 0 ? '+' : change < 0 ? '−' : ''}${formatNGN(Math.abs(change))}`} · coverage {coverageDelta == null ? 'change unavailable' : `${coverageDelta > 0 ? '+' : ''}${coverageDelta.toFixed(1)} percentage points`}.</p>}
    <dl className="grid grid-cols-1 sm:grid-cols-2 xl:grid-cols-4 gap-5 mt-6 pt-5 border-t border-gray-200 text-sm">
      {[['Commission owed', empty ? 'No records' : money(data.total_commission_owed)], ['Amount settled', empty ? 'No records' : money(data.total_amount_paid)], ['Settlement coverage', empty ? 'No records' : percent(coverage)], ['Disputed accounts', empty ? 'No records' : data.disputed_count?.toLocaleString() ?? 'Unavailable']].map(([label, value]) => <div key={label}><dt className="text-gray-600">{label}</dt><dd className="font-semibold tabular-nums mt-2">{value}</dd></div>)}
    </dl>
    {data.total_commission_owed === 0 && !empty && <p className="text-sm mt-4 text-gray-600">Coverage is undefined when recorded commission owed is zero.</p>}
  </section>;
}
