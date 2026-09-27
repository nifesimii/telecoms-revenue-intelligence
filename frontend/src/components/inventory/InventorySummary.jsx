import { units } from './inventoryPresentation.js';

export default function InventorySummary({ summary, view }) {
  const metrics = view === 'coverage' ? [
    ['Invoice coverage gaps', summary.no_invoice_record_count, 'Dealer-product combinations without matched invoices'],
    ['Affected dealers', summary.distinct_dealer_count, 'Distinct dealers across these coverage gaps'],
    ['Activations without invoice evidence', summary.total_activation_count, 'Activation records across these coverage gaps'],
  ] : view === 'within' ? [
    ['Within recorded purchases', summary.within_allocation_count, 'Dealer-product combinations without positive gaps'],
    ['Recorded purchased units', summary.total_recorded_purchased_units, 'Available invoice quantities for these combinations'],
    ['Activation records', summary.total_activation_count, 'Reported activations for these combinations'],
  ] : [
    ['Observed excess units', summary.total_gap_units, 'Across observed mismatches only'],
    ['Observed mismatches', summary.confirmed_mismatch_count, 'Dealer-product combinations requiring investigation'],
    ['Invoice coverage gaps', summary.no_invoice_record_count, 'Dealer-product combinations without matched invoices'],
  ];
  const note = view === 'coverage'
    ? 'Purchased quantities and excess are unknown until matching invoice evidence is available.'
    : view === 'within'
      ? 'Purchases use the available invoice dataset. The difference from activations is not a stock balance.'
      : 'Missing invoice quantities are excluded from excess units.';
  return <section className="overview-surface" aria-label="Current-filter inventory summary">
    <dl className="grid md:grid-cols-3">{metrics.map(([label, value, note], i) => <div key={label} className={`p-5 sm:p-6 ${i === 0 ? 'bg-yellow-50 rounded-t-lg md:rounded-tr-none' : ''}`}>
      <dt className="text-sm text-gray-600">{label}</dt><dd className="text-3xl font-semibold tabular-nums tracking-tight mt-2">{units(value)}</dd>
      <dd className="text-xs text-gray-600 mt-3 leading-relaxed">{note}</dd>
    </div>)}</dl>
    <p className="border-t border-gray-200 px-5 py-3 text-xs text-gray-600">Current-filter totals across all matching pages. Combination counts are not unique dealer counts. {note}</p>
  </section>;
}
