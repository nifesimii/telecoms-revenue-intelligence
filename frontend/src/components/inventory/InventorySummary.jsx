import { units } from './inventoryPresentation.js';

export default function InventorySummary({ summary, includeWithin }) {
  const metrics = [
    ['Observed excess units', summary.total_gap_units, 'Across observed mismatches only'],
    ['Observed mismatches', summary.confirmed_mismatch_count, 'Dealer-product combinations requiring investigation'],
    ['Invoice coverage gaps', summary.no_invoice_record_count, 'Dealer-product combinations without matched invoices'],
    ['Within recorded purchases', includeWithin ? summary.within_allocation_count : null, includeWithin ? 'Dealer-product combinations without positive gaps' : 'Available in the within-purchases view'],
  ];
  return <section className="overview-surface" aria-label="Current-filter inventory summary">
    <dl className="grid sm:grid-cols-2 xl:grid-cols-4">{metrics.map(([label, value, note], i) => <div key={label} className={`p-5 sm:p-6 ${i === 0 ? 'bg-yellow-50 rounded-t-lg sm:rounded-tr-none' : ''}`}>
      <dt className="text-sm text-gray-600">{label}</dt><dd className="text-3xl font-semibold tabular-nums tracking-tight mt-2">{units(value)}</dd>
      <dd className="text-xs text-gray-600 mt-3 leading-relaxed">{note}</dd>
    </div>)}</dl>
    <p className="border-t border-gray-200 px-5 py-3 text-xs text-gray-600">Current-filter totals across all matching pages. Combination counts are not unique dealer counts. Missing invoice quantities are excluded from excess units.</p>
  </section>;
}
