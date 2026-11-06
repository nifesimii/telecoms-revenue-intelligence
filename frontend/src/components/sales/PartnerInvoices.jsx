// A partner's own invoices from every issue month, read-only. MTN Finance issues them
// and records their collections; the partner sees each change on their next refresh.

import { useState } from 'react';
import { useQuery } from '@tanstack/react-query';
import { formatCount, formatDate, formatMinorNGN } from '../../lib/format.js';
import { ReadState, usePagedQuery } from './InvoiceViews.jsx';
import { ownInvoicesQuery } from './useSalesQueries.js';

export default function PartnerInvoices({ statuses, onOpen }) {
  const [status, setStatus] = useState('');
  const { query: invoices, controls } = usePagedQuery(`own-invoices|${status}`, 'sales-own-invoices-heading',
    (page) => ownInvoicesQuery({ status, ...page }), (data) => data.pagination, useQuery);
  const summary = invoices.data?.summary;
  const visible = invoices.data?.items ?? [];
  const clearStatus = () => {
    setStatus('');
    document.getElementById('sales-own-invoice-status')?.focus();
  };
  return <section className="sales-paper" aria-labelledby="sales-own-invoices-heading">
    <h2 id="sales-own-invoices-heading" tabIndex={-1} className="text-lg font-semibold">Your invoices</h2>
    <p className="text-xs text-gray-600 mt-1">Fictional invoices MTN Finance issued from your orders, from every issue month. MTN Finance records collections against them. Refresh to see new invoices and collections.</p>
    <div className="sales-filters">
      <label className="sales-field">Status<select id="sales-own-invoice-status" value={status} onChange={(event) => setStatus(event.target.value)}>
        <option value="">All statuses</option>
        {statuses.map((option) => <option key={option} value={option}>{option}</option>)}
      </select></label>
    </div>
    <ReadState query={invoices} what="invoice list" />
    {summary && <><dl className="sales-facts" aria-label="Totals for all matching invoices">
      <div><dt>Matching invoices</dt><dd>{formatCount(summary.count)}</dd></div>
      <div><dt>Outstanding purchase obligation</dt><dd>{formatMinorNGN(summary.outstanding_minor)}</dd></div>
    </dl>
    {summary.count > 0 && <p className="text-xs text-gray-600 mt-2">Outstanding counts every collection recorded up to {formatDate(summary.as_of)}. It is what you would owe MTN for goods bought, separate from any commission MTN owes you.</p>}
    {!summary.count ? <div role="status" className="text-sm text-gray-600 mt-4">
      {status ? <>None of your invoices are {status.toLowerCase()}. <button type="button" className="sales-button mt-2 block" onClick={clearStatus}>Show all statuses</button></>
        : 'MTN Finance has not issued you any invoices yet.'}
    </div> : <>
      <table className="sales-table mt-4">
        <caption className="sr-only">Your invoices</caption>
        <thead><tr><th scope="col">Reference</th><th scope="col" className="hidden sm:table-cell">Issue date</th><th scope="col" className="hidden sm:table-cell">Status</th><th scope="col" className="sales-amount hidden sm:table-cell">Amount and outstanding</th><th scope="col"><span className="sr-only">Actions</span></th></tr></thead>
        <tbody>{visible.map((record) => <tr key={record.reference}>
          <th scope="row"><span className="block font-semibold">{record.reference}</span>
            <span className="block sm:hidden text-gray-600 mt-1">{formatDate(record.date)} · {record.status}</span>
            <span className="block sm:hidden font-semibold mt-1 whitespace-nowrap">{formatMinorNGN(record.amount_minor)}</span>
            <span className="block sm:hidden text-gray-600 mt-1">Outstanding <span className="whitespace-nowrap">{formatMinorNGN(record.outstanding_minor)}</span></span></th>
          <td className="hidden sm:table-cell whitespace-nowrap">{formatDate(record.date)}</td>
          <td className="hidden sm:table-cell">{record.status}</td>
          <td className="sales-amount hidden sm:table-cell">{formatMinorNGN(record.amount_minor)}
            <span className="block text-gray-600 mt-1">Outstanding {formatMinorNGN(record.outstanding_minor)}</span></td>
          <td className="text-right"><button id={`sales-own-invoice-open-${record.reference}`} type="button" className="sales-button" aria-label={`Open invoice ${record.reference}`} onClick={() => onOpen(record.reference, `sales-own-invoice-open-${record.reference}`)}>Open</button></td>
        </tr>)}</tbody>
      </table>
      {controls}
    </>}</>}
  </section>;
}
