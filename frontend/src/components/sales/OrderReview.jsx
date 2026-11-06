// Finance's review of submitted partner orders: the queue across every partner, and
// one order issued as an invoice or rejected with a reason. The server decides each
// order once; these forms only explain a problem before it is sent.

import { useRef, useState } from 'react';
import { formatCount, formatMinorNGN, formatPeriod } from '../../lib/format.js';
import { describeFailure, partnerLabel } from './salesDisplay.js';
import { issueDateRange, orderIssueErrors, rejectionError } from './salesFormChecks.js';
import { orderQueueQuery } from './useSalesQueries.js';
import { ReadState, usePagedQuery } from './InvoiceViews.jsx';
import OrderLines from './OrderLines.jsx';

export const ORDER_QUEUE_HEADING = 'sales-order-queue-heading';
export const ORDER_NOTICE = 'sales-order-decision-notice';
export const reviewOpenerId = (reference) => `sales-review-${reference}`;

export function OrderQueue({ notice, onReview }) {
  const { query: queue, controls } = usePagedQuery('order-queue', ORDER_QUEUE_HEADING, orderQueueQuery, (data) => data.pagination);
  const total = queue.data?.pagination.total;
  return <section className="sales-paper" aria-labelledby={ORDER_QUEUE_HEADING}>
    <h2 id={ORDER_QUEUE_HEADING} tabIndex={-1} className="text-lg font-semibold">Orders awaiting review</h2>
    <p className="text-xs text-gray-600 mt-1">Fictional orders partners have submitted, oldest first. Issue each as an invoice or reject it with a reason; either decision is final. Refresh to see new orders.</p>
    {notice && <p id={ORDER_NOTICE} role="status" tabIndex={-1} className="sales-notice mt-3">{notice}</p>}
    <ReadState query={queue} what="order queue" />
    {queue.data && (!total ? <p role="status" className="text-sm text-gray-600 mt-4">No partner orders await review.</p> : <>
      <p className="text-sm text-gray-700 mt-3">{formatCount(total)} {total === 1 ? 'order awaits' : 'orders await'} review.</p>
      <table className="sales-table mt-3">
        <caption className="sr-only">Orders awaiting review</caption>
        <thead><tr><th scope="col">Reference</th><th scope="col" className="hidden md:table-cell">Partner</th><th scope="col" className="sales-amount hidden md:table-cell">Total</th><th scope="col"><span className="sr-only">Actions</span></th></tr></thead>
        <tbody>{queue.data.items.map((order) => <tr key={order.reference}>
          <th scope="row"><span className="block font-semibold">{order.reference}</span>
            <span className="block md:hidden mt-1">{partnerLabel(order.account)}</span>
            <span className="block md:hidden font-semibold mt-1 whitespace-nowrap">{formatMinorNGN(order.total_minor)}</span></th>
          <td className="hidden md:table-cell">{partnerLabel(order.account)}</td>
          <td className="sales-amount hidden md:table-cell">{formatMinorNGN(order.total_minor)}</td>
          <td className="text-right"><button id={reviewOpenerId(order.reference)} type="button" className="sales-button" aria-label={`Review order ${order.reference}`} onClick={() => onReview(order, reviewOpenerId(order.reference))}>Review</button></td>
        </tr>)}</tbody>
      </table>
      {controls}
    </>)}
  </section>;
}

