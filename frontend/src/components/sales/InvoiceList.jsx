// Finance's invoices for one issue month. The server pages, filters and totals the set.

import { formatCount, formatDate, formatMinorNGN, formatPeriod } from '../../lib/format.js';
import { invoiceOpenerId, partnerLabel } from './salesDisplay.js';
import { PartnerCell, StatusBadge } from './SalesParts.jsx';
import { ReadState, usePagedQuery } from './SalesReads.jsx';
import { recordsQuery } from './useSalesQueries.js';

export const INVOICES_HEADING = 'sales-invoices-heading';

export default function InvoiceList({ period, statuses, filters: { search, status }, onFiltersChange, onOpenInvoice }) {
  const periodLabel = formatPeriod(period);
  const term = search.trim();
  const { query: records, controls } = usePagedQuery(`${period}|${term.toLowerCase()}|${status}`, INVOICES_HEADING,
    (page) => recordsQuery({ mon_period: period, search: term, status, ...page }), (data) => data.pagination);
  const summary = records.data?.summary;
  const visible = records.data?.items ?? [];
  const filtered = Boolean(term || status);
  const clearFilters = () => {
    onFiltersChange({ search: '', status: '' });
    document.getElementById('sales-invoice-search')?.focus();
  };
  return <section aria-labelledby={INVOICES_HEADING}>
    <div className="sales-sec">
      <h2 id={INVOICES_HEADING} tabIndex={-1} aria-label={`Invoices for ${periodLabel}`} className="sales-h">Invoices · {periodLabel}</h2>
      {summary && <dl className="sales-totals" aria-label="Totals for all matching invoices">
        <div><dt>Matching invoices</dt><dd>{formatCount(summary.count)}</dd></div>
        <div><dt>Outstanding purchase obligation</dt><dd>{formatMinorNGN(summary.outstanding_minor)}</dd></div>
      </dl>}
    </div>
    <div className="sales-filters">
      <label><span className="sr-only">Search invoices by partner or account code</span><input id="sales-invoice-search" className="overview-select w-full" type="search" value={search} maxLength={200} placeholder="Partner name or account code" onChange={(event) => onFiltersChange({ search: event.target.value, status })} /></label>
      <label><span className="sr-only">Status</span><select className="overview-select w-full" value={status} onChange={(event) => onFiltersChange({ search, status: event.target.value })}>
        <option value="">All statuses</option>
        {statuses.map((option) => <option key={option} value={option}>{option}</option>)}
      </select></label>
    </div>
    {!summary && <div className="sales-body"><ReadState query={records} what="invoice list" /></div>}
    {summary && records.isError && <div className="sales-body"><ReadState query={records} what="invoice list" /></div>}
    {summary && (!summary.count ? <div role="status" className="sales-body sales-muted">
      {filtered ? <>No invoices in {periodLabel} match your search and status. <button type="button" className="overview-button mt-2 block" onClick={clearFilters}>Clear filters</button></>
        : `No invoices for ${periodLabel}. Invoices stay in their issue month.`}
    </div> : <>
      <table className="sales-table">
        <caption className="sr-only">Invoices for {periodLabel}</caption>
        <thead><tr><th scope="col">Reference</th><th scope="col" className="hidden lg:table-cell">Partner</th><th scope="col" className="hidden lg:table-cell">Issue date</th><th scope="col" className="hidden lg:table-cell">Status</th><th scope="col" className="sales-num hidden lg:table-cell">Amount</th><th scope="col" className="sales-num hidden lg:table-cell">Outstanding</th><th scope="col"><span className="sr-only">Actions</span></th></tr></thead>
        <tbody>{visible.map((record) => <tr key={record.reference}>
          <th scope="row"><span className="block sales-strong">{record.reference}</span>
            <span className="block lg:hidden mt-1">{partnerLabel(record.partner)}</span>
            <span className="block lg:hidden sales-muted mt-1">{formatDate(record.date)} · <StatusBadge status={record.status} /></span>
            <span className="block lg:hidden sales-strong mt-1 whitespace-nowrap">{formatMinorNGN(record.amount_minor)}</span>
            <span className="block lg:hidden sales-muted mt-1">Outstanding <span className="whitespace-nowrap">{formatMinorNGN(record.outstanding_minor)}</span></span></th>
          <td className="hidden lg:table-cell"><PartnerCell partner={record.partner} /></td>
          <td className="hidden lg:table-cell whitespace-nowrap">{formatDate(record.date)}</td>
          <td className="hidden lg:table-cell"><StatusBadge status={record.status} /></td>
          <td className="sales-num hidden lg:table-cell">{formatMinorNGN(record.amount_minor)}</td>
          <td className={`sales-num hidden lg:table-cell ${record.outstanding_minor ? 'sales-strong' : ''}`}>{formatMinorNGN(record.outstanding_minor)}</td>
          <td className="sales-row-actions"><button id={invoiceOpenerId(record.reference)} type="button" className="overview-button sales-go" aria-label={`Open invoice ${record.reference}`} onClick={() => onOpenInvoice(record.reference, invoiceOpenerId(record.reference))}>Open</button></td>
        </tr>)}</tbody>
      </table>
      {controls}
      <p className="sales-foot">Outstanding counts every collection recorded up to {formatDate(summary.as_of)}, including any dated after {periodLabel}. It is not a month-end balance for {periodLabel}.</p>
    </>)}
  </section>;
}
