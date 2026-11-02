// Partner Sales invoice browsing: the bounded list, one partner's purchase
// obligations and a frozen invoice with its collections. Recording a collection
// goes through onRecordCollection; nothing here edits the simulation directly.

import { useState } from 'react';
import PaginationControls from '../shared/PaginationControls.jsx';
import { formatCount, formatDate, formatMinorNGN, formatPeriod } from '../../lib/format.js';
import { STATUSES, collectionActionId, collectionErrors, collectionReferenceFor, invoiceBalance, invoiceOpenerId, matchingRecords, parseAmountMinor, partnerLabel, partnerObligations, quantityLabel, summarizeRecords } from './salesSimulation.js';

const displayDate = (date) => (date ? formatDate(date) : 'Not set');
const recordDate = (record) => (record.status === 'Draft' ? `Intended ${displayDate(record.date)}` : displayDate(record.date));
const displayAmount = (minor) => (minor === null ? 'Unavailable' : formatMinorNGN(minor));

// One bounded page of an in-browser set. A new scope starts at the first page; a
// set that shrinks falls back to its last page.
function useBoundedPage(items, scope, headingId) {
  const [limit, setLimit] = useState(25);
  const [position, setPosition] = useState({ scope, offset: 0 });
  const wanted = position.scope === scope ? position.offset : 0;
  const offset = Math.min(wanted, Math.max(0, Math.floor((items.length - 1) / limit) * limit));
  // Record the correction, so changing back or regrowing never revives an old page.
  if (position.scope !== scope || position.offset !== offset) setPosition({ scope, offset });
  const visible = items.slice(offset, offset + limit);
  // Previous/Next can disable themselves on arrival, so focus moves to the results.
  const focusResults = () => requestAnimationFrame(() => document.getElementById(headingId)?.focus());
  return {
    visible,
    controls: <div className="sales-pagination"><PaginationControls
      pagination={{ total: items.length, returned: visible.length, offset, limit, has_more: offset + visible.length < items.length }}
      pageSize={limit}
      onOffsetChange={(next) => { setPosition({ scope, offset: next }); focusResults(); }}
      onPageSizeChange={(next) => { setLimit(next); setPosition({ scope, offset: 0 }); }}
    /></div>,
  };
}

const PURCHASE_NOTE = 'A purchase obligation is what the partner would owe MTN for goods bought. It is not commission, and it is not netted against the Partner Commission Account, the separate record of commission owed by MTN.';

