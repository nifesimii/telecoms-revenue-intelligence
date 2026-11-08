// Finance's review of submitted partner orders: the queue across every partner, and
// one order issued as an invoice or rejected with a reason. The server decides each
// order once; these forms only explain a problem before it is sent.

import { useRef, useState } from 'react';
import { formatCount, formatMinorNGN, formatPeriod } from '../../lib/format.js';
import { describeFailure, partnerLabel } from './salesDisplay.js';
import { issueDateRange, orderIssueErrors, rejectionError } from './salesFormChecks.js';
import { orderQueueQuery } from './useSalesQueries.js';
import { DetailHeader, Disclaimer, Figures, PartnerCell, StatusBadge } from './SalesParts.jsx';
import { ReadState, usePagedQuery } from './SalesReads.jsx';
import OrderLines from './OrderLines.jsx';

export const ORDER_QUEUE_HEADING = 'sales-order-queue-heading';
export const ORDER_NOTICE = 'sales-order-decision-notice';
export const reviewOpenerId = (reference) => `sales-review-${reference}`;

export function OrderQueue({ notice, onReview }) {
  const { query: queue, controls } = usePagedQuery('order-queue', ORDER_QUEUE_HEADING, orderQueueQuery, (data) => data.pagination);
  const total = queue.data?.pagination.total;
  return <section aria-labelledby={ORDER_QUEUE_HEADING}>
    <div className="sales-sec"><div>
      <h2 id={ORDER_QUEUE_HEADING} tabIndex={-1} aria-label="Orders awaiting review" className="sales-h">Orders to review</h2>
      <p className="sales-muted">Oldest first. Issuing or rejecting an order is final.</p>
    </div></div>
    {notice && <p id={ORDER_NOTICE} role="status" tabIndex={-1} className="overview-notice mx-5 mb-4">{notice}</p>}
    {(!queue.data || queue.isError) && <div className="sales-body"><ReadState query={queue} what="order queue" /></div>}
    {queue.data && (!total ? <p role="status" className="sales-body sales-muted">No partner orders await review.</p> : <>
      <p className="sr-only">{formatCount(total)} {total === 1 ? 'order awaits' : 'orders await'} review.</p>
      <table className="sales-table">
        <caption className="sr-only">Orders awaiting review</caption>
        <thead><tr><th scope="col">Reference</th><th scope="col" className="hidden md:table-cell">Partner</th><th scope="col" className="hidden md:table-cell">Status</th><th scope="col" className="sales-num hidden md:table-cell">Total</th><th scope="col"><span className="sr-only">Actions</span></th></tr></thead>
        <tbody>{queue.data.items.map((order) => <tr key={order.reference}>
          <th scope="row"><span className="block sales-strong">{order.reference}</span>
            <span className="block md:hidden mt-1">{partnerLabel(order.account)}</span>
            <span className="block md:hidden sales-strong mt-1 whitespace-nowrap">{formatMinorNGN(order.total_minor)}</span></th>
          <td className="hidden md:table-cell"><PartnerCell partner={order.account} /></td>
          <td className="hidden md:table-cell"><StatusBadge status={order.status} /></td>
          <td className="sales-num hidden md:table-cell">{formatMinorNGN(order.total_minor)}</td>
          <td className="sales-row-actions"><button id={reviewOpenerId(order.reference)} type="button" className="overview-button sales-go" aria-label={`Review order ${order.reference}`} onClick={() => onReview(order, reviewOpenerId(order.reference))}>Review</button></td>
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
  const field = (name, label, input, error) => <div className="flex flex-col gap-1">
    <label className="sales-field">{label}{input}</label>
    {error && <span id={`${id(name)}-error`} className="sales-error">{error}</span>}
  </div>;
  const describedBy = (name, error) => ({ 'aria-invalid': Boolean(error), 'aria-describedby': error ? `${id(name)}-error` : undefined });
  const locked = deciding || refused;
  const units = order.lines.reduce((sum, line) => sum + line.quantity, 0);

  return <section className="flex flex-col gap-6" aria-labelledby={headingId}>
    <DetailHeader eyebrow="Order review" title={order.account.name} headingId={headingId} headingLabel={`Review order ${order.reference}, ${partnerLabel(order.account)}`} backLabel={backLabel} onBack={onBack} backDisabled={deciding}
      meta={<>{order.reference} · Account {order.account.code} · <StatusBadge status={order.status} /></>} />
    <div className="sales-detail">
      <div className="sales-stack">
        <div className="overview-surface sales-card-pad">
          <p>Order total</p>
          <p className="sales-big overview-headline">{formatMinorNGN(order.total_minor)}</p>
          <Figures items={[['Seller', 'MTN'], ['Currency', order.currency], ['Lines', formatCount(order.lines.length)], ['Units', formatCount(units)]]} />
          <Disclaimer className="mt-3.5" summary="Fictional simulation, not an actual order or invoice">Fictional partner order with fictional products and prices. Taxes and discounts are not modeled, and nothing here touches recorded commission, payment or inventory evidence.</Disclaimer>
        </div>
        <OrderLines caption={`Lines in order ${order.reference}`} lines={order.lines} totalMinor={order.total_minor} />
      </div>
      <div className="overview-surface sales-rail">
        <h2 className="sales-h">Decision</h2>
        {message && <p role="alert" className="sales-alert">{message}</p>}
        {refused && <div role="alert" className="sales-alert">This order was already decided, possibly in another session, or the simulation was reset. Nothing here was applied.
          <div className="mt-2"><button type="button" className="overview-button" onClick={onLoadLatest}>Load latest orders</button></div></div>}
        <form noValidate aria-label={`Issue order ${order.reference} as an invoice`} onSubmit={issue}>
          {field('issueDate', 'Issue date', <input id={id('issueDate')} className="overview-select" type="date" min={monthStart} max={monthEnd} disabled={locked} value={issueDate} onChange={(event) => setIssueDate(event.target.value)} {...describedBy('issueDate', dateErrors.issueDate)} />, dateErrors.issueDate)}
          {field('dueDate', 'Due date', <input id={id('dueDate')} className="overview-select" type="date" min={issueDate || undefined} max="9999-12-31" disabled={locked} value={dueDate} onChange={(event) => setDueDate(event.target.value)} {...describedBy('dueDate', dateErrors.dueDate)} />, dateErrors.dueDate)}
          <button type="submit" className="overview-button overview-primary sales-full" disabled={locked}>Issue invoice</button>
          <p className="sales-note">Creates a simulated invoice with exactly these lines and this total, owed by account {order.account.code}.</p>
        </form>
        <hr />
        <form noValidate aria-label={`Reject order ${order.reference}`} onSubmit={reject}>
          {field('reason', 'Reason for rejecting', <textarea id={id('reason')} className="overview-select" rows={3} maxLength={500} disabled={locked} value={reason} onChange={(event) => setReason(event.target.value)} {...describedBy('reason', reasonError)} />, reasonError)}
          <button type="submit" className="overview-button sales-danger sales-full" disabled={locked}>Reject order</button>
          <p className="sales-note">Final. The partner sees this reason on their order.</p>
        </form>
      </div>
    </div>
  </section>;
}
