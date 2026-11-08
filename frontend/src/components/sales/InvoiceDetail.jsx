// A frozen invoice with its collections. Recording a collection goes through
// onRecordCollection. Without it, as for a partner, the invoice is read-only.

import { useRef, useState } from 'react';
import { formatDate, formatMinorNGN } from '../../lib/format.js';
import { PURCHASE_NOTE } from './PartnerObligations.jsx';
import { partnerLabel, quantityLabel } from './salesDisplay.js';
import { collectionErrors, parseAmountMinor } from './salesFormChecks.js';
import { DetailHeader, Disclaimer, Figures, StatusBadge } from './SalesParts.jsx';
import { ActionFailure, ReadState, useActionFailure, usePagedQuery } from './SalesReads.jsx';
import { invoiceQuery } from './useSalesQueries.js';

const displayDate = (date) => (date ? formatDate(date) : 'Not set');
const amountOnly = (minor) => formatMinorNGN(minor).replace('NGN ', '');

// The second click of a double click lands on a form the first has just cleared.
const ignoreRepeatClick = (event) => {
  if (event.detail > 1) event.preventDefault();
};

function CollectionRail({ invoice, balance, headingId, onRecord, onLoadLatest }) {
  const [date, setDate] = useState(balance.as_of);
  const [amount, setAmount] = useState('');
  const [attempted, setAttempted] = useState(false);
  const [recorded, setRecorded] = useState(null);
  const [recording, setRecording] = useState(false);
  const { failure, clearFailure, noteFailure } = useActionFailure();
  // The version this form opened on. If a read later brings a new one, what was typed
  // stays and the server refuses it, rather than it landing on a different invoice.
  const [token] = useState(invoice.token);
  // Kept until the server accepts it, so retrying a lost response records one collection.
  const action = useRef(null);
  const busy = useRef(false);
  const dateErrorId = `sales-collection-date-error-${invoice.reference}`;
  const amountErrorId = `sales-collection-amount-error-${invoice.reference}`;
  const errors = collectionErrors(invoice, balance.outstanding_minor, { date, amount });
  const amountError = attempted || amount ? errors.amount : null;
  const edit = (setter) => (event) => {
    setter(event.target.value);
    setRecorded(null);
    clearFailure();
    action.current = null;
  };
  const submit = async (event) => {
    event.preventDefault();
    if (busy.current) return;
    setAttempted(true);
    if (errors.date || errors.amount) {
      document.getElementById(`sales-collection-${errors.date ? 'date' : 'amount'}-${invoice.reference}`)?.focus();
      return;
    }
    busy.current = true;
    action.current ??= crypto.randomUUID();
    setRecording(true);
    clearFailure();
    const amountMinor = parseAmountMinor(amount);
    try {
      const collection = await onRecord(invoice.reference, { token, action_id: action.current, date, amount_minor: amountMinor });
      action.current = null;
      setRecorded({ reference: collection.reference, amountMinor });
      setAmount('');
      setAttempted(false);
      // Paying in full removes the form and the button holding focus.
      requestAnimationFrame(() => document.getElementById(headingId)?.focus());
    } catch (error) {
      noteFailure(error, 'This collection could not be recorded, so the balance is unchanged. Try again.');
    } finally {
      busy.current = false;
      setRecording(false);
    }
  };
  const paid = balance.outstanding_minor === 0;
  return <div className="overview-surface sales-rail">
    <h2 className="sales-h">{paid || !onRecord ? 'Collections status' : 'Record collection'}</h2>
    {recorded && <p role="status" className="overview-notice">Recorded {recorded.reference} for {formatMinorNGN(recorded.amountMinor)}.</p>}
    <ActionFailure failure={failure} onLoadLatest={onLoadLatest} />
    {paid ? <p className="text-sm font-medium">Paid in full. No further collections can be recorded.</p>
      : !onRecord ? <p className="sales-muted">{formatMinorNGN(balance.outstanding_minor)} outstanding. MTN Finance records collections against this invoice. Refresh to see new ones.</p>
      : <form noValidate aria-label={`Record a collection against ${invoice.reference}`} onSubmit={submit}>
        <div className="flex flex-col gap-1"><label className="sales-field">Collection date<input id={`sales-collection-date-${invoice.reference}`} className="overview-select" type="date" min={invoice.issue_date} max="9999-12-31" disabled={recording} aria-invalid={Boolean(errors.date)} aria-describedby={errors.date ? dateErrorId : undefined} value={date} onChange={edit(setDate)} /></label>
          {errors.date && <span id={dateErrorId} className="sales-error">{errors.date}</span>}</div>
        <div className="flex flex-col gap-1"><label className="sales-field">Amount in NGN<input id={`sales-collection-amount-${invoice.reference}`} className="overview-select" type="text" inputMode="decimal" autoComplete="off" placeholder={`Up to ${amountOnly(balance.outstanding_minor)}`} disabled={recording} aria-invalid={Boolean(amountError)} aria-describedby={amountError ? amountErrorId : undefined} value={amount} onChange={edit(setAmount)} /></label>
          {amountError && <span id={amountErrorId} className="sales-error">{amountError}</span>}</div>
        <button type="submit" className="overview-button overview-primary sales-full" disabled={recording} onClick={ignoreRepeatClick}>Record collection</button>
      </form>}
    <p className="sales-note">{!paid && onRecord && 'Collections cannot be refunded or reversed. '}Collections never generate commission or offset commission outstanding, and no money moves.</p>
  </div>;
}

