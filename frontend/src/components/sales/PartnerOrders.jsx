// A partner's submitted orders, read-only, with what MTN Finance decided about each.

import { useQuery } from '@tanstack/react-query';
import { formatDate, formatMinorNGN } from '../../lib/format.js';
import OrderLines from './OrderLines.jsx';
import { partnerLabel } from './salesDisplay.js';
import { DetailHeader, Figures, StatusBadge } from './SalesParts.jsx';
import { ReadState, usePagedQuery } from './SalesReads.jsx';
import { ownOrdersQuery, useOwnOrder } from './useSalesQueries.js';

export const OWN_ORDER_COUNT = { limit: 1, offset: 0 };

export function OrderList({ onOpen }) {
  const { query: orders, controls } = usePagedQuery('own-orders', 'sales-orders-heading', ownOrdersQuery, (data) => data.pagination, useQuery);
  const visible = orders.data?.items ?? [];
  return <section className="overview-surface" aria-labelledby="sales-orders-heading">
    <div className="sales-sec"><div>
      <h2 id="sales-orders-heading" tabIndex={-1} aria-label="Your orders" className="sales-h">My orders</h2>
      <p className="sales-muted">Submitted orders cannot be changed or withdrawn. MTN Finance issues each as an invoice or rejects it with a reason. Refresh to see their decisions.</p>
    </div></div>
    {(!orders.data || orders.isError) && <div className="sales-body"><ReadState query={orders} what="order list" /></div>}
    {orders.data && (!orders.data.pagination.total ? <p role="status" className="sales-body sales-muted">You have not submitted any orders yet.</p> : <>
      <table className="sales-table">
        <caption className="sr-only">Your submitted orders</caption>
        <thead><tr><th scope="col">Reference</th><th scope="col">Status</th><th scope="col" className="sales-num">Total</th><th scope="col"><span className="sr-only">Actions</span></th></tr></thead>
        <tbody>{visible.map((order) => <tr key={order.reference}>
          <th scope="row" className="!font-semibold">{order.reference}</th>
          <td><StatusBadge status={order.status} /></td>
          <td className="sales-num">{formatMinorNGN(order.total_minor)}</td>
          <td className="sales-row-actions"><button id={`sales-order-open-${order.reference}`} type="button" className="overview-button sales-go" aria-label={`Open order ${order.reference}`} onClick={() => onOpen(order.reference, `sales-order-open-${order.reference}`)}>Open</button></td>
        </tr>)}</tbody>
      </table>
      {controls}
    </>)}
  </section>;
}

export function OrderDetail({ reference, headingId, onBack }) {
  const order = useOwnOrder(reference);
  return <section className="flex flex-col gap-6" aria-labelledby={headingId}>
    <DetailHeader eyebrow="Fictional simulation" title={`Order ${reference}`} headingId={headingId} backLabel="Back to your orders" onBack={onBack}
      meta={order.data && <><StatusBadge status={order.data.status} /></>} />
    {(!order.data || order.isError) && <div className="overview-surface sales-card-pad"><ReadState query={order} what="order" /></div>}
    {order.data && <div className="sales-detail">
      <div className="sales-stack">
        <div className="overview-surface sales-card-pad">
          <p>Order total</p>
          <p className="sales-big overview-headline">{formatMinorNGN(order.data.total_minor)}</p>
          <Figures items={[['Status', order.data.status], ['Seller', 'MTN'], ['Buyer', partnerLabel(order.data.account)], ['Currency', order.data.currency]]} />
        </div>
        <OrderLines caption={`Lines in order ${reference}`} lines={order.data.lines} totalMinor={order.data.total_minor} />
      </div>
      <div className="overview-surface sales-rail">
        <h2 className="sales-h">Decision</h2>
        <OrderDecision order={order.data} />
        <p className="sales-note">This order is read-only. It is not an invoice or a purchase obligation unless MTN Finance issues it.</p>
      </div>
    </div>}
  </section>;
}

function OrderDecision({ order }) {
  if (order.status === 'Issued') {
    const { reference, issue_date: issued, due_date: due } = order.invoice;
    return <p className="text-sm font-medium">MTN Finance issued this order as invoice {reference} on {formatDate(issued)}, due {formatDate(due)}.</p>;
  }
  if (order.status === 'Rejected') {
    return <div className="text-sm"><p className="font-medium">MTN Finance rejected this order: {order.rejection_reason}</p>
      <p className="sales-muted mt-1">A rejected order is final. Start a new draft to order again.</p></div>;
  }
  return <p className="sales-muted">Awaiting review by MTN Finance.</p>;
}
