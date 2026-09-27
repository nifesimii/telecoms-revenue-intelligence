import { useEffect, useRef } from 'react';
import { formatPeriod } from '../../lib/format.js';
import { ComparisonStatus } from './InventoryComparisonTable.jsx';
import { gapPercent, gapUnits, subjectFor, units } from './inventoryPresentation.js';
import InventoryEvidence from './InventoryEvidence.jsx';

export default function InventoryDetail({ row, period, retrievedAt, onBack, onAsk, onTicket }) {
  const heading = useRef(null);
  useEffect(() => { heading.current?.focus(); }, []);
  const hasInvoice = row.total_units_purchased != null;
  const metrics = [
    ['Recorded purchased units', units(row.total_units_purchased)],
    ['Activation records', units(row.activation_count)],
    ['Excess units', gapUnits(row.inventory_gap)],
    ['Excess %', gapPercent(row.gap_pct)],
  ];
  return <div className="space-y-5">
    <button className="overview-button" onClick={onBack}>← Back to comparison</button>
    <header ref={heading} tabIndex={-1}>
      <h2 className="text-xl font-semibold break-words">{row.dealer_name || row.dealer_id}</h2>
      <p className="mt-2 text-sm text-gray-600">Dealer {row.dealer_id} · {formatPeriod(period)}</p>
      <p className="mt-2 font-medium break-words">{row.product_name || 'Product name unavailable'} · {row.product_code}</p>
      {row.scenario_id && <p className="mt-3 text-sm font-medium text-blue-900">{row.scenario_label}</p>}
    </header>
    <section className="overview-surface p-5 sm:p-6">
      <div className="flex flex-wrap items-center justify-between gap-3"><h3 className="font-semibold">Observed comparison</h3><ComparisonStatus type={row.finding_type} /></div>
      <dl className="grid grid-cols-2 lg:grid-cols-4 gap-5 mt-5 text-sm">{metrics.map(([label, value]) => <div key={label}><dt className="text-gray-600">{label}</dt><dd className="mt-2 text-xl font-semibold tabular-nums">{value}</dd></div>)}</dl>
      <p className="mt-5 text-sm text-gray-600">{row.data_coverage_note}</p>
      <p className="mt-2 text-sm text-gray-600">{hasInvoice
        ? 'Excess units = activation records minus recorded purchased units. Excess % uses recorded purchases as the denominator. A negative difference is not a stock balance.'
        : 'Purchases and excess are unknown because no matching invoice was found in the available data. Missing invoice evidence does not mean zero purchased units.'}</p>
      {hasInvoice && row.total_units_purchased === 0 && <p className="mt-2 text-sm text-amber-900">The recorded purchase quantity is zero; a percentage cannot be calculated.</p>}
      <p className="mt-4 text-sm"><strong>{units(row.qualified_count)}</strong> qualified activation records for this product. Qualification is context only; it does not identify whether excess units earned commission.</p>
      <p className="mt-4 text-xs text-gray-500">Comparison retrieved {new Date(retrievedAt).toLocaleString()}. {row.scenario_id
        ? 'This scenario uses fictional shared purchase evidence or a deliberately retained missing quantity. It does not supply source invoice lines.'
        : 'Invoice quantities are derived from deduplicated records in the available dataset; invoice lines and source freshness are not provided here.'}</p>
    </section>
    {row.scenario_id ? <section className="overview-surface p-5"><h3 className="font-semibold">Synthetic scenario evidence</h3><p className="mt-2 text-sm text-gray-600">This comparison demonstrates fictional purchase evidence. Existing saved trails are not shown as verification of these quantities. The scenario does not establish actual stock, carryover, product-code aliases or commission exposure.</p></section>
      : row.finding_type !== 'WITHIN_ALLOCATION' ? <InventoryEvidence subject={subjectFor(row)} period={period} />
      : <section className="overview-surface p-5"><h3 className="font-semibold">Verification scope</h3><p className="mt-2 text-sm text-gray-600">No positive gap is observed. Within-purchase comparisons are not subjects of the current Inventory verification process. Invoice-window limitations still apply.</p></section>}
    <section className="overview-surface p-5"><h3 className="font-semibold">Next steps</h3>
      <p className="mt-2 text-sm text-gray-600">Check purchase coverage, prior-period carryover and confirmed product-code aliases before acting on an observed excess.</p>
      <div className="mt-4 flex flex-wrap gap-3">
        {onAsk && <button className="overview-button" onClick={() => onAsk(`Investigate Inventory for dealer ${row.dealer_id} (${row.dealer_name}), product ${row.product_code} (${row.product_name}), reporting period ${period}. The comparison has ${units(row.activation_count)} activation records, ${units(row.total_units_purchased)} recorded purchased units and status ${row.finding_type}. ${row.scenario_id ? `Synthetic scenario: ${row.scenario_label}. Fictional shared purchase quantities do not establish authentic invoice evidence, stock carryover or aliases.` : ''} Missing values are unknown. Explain only what the available data and Inventory KB support about prior-period carryover, confirmed SKU aliases and invoice coverage. Do not infer commission on excess units from dealer-wide totals. State the tools and periods used and any additional evidence needed.`)}>Ask about this comparison →</button>}
        <button className="overview-button" onClick={onTicket}>Prepare coverage ticket</button>
      </div>
      <p className="mt-3 text-xs text-gray-500">Coverage tickets include all affected dealers in the reporting period, not just this comparison.</p>
    </section>
  </div>;
}
