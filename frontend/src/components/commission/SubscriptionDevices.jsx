import { useEffect, useState } from 'react';
import { keepPreviousData, useQuery } from '@tanstack/react-query';
import { getSubscriptionDevices } from '../../api/client.js';
import useDebouncedValue from '../../hooks/useDebouncedValue.js';
import { formatPeriod } from '../../lib/format.js';
import PaginationControls from '../shared/PaginationControls.jsx';
import { POLICY_LABEL, PAYMENT_LABELS, REASON_LABELS, subscriptionMoney, churnLabel } from './subscriptionPresentation.js';

export default function SubscriptionDevices({ dealerId, period, reason, onReasonChange }) {
  const [filters, setFilters] = useState({ search: '', sort_by: 'imei', direction: 'asc', limit: 25, offset: 0 });
  const search = useDebouncedValue(filters.search);
  useEffect(() => { setFilters((current) => ({ ...current, offset: 0 })); }, [reason]);
  const params = { ...filters, search, reason, mon_period: period };
  const query = useQuery({ queryKey: ['subscription-devices', dealerId, params], queryFn: ({ signal }) => getSubscriptionDevices(dealerId, params, signal), placeholderData: keepPreviousData });
  const data = query.data;
  const busy = query.isFetching || search !== filters.search;
  useEffect(() => {
    if (data && !query.isPlaceholderData && filters.offset > 0 && filters.offset >= data.total) setFilters((current) => ({ ...current, offset: 0 }));
  }, [data, query.isPlaceholderData, filters.offset]);
  function filter(key, value) { setFilters((current) => ({ ...current, [key]: value, offset: 0 })); }
  return <section className="overview-surface min-w-0 overflow-hidden" aria-label="Device subscription evidence" aria-busy={busy}>
    <div className="p-5 border-b border-gray-200">
      <h3 className="font-semibold">Device evidence · {formatPeriod(period)}</h3>
      <p className="text-sm text-gray-600 mt-2">Inspect paid activity, date eligibility, recorded calculations and payment evidence. Open a device for the full chain.</p>
      <div className="flex flex-wrap gap-3 mt-4">
        <label className="text-xs text-gray-600 flex-1 min-w-0 basis-full sm:basis-48">Find a device<input type="search" maxLength={100} className="overview-select w-full mt-1" placeholder="IMEI or product" value={filters.search} onChange={(e) => filter('search', e.target.value)} /></label>
        <label className="text-xs text-gray-600 flex-1 min-w-0">Eligibility result<select className="overview-select w-full mt-1" value={reason} onChange={(e) => onReasonChange(e.target.value)}><option value="all">All results</option>{Object.entries(REASON_LABELS).map(([value, label]) => <option key={value} value={value}>{label}</option>)}</select></label>
        <label className="text-xs text-gray-600 flex-1 min-w-0">Sort by<select className="overview-select w-full mt-1" value={filters.sort_by} onChange={(e) => filter('sort_by', e.target.value)}><option value="imei">IMEI</option><option value="simulated_commission_ngn">Simulated commission</option><option value="recorded_subscription_revenue_ngn">Recorded revenue</option><option value="variance_ngn">Variance</option><option value="due_date">Due date</option></select></label>
      </div>
      <div className="flex flex-wrap items-center gap-3 mt-3"><button className="overview-button" onClick={() => filter('direction', filters.direction === 'asc' ? 'desc' : 'asc')}>{filters.direction === 'asc' ? 'Ascending ↑' : 'Descending ↓'}</button><p className="text-xs text-gray-600" role="status">{busy ? 'Updating device evidence…' : `${data?.total ?? 0} matching devices`}</p></div>
    </div>
    {query.isError ? <div role="alert" className="p-5">Device evidence unavailable. <button className="underline" onClick={() => query.refetch()}>Retry device evidence</button></div>
      : !data ? <p className="p-5 animate-pulse" role="status">Loading device evidence…</p>
      : !data.evidence_available ? <p className="p-5 text-sm" role="status">{data.unavailable_reason}</p>
      : <>
        <div className={busy ? 'opacity-60' : ''}>{data.items.map((device) => <DeviceEvidence key={`${period}:${device.imei}`} device={device} />)}</div>
        {!data.items.length && <div role="status" className="p-5"><p className="font-medium">No device records match these filters</p><p className="text-sm text-gray-600 mt-2">Try another IMEI or eligibility result. Missing records do not establish zero commission.</p><button className="overview-button mt-3" onClick={() => { filter('search', ''); onReasonChange('all'); }}>Clear device filters</button></div>}
        <fieldset disabled={busy} className="p-4 border-t border-gray-200 commission-pagination"><legend className="sr-only">Subscription device pages</legend><PaginationControls pagination={{ total: data.total, returned: data.items.length, limit: data.limit, offset: data.offset, has_more: data.offset + data.items.length < data.total }} pageSize={filters.limit} onPageSizeChange={(n) => filter('limit', n)} onOffsetChange={(offset) => setFilters((current) => ({ ...current, offset }))} /></fieldset>
      </>}
  </section>;
}