export function InvoiceList({ simulation, period, onOpenInvoice, onOpenPartner, onOpenDraft }) {
  const [search, setSearch] = useState('');
  const [status, setStatus] = useState('');
  const periodLabel = formatPeriod(period);
  const records = matchingRecords(simulation, { period, search, status });
  const summary = summarizeRecords(records);
  const { visible, controls } = useBoundedPage(records, `${period}|${search.trim().toLowerCase()}|${status}`, 'sales-invoices-heading');
  const filtered = Boolean(search.trim() || status);
  const clearFilters = () => {
    setSearch('');
    setStatus('');
    document.getElementById('sales-invoice-search')?.focus();
  };
  return <section className="sales-paper" aria-labelledby="sales-invoices-heading">
    <h2 id="sales-invoices-heading" tabIndex={-1} className="text-lg font-semibold">Invoices for {periodLabel}</h2>
    <p className="text-xs text-gray-600 mt-1">Fictional simulation. Invoices are listed by issue month and drafts by intended issue month.</p>
    <div className="sales-filters">
      <label className="sales-field">Search invoices by partner or account code<input id="sales-invoice-search" type="search" value={search} maxLength={200} placeholder="Name or account code" onChange={(event) => setSearch(event.target.value)} /></label>
      <label className="sales-field">Status<select value={status} onChange={(event) => setStatus(event.target.value)}>
        <option value="">All statuses</option>
        {STATUSES.map((option) => <option key={option} value={option}>{option}</option>)}
      </select></label>
    </div>
    <dl className="sales-facts" aria-label="Totals for all matching records">
      <div><dt>Matching records</dt><dd>{formatCount(summary.count)}</dd></div>
      <div><dt>Issued invoices</dt><dd>{formatCount(summary.issued)}</dd></div>
      <div><dt>Drafts (excluded from outstanding)</dt><dd>{formatCount(summary.drafts)}</dd></div>
      <div><dt>Outstanding purchase obligation</dt><dd>{formatMinorNGN(summary.outstandingMinor)}</dd></div>
    </dl>
    {summary.issued > 0 && <p className="text-xs text-gray-600 mt-2">Outstanding counts every collection recorded up to {formatDate(summary.asOf)}, including any dated after {periodLabel}. It is not a month-end balance for {periodLabel}.</p>}
    {!records.length ? <div role="status" className="text-sm text-gray-600 mt-4">
      {filtered ? <>No invoices or drafts in {periodLabel} match your search and status. <button type="button" className="sales-button mt-2 block" onClick={clearFilters}>Clear filters</button></>
        : `No invoices or drafts for ${periodLabel}. Issued invoices stay in their issue month.`}
    </div> : <>
      <table className="sales-table mt-4">
        <caption className="sr-only">Invoices and drafts for {periodLabel}</caption>
        <thead><tr><th scope="col">Reference</th><th scope="col" className="hidden md:table-cell">Partner</th><th scope="col" className="hidden md:table-cell">Issue date</th><th scope="col" className="hidden md:table-cell">Status</th><th scope="col" className="sales-amount hidden md:table-cell">Amount and outstanding</th><th scope="col"><span className="sr-only">Actions</span></th></tr></thead>
        <tbody>{visible.map((record) => <tr key={record.reference}>
          <th scope="row"><span className="block font-semibold">{record.reference}</span>
            <span className="block md:hidden mt-1">{partnerLabel(record.partner)}</span>
            <span className="block md:hidden text-gray-600 mt-1">{recordDate(record)} · {record.status}</span>
            <span className="block md:hidden font-semibold mt-1 whitespace-nowrap">{displayAmount(record.amountMinor)}</span>
            {record.status !== 'Draft' && <span className="block md:hidden text-gray-600 mt-1">Outstanding <span className="whitespace-nowrap">{formatMinorNGN(record.outstandingMinor)}</span></span>}</th>
          <td className="hidden md:table-cell">{partnerLabel(record.partner)}</td>
          <td className="hidden md:table-cell">{recordDate(record)}</td>
          <td className="hidden md:table-cell">{record.status}</td>
          <td className="sales-amount hidden md:table-cell">{displayAmount(record.amountMinor)}
            {record.status !== 'Draft' && <span className="block text-gray-600 mt-1">Outstanding {formatMinorNGN(record.outstandingMinor)}</span>}</td>
          <td><div className="sales-row-actions">
            {record.status === 'Draft'
              ? <button type="button" className="sales-button" aria-label={`Open draft ${record.reference}`} onClick={() => onOpenDraft(record)}>Open</button>
              : <button id={invoiceOpenerId(record.reference)} type="button" className="sales-button" aria-label={`Open invoice ${record.reference}`} onClick={() => onOpenInvoice(record.reference, invoiceOpenerId(record.reference))}>Open</button>}
            <button id={`sales-obligations-${record.reference}`} type="button" className="sales-button" aria-label={`View purchase obligations for ${partnerLabel(record.partner)} from ${record.reference}`} onClick={() => onOpenPartner(record.partner.code, `sales-obligations-${record.reference}`)}>Obligations</button>
          </div></td>
        </tr>)}</tbody>
      </table>
      {controls}
    </>}
  </section>;
}

