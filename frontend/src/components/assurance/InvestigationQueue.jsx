import { useRef } from 'react';
import { formatNGN, formatPeriod } from '../../lib/format.js';
import DealerEvidence, { AUDIT_MODULE } from './DealerEvidence.jsx';

const TONES = { HIGH: 'text-red-800 bg-red-50', MEDIUM: 'text-amber-800 bg-amber-50', LOW: 'text-gray-700 bg-gray-100' };
const LABELS = {
  COMMISSION_DISPUTE: 'Payment disputed', PARTIAL_PAYMENT: 'Partial settlement',
  PENDING_SETTLEMENT: 'Settlement pending', ZERO_COMMISSION_ACTIVATION: 'Zero-commission activations',
  INVENTORY_MISMATCH: 'Inventory discrepancy', ALL_UNQUALIFIED: 'No qualified activations',
  HIGH_UNQUALIFIED_RATE: 'High unqualified rate',
};

export function openEvidence(onNavigate, module, dealerId = '', productCode = '') {
  if (module === 'payment' || module === 'activation') onNavigate(module, { tab: 'exceptions', search: dealerId });
  else onNavigate('audit', { module: AUDIT_MODULE[module] || 'zero_commission',
    search: productCode ? `${dealerId}:${productCode}` : dealerId });
}

