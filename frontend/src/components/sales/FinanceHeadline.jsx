// The month's position, from a server summary that no invoice filter or page changes.

import { formatMinorNGN, formatPeriod } from '../../lib/format.js';
import { quantityLabel } from './salesDisplay.js';
import { ReadState } from './SalesReads.jsx';

export default function FinanceHeadline({ query, period, onReview }) {
  const summary = query.data;
  if (!summary) return <div className="overview-surface sales-card-pad"><ReadState query={query} what="period summary" /></div>;
  const { orders_awaiting: awaiting, invoiced_minor: invoiced, collected_minor: collected, outstanding_minor: outstanding, open_invoices: openInvoices, partners_owing: partnersOwing } = summary;
  const coverage = invoiced ? (collected / invoiced) * 100 : null;
  return <section className="overview-surface sales-hero" aria-label={`Partner Sales summary for ${formatPeriod(period)}`}>
    <div className="sales-tint">
      <p>Outstanding purchase obligation</p>
      <p className="sales-big overview-headline">{formatMinorNGN(outstanding)}</p>
      <p className="sales-muted">{openInvoices ? `Owed to MTN by ${quantityLabel(partnersOwing, 'trade partner')}, across ${quantityLabel(openInvoices, 'open invoice')}.` : `No open invoices for ${formatPeriod(period)}.`}</p>
      {awaiting.count > 0 && <div className="sales-actions mt-3.5">
        <button type="button" className="overview-button overview-primary sales-go" onClick={onReview}>Review {quantityLabel(awaiting.count, 'order')}</button>
        <span className="sales-muted">{formatMinorNGN(awaiting.total_minor)} awaiting a decision</span>
      </div>}
    </div>
    <div>
      <dl className="sales-two">
        <div><dt className="sales-muted">Invoiced</dt><dd className="sales-figure">{formatMinorNGN(invoiced)}</dd></div>
        <div><dt className="sales-muted">Collected</dt><dd className="sales-figure">{formatMinorNGN(collected)}</dd></div>
      </dl>
      <div className="mt-3.5 flex justify-between gap-4"><span id="sales-coverage-label" className="sales-muted">Collection coverage</span><span className="text-sm font-semibold">{coverage === null ? 'No invoices' : `${coverage.toFixed(1)}%`}</span></div>
      {coverage !== null && <progress className="overview-progress w-full mt-2 block" aria-labelledby="sales-coverage-label" max={100} value={coverage} />}
      <p className="sales-note mt-3.5">Purchase obligations are what partners would owe MTN. They are never netted against commission.</p>
    </div>
  </section>;
}