export function PartnerObligations({ simulation, partner, headingId, backLabel, onBack, onOpenInvoice }) {
  const { invoices, drafts, outstandingMinor, asOf } = partnerObligations(simulation, partner.code);
  const { visible, controls } = useBoundedPage(invoices, partner.code, headingId);
  return <section className="sales-paper" aria-labelledby={headingId}>
    <p className="text-xs font-semibold tracking-widest uppercase text-amber-800">Fictional simulation</p>
    <h2 id={headingId} tabIndex={-1} className="text-lg font-semibold mt-1">Purchase obligations for {partnerLabel(partner)}</h2>
    <p className="sales-notice mt-3">{PURCHASE_NOTE}</p>
    {invoices.length ? <>
      <dl className="sales-facts">
        <div><dt>Issued invoices</dt><dd>{formatCount(invoices.length)}</dd></div>
        <div><dt>{`Outstanding as of ${formatDate(asOf)}`}</dt><dd>{formatMinorNGN(outstandingMinor)}</dd></div>
      </dl>
      <p className="text-xs text-gray-600 mt-2">This balance covers this account's invoices from every issue month, up to its latest simulated issue or collection on {formatDate(asOf)}. It is not a month-end balance for any reporting month.</p>
      <table className="sales-table mt-4">
        <caption className="sr-only">Issued invoices for {partnerLabel(partner)}</caption>
        <thead><tr><th scope="col">Reference</th><th scope="col" className="hidden sm:table-cell">Issue date</th><th scope="col" className="hidden sm:table-cell">Status</th><th scope="col" className="sales-amount hidden sm:table-cell">Outstanding</th><th scope="col"><span className="sr-only">Actions</span></th></tr></thead>
        <tbody>{visible.map((record) => <tr key={record.reference}>
          <th scope="row"><span className="block font-semibold">{record.reference}</span>
            <span className="block sm:hidden text-gray-600 mt-1">{formatDate(record.date)} · {record.status} · Outstanding</span>
            <span className="block sm:hidden font-semibold mt-1 whitespace-nowrap">{formatMinorNGN(record.outstandingMinor)}</span></th>
          <td className="hidden sm:table-cell whitespace-nowrap">{formatDate(record.date)}</td>
          <td className="hidden sm:table-cell">{record.status}</td>
          <td className="sales-amount hidden sm:table-cell">{formatMinorNGN(record.outstandingMinor)}</td>
          <td className="text-right"><button id={`sales-partner-open-${record.reference}`} type="button" className="sales-button" aria-label={`Open invoice ${record.reference}`} onClick={() => onOpenInvoice(record.reference, `sales-partner-open-${record.reference}`)}>Open</button></td>
        </tr>)}</tbody>
      </table>
      {controls}
    </> : <p role="status" className="text-sm text-gray-600 mt-4">No issued invoices for this account in this simulation, so it has no simulated purchase obligation to show.</p>}
    {drafts.length > 0 && <div className="mt-4">
      <h3 className="text-sm font-semibold">Drafts excluded from outstanding</h3>
      <ul aria-label="Drafts excluded from outstanding" className="mt-2 text-sm text-gray-600">{drafts.map((draft) => <li key={draft.reference}>{draft.reference} · intended {formatPeriod(draft.period)} · {displayAmount(draft.amountMinor)}</li>)}</ul>
    </div>}
    <div className="sales-actions"><button type="button" className="sales-button" onClick={onBack}>{backLabel}</button></div>
  </section>;
}

// The second click of a double click lands on a form the first has just cleared.
const ignoreRepeatClick = (event) => {
  if (event.detail > 1) event.preventDefault();
};