export default function InvestigationQueue({ data, busy, search, setSearch, severity, setSeverity,
  module, setModule, offset, setOffset, onNavigate, onAsk, period, evidence, setEvidence }) {
  const evidenceTrigger = useRef(null);
  const showEvidence = (event, dealer, selectedModule) => {
    evidenceTrigger.current = event.currentTarget;
    setEvidence({ dealer, module: selectedModule });
  };
  return <section className="overview-surface min-w-0" aria-labelledby="queue-title" aria-busy={busy}>
    <div className="p-5 border-b border-gray-200">
      <div className="flex flex-wrap items-baseline justify-between gap-2">
        <h2 id="queue-title" className="text-lg font-semibold">Investigate next</h2>
        <span className="text-sm text-gray-500">{data.affected_dealers.toLocaleString()} affected accounts</span>
      </div>
      <p className="text-sm text-gray-600 mt-1">Ranked by severity, then outstanding amount. Each dealer appears once.</p>
      <p className="text-xs text-gray-500 mt-2">{data.finding_count.toLocaleString()} findings across all modules · {data.cross_module_dealers.toLocaleString()} accounts with findings in multiple modules</p>
      <div className="mt-4 grid grid-cols-1 sm:grid-cols-[minmax(0,1fr)_auto_auto] gap-2">
        <input type="search" aria-label="Search investigation queue" placeholder="Search dealer name or code" className="overview-select min-w-0" value={search} onChange={(e) => setSearch(e.target.value)} />
        <select aria-label="Queue severity" className="overview-select" value={severity} onChange={(e) => setSeverity(e.target.value)}>
          <option value="">All severities</option><option value="HIGH">High</option><option value="MEDIUM">Medium</option><option value="LOW">Low</option>
        </select>
        <select aria-label="Queue module" className="overview-select" value={module} onChange={(e) => setModule(e.target.value)}>
          <option value="">All modules</option>{['commission', 'activation', 'inventory', 'payment'].map((m) => <option key={m} value={m}>{m[0].toUpperCase() + m.slice(1)}</option>)}
        </select>
      </div>
    </div>
    {!data.items.length ? <div role="status" className="p-8 text-center">
      <p className="font-medium">{data.finding_count ? 'No dealers match these filters' : data.complete ? 'No findings require review' : 'No findings available from the checked sources'}</p>
      <p className="text-sm text-gray-500 mt-2">{data.finding_count ? 'Try a different dealer, severity or module.' : 'Review the evidence coverage alongside this assessment.'}</p>
    </div> : <ol className="divide-y divide-gray-200">
      {data.items.map((row, i) => <li key={row.dealer_id} className="p-5 hover:bg-gray-50/60">
        <div className="flex items-start gap-3">
          <span className="hidden sm:block text-xs text-gray-400 tabular-nums pt-1 w-5 shrink-0">{offset + i + 1}</span>
          <div className="min-w-0 flex-1">
            <div className="flex flex-wrap items-start justify-between gap-2">
              <div><h3 className="font-semibold text-sm">{row.dealer_name}</h3><p className="text-xs text-gray-500 mt-1">Dealer {row.dealer_id} · {row.finding_count} finding{row.finding_count === 1 ? '' : 's'}</p></div>
              <span className={`text-xs px-2 py-1 rounded font-medium ${TONES[row.severity] || TONES.LOW}`}>{row.severity.toLowerCase()} priority</span>
            </div>
            <p className="mt-3 text-sm font-medium">{LABELS[row.lead_finding.type] || row.lead_finding.type.replaceAll('_', ' ').toLowerCase()}</p>
            <p className="mt-1 text-sm text-gray-600 break-words">{row.lead_finding.description}</p>
            <div className="mt-3 flex flex-wrap gap-x-4 gap-y-2 items-center">
              <span className="text-xs text-gray-500">Evidence:</span>
              {row.modules.map((m) => <button key={m} disabled={busy} aria-expanded={evidence?.dealer === row.dealer_id && evidence.module === m} aria-label={`View ${m} evidence for dealer ${row.dealer_id}`} className="text-xs capitalize underline underline-offset-4 text-gray-700 disabled:opacity-50" onClick={(event) => showEvidence(event, row.dealer_id, m)}>{m}</button>)}
            </div>
            <div className="mt-4 flex flex-wrap items-center justify-between gap-3">
              <div className="text-xs text-gray-500">Recorded outstanding <span className="block text-sm font-semibold text-gray-900 tabular-nums mt-0.5">{row.amount_outstanding === null ? 'Payment evidence unavailable' : formatNGN(row.amount_outstanding)}</span></div>
              <div className="flex flex-wrap items-center gap-3">
                {onAsk && <button disabled={busy} className="text-xs text-gray-600 underline" onClick={() => onAsk(`Explain the findings for ${row.dealer_name} (dealer code ${row.dealer_id}) for ${formatPeriod(period)}. Start with: ${row.lead_finding.description}. Use the evidence and documented rules; distinguish missing evidence from confirmed discrepancies.`, {
                  kind: 'findings', period, dealer_id: row.dealer_id, dealer_name: row.dealer_name,
                  finding: { module: row.lead_finding.module, type: row.lead_finding.type,
                    ...(row.lead_finding.module === 'inventory' && row.lead_finding.product_code ? { product_code: row.lead_finding.product_code } : {}) },
                })}>Ask Atlas about these findings</button>}
                <button disabled={busy} aria-expanded={evidence?.dealer === row.dealer_id} aria-label={`View evidence for ${row.dealer_name}, dealer ${row.dealer_id}`} className="overview-button" onClick={(event) => showEvidence(event, row.dealer_id, row.lead_finding.module)}>View evidence →</button>
              </div>
            </div>
            {evidence?.dealer === row.dealer_id && row.module_findings[evidence.module] && <DealerEvidence key={`${period}:${row.dealer_id}:${evidence.module}`} finding={row.module_findings[evidence.module]} period={period} onClose={() => { setEvidence(null); evidenceTrigger.current?.focus(); }} onNavigate={onNavigate} />}
          </div>
        </div>
      </li>)}
    </ol>}
    <div className="p-4 border-t border-gray-200 flex flex-wrap items-center justify-between gap-3 text-sm">
      <span role="status" className="text-gray-500">{busy ? 'Updating queue…' : `${data.total ? offset + 1 : 0}–${offset + data.items.length} of ${data.total.toLocaleString()} accounts`}</span>
      <div className="flex gap-2">
        <button className="overview-button" disabled={busy || offset === 0} onClick={() => setOffset(Math.max(0, offset - data.limit))}>Previous</button>
        <button className="overview-button" disabled={busy || offset + data.limit >= data.total} onClick={() => setOffset(offset + data.limit)}>Next</button>
      </div>
    </div>
  </section>;
}