// Shows the order as it was queued. A decision sends that copy's token, so an order
// decided elsewhere, or replaced by a reset, is refused rather than decided twice.
export function OrderReview({ order, period, headingId, backLabel, onBack, onIssue, onReject, onLoadLatest }) {
  const [issueDate, setIssueDate] = useState(() => issueDateRange(period).max);
  const [dueDate, setDueDate] = useState('');
  const [reason, setReason] = useState('');
  const [attempted, setAttempted] = useState(null);
  const [deciding, setDeciding] = useState(false);
  const [refused, setRefused] = useState(false);
  const [message, setMessage] = useState(null);
  const busy = useRef(false);
  const id = (field) => `sales-review-${field}-${order.reference}`;
  const { min: monthStart, max: monthEnd } = issueDateRange(period);
  const checkDates = () => orderIssueErrors({ issueDate, dueDate }, period, formatPeriod(period));
  const dateErrors = attempted === 'issue' ? checkDates() : {};
  const reasonError = attempted === 'reject' ? rejectionError(reason) : null;

  const decide = async (kind, fieldErrors, send, fallback) => {
    if (busy.current) return;
    setAttempted(kind);
    setMessage(null);
    const invalid = Object.entries(fieldErrors).find(([, error]) => error);
    if (invalid) {
      document.getElementById(id(invalid[0]))?.focus();
      return;
    }
    busy.current = true;
    setDeciding(true);
    try {
      await send();
    } catch (error) {
      const failure = describeFailure(error, fallback);
      setRefused(failure.refused);
      setMessage(failure.message ?? null);
      busy.current = false;
      setDeciding(false);
    }
  };
  const issue = (event) => {
    event.preventDefault();
    decide('issue', checkDates(), () => onIssue(order.reference, { token: order.token, issue_date: issueDate, due_date: dueDate }),
      'The order could not be issued, so it still awaits review. Try again.');
  };
  const reject = (event) => {
    event.preventDefault();
    decide('reject', { reason: rejectionError(reason) }, () => onReject(order.reference, { token: order.token, reason }),
      'The order could not be rejected, so it still awaits review. Try again.');
  };
  const field = (name, label, input, error) => <div className="flex flex-col gap-2">
    <label className="sales-field">{label}{input}</label>
    {error && <span id={`${id(name)}-error`} className="sales-error">{error}</span>}
  </div>;
  const describedBy = (name, error) => ({ 'aria-invalid': Boolean(error), 'aria-describedby': error ? `${id(name)}-error` : undefined });
  const locked = deciding || refused;

  return <section className="sales-paper" aria-labelledby={headingId}>
    <p className="text-xs font-semibold tracking-widest uppercase text-amber-800">Fictional simulation</p>
    <h2 id={headingId} tabIndex={-1} className="text-lg font-semibold mt-1">Review order {order.reference}</h2>
    <dl className="sales-facts">
      <div><dt>Status</dt><dd>{order.status}</dd></div>
      <div><dt>Partner</dt><dd>{partnerLabel(order.account)}</dd></div>
      <div><dt>Seller</dt><dd>MTN</dd></div>
      <div><dt>Currency</dt><dd>{order.currency}</dd></div>
    </dl>
    <OrderLines caption={`Lines in order ${order.reference}`} lines={order.lines} totalMinor={order.total_minor} />
    <p className="sales-notice mt-5">Issuing creates a simulated invoice with exactly these lines and this total, owed by account {order.account.code}. A rejection is final, and the partner sees your reason.</p>
    {message && <p role="alert" className="sales-alert">{message}</p>}
    {refused && <div role="alert" className="sales-alert">This order was already decided, possibly in another session, or the simulation was reset. Nothing here was applied.
      <div className="mt-2"><button type="button" className="sales-button" onClick={onLoadLatest}>Load latest orders</button></div></div>}
    <form noValidate className="mt-5" aria-label={`Issue order ${order.reference} as an invoice`} onSubmit={issue}>
      <h3 className="text-base font-semibold">Issue as an invoice</h3>
      <div className="sales-dates mt-2">
        {field('issueDate', 'Issue date', <input id={id('issueDate')} type="date" min={monthStart} max={monthEnd} disabled={locked} value={issueDate} onChange={(event) => setIssueDate(event.target.value)} {...describedBy('issueDate', dateErrors.issueDate)} />, dateErrors.issueDate)}
        {field('dueDate', 'Due date', <input id={id('dueDate')} type="date" min={issueDate || undefined} max="9999-12-31" disabled={locked} value={dueDate} onChange={(event) => setDueDate(event.target.value)} {...describedBy('dueDate', dateErrors.dueDate)} />, dateErrors.dueDate)}
      </div>
      <div className="sales-actions"><button type="submit" className="sales-button sales-primary" disabled={locked}>Issue invoice</button></div>
    </form>
    <form noValidate className="mt-5" aria-label={`Reject order ${order.reference}`} onSubmit={reject}>
      <h3 className="text-base font-semibold">Reject</h3>
      {field('reason', 'Reason for rejecting', <textarea id={id('reason')} rows={3} maxLength={500} disabled={locked} value={reason} onChange={(event) => setReason(event.target.value)} {...describedBy('reason', reasonError)} />, reasonError)}
      <div className="sales-actions"><button type="submit" className="sales-button" disabled={locked}>Reject order</button>
        <p className="text-xs text-gray-600">The partner sees this reason on their order.</p></div>
    </form>
    <div className="sales-actions"><button type="button" className="sales-button" disabled={deciding} onClick={onBack}>{backLabel}</button></div>
  </section>;
}