function CollectionHistory({ invoice, collections, controls, headingId }) {
  const history = collections.items;
  return <section className="overview-surface" aria-labelledby={headingId}>
    <div className="sales-sec"><h2 id={headingId} tabIndex={-1} aria-label="Invoice collections" className="sales-h">Collections</h2></div>
    {history.length ? <>
      <table className="sales-table">
        <caption className="sr-only">Collections recorded against {invoice.reference}</caption>
        <thead><tr><th scope="col">Date</th><th scope="col" className="hidden md:table-cell">Reference</th><th scope="col" className="sales-num hidden md:table-cell">Amount</th><th scope="col" className="sales-num hidden md:table-cell">Outstanding after</th></tr></thead>
        <tbody>{history.map((collection) => <tr key={collection.reference}>
          <th scope="row"><span className="block whitespace-nowrap">{formatDate(collection.date)}</span>
            <span className="block md:hidden sales-strong mt-1">{collection.reference}</span>
            <span className="block md:hidden mt-1">Amount <span className="whitespace-nowrap">{formatMinorNGN(collection.amount_minor)}</span></span>
            <span className="block md:hidden sales-muted mt-1">Outstanding after <span className="whitespace-nowrap">{formatMinorNGN(collection.outstanding_after_minor)}</span></span></th>
          <td className="hidden md:table-cell sales-strong">{collection.reference}</td>
          <td className="sales-num hidden md:table-cell">{formatMinorNGN(collection.amount_minor)}</td>
          <td className="sales-num hidden md:table-cell">{formatMinorNGN(collection.outstanding_after_minor)}</td>
        </tr>)}</tbody>
      </table>
      {controls}
    </> : <p className="sales-foot !text-sm">No collections recorded against this invoice yet.</p>}
  </section>;
}

function InvoiceLines({ invoice }) {
  return <div className="overview-surface">
    <div className="sales-sec"><h2 className="sales-h">Invoice lines</h2></div>
    <table className="sales-table">
      <caption className="sr-only">Invoice lines for {invoice.reference}</caption>
      <thead><tr><th scope="col">Product</th><th scope="col" className="sales-num hidden sm:table-cell">Quantity</th><th scope="col" className="sales-num hidden sm:table-cell">Unit price</th><th scope="col" className="sales-num">Line total</th></tr></thead>
      <tbody>{invoice.lines.map((line) => <tr key={line.product_code}>
        <th scope="row"><span className="block sales-strong">{line.product_code}</span> <span className="sales-sub">{line.description}</span>
          <span className="block sm:hidden sales-muted mt-1">{quantityLabel(line.quantity, line.unit)} × {formatMinorNGN(line.unit_price_minor)}</span></th>
        <td className="sales-num hidden sm:table-cell">{quantityLabel(line.quantity, line.unit)}</td>
        <td className="sales-num hidden sm:table-cell">{formatMinorNGN(line.unit_price_minor)}</td>
        <td className="sales-num">{formatMinorNGN(line.line_total_minor)}</td>
      </tr>)}</tbody>
      <tfoot><tr><th scope="row">Total</th><td className="hidden sm:table-cell" /><td className="hidden sm:table-cell" /><td className="sales-num">{formatMinorNGN(invoice.total_minor)}</td></tr></tfoot>
    </table>
  </div>;
}