function InvoiceCollections({ invoice, balance, nextCollectionSequence, onRecord }) {
  const [date, setDate] = useState(balance.asOf);
  const [amount, setAmount] = useState('');
  const [attempted, setAttempted] = useState(false);
  const [recorded, setRecorded] = useState(null);
  const headingId = `sales-collections-heading-${invoice.reference}`;
  const dateErrorId = `sales-collection-date-error-${invoice.reference}`;
  const amountErrorId = `sales-collection-amount-error-${invoice.reference}`;
  const { visible, controls } = useBoundedPage(balance.history, invoice.reference, headingId);
  const errors = collectionErrors(invoice, balance.outstandingMinor, { date, amount });
  const amountError = attempted || amount ? errors.amount : null;
  const edit = (setter) => (event) => {
    setter(event.target.value);
    setRecorded(null);
  };
  const submit = (event) => {
    event.preventDefault();
    setAttempted(true);
    if (errors.date || errors.amount) {
      document.getElementById(`sales-collection-${errors.date ? 'date' : 'amount'}-${invoice.reference}`)?.focus();
      return;
    }
    onRecord({ actionId: collectionActionId(invoice.reference, nextCollectionSequence), invoiceReference: invoice.reference, date, amount });
    setRecorded({ reference: collectionReferenceFor(nextCollectionSequence), amountMinor: parseAmountMinor(amount) });
    setAmount('');
    setAttempted(false);
    // Paying in full removes the form and the button holding focus.
    requestAnimationFrame(() => document.getElementById(headingId)?.focus());
  };
  return <section className="mt-6" aria-labelledby={headingId}>
    <h3 id={headingId} tabIndex={-1} className="text-base font-semibold">Invoice collections</h3>
    <p className="text-xs text-gray-600 mt-1">Fictional collections reduce only this invoice's purchase obligation. They never generate commission or offset commission outstanding, and no money moves.</p>
    {recorded && <p role="status" className="sales-notice mt-3">Recorded {recorded.reference} for {formatMinorNGN(recorded.amountMinor)}.</p>}
    {balance.history.length ? <>
      <table className="sales-table mt-3">
        <caption className="sr-only">Collections recorded against {invoice.reference}</caption>
        <thead><tr><th scope="col">Date</th><th scope="col" className="hidden md:table-cell">Reference</th><th scope="col" className="sales-amount hidden md:table-cell">Amount</th><th scope="col" className="sales-amount hidden md:table-cell">Outstanding after</th></tr></thead>
        <tbody>{visible.map((collection) => <tr key={collection.reference}>
          <th scope="row"><span className="block whitespace-nowrap">{formatDate(collection.date)}</span>
            <span className="block md:hidden font-semibold mt-1">{collection.reference}</span>
            <span className="block md:hidden mt-1">Amount <span className="whitespace-nowrap">{formatMinorNGN(collection.amountMinor)}</span></span>
            <span className="block md:hidden text-gray-600 mt-1">Outstanding after <span className="whitespace-nowrap">{formatMinorNGN(collection.outstandingAfterMinor)}</span></span></th>
          <td className="hidden md:table-cell font-semibold">{collection.reference}</td>
          <td className="sales-amount hidden md:table-cell">{formatMinorNGN(collection.amountMinor)}</td>
          <td className="sales-amount hidden md:table-cell">{formatMinorNGN(collection.outstandingAfterMinor)}</td>
        </tr>)}</tbody>
      </table>
      {controls}
    </> : <p className="text-sm text-gray-600 mt-3">No collections recorded against this invoice yet.</p>}
    {balance.status === 'Paid' ? <p className="text-sm font-medium mt-4">Paid in full. No further collections can be recorded.</p>
      : <form noValidate className="mt-4" aria-label={`Record a collection against ${invoice.reference}`} onSubmit={submit}>
        <div className="sales-dates">
          <div className="flex flex-col gap-2"><label className="sales-field">Collection date<input id={`sales-collection-date-${invoice.reference}`} type="date" min={invoice.issueDate} max="9999-12-31" aria-invalid={Boolean(errors.date)} aria-describedby={errors.date ? dateErrorId : undefined} value={date} onChange={edit(setDate)} /></label>
            {errors.date && <span id={dateErrorId} className="sales-error">{errors.date}</span>}</div>
          <div className="flex flex-col gap-2"><label className="sales-field">Amount in NGN<input id={`sales-collection-amount-${invoice.reference}`} type="text" inputMode="decimal" autoComplete="off" aria-invalid={Boolean(amountError)} aria-describedby={amountError ? amountErrorId : undefined} value={amount} onChange={edit(setAmount)} /></label>
            {amountError && <span id={amountErrorId} className="sales-error">{amountError}</span>}</div>
        </div>
        <div className="sales-actions"><button type="submit" className="sales-button sales-primary" onClick={ignoreRepeatClick}>Record collection</button>
          <p className="text-xs text-gray-600">Up to {formatMinorNGN(balance.outstandingMinor)} outstanding. Collections cannot be refunded or reversed in this simulation.</p></div>
      </form>}
  </section>;
}

