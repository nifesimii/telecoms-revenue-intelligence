import PaginationControls from '../shared/PaginationControls.jsx';
import { PAYMENT_LABELS, subscriptionMoney } from './subscriptionPresentation.js';
import { SubscriptionFigures } from './SubscriptionFigures.jsx';

export default function SubscriptionAccounts({ data, busy, filters, onFilter, onSelect, onPage, rowRefs, headingRef }) {
  const activeFilters = filters.search || filters.payment_status !== 'all';
  return <>
    <section className="overview-surface min-w-0 overflow-hidden" aria-label="Subscription dealer accounts" aria-busy={busy}>
      <div className="p-5 space-y-4">
        <div className="flex flex-wrap justify-between gap-3"><div><h2 ref={headingRef} tabIndex={-1} className="text-lg font-semibold">Subscription dealer accounts</h2>
          <p className="text-sm text-gray-600 mt-1">Follow each account from recorded revenue to supplied commission and payment evidence.</p></div><p className="text-sm text-gray-600">{data.total.toLocaleString()} matching accounts</p></div>
        <div className="flex flex-wrap gap-3">
          <label className="text-xs text-gray-600 flex-1 basis-full sm:basis-56 min-w-0">Search accounts<input type="search" maxLength={100} className="overview-select w-full mt-1" placeholder="Dealer name or account code" value={filters.search} onChange={(e) => onFilter('search', e.target.value)} /></label>
          <label className="text-xs text-gray-600 flex-1 min-w-0">Payment evidence<select className="overview-select w-full mt-1" value={filters.payment_status} onChange={(e) => onFilter('payment_status', e.target.value)}><option value="all">All payment states</option>{Object.entries(PAYMENT_LABELS).map(([key, label]) => <option key={key} value={key}>{label}</option>)}</select></label>
        </div>
        <div className="flex flex-wrap items-center gap-3">
          <label className="text-xs text-gray-600 min-w-0 flex-1 sm:flex-none">Sort by<select className="overview-select w-full mt-1" value={filters.sort_by} onChange={(e) => onFilter('sort_by', e.target.value)}>
            <option value="simulated_commission_ngn">Simulated commission</option><option value="recorded_subscription_revenue_ngn">Recorded revenue</option><option value="eligible_revenue_ngn">Eligible revenue</option><option value="dealer_expectation_ngn">Dealer expectation</option><option value="variance_ngn">Variance</option><option value="outstanding_ngn">Outstanding amount</option><option value="dealer_name">Dealer name</option><option value="device_count">Devices</option>
          </select></label>
          <button className="overview-button" onClick={() => onFilter('direction', filters.direction === 'desc' ? 'asc' : 'desc')}>{filters.direction === 'desc' ? 'Descending ↓' : 'Ascending ↑'}</button>
          {activeFilters && <button className="text-sm underline" onClick={() => onFilter('reset')}>Clear filters</button>}
          <span className="text-xs text-gray-500 ml-auto" role="status">{busy ? 'Updating accounts…' : 'Figures reflect server-filtered records'}</span>
        </div>
      </div>
      <div className="overflow-x-auto" role="region" tabIndex={0} aria-label="Scrollable subscription dealer table">
        <table className="commission-table w-full text-sm text-left">
          <caption className="sr-only">Dealer subscription amounts; variance is recorded simulated commission minus dealer expectation</caption>
          <thead><tr><th scope="col">Dealer / account</th><th scope="col" className="text-right">Recorded / eligible revenue</th><th scope="col" className="text-right">Simulated commission</th><th scope="col" className="text-right">Dealer expectation</th><th scope="col" className="text-right">Variance</th><th scope="col">Payment evidence</th><th scope="col">Investigation</th></tr></thead>
          <tbody>{data.items.map((row) => <tr key={row.dealer_id}>
            <td><p className="font-medium">{row.dealer_name}</p><p className="mt-1 text-xs text-gray-500">{row.dealer_id} · {row.account_profile_class || 'Class not recorded'}</p><p className="mt-1 text-xs text-gray-500">{row.device_count} devices</p></td>
            <td className="text-right tabular-nums whitespace-nowrap"><p>{subscriptionMoney(row.recorded_subscription_revenue_ngn)}</p><p className="text-xs text-gray-600 mt-1">Eligible: {data.commission_available ? subscriptionMoney(row.eligible_revenue_ngn) : 'Unavailable'}</p></td>
            <td className="text-right tabular-nums whitespace-nowrap"><p className="font-semibold">{data.commission_available ? subscriptionMoney(row.simulated_commission_ngn) : 'Unavailable'}</p>{data.commission_available && row.unknown_commission_count > 0 && <p className="text-xs text-gray-600 mt-1">{row.unknown_commission_count} devices unknown</p>}</td>
            <td className="text-right tabular-nums whitespace-nowrap">{data.commission_available ? subscriptionMoney(row.dealer_expectation_ngn) : 'Unavailable'}</td>
            <td className="text-right tabular-nums whitespace-nowrap">{data.commission_available ? subscriptionMoney(row.variance_ngn) : 'Unavailable'}</td>
            <td><p className={`font-medium ${row.payment_status === 'overdue' ? 'text-amber-900' : ''}`}>{PAYMENT_LABELS[row.payment_status]}</p><p className="text-xs text-gray-600 whitespace-nowrap mt-1">Paid: {subscriptionMoney(row.amount_paid_ngn)}</p><p className="text-xs text-gray-600 whitespace-nowrap mt-1">Outstanding: {subscriptionMoney(row.outstanding_ngn)}</p></td>
            <td><button ref={(el) => { rowRefs.current[row.dealer_id] = el; }} className="overview-button whitespace-nowrap" disabled={busy} aria-label={`View subscription evidence for account ${row.dealer_id}`} onClick={() => onSelect(row)}>View evidence →</button></td>
          </tr>)}</tbody>
        </table>
      </div>
      {!data.items.length && <div role="status" className="p-6"><h3 className="font-semibold">{data.summary.account_count ? 'No matching subscription accounts' : 'No subscription source records for this month'}</h3><p className="text-sm text-gray-600 mt-2">{data.summary.account_count ? 'Try another dealer name or payment filter.' : 'Choose another reporting month. Missing records do not establish a zero balance.'}</p></div>}
      <fieldset disabled={busy} className="p-4 border-t border-gray-200 commission-pagination"><legend className="sr-only">Subscription account pages</legend><PaginationControls pagination={{ total: data.total, returned: data.items.length, limit: data.limit, offset: data.offset, has_more: data.offset + data.items.length < data.total }} pageSize={filters.limit} onPageSizeChange={(n) => onFilter('limit', n)} onOffsetChange={onPage} /></fieldset>
    </section>
    {activeFilters && <SubscriptionFigures figures={data.filtered_summary} totals title="Matching account totals" available={data.commission_available} />}
  </>;
}
