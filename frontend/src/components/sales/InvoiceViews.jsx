// Partner Sales invoice browsing: the bounded list, one partner's purchase
// obligations and a frozen invoice. Reads the simulation only; it never edits one.

import { useState } from 'react';
import PaginationControls from '../shared/PaginationControls.jsx';
import { formatCount, formatDate, formatMinorNGN, formatPeriod } from '../../lib/format.js';
import { STATUSES, invoiceOpenerId, invoiceStatus, matchingRecords, partnerLabel, partnerObligations, quantityLabel, summarizeRecords } from './salesSimulation.js';

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
    {!records.length ? <div role="status" className="text-sm text-gray-600 mt-4">
      {filtered ? <>No invoices or drafts in {periodLabel} match your search and status. <button type="button" className="sales-button mt-2 block" onClick={clearFilters}>Clear filters</button></>
        : `No invoices or drafts for ${periodLabel}. Issued invoices stay in their issue month.`}
    </div> : <>
      <table className="sales-table mt-4">
        <caption className="sr-only">Invoices and drafts for {periodLabel}</caption>
        <thead><tr><th scope="col">Reference</th><th scope="col" className="hidden md:table-cell">Partner</th><th scope="col" className="hidden md:table-cell">Issue date</th><th scope="col" className="hidden md:table-cell">Status</th><th scope="col" className="sales-amount hidden md:table-cell">Amount</th><th scope="col"><span className="sr-only">Actions</span></th></tr></thead>
        <tbody>{visible.map((record) => <tr key={record.reference}>
          <th scope="row"><span className="block font-semibold">{record.reference}</span>
            <span className="block md:hidden mt-1">{partnerLabel(record.partner)}</span>
            <span className="block md:hidden text-gray-600 mt-1">{recordDate(record)} · {record.status}</span>
            <span className="block md:hidden font-semibold mt-1 whitespace-nowrap">{displayAmount(record.amountMinor)}</span></th>
          <td className="hidden md:table-cell">{partnerLabel(record.partner)}</td>
          <td className="hidden md:table-cell">{recordDate(record)}</td>
          <td className="hidden md:table-cell">{record.status}</td>
          <td className="sales-amount hidden md:table-cell">{displayAmount(record.amountMinor)}</td>
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
      <p className="text-xs text-gray-600 mt-2">This balance covers this account's invoices from every issue month, up to its latest simulated invoice activity on {formatDate(asOf)}. It is not a month-end balance for any reporting month.</p>
      <table className="sales-table mt-4">
        <caption className="sr-only">Issued invoices for {partnerLabel(partner)}</caption>
        <thead><tr><th scope="col">Reference</th><th scope="col" className="hidden sm:table-cell">Issue date</th><th scope="col" className="hidden sm:table-cell">Status</th><th scope="col" className="sales-amount hidden sm:table-cell">Outstanding</th><th scope="col"><span className="sr-only">Actions</span></th></tr></thead>
        <tbody>{visible.map((record) => <tr key={record.reference}>
          <th scope="row"><span className="block font-semibold">{record.reference}</span>
            <span className="block sm:hidden text-gray-600 mt-1">{formatDate(record.date)} · {record.status} · Outstanding</span>
            <span className="block sm:hidden font-semibold mt-1 whitespace-nowrap">{formatMinorNGN(record.amountMinor)}</span></th>
          <td className="hidden sm:table-cell whitespace-nowrap">{formatDate(record.date)}</td>
          <td className="hidden sm:table-cell">{record.status}</td>
          <td className="sales-amount hidden sm:table-cell">{formatMinorNGN(record.amountMinor)}</td>
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

export function InvoiceDetail({ invoice, headingId, backLabel, onBack, onOpenPartner }) {
  const openerId = `sales-invoice-partner-${invoice.reference}`;
  return <section className="sales-paper" aria-labelledby={headingId}>
    <p className="text-xs font-semibold tracking-widest uppercase text-amber-800">Fictional simulation</p>
    <h2 id={headingId} tabIndex={-1} className="text-lg font-semibold mt-1">Simulated invoice {invoice.reference}</h2>
    <dl className="sales-facts">
      <div><dt>Status</dt><dd>{invoiceStatus(invoice)}</dd></div>
      <div><dt>Seller</dt><dd>{invoice.seller}</dd></div>
      <div><dt>Buyer</dt><dd>{partnerLabel(invoice.buyer)}</dd></div>
      <div><dt>Issue date</dt><dd>{formatDate(invoice.issueDate)}</dd></div>
      <div><dt>Due date</dt><dd>{displayDate(invoice.dueDate)}</dd></div>
      <div><dt>Currency</dt><dd>{invoice.currency}</dd></div>
      <div><dt>{`Outstanding as of ${formatDate(invoice.issueDate)}`}</dt><dd>{formatMinorNGN(invoice.totalMinor)}</dd></div>
    </dl>
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
    <p className="sales-notice mt-5">Simplified fictional demonstration with fictional prices: not an actual purchase obligation or an operational tax invoice. Taxes and discounts are not modeled. {PURCHASE_NOTE} These details stay fixed after issue, whichever reporting month is selected.</p>
    <div className="sales-actions">
      <button type="button" className="sales-button" onClick={onBack}>{backLabel}</button>
      <button id={openerId} type="button" className="sales-button" onClick={() => onOpenPartner(invoice.buyer.code, openerId)}>View purchase obligations for {partnerLabel(invoice.buyer)}</button>
    </div>
  </section>;
}
