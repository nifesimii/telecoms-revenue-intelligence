import { formatNGN } from '../../lib/format.js';

export function SubscriptionMoney({ value }) {
  return value == null ? <span className="text-gray-500">Not available</span> : formatNGN(value);
}

export default function SubscriptionAmounts({ figures }) {
  return <div>
    <dl className="grid sm:grid-cols-3 gap-5 text-sm">
      {[
        ['subscription_commission_ngn', 'Recorded subscription commission'],
        ['subscription_settled_ngn', 'Subscription settled'],
        ['subscription_outstanding_ngn', 'Subscription outstanding'],
      ].map(([field, label]) => <div key={field}><dt className="text-gray-600">{label}</dt><dd className="font-semibold tabular-nums mt-2"><SubscriptionMoney value={figures[field]} /></dd></div>)}
    </dl>
    <p className="text-xs text-gray-500 mt-4">Commission is shown when supported by an upstream statement. The calculation rate and eligibility policy have not been supplied.</p>
    {!figures.subscription_commission_complete && <p className="text-xs text-gray-600 mt-2">Commission evidence covers {figures.subscription_commission_record_count ?? 0} of {figures.record_count.toLocaleString()} device records. Incomplete totals are not available.</p>}
  </div>;
}
