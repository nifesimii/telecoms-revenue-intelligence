import { formatPeriod } from '../../lib/format.js';
import { money, statusLabel } from './paymentPresentation.js';

export default function PaymentComparison({ rows, period, comparison, rowRefs, onSelect }) {
  return <>
    <p className="p-5 text-sm text-gray-600">Only accounts present in both {formatPeriod(comparison)} and {formatPeriod(period)}. Entrants and exits are excluded. Sorted by absolute paid change; more paid does not automatically mean a better position.</p>
    <div className="overflow-auto max-h-[640px]" tabIndex={0} role="region" aria-label="Scrollable period comparison"><table className="commission-table w-full text-sm text-left">
      <thead className="sticky top-0"><tr><th>Dealer</th><th>Settled {formatPeriod(comparison)}</th><th>Settled {formatPeriod(period)}</th><th>Paid change</th><th>Status {formatPeriod(comparison)} → {formatPeriod(period)}</th><th>Evidence</th></tr></thead>
      <tbody>{rows.map((r) => <tr key={r.dealer_id}><td className="min-w-48">{r.dealer_name}<p className="text-xs text-gray-500 mt-1">{r.dealer_id}</p></td>{[r.amount_paid_a, r.amount_paid_b, r.delta_paid].map((v, i) => <td key={i} className="text-right whitespace-nowrap tabular-nums">{money(v)}</td>)}<td>{statusLabel(r.payment_status_a)} → {statusLabel(r.payment_status_b)}</td><td><button ref={(node) => { rowRefs.current[r.dealer_id] = node; }} className="overview-button" aria-label={`View evidence for ${r.dealer_name}, ${r.dealer_id}`} onClick={() => onSelect(r.dealer_id)}>View evidence</button></td></tr>)}</tbody>
    </table></div>
  </>;
}
