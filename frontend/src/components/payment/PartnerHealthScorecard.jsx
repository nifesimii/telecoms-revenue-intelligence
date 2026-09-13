import { money, percent } from './paymentPresentation.js';

export default function PartnerHealthScorecard({ rows, rowRefs, onSelect }) {
  return <>
    <p className="p-5 text-sm text-gray-600">Existing score = settlement rate × 0.5 + (100 − zero-commission rate) × 0.3 + 20 when neither disputed nor partially paid. Healthy ≥80; Watch ≥60; At risk &lt;60. Missing activation evidence currently contributes a zero zero-commission rate, and over-settlement can push the score above 100. This is a screening indicator, not verified financial health. Settlement changes are percentage points.</p>
    <div className="overflow-auto max-h-[640px]" tabIndex={0} role="region" aria-label="Scrollable account health"><table className="commission-table w-full text-sm text-left">
      <thead className="sticky top-0"><tr><th>Dealer</th><th>Score / band</th><th>Settlement</th><th>Settlement change</th><th>Commission yield</th><th>Zero commission</th><th>Outstanding</th><th>Evidence</th></tr></thead>
      <tbody>{rows.map((r) => <tr key={r.dealer_id}><td className="min-w-48">{r.dealer_name}<p className="text-xs text-gray-500 mt-1">{r.dealer_id}</p></td><td>{r.health_score} / {r.health_band?.toLowerCase()}</td><td>{percent(r.settlement_rate_pct)}</td><td>{r.settlement_rate_delta == null ? 'Unavailable' : `${r.settlement_rate_delta > 0 ? '+' : ''}${r.settlement_rate_delta.toFixed(1)} pp`}</td><td>{percent(r.commission_yield_pct)}</td><td>{percent(r.zero_commission_rate_pct)}</td><td className="text-right tabular-nums whitespace-nowrap">{money(r.outstanding_ngn)}</td><td><button ref={(node) => { rowRefs.current[r.dealer_id] = node; }} className="overview-button" aria-label={`View evidence for ${r.dealer_name}, ${r.dealer_id}`} onClick={() => onSelect(r.dealer_id)}>View evidence</button></td></tr>)}</tbody>
    </table></div>
  </>;
}
