import { units } from './inventoryPresentation.js';

export default function InventorySummary({ summary, view }) {
  const metrics = view === 'coverage' ? [
    ['Invoice coverage gaps', summary.no_invoice_record_count, 'Dealer-product combinations'],
    ['Affected dealers', summary.distinct_dealer_count],
    ['Activations without invoice evidence', summary.total_activation_count],
  ] : view === 'within' ? [
    ['Within recorded purchases', summary.within_allocation_count, 'Dealer-product combinations'],
    ['Recorded purchased units', summary.total_recorded_purchased_units, 'Not a stock balance'],
    ['Activation records', summary.total_activation_count],
  ] : [
    ['Observed excess units', summary.total_gap_units, 'Across observed mismatches only'],
    ['Observed mismatches', summary.confirmed_mismatch_count, 'Dealer-product combinations'],
    ['Invoice coverage gaps', summary.no_invoice_record_count, 'Dealer-product combinations'],
  ];
  const viewNote = view === 'coverage'
    ? 'Purchased quantities and excess are unknown until matching invoice evidence is available.'
    : view === 'within'
      ? 'Purchases use the available invoice dataset. The difference from activations is not a stock balance.'
      : 'Missing invoice quantities are excluded from excess units.';
  return <section className="overview-surface" aria-label="Current-filter inventory summary">
    <dl className="grid md:grid-cols-3">{metrics.map(([label, value, metricNote], i) => <div key={label} className="p-5 sm:p-6">
      <dt className="text-sm text-gray-600">{label}</dt><dd className={`${i === 0 ? 'text-4xl' : 'text-3xl'} font-semibold tabular-nums tracking-tight mt-2`}>{units(value)}</dd>
      {metricNote && <dd className="text-xs text-gray-600 mt-3 leading-relaxed">{metricNote}</dd>}
    </div>)}</dl>
    <p className="border-t border-gray-200 px-5 py-3 text-xs text-gray-600">Totals cover all pages for the current filters. {viewNote}</p>
  </section>;
}
