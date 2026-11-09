// One partner's purchase obligations across every issue month, for Finance.

import { formatCount, formatDate, formatMinorNGN } from '../../lib/format.js';
import { partnerLabel } from './salesDisplay.js';
import { DetailHeader, Disclaimer, Figures, StatusBadge } from './SalesParts.jsx';
import { ReadState, usePagedQuery } from './SalesReads.jsx';
import { obligationsQuery } from './useSalesQueries.js';

export const PURCHASE_NOTE = 'A purchase obligation is what the partner would owe MTN for goods bought. It is not commission, and it is not netted against the Partner Commission Account, the separate record of commission owed by MTN.';

export default function PartnerObligations({ partner, headingId, backLabel, onBack, onOpenInvoice, onOpenCommission }) {
  const { query: obligations, controls } = usePagedQuery(partner.code, headingId, (page) => obligationsQuery(partner.code, page), (data) => data.invoices.pagination);
  const { invoices, outstanding_minor: outstandingMinor, as_of: asOf } = obligations.data ?? {};
  const visible = invoices?.items ?? [];
  const commissionOpener = `sales-obligations-commission-${partner.code}`;
  return <section className="flex flex-col gap-6" aria-labelledby={headingId}>
    <DetailHeader eyebrow="Fictional simulation" title={partner.name} headingId={headingId} headingLabel={`Purchase obligations for ${partnerLabel(partner)}`} backLabel={backLabel} onBack={onBack} meta={`Purchase obligations · Account ${partner.code}`} />
    <div className="sales-detail">
      <div className="sales-stack">
        {(!invoices || obligations.isError) && <div className="overview-surface sales-card-pad"><ReadState query={obligations} what="account" /></div>}
        {invoices && (invoices.pagination.total ? <>
          <div className="overview-surface sales-card-pad">
            <dl><dt>{`Outstanding as of ${formatDate(asOf)}`}</dt><dd className="sales-big overview-headline">{formatMinorNGN(outstandingMinor)}</dd></dl>
            <Figures items={[['Issued invoices', formatCount(invoices.pagination.total)]]} />
            <p className="sales-note mt-3.5">This balance covers this account's invoices from every issue month, up to its latest simulated issue or collection on {formatDate(asOf)}. It is not a month-end balance for any reporting month.</p>
            <Disclaimer className="mt-2" summary="Fictional simulation, not an actual purchase obligation">{PURCHASE_NOTE}</Disclaimer>
          </div>
          <div className="overview-surface">
            <div className="sales-sec"><h2 className="sales-h">Issued invoices</h2></div>
            <table className="sales-table">
              <caption className="sr-only">Issued invoices for {partnerLabel(partner)}</caption>
              <thead><tr><th scope="col">Reference</th><th scope="col" className="hidden sm:table-cell">Issue date</th><th scope="col" className="hidden sm:table-cell">Status</th><th scope="col" className="sales-num hidden sm:table-cell">Outstanding</th><th scope="col"><span className="sr-only">Actions</span></th></tr></thead>
              <tbody>{visible.map((record) => <tr key={record.reference}>
                <th scope="row"><span className="block sales-strong">{record.reference}</span>
                  <span className="block sm:hidden sales-muted mt-1">{formatDate(record.date)} · <StatusBadge status={record.status} /> · Outstanding</span>
                  <span className="block sm:hidden sales-strong mt-1 whitespace-nowrap">{formatMinorNGN(record.outstanding_minor)}</span></th>
                <td className="hidden sm:table-cell whitespace-nowrap">{formatDate(record.date)}</td>
                <td className="hidden sm:table-cell"><StatusBadge status={record.status} /></td>
                <td className="sales-num hidden sm:table-cell">{formatMinorNGN(record.outstanding_minor)}</td>
                <td className="sales-row-actions"><button id={`sales-partner-open-${record.reference}`} type="button" className="overview-button sales-go" aria-label={`Open invoice ${record.reference}`} onClick={() => onOpenInvoice(record.reference, `sales-partner-open-${record.reference}`)}>Open</button></td>
              </tr>)}</tbody>
            </table>
            {controls}
          </div>
        </> : <div className="overview-surface sales-card-pad"><p role="status" className="sales-muted">No issued invoices for this account in this simulation, so it has no simulated purchase obligation to show.</p>
          <Disclaimer className="mt-2" summary="Fictional simulation, not an actual purchase obligation">{PURCHASE_NOTE}</Disclaimer></div>)}
      </div>
      <div className="overview-surface sales-rail">
        <h2 className="sales-h">{partner.name}</h2>
        <button id={commissionOpener} type="button" className="overview-button sales-full" aria-label={`View commission account for ${partnerLabel(partner)}`} onClick={() => onOpenCommission(partner.code, commissionOpener)}>View commission account</button>
      </div>
    </div>
  </section>;
}