// The heading shows at once, so opening an invoice can move focus before it loads.
export default function InvoiceDetail({ reference, headingId, backLabel, onBack, onOpenPartner, onOpenCommission, onRecordCollection, onLoadLatest, queryFor = invoiceQuery, useRead }) {
  const collectionsHeadingId = `sales-collections-heading-${reference}`;
  const { query: detail, controls } = usePagedQuery(reference, collectionsHeadingId, (page) => queryFor(reference, page), (data) => data.collections.pagination, useRead);
  const { invoice, balance, collections } = detail.data ?? {};
  // The refused form disappears while the invoice reloads, taking focus with it.
  const loadLatest = () => {
    onLoadLatest(reference);
    document.getElementById(headingId)?.focus();
  };
  const name = invoice?.buyer.name;
  const obligationsOpener = `sales-invoice-partner-${reference}`;
  const commissionOpener = `sales-invoice-commission-${reference}`;
  return <section className="flex flex-col gap-6" aria-labelledby={headingId}>
    <DetailHeader eyebrow="Simulated invoice" title={name ?? reference} headingId={headingId} headingLabel={`Simulated invoice ${reference}${name ? `, ${name}` : ''}`} backLabel={backLabel} onBack={onBack}
      meta={invoice && <>{reference} · Account {invoice.buyer.code} · <StatusBadge status={balance.status} /></>} />
    {(!invoice || detail.isError) && <div className="overview-surface sales-card-pad"><ReadState query={detail} what="invoice" /></div>}
    {invoice && <div className="sales-detail">
      <div className="sales-stack">
        <div className="overview-surface sales-card-pad">
          <dl><dt>{`Outstanding as of ${formatDate(balance.as_of)}`}</dt><dd className="sales-big overview-headline">{formatMinorNGN(balance.outstanding_minor)}</dd></dl>
          <Figures items={[['Invoice total', formatMinorNGN(invoice.total_minor)], ['Collected', formatMinorNGN(balance.collected_minor)], ['Issue date', formatDate(invoice.issue_date)], ['Due date', displayDate(invoice.due_date)]]} />
          <p className="sales-note mt-3.5">Includes every collection recorded up to {formatDate(balance.as_of)}. Not a month-end balance for any reporting month.{invoice.order_reference && ` From partner order ${invoice.order_reference}, with its lines and total unchanged.`}</p>
          <Disclaimer className="mt-2" summary="Fictional simulation, not an actual purchase obligation or tax invoice">Simplified fictional demonstration with fictional prices. Seller {invoice.seller}, buyer {partnerLabel(invoice.buyer)}, in {invoice.currency}. Taxes and discounts are not modeled. {PURCHASE_NOTE} These details stay fixed after issue, whichever reporting month is selected.</Disclaimer>
        </div>
        <InvoiceLines invoice={invoice} />
        <CollectionHistory invoice={invoice} collections={collections} controls={controls} headingId={collectionsHeadingId} />
      </div>
      <div className="sales-stack">
        <CollectionRail invoice={invoice} balance={balance} headingId={collectionsHeadingId} onRecord={onRecordCollection} onLoadLatest={loadLatest} />
        {onOpenPartner && <div className="overview-surface sales-rail">
          <h2 className="sales-h">{invoice.buyer.name}</h2>
          <button id={obligationsOpener} type="button" className="overview-button sales-full" aria-label={`View all purchase obligations for ${partnerLabel(invoice.buyer)}`} onClick={() => onOpenPartner(invoice.buyer.code, obligationsOpener)}>View all purchase obligations</button>
          <button id={commissionOpener} type="button" className="overview-button sales-full" aria-label={`View commission account for ${partnerLabel(invoice.buyer)}`} onClick={() => onOpenCommission(invoice.buyer.code, commissionOpener)}>View commission account</button>
        </div>}
      </div>
    </div>}
  </section>;
}
