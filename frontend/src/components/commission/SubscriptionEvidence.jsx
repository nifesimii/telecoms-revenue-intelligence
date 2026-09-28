import { useState } from 'react';
import { useQuery } from '@tanstack/react-query';
import { getCommissionSubscriptionRecords } from '../../api/client.js';
import { formatNGN } from '../../lib/format.js';
import { SubscriptionMoney } from './SubscriptionAmounts.jsx';
import PaginationControls from '../shared/PaginationControls.jsx';

export default function SubscriptionEvidence({ dealerId, period }) {
  const [offset, setOffset] = useState(0);
  const [limit, setLimit] = useState(25);
  const query = useQuery({ queryKey: ['subscription-records', dealerId, period, offset, limit],
    queryFn: ({ signal }) => getCommissionSubscriptionRecords(dealerId, { mon_period: period, stream: 'orsc', offset, limit }, signal) });
  const data = query.data;
  return <section className="overview-surface overflow-hidden" aria-label="Subscription device evidence">
    <div className="p-5"><h3 className="font-semibold">Subscription device records</h3><p className="text-sm text-gray-600 mt-2">Dealer attribution follows the subscription source. Original sale ownership has not been independently verified.</p></div>
    {query.isPending && <p role="status" className="p-5">Loading device evidence…</p>}
    {query.isError && <p role="alert" className="p-5 text-red-800">Device evidence unavailable. <button className="underline" onClick={() => query.refetch()}>Retry</button></p>}
    {data && <>
      <div className="overflow-x-auto" tabIndex={0} role="region" aria-label="Scrollable subscription device records"><table className="commission-table w-full text-sm text-left">
        <thead><tr><th>Device / IMEI</th><th className="text-right">Subscription revenue</th><th className="text-right">Recorded commission</th><th className="text-right">Settled</th><th className="text-right">Outstanding</th><th>Statement reference</th><th>Settlement reference</th></tr></thead>
        <tbody>{data.items.map((row, index) => <tr key={`${row.imei}-${offset + index}`}>
          <td className="font-mono text-xs">{row.imei || 'Not recorded'}</td>
          <td className="text-right tabular-nums whitespace-nowrap">{formatNGN(row.subscription_revenue_ngn)}</td>
          {['subscription_commission_ngn', 'subscription_settled_ngn', 'subscription_outstanding_ngn'].map((field) => <td key={field} className="text-right tabular-nums whitespace-nowrap"><SubscriptionMoney value={row[field]} /></td>)}
          <td className="text-xs">{row.statement_reference || 'Not available'}</td><td className="text-xs">{row.settlement_reference || 'Not available'}</td>
        </tr>)}</tbody>
      </table></div>
      {!data.total && <p className="p-5 text-sm" role="status">No subscription device evidence is available for this account and period. This does not establish a zero balance.</p>}
      <div className="p-4 commission-pagination"><PaginationControls pagination={{ total: data.total, returned: data.items.length, offset, limit, has_more: offset + data.items.length < data.total }} pageSize={limit} onPageSizeChange={(n) => { setLimit(n); setOffset(0); }} onOffsetChange={setOffset} /></div>
    </>}
  </section>;
}
