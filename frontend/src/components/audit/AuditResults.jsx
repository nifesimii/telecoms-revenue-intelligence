import { label, measureLabel, measureValue, savedTime, qualifications } from './auditPresentation.js';

export function AuditSummary({ summary, filtered }) {
  return <section className="overview-surface p-5" aria-label="Saved assessment scope">
    <h2 className="font-semibold">Full module · reporting period</h2>
    <p className="text-sm text-gray-600 mt-2">{summary.trail_count.toLocaleString()} saved trails · {summary.subject_count.toLocaleString()} subjects · {summary.dealer_count.toLocaleString()} distinct dealers</p>
    <h3 className="font-semibold mt-4">All matching results</h3>
    <p className="text-sm text-gray-600 mt-2">{filtered.trail_count.toLocaleString()} trails · {filtered.subject_count.toLocaleString()} subjects · {filtered.dealer_count.toLocaleString()} distinct dealers · {filtered.caveat_trail_count.toLocaleString()} trails with recorded caveats</p>
    <ul className="flex flex-wrap gap-x-5 gap-y-2 mt-3 text-sm">{filtered.breakdown.map((entry) => <li key={`${entry.conclusion}-${entry.confidence}`}>{label(entry.conclusion)} · {label(entry.confidence)}: <strong>{entry.count.toLocaleString()}</strong></li>)}</ul>
    <p className="text-xs text-gray-500 mt-3">Counts cover the whole filter set, not this page. Inventory subjects are dealer-products; other subjects are dealers. These are saved assessments, not independently verified financial outcomes.</p>
  </section>;
}
export default function AuditResults({ rows, onSelect, rowRefs, busy }) {
  return <div className="overflow-auto max-h-[65vh]">
    <table className="w-full min-w-[900px] text-sm text-left">
      <caption className="sr-only">Matching saved audit assessments</caption>
      <thead className="sticky top-0 bg-gray-50"><tr>{['Dealer / subject', 'Recorded conclusion', 'Recorded confidence', 'Supporting measures', 'Saved evidence', ''].map((heading, i) => <th key={i} scope="col" className="px-4 py-3 font-semibold">{heading || <span className="sr-only">Evidence action</span>}</th>)}</tr></thead>
      <tbody className="divide-y divide-gray-100">{rows.map((row) => <tr key={row.trail_id || row.partner_code} className="align-top">
        <td className="px-4 py-4"><p className="font-medium">{row.dealer_name}</p><p className="text-xs text-gray-500 mt-1">{row.dealer_id}</p>{row.product_code && <p className="mt-2">{row.product_name || 'Product'} <span className="text-gray-500">· {row.product_code}</span></p>}</td>
        <td className="px-4 py-4"><p className="font-medium">{label(row.conclusion)}</p>{qualifications(row).filter((note) => note.includes('payment')).map((note) => <p key={note} className="text-xs text-amber-900 mt-2 max-w-xs">{note}</p>)}</td>
        <td className="px-4 py-4">{label(row.confidence)}<p className="text-xs text-gray-500 mt-2">{row.caveat_steps.length ? `${row.caveat_steps.length} recorded caveat steps` : 'No recorded caveats'}</p>{row.limitations.length > 0 && <p className="text-xs text-amber-900 mt-2">Recorded limitations · see evidence</p>}</td>
        <td className="px-4 py-4"><dl className="space-y-2">{Object.entries(row.measures || {}).map(([key, value]) => <div key={key}><dt className="text-xs text-gray-500">{measureLabel(key)}</dt><dd className="tabular-nums">{measureValue(key, value)}</dd></div>)}</dl></td>
        <td className="px-4 py-4 text-xs text-gray-600"><p>{savedTime(row.generated_at)}</p><p className="mt-2">Source: {row.payment_source || 'Unavailable'}</p><p className="mt-2">Pipeline: {row.pipeline_version || 'Unavailable'}</p><p className="mt-2 break-all" title={row.run_id}>Run: {row.run_id || 'Unavailable'}</p></td>
        <td className="px-4 py-4"><button ref={(node) => { rowRefs.current[row.trail_id || row.partner_code] = node; }} disabled={busy} className="overview-button whitespace-nowrap" aria-label={`Open evidence for ${row.partner_code}`} onClick={() => onSelect(row)}>Open evidence</button></td>
      </tr>)}</tbody>
    </table>
  </div>;
}
