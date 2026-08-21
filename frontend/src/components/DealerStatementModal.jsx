// Per-period dealer statement — Finance/RA internal view.
//
// Composes commission entitlement + payment settlement + variance +
// linked audit trails into one screen. Reads whichever payment source
// the backend is on (simulated | apdp) and badges the source explicitly.
//
// Launched as a modal from a dealer row (Payment tab, Activation tab,
// Commission tab). Mirrors the shape of DisputeDraftModal so users
// already familiar with the dispute-draft flow have zero relearning.
//
// Downloads a markdown snapshot of the statement for pasting into a
// finance ticket or emailing to Revenue Assurance.

import { useEffect, useMemo, useState } from 'react';
import { getDealerStatement } from '../api/client.js';
import { formatNGN, formatPeriod } from '../lib/format.js';

const HEADLINE_TONE = {
  PAID_IN_FULL: 'bg-emerald-100 text-emerald-800 border-emerald-200',
  UNDERPAID:    'bg-red-100 text-red-800 border-red-200',
  OVERPAID:     'bg-amber-100 text-amber-800 border-amber-200',
};

const AUDIT_CONCLUSION_TONE = {
  PAID: 'text-emerald-700', PAID_IN_FULL: 'text-emerald-700',
  RECONCILED: 'text-emerald-700', POLICY_MET: 'text-emerald-700',
  NOT_PAID: 'text-red-700', UNDERPAID: 'text-red-700',
  EXCESS_ACTIVATION: 'text-red-700', POLICY_VIOLATED: 'text-red-700',
  OVERPAID: 'text-amber-700', DISPUTED_ROUNDING: 'text-amber-700',
  MIXED_ATTRIBUTION: 'text-amber-700',
  INSUFFICIENT_DATA: 'text-gray-600',
};

function Row({ label, value, tone = 'text-gray-900', bold = false }) {
  return (
    <div className="flex items-baseline justify-between py-1 border-b border-gray-100 last:border-b-0">
      <span className="text-xs text-gray-600">{label}</span>
      <span className={`tabular-nums text-sm ${tone} ${bold ? 'font-semibold' : ''}`}>{value}</span>
    </div>
  );
}

function SectionCard({ title, badge, children }) {
  return (
    <div className="bg-white border border-gray-200 rounded-md p-3">
      <div className="flex items-center justify-between mb-2">
        <div className="text-[11px] uppercase tracking-wide text-gray-500 font-semibold">
          {title}
        </div>
        {badge}
      </div>
      {children}
    </div>
  );
}

function DataSourceBadge({ source }) {
  if (source === 'apdp') {
    return (
      <span className="inline-block px-1.5 py-0.5 text-[9px] font-semibold uppercase tracking-wide border rounded bg-emerald-100 text-emerald-800 border-emerald-200">
        Live · APDP
      </span>
    );
  }
  return (
    <span className="inline-block px-1.5 py-0.5 text-[9px] font-semibold uppercase tracking-wide border rounded bg-amber-100 text-amber-800 border-amber-200">
      Simulated
    </span>
  );
}

function composeMarkdown(s) {
  if (!s) return '';
  const lines = [];
  lines.push(`# Dealer Statement — ${s.dealer_name} (${s.dealer_id})`);
  lines.push('');
  lines.push(`**Period:** ${formatPeriod(s.mon_period)}   **Profile class:** ${s.account_profile_class}`);
  lines.push(`**Payment data source:** ${s.payment.data_source === 'apdp' ? 'Live · APDP' : 'Simulated'}`);
  lines.push('');
  lines.push('## Position');
  lines.push(`- Expected commission: **${formatNGN(s.position.expected_ngn)}**`);
  lines.push(`- Amount settled:      **${formatNGN(s.position.paid_ngn)}**`);
  lines.push(`- Outstanding:         **${formatNGN(s.position.outstanding_ngn)}** ${s.position.variance_pct != null ? `(${s.position.variance_pct.toFixed(2)}%)` : ''}`);
  lines.push(`- Verdict:             **${s.position.headline}**`);
  lines.push('');
  lines.push('## Commission side (activation entitlement)');
  lines.push(`- Total activations: ${s.commission.total_activations.toLocaleString()}`);
  lines.push(`- Qualified: ${s.commission.qualified_activation_count.toLocaleString()}`);
  lines.push(`- Zero-commission records: ${s.commission.zero_commission_count.toLocaleString()}`);
  lines.push('- Breakdown by denomination:');
  for (const [k, v] of Object.entries(s.commission.by_denomination || {})) {
    lines.push(`  * ${k}: ${formatNGN(v)}`);
  }
  lines.push('');
  lines.push('## Payment side (settlement)');
  lines.push(`- Amount paid: ${formatNGN(s.payment.amount_paid_ngn)}`);
  lines.push(`- Payment status: ${s.payment.payment_status || '—'}`);
  if (s.payment.apdp_detail) {
    const d = s.payment.apdp_detail;
    lines.push(`- APDP detail: ${d.settlement_count} settlements (${d.paid_count} paid, ${d.partial_count} partial, ${d.disputed_count} disputed)`);
    lines.push(`- Sales captured: ${d.sale_count} totalling ${formatNGN(d.total_sales_ngn)}`);
    lines.push(`- Reconciliation status: ${d.reconciliation_status}`);
  }
  if (s.orsc) {
    lines.push('');
    lines.push('## ORSC side (informational)');
    lines.push(`- Devices: ${s.orsc.device_count}`);
    lines.push(`- Total subscription: ${formatNGN(s.orsc.total_subscription_amount_ngn)}`);
    lines.push(`- Zero-amount records: ${s.orsc.zero_amount_count}`);
  }
  if ((s.audit_trails || []).length > 0) {
    lines.push('');
    lines.push('## Linked audit trails');
    for (const t of s.audit_trails) {
      lines.push(`- ${t.label}: **${t.conclusion}** (${t.confidence}) — trail_id ${t.trail_id}`);
    }
  }
  lines.push('');
  lines.push(`_Generated by FBB Trade Partner Intelligence · ${new Date().toISOString()}_`);
  return lines.join('\n');
}

