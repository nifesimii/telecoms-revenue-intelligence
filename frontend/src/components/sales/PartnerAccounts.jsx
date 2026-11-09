// Every trade partner with what it would owe MTN, and the way into its two accounts.

import { formatCount, formatMinorNGN } from '../../lib/format.js';
import { partnerLabel } from './salesDisplay.js';
import { PartnerCell } from './SalesParts.jsx';
import { ReadState, usePagedQuery } from './SalesReads.jsx';
import { partnerAccountsQuery } from './useSalesQueries.js';

export const PARTNERS_HEADING = 'sales-partner-heading';
export const partnerCommissionOpener = (code) => `sales-partner-commission-${code}`;

export default function PartnerAccounts({ search, onSearchChange, onOpenObligations, onOpenCommission }) {
  const term = search.trim();
  const { query: accounts, controls } = usePagedQuery(term.toLowerCase(), PARTNERS_HEADING, (page) => partnerAccountsQuery({ search: term, ...page }), (data) => data.pagination);
  const total = accounts.data?.pagination.total;
  return <section aria-labelledby={PARTNERS_HEADING}>
    <div className="sales-sec">
      <div><h2 id={PARTNERS_HEADING} tabIndex={-1} className="sales-h">Partner accounts</h2>
        <p className="sales-muted">Select a partner to inspect what they would owe MTN and what MTN would owe them.</p></div>
      {accounts.data && <span className="sales-muted">{formatCount(total)} matching {total === 1 ? 'partner' : 'partners'}</span>}
    </div>
    <div className="sales-filters">
      <label><span className="sr-only">Find a partner</span><input className="overview-select w-full" type="search" value={search} maxLength={200} placeholder="Partner name or account code" onChange={(event) => onSearchChange(event.target.value)} /></label>
    </div>
    {(!accounts.data || accounts.isError) && <div className="sales-body"><ReadState query={accounts} what="partner list" /></div>}
    {accounts.data && (!total ? <p role="status" className="sales-body sales-muted">No partners match your search. Try another name or account code.</p> : <>
      <table className="sales-table">
        <caption className="sr-only">Partner accounts</caption>
        <thead><tr><th scope="col">Partner</th><th scope="col" className="sales-num hidden sm:table-cell">Open invoices</th><th scope="col" className="sales-num hidden sm:table-cell">Purchase obligation</th><th scope="col"><span className="sr-only">Actions</span></th></tr></thead>
        <tbody>{accounts.data.items.map(({ partner, open_invoices: openInvoices, outstanding_minor: outstandingMinor }) => <tr key={partner.code}>
          <th scope="row"><span className="sales-strong"><PartnerCell partner={partner} /></span>
            <span className="block sm:hidden sales-muted mt-1">{formatCount(openInvoices)} open · <span className="whitespace-nowrap">{formatMinorNGN(outstandingMinor)}</span></span></th>
          <td className="sales-num hidden sm:table-cell">{formatCount(openInvoices)}</td>
          <td className="sales-num hidden sm:table-cell">{formatMinorNGN(outstandingMinor)}</td>
          <td className="sales-row-actions"><div className="inline-flex flex-wrap justify-end gap-2">
            <button id={`sales-partner-obligations-${partner.code}`} type="button" className="overview-button" aria-label={`View purchase obligations for ${partnerLabel(partner)}`} onClick={() => onOpenObligations(partner.code, `sales-partner-obligations-${partner.code}`)}>Obligations</button>
            <button id={partnerCommissionOpener(partner.code)} type="button" className="overview-button" aria-label={`View commission account for ${partnerLabel(partner)}`} onClick={() => onOpenCommission(partner.code, partnerCommissionOpener(partner.code))}>Commission</button>
          </div></td>
        </tr>)}</tbody>
      </table>
      {controls}
    </>)}
  </section>;
}
