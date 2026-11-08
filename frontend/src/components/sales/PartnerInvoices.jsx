// A partner's own invoices from every issue month, read-only. MTN Finance issues them
// and records their collections; the partner sees each change on their next refresh.

import { useState } from 'react';
import { useQuery } from '@tanstack/react-query';
import { formatCount, formatDate, formatMinorNGN } from '../../lib/format.js';
import { StatusBadge } from './SalesParts.jsx';
import { ReadState, usePagedQuery } from './SalesReads.jsx';
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
  return <section className="overview-surface" aria-labelledby="sales-own-invoices-heading">
    <div className="sales-sec">
      <div><h2 id="sales-own-invoices-heading" tabIndex={-1} aria-label="Your invoices" className="sales-h">Invoices</h2>
        <p className="sales-muted">Issued by MTN Finance from your orders, from every issue month. Refresh to see new invoices and collections.</p></div>
      {summary && <dl className="sales-totals" aria-label="Totals for all matching invoices">
        <div><dt>Matching invoices</dt><dd>{formatCount(summary.count)}</dd></div>
        <div><dt>Outstanding purchase obligation</dt><dd>{formatMinorNGN(summary.outstanding_minor)}</dd></div>
      </dl>}
    </div>
    <div className="sales-filters">
      <label><span className="sr-only">Status</span><select id="sales-own-invoice-status" className="overview-select w-full" value={status} onChange={(event) => setStatus(event.target.value)}>
        <option value="">All statuses</option>
        {statuses.map((option) => <option key={option} value={option}>{option}</option>)}
      </select></label>
    </div>
    {(!summary || invoices.isError) && <div className="sales-body"><ReadState query={invoices} what="invoice list" /></div>}
    {summary && (!summary.count ? <div role="status" className="sales-body sales-muted">
      {status ? <>None of your invoices are {status.toLowerCase()}. <button type="button" className="overview-button mt-2 block" onClick={clearStatus}>Show all statuses</button></>
        : 'MTN Finance has not issued you any invoices yet.'}
    </div> : <>
      <table className="sales-table">
        <caption className="sr-only">Your invoices</caption>
        <thead><tr><th scope="col">Reference</th><th scope="col" className="hidden sm:table-cell">Issue date</th><th scope="col" className="hidden sm:table-cell">Due date</th><th scope="col" className="hidden sm:table-cell">Status</th><th scope="col" className="sales-num hidden sm:table-cell">Amount</th><th scope="col" className="sales-num hidden sm:table-cell">Outstanding</th><th scope="col"><span className="sr-only">Actions</span></th></tr></thead>
        <tbody>{visible.map((record) => <tr key={record.reference}>
          <th scope="row"><span className="block sales-strong">{record.reference}</span>
            <span className="block sm:hidden sales-muted mt-1">{formatDate(record.date)} · <StatusBadge status={record.status} /></span>
            <span className="block sm:hidden sales-strong mt-1 whitespace-nowrap">{formatMinorNGN(record.amount_minor)}</span>
            <span className="block sm:hidden sales-muted mt-1">Outstanding <span className="whitespace-nowrap">{formatMinorNGN(record.outstanding_minor)}</span></span></th>
          <td className="hidden sm:table-cell whitespace-nowrap">{formatDate(record.date)}</td>
          <td className="hidden sm:table-cell whitespace-nowrap">{formatDate(record.due_date)}</td>
          <td className="hidden sm:table-cell"><StatusBadge status={record.status} /></td>
          <td className="sales-num hidden sm:table-cell">{formatMinorNGN(record.amount_minor)}</td>
          <td className={`sales-num hidden sm:table-cell ${record.outstanding_minor ? 'sales-strong' : ''}`}>{formatMinorNGN(record.outstanding_minor)}</td>
          <td className="sales-row-actions"><button id={`sales-own-invoice-open-${record.reference}`} type="button" className="overview-button sales-go" aria-label={`Open invoice ${record.reference}`} onClick={() => onOpen(record.reference, `sales-own-invoice-open-${record.reference}`)}>Open</button></td>
        </tr>)}</tbody>
      </table>
      {controls}
      <p className="sales-foot">Outstanding counts every collection recorded up to {formatDate(summary.as_of)}. It is what you would owe MTN for goods bought, separate from any commission MTN owes you.</p>
    </>)}
  </section>;
}