export default function DealerStatementModal({ open, onClose, dealerId, dealerName, period }) {
  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState(null);
  const [copyOk, setCopyOk] = useState(false);

  useEffect(() => {
    if (!open || !dealerId || !period) return;
    let cancelled = false;
    setLoading(true);
    setError(null);
    setData(null);
    setCopyOk(false);
    getDealerStatement(dealerId, period)
      .then((d) => !cancelled && setData(d))
      .catch((e) => !cancelled && setError(e?.response?.data?.detail || e?.message || String(e)))
      .finally(() => !cancelled && setLoading(false));
    return () => { cancelled = true; };
  }, [open, dealerId, period]);

  const markdown = useMemo(() => composeMarkdown(data), [data]);

  async function copyMarkdown() {
    if (!markdown) return;
    try {
      await navigator.clipboard.writeText(markdown);
      setCopyOk(true);
      setTimeout(() => setCopyOk(false), 2000);
    } catch (e) {
      setError('Clipboard write failed: ' + String(e));
    }
  }

  function downloadMarkdown() {
    if (!markdown || !data) return;
    const blob = new Blob([markdown], { type: 'text/markdown;charset=utf-8' });
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = `statement_${data.dealer_id}_${data.mon_period}.md`;
    document.body.appendChild(a);
    a.click();
    document.body.removeChild(a);
    URL.revokeObjectURL(url);
  }

  if (!open) return null;

  const headlineTone = data?.position ? (HEADLINE_TONE[data.position.headline] || '') : '';

  return (
    <div
      role="dialog"
      aria-modal="true"
      className="fixed inset-0 z-50 flex items-center justify-center bg-black/40 p-4"
      onClick={(e) => e.target === e.currentTarget && onClose?.()}
    >
      <div className="bg-white rounded-lg shadow-2xl w-full max-w-4xl max-h-[90vh] flex flex-col">
        <div className="px-5 py-3 border-b border-gray-200 flex items-center justify-between shrink-0">
          <div>
            <h2 className="text-sm font-semibold text-gray-900">
              Dealer statement — {data?.dealer_name || dealerName || dealerId}
            </h2>
            <div className="text-[11px] text-gray-500 mt-0.5">
              {formatPeriod(period)}
              {data && (
                <>
                  {' · '}
                  <span className="font-mono">{data.dealer_id}</span>
                  {' · '}
                  {data.account_profile_class}
                </>
              )}
            </div>
          </div>
          <button
            onClick={onClose}
            className="text-gray-400 hover:text-gray-700 text-lg leading-none px-2"
            aria-label="Close"
          >
            ×
          </button>
        </div>

        <div className="flex-1 min-h-0 overflow-auto p-5">
          {loading && (
            <div className="text-sm text-gray-500 italic">Loading statement…</div>
          )}
          {error && (
            <div className="text-sm text-red-700 bg-red-50 border border-red-200 rounded px-3 py-2">
              {error}
            </div>
          )}
          {data && (
            <div className="flex flex-col gap-4">
              {/* Position headline */}
              <div className={`border rounded-md px-4 py-3 ${headlineTone}`}>
                <div className="flex flex-wrap items-baseline gap-x-6 gap-y-1">
                  <span className="text-[11px] uppercase tracking-wide font-semibold">Verdict</span>
                  <span className="text-lg font-bold">{data.position.headline}</span>
                  <span className="tabular-nums text-sm ml-auto">
                    Outstanding: <span className="font-semibold">{formatNGN(data.position.outstanding_ngn)}</span>
                    {data.position.variance_pct != null && (
                      <span className="ml-2 text-xs">({data.position.variance_pct.toFixed(2)}%)</span>
                    )}
                  </span>
                </div>
              </div>

              {/* 2-column: commission side + payment side */}
              <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                <SectionCard title="Commission side (entitlement)">
                  <Row label="Expected commission" value={formatNGN(data.commission.expected_ngn)} bold />
                  <Row label="Total activations" value={data.commission.total_activations.toLocaleString()} />
                  <Row label="Qualified" value={data.commission.qualified_activation_count.toLocaleString()} tone="text-emerald-700" />
                  <Row label="Zero-commission records" value={data.commission.zero_commission_count.toLocaleString()} tone={data.commission.zero_commission_count > 0 ? 'text-amber-700' : 'text-gray-900'} />
                  {Object.keys(data.commission.by_denomination || {}).length > 0 && (
                    <div className="mt-2">
                      <div className="text-[10px] uppercase tracking-wide text-gray-500 font-semibold mb-1">By denomination</div>
                      {Object.entries(data.commission.by_denomination).map(([k, v]) => (
                        <Row key={k} label={k} value={formatNGN(v)} />
                      ))}
                    </div>
                  )}
                </SectionCard>

                <SectionCard
                  title="Payment side (settlement)"
                  badge={<DataSourceBadge source={data.payment.data_source} />}
                >
                  <Row label="Amount settled" value={formatNGN(data.payment.amount_paid_ngn)} bold />
                  <Row label="Payment found" value={data.payment.payment_found ? 'Yes' : 'No'} />
                  <Row label="Status" value={data.payment.payment_status || '—'} />
                  {data.payment.apdp_detail && (
                    <div className="mt-2">
                      <div className="text-[10px] uppercase tracking-wide text-gray-500 font-semibold mb-1">APDP detail</div>
                      <Row label="Settlements" value={`${data.payment.apdp_detail.settlement_count} (${data.payment.apdp_detail.paid_count} paid, ${data.payment.apdp_detail.partial_count} partial, ${data.payment.apdp_detail.disputed_count} disputed)`} />
                      <Row label="Sales captured" value={`${data.payment.apdp_detail.sale_count} · ${formatNGN(data.payment.apdp_detail.total_sales_ngn)}`} />
                      <Row label="Statements" value={`${data.payment.apdp_detail.statement_count} · ${formatNGN(data.payment.apdp_detail.statement_gross_revenue_ngn)}`} />
                      <Row label="Reconciliation status" value={data.payment.apdp_detail.reconciliation_status} />
                    </div>
                  )}
                </SectionCard>
              </div>

              {/* ORSC — informational only */}
              {data.orsc && (
                <SectionCard title="ORSC side (informational — not part of the reconciliation)">
                  <div className="grid grid-cols-3 gap-3">
                    <Row label="Devices" value={data.orsc.device_count.toLocaleString()} />
                    <Row label="Total subscription" value={formatNGN(data.orsc.total_subscription_amount_ngn)} />
                    <Row label="Zero-amount records" value={data.orsc.zero_amount_count.toLocaleString()} />
                  </div>
                </SectionCard>
              )}

              {/* Linked audit trails */}
              {data.audit_trails && data.audit_trails.length > 0 && (
                <SectionCard title="Linked audit trails">
                  <ul className="space-y-1.5">
                    {data.audit_trails.map((t) => (
                      <li key={t.module} className="flex items-baseline gap-3 text-xs">
                        <span className="font-semibold text-gray-800 min-w-[180px]">{t.label}</span>
                        <span className={`font-semibold ${AUDIT_CONCLUSION_TONE[t.conclusion] || 'text-gray-700'}`}>
                          {t.conclusion}
                        </span>
                        <span className="text-gray-500">{t.confidence}</span>
                        {t.trail_id != null && (
                          <span className="text-gray-400 font-mono ml-auto">trail_id {t.trail_id}</span>
                        )}
                      </li>
                    ))}
                  </ul>
                </SectionCard>
              )}
            </div>
          )}
        </div>

        {/* Footer actions */}
        <div className="px-5 py-3 border-t border-gray-200 flex items-center justify-end gap-2 shrink-0">
          <button
            onClick={copyMarkdown}
            disabled={!data}
            className="text-xs text-gray-700 hover:text-gray-900 font-medium border border-gray-200 rounded-md px-3 py-1.5 hover:bg-yellow-50 hover:border-mtn-yellow transition disabled:opacity-40"
          >
            {copyOk ? '✓ Copied' : 'Copy as markdown'}
          </button>
          <button
            onClick={downloadMarkdown}
            disabled={!data}
            className="text-xs text-gray-700 hover:text-gray-900 font-medium border border-gray-200 rounded-md px-3 py-1.5 hover:bg-yellow-50 hover:border-mtn-yellow transition disabled:opacity-40"
          >
            ⬇ Download .md
          </button>
          <button
            onClick={onClose}
            className="text-xs text-gray-700 hover:text-gray-900 font-medium border border-gray-200 rounded-md px-3 py-1.5 hover:bg-gray-50 transition"
          >
            Close
          </button>
        </div>
      </div>
    </div>
  );
}