export function InvoiceDetail({ invoice, simulation, headingId, backLabel, onBack, onOpenPartner, onRecordCollection }) {
  const openerId = `sales-invoice-partner-${invoice.reference}`;
  const balance = invoiceBalance(simulation, invoice);
  return <section className="sales-paper" aria-labelledby={headingId}>
    <p className="text-xs font-semibold tracking-widest uppercase text-amber-800">Fictional simulation</p>
    <h2 id={headingId} tabIndex={-1} className="text-lg font-semibold mt-1">Simulated invoice {invoice.reference}</h2>
    <dl className="sales-facts">
      <div><dt>Status</dt><dd>{balance.status}</dd></div>
      <div><dt>Seller</dt><dd>{invoice.seller}</dd></div>
      <div><dt>Buyer</dt><dd>{partnerLabel(invoice.buyer)}</dd></div>
      <div><dt>Issue date</dt><dd>{formatDate(invoice.issueDate)}</dd></div>
      <div><dt>Due date</dt><dd>{displayDate(invoice.dueDate)}</dd></div>
      <div><dt>Currency</dt><dd>{invoice.currency}</dd></div>
      <div><dt>Collected</dt><dd>{formatMinorNGN(balance.collectedMinor)}</dd></div>
      <div><dt>{`Outstanding as of ${formatDate(balance.asOf)}`}</dt><dd>{formatMinorNGN(balance.outstandingMinor)}</dd></div>
    </dl>
    <p className="text-xs text-gray-600 mt-2">This balance includes every collection recorded up to {formatDate(balance.asOf)}. It is not a month-end balance for any reporting month.</p>
    <table className="sales-table mt-5">
      <caption className="sr-only">Invoice lines for {invoice.reference}</caption>
      <thead><tr><th scope="col">Product</th><th scope="col" className="sales-amount hidden sm:table-cell">Quantity</th><th scope="col" className="sales-amount hidden sm:table-cell">Unit price</th><th scope="col" className="sales-amount">Line total</th></tr></thead>
      <tbody>{invoice.lines.map((line) => <tr key={line.productCode}>
        <th scope="row"><span className="block font-semibold">{line.productCode}</span> <span className="block">{line.description}</span>
          <span className="block sm:hidden text-gray-600 mt-1">{quantityLabel(line.quantity, line.unit)} × {formatMinorNGN(line.unitPriceMinor)}</span></th>
        <td className="sales-amount hidden sm:table-cell">{quantityLabel(line.quantity, line.unit)}</td>
        <td className="sales-amount hidden sm:table-cell">{formatMinorNGN(line.unitPriceMinor)}</td>
        <td className="sales-amount">{formatMinorNGN(line.lineTotalMinor)}</td>
      </tr>)}</tbody>
      <tfoot><tr><th scope="row">Total</th><td className="hidden sm:table-cell" /><td className="hidden sm:table-cell" /><td className="sales-amount">{formatMinorNGN(invoice.totalMinor)}</td></tr></tfoot>
    </table>
    <InvoiceCollections invoice={invoice} balance={balance} nextCollectionSequence={simulation.nextCollectionSequence} onRecord={onRecordCollection} />
    <p className="sales-notice mt-5">Simplified fictional demonstration with fictional prices: not an actual purchase obligation or an operational tax invoice. Taxes and discounts are not modeled. {PURCHASE_NOTE} These details stay fixed after issue, whichever reporting month is selected.</p>
    <div className="sales-actions">
      <button type="button" className="sales-button" onClick={onBack}>{backLabel}</button>
      <button id={openerId} type="button" className="sales-button" onClick={() => onOpenPartner(invoice.buyer.code, openerId)}>View purchase obligations for {partnerLabel(invoice.buyer)}</button>
    </div>
  </section>;
}
