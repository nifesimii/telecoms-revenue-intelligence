import { PAYMENT_LABELS, subscriptionMoney, subscriptionTotal } from './subscriptionPresentation.js';

export function SubscriptionProvenance({ data }) {
  return <section className="overview-notice border-amber-200 bg-amber-50" aria-label="Subscription source and policy">
    <p className="font-semibold">{data.synthetic ? 'Synthetic demonstration · fictional subscription records' : 'Recorded subscription revenue only'}</p>
    <p className="mt-2 font-medium">{data.synthetic ? data.policy_label : 'Subscription commission is unavailable. Verified terms and recorded commission calculations are not supplied.'}</p>
    {data.synthetic && <details className="mt-3"><summary className="cursor-pointer underline underline-offset-4">Illustrative policy and date boundary</summary>
      <p className="mt-2">Original selling dealer attribution. A successful PAID purchase or renewal in the reporting month and at least NGN 5,000.00 qualifying monthly revenue per device are required. Eligible devices earn 5% of all qualifying revenue. Eligibility lasts 12 months from first activation; renewal never restarts it. Payment is due on the final day of the following month.</p>
      <p className="mt-2">{data.eligibility_boundary || 'Eligibility boundary evidence unavailable.'}</p>
      <p className="mt-2">Figures are supplied recorded simulations. Churn is context only, never an exclusion.</p>
    </details>}
    <p className="mt-3 text-xs text-gray-600 break-words">{data.source} · Evidence as of {data.evidence_as_of || 'unknown'}</p>
  </section>;
}

const FIELDS = [
  ['recorded_subscription_revenue_ngn', 'Recorded subscription revenue'],
  ['eligible_revenue_ngn', 'Eligible revenue'],
  ['simulated_commission_ngn', 'Simulated commission'],
  ['dealer_expectation_ngn', 'Dealer expectation'],
  ['variance_ngn', 'Variance · recorded minus expectation'],
  ['amount_paid_ngn', 'Supplied subscription payment'],
  ['outstanding_ngn', 'Outstanding subscription commission'],
];

export function SubscriptionFigures({ figures, totals = false, title = 'Account figures', available = true }) {
  return <section className="overview-surface p-5 sm:p-6" aria-label={title}>
    <h2 className="font-semibold">{title}</h2>
    {totals && <p className="text-sm text-gray-600 mt-1">{figures.account_count != null && `${figures.account_count.toLocaleString()} accounts · `}{figures.device_count.toLocaleString()} devices · {title === 'Reporting month totals' ? 'Entire reporting month' : 'Entire matching set'}</p>}
    <dl className="grid sm:grid-cols-2 lg:grid-cols-3 gap-x-6 gap-y-5 mt-5">
      {FIELDS.map(([field, label]) => <div key={field}><dt className="text-xs text-gray-600">{label}</dt>
        <dd className={`mt-1 tabular-nums break-words ${field === 'simulated_commission_ngn' ? 'text-lg font-semibold' : 'text-sm font-medium'}`}>
          {totals && !figures.device_count ? 'No source records' : !available && field !== 'recorded_subscription_revenue_ngn' ? 'Unavailable' : totals ? subscriptionTotal(figures, field) : subscriptionMoney(figures[field])}
        </dd></div>)}
      {!totals && <div><dt className="text-xs text-gray-600">Payment evidence</dt><dd className="text-sm font-medium mt-1">{PAYMENT_LABELS[figures.payment_status]}</dd></div>}
    </dl>
    {available && <p className="text-xs text-gray-600 mt-5">Unknown amounts prevent a complete total. Any known subtotal includes only {figures.account_count != null ? 'accounts' : 'devices'} with complete amounts; it is not the complete balance.{figures.unknown_commission_count > 0 && ` Commission is unknown for ${figures.unknown_commission_count} devices.`} Subscription payments are separate from activation settlements.</p>}
  </section>;
}