function EvidenceItem({ label, children }) {
  return <div className="min-w-0"><dt className="text-xs text-gray-600">{label}</dt><dd className="text-sm mt-1 break-words">{children}</dd></div>;
}

function DeviceEvidence({ device: d }) {
  return <details className="border-b border-gray-200 p-5">
    <summary className="cursor-pointer marker:text-gray-500">
      <span className="font-medium break-all">Device {d.imei}</span><span className="text-sm text-gray-600"> · {d.product_name}</span>
      <span className="block text-sm mt-2">{REASON_LABELS[d.reason]} · Simulated commission: <strong className="tabular-nums">{subscriptionMoney(d.simulated_commission_ngn)}</strong> · {PAYMENT_LABELS[d.payment_status]}</span>
    </summary>
    <div className="mt-5 space-y-5">
      <p className="text-xs text-gray-600">Synthetic device evidence · {d.scenario}. {POLICY_LABEL}</p>
      <section aria-label={`Activity and eligibility for ${d.imei}`}>
        <h4 className="text-sm font-semibold">Selling dealer, paid activity and date eligibility</h4>
        <dl className="grid sm:grid-cols-2 lg:grid-cols-3 gap-4 mt-3">
          <EvidenceItem label="Original selling dealer">{d.selling_dealer_id} · {d.dealer_name}</EvidenceItem>
          <EvidenceItem label="Reporting month">{formatPeriod(d.mon_period)}</EvidenceItem>
          <EvidenceItem label="First activation">{d.first_activation_date || 'Unknown'}</EvidenceItem>
          <EvidenceItem label="Eligibility ends · exclusive">{d.eligibility_end_exclusive || 'Unknown'}</EvidenceItem>
          <EvidenceItem label="Date eligibility">{{ within_window: 'Within eligibility window', expired: 'Expired', unknown: 'Unknown' }[d.eligibility_status]}</EvidenceItem>
          <EvidenceItem label="Eligibility result / exclusion">{REASON_LABELS[d.reason]}</EvidenceItem>
          <EvidenceItem label="Successful paid subscriptions">{d.paid_subscription_count ?? 'Unknown'}</EvidenceItem>
          <EvidenceItem label="Paid subscription dates">{d.paid_subscription_dates == null ? 'Unknown' : d.paid_subscription_dates.length ? d.paid_subscription_dates.join(', ') : 'None recorded'}</EvidenceItem>
          <EvidenceItem label="Activity evidence">{d.activity_evidence_complete ? 'Complete for reporting month' : 'Incomplete · amounts may be unknown'}</EvidenceItem>
        </dl>
        <p className="text-xs text-gray-600 mt-3">{d.eligibility_boundary}</p>
        <h5 className="text-xs font-semibold mt-4">Recorded purchases and renewals</h5>
        {d.purchases.length ? <ul className="text-sm mt-2 space-y-1">{d.purchases.map((purchase, i) => <li key={`${purchase.date}:${i}`}>{purchase.date} · {purchase.status} · {subscriptionMoney(purchase.amount_ngn)}</li>)}</ul> : <p className="text-sm text-gray-600 mt-2">{d.activity_evidence_complete ? 'No purchase or renewal recorded this month.' : 'Purchase and renewal evidence is incomplete.'}</p>}
      </section>
      <section className="border-t border-gray-200 pt-4" aria-label={`Recorded calculation for ${d.imei}`}>
        <h4 className="text-sm font-semibold">Recorded revenue, simulated commission and expectation</h4>
        <dl className="grid sm:grid-cols-2 lg:grid-cols-3 gap-4 mt-3">
          <EvidenceItem label="Recorded subscription revenue">{subscriptionMoney(d.recorded_subscription_revenue_ngn)}</EvidenceItem>
          <EvidenceItem label="Qualifying monthly revenue">{subscriptionMoney(d.qualifying_revenue_ngn)}</EvidenceItem>
          <EvidenceItem label="Eligible revenue">{subscriptionMoney(d.eligible_revenue_ngn)}</EvidenceItem>
          <EvidenceItem label="Simulated commission">{subscriptionMoney(d.simulated_commission_ngn)}</EvidenceItem>
          <EvidenceItem label="Dealer expectation">{subscriptionMoney(d.dealer_expectation_ngn)}</EvidenceItem>
          <EvidenceItem label="Variance · recorded minus expectation">{subscriptionMoney(d.variance_ngn)}</EvidenceItem>
        </dl>
        <p className="text-sm mt-3">{d.variance_explanation}</p>
        <p className="text-xs text-gray-600 mt-2 break-words">Expectation reference: {d.expectation_reference || 'Unknown'}</p>
      </section>
      <section className="border-t border-gray-200 pt-4" aria-label={`Subscription payment for ${d.imei}`}>
        <h4 className="text-sm font-semibold">Supplied subscription payment evidence</h4>
        <dl className="grid sm:grid-cols-2 lg:grid-cols-3 gap-4 mt-3">
          <EvidenceItem label="Payment status">{PAYMENT_LABELS[d.payment_status]}</EvidenceItem>
          <EvidenceItem label="Due date">{d.due_date || 'Not supplied'}</EvidenceItem>
          <EvidenceItem label="Payment date">{d.payment_date || 'Not supplied'}</EvidenceItem>
          <EvidenceItem label="Paid amount">{subscriptionMoney(d.amount_paid_ngn)}</EvidenceItem>
          <EvidenceItem label="Outstanding amount">{subscriptionMoney(d.outstanding_ngn)}</EvidenceItem>
          <EvidenceItem label="Payment reference">{d.payment_evidence_reference || 'Unknown'}</EvidenceItem>
        </dl>
      </section>
      <section className="border-t border-gray-200 pt-4" aria-label={`Contextual churn for ${d.imei}`}>
        <h4 className="text-sm font-semibold">Churn context · not a commission exclusion</h4>
        <p className="text-sm mt-2">{churnLabel(d)}</p>
        <p className="text-xs text-gray-600 mt-2">Three consecutive months without paid subscriptions support this contextual indicator only when history is sufficient.</p>
        <ul className="text-sm mt-3 space-y-1">{d.history.map((month) => <li key={month.mon_period}>{formatPeriod(month.mon_period)}: {month.has_paid_subscription == null ? 'Unknown activity' : month.has_paid_subscription ? 'Paid subscription recorded' : 'No paid subscription recorded'}</li>)}</ul>
      </section>
      <p className="text-xs text-gray-500 break-words">{d.source} · Evidence as of {d.evidence_as_of}</p>
    </div>
  </details>;
}
