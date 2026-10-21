import { formatNGN, formatPeriod } from '../../lib/format.js';
import { SubscriptionMoney } from './SubscriptionAmounts.jsx';
import { MoneyChange } from './CommissionSummary.jsx';
import PaginationControls from '../shared/PaginationControls.jsx';

export default function CommissionAccounts({ data, busy, filters, onFilter, onSelect, onPage, rowRefs, headingRef }) {
  const orsc = data.stream === 'orsc';
  const activeFilters = filters.search || filters.partner_class || filters.status !== 'all';
  return <section className="overview-surface min-w-0 overflow-hidden" aria-label="Dealer accounts" aria-busy={busy}>
    <div className="p-5 space-y-4">
      <div className="flex flex-wrap justify-between gap-2">
        <div><h2 ref={headingRef} tabIndex={-1} className="text-lg font-semibold">Dealer accounts</h2><p className="mt-1 text-sm text-gray-600">Select an account to inspect its {orsc ? 'subscription revenue, commission, settlement' : 'commission'} and evidence.</p></div>
        <p className="text-sm text-gray-600">{data.total.toLocaleString()} matching accounts</p>
      </div>
      <div className="flex flex-wrap gap-3">
        <label className="flex-1 min-w-0 basis-full sm:basis-56 text-xs text-gray-600">Search accounts
          <input type="search" className="overview-select mt-1 w-full" placeholder="Dealer name or account code" value={filters.search} onChange={(e) => onFilter('search', e.target.value)} />
        </label>
        <label className="text-xs text-gray-600 flex-1 min-w-0">Partner class
          <select className="overview-select mt-1 w-full" value={filters.partner_class} onChange={(e) => onFilter('partner_class', e.target.value)}>
            <option value="">All classes</option>{data.partner_classes.map((c) => <option key={c} value={c}>{c}</option>)}
          </select>
        </label>
        <label className="text-xs text-gray-600 flex-1 min-w-0">Records
          <select className="overview-select mt-1 w-full" value={filters.status} onChange={(e) => onFilter('status', e.target.value)}>
            <option value="all">All accounts</option><option value="with_zero">With zero {orsc ? 'revenue' : 'commission'}</option><option value="all_zero">Entirely zero {orsc ? 'revenue' : 'commission'}</option>
          </select>
        </label>
      </div>
      <div className="flex flex-wrap gap-3 items-center text-sm">
        <label className="flex flex-wrap gap-2 items-center text-gray-600">Sort by
          <select className="overview-select" value={filters.sort_by} onChange={(e) => onFilter('sort_by', e.target.value)}>
            <option value="amount_ngn">{orsc ? 'Revenue' : 'Commission'}</option>{orsc && <><option value="subscription_commission_ngn">Subscription commission</option><option value="subscription_settled_ngn">Subscription settled</option><option value="subscription_outstanding_ngn">Subscription outstanding</option></>}<option value="dealer_name">Dealer name</option><option value="delta_ngn">{orsc ? 'Revenue change' : 'Period change'}</option><option value="record_count">Record count</option><option value="zero_count">Zero records</option>
          </select>
        </label>
        <button className="overview-button" onClick={() => onFilter('direction', filters.direction === 'desc' ? 'asc' : 'desc')}>{filters.direction === 'desc' ? 'Descending ↓' : 'Ascending ↑'}</button>
        {activeFilters && <button className="underline" onClick={() => onFilter('reset')}>Clear filters</button>}
        <span className="text-xs text-gray-500 ml-auto" role="status">{busy ? 'Updating accounts…' : `Matching ${orsc ? 'revenue' : 'commission'}: ${formatNGN(data.filtered_summary.amount_ngn)}`}</span>
      </div>
      {orsc && <dl className="flex flex-wrap gap-x-6 gap-y-2 text-xs text-gray-600">{[['subscription_commission_ngn', 'Matching commission'], ['subscription_settled_ngn', 'Matching settled'], ['subscription_outstanding_ngn', 'Matching outstanding']].map(([field, label]) => <div key={field}><dt className="inline">{label}: </dt><dd className="inline font-medium"><SubscriptionMoney value={data.filtered_summary[field]} /></dd></div>)}</dl>}
    </div>
    <div className="relative overflow-x-auto" tabIndex={0} role="region" aria-label="Scrollable dealer account table">
      <table className="commission-table w-full text-sm text-left">
        <thead><tr>
          <th scope="col">Dealer / account</th>
          <th scope="col" className="text-right">{orsc ? 'Subscription revenue' : 'Recorded commission'}</th>
          {orsc ? <>
            <th scope="col" className="text-right">Recorded commission</th>
            <th scope="col" className="text-right">Amount settled</th>
            <th scope="col" className="text-right">Outstanding</th>
          </> : <>
            <th scope="col" className="text-right">Prior period</th>
            <th scope="col" className="text-right">Change</th>
          </>}
          <th scope="col" className="text-right">{orsc ? 'Device records' : 'Activations'}</th>
          {!orsc && <th scope="col" className="text-right">Zero records</th>}
          <th scope="col"><span className="sr-only">Investigation</span></th>
        </tr></thead>
        <tbody>{data.items.map((row) => <tr key={row.dealer_id}>
          <td><div className="font-medium">{row.dealer_name}</div><div className="text-xs text-gray-500 mt-1">{row.dealer_id} · {row.account_profile_class}</div></td>
          <td className="text-right tabular-nums whitespace-nowrap">
            <div className="font-semibold">{formatNGN(row.amount_ngn)}</div>
            {orsc && data.prior_period && <div className="text-xs text-gray-600 mt-1">
              {row.prior_amount_ngn == null ? 'No prior record' : <MoneyChange value={row.delta_ngn} />}<br />vs {formatPeriod(data.prior_period)}
            </div>}
          </td>
          {orsc ? ['subscription_commission_ngn', 'subscription_settled_ngn', 'subscription_outstanding_ngn'].map((field) => <td key={field} className="text-right tabular-nums whitespace-nowrap"><SubscriptionMoney value={row[field]} /></td>) : <>
            <td className="text-right tabular-nums whitespace-nowrap">{row.prior_amount_ngn == null ? <span className="text-gray-500">{data.prior_period ? 'No prior record' : '—'}</span> : formatNGN(row.prior_amount_ngn)}</td>
            <td className="text-right"><MoneyChange value={row.delta_ngn} />{row.delta_pct != null && <div className="text-xs text-gray-500 mt-1">{row.delta_pct > 0 ? '+' : ''}{row.delta_pct}%</div>}</td>
          </>}
          <td className="text-right tabular-nums">{row.record_count.toLocaleString()}
            {orsc && <div className="mt-2 text-xs whitespace-nowrap"><span className={row.zero_count > 0 ? 'text-amber-900 bg-amber-50 rounded px-2 py-1' : 'text-gray-500'}>{row.zero_count.toLocaleString()} zero revenue</span></div>}
          </td>
          {!orsc && <td className="text-right tabular-nums">{row.zero_count > 0 ? <span className="text-amber-900 bg-amber-50 rounded px-2 py-1">{row.zero_count.toLocaleString()}</span> : '0'}</td>}
          <td><button ref={(el) => { rowRefs.current[row.dealer_id] = el; }} aria-label={`View breakdown for account ${row.dealer_id}`} className="overview-button whitespace-nowrap" disabled={busy} onClick={() => onSelect(row)}>View breakdown →</button></td>
        </tr>)}</tbody>
      </table>
    </div>
    {!data.items.length && <div className="p-8 text-center" role="status"><h3 className="font-medium">{data.summary.account_count ? 'No matching accounts' : 'No source accounts for this period'}</h3><p className="mt-2 text-sm text-gray-600">{data.summary.account_count ? 'Try another name, code or filter. The monthly totals above remain unchanged.' : 'Choose another period or revenue stream. An empty source does not establish a zero balance.'}</p></div>}
    <div className="p-4 border-t border-gray-200 commission-pagination">
      <PaginationControls pagination={{ total: data.total, returned: data.items.length, offset: data.offset, limit: data.limit, has_more: data.offset + data.items.length < data.total }}
        pageSize={filters.limit} onPageSizeChange={(n) => onFilter('limit', n)} onOffsetChange={onPage} />
    </div>
  </section>;
}
