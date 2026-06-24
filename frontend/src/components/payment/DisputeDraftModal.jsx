// Dispute response draft modal.
//
// Opened from a Payment Exceptions row → composes a finance-ready dispute
// response letter via POST /payments/disputes/draft. The letter is
// deterministic (pure-Python template, no LLM), grounded in the same query
// layer the rest of the platform uses, and shipped as markdown ready to
// paste into an email or download as a .md file.
//
// The finance officer can also add a verbatim quote of the dealer's claim
// before composing — it's included in the letter so the recipient sees
// exactly what we're responding to.

import { useEffect, useState } from 'react';
import { draftDisputeResponse } from '../../api/client.js';
import { formatNGN, formatPeriod } from '../../lib/format.js';

const POSITION_TONE = {
  NO_FURTHER_ACTION: 'bg-emerald-100 text-emerald-800 border-emerald-200',
  PARTIAL_PAYMENT_AGREED: 'bg-amber-100 text-amber-800 border-amber-200',
  DISPUTE_DECLINED: 'bg-red-100 text-red-800 border-red-200',
  DECLINED_INSUFFICIENT_QUALIFICATION: 'bg-red-100 text-red-800 border-red-200',
};

const CAUSE_LABEL = {
  USP_SNAPSHOT_MISS: 'USP snapshot miss',
  OUTSIDE_6_MONTH_WINDOW: 'Outside 6-month window',
  NULL_PROFILE_CLASS: 'Missing profile class',
  HYNEX_DENOMINATION_SPLIT: 'Hynex denomination',
};

export default function DisputeDraftModal({ open, onClose, row, period }) {
  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState(null);
  const [disputeText, setDisputeText] = useState('');
  const [copyOk, setCopyOk] = useState(false);
  const [composed, setComposed] = useState(false);

  // Reset every time the modal opens for a new row.
  useEffect(() => {
    if (!open) return;
    setData(null);
    setError(null);
    setDisputeText('');
    setCopyOk(false);
    setComposed(false);
  }, [open, row?.distributor_code]);

  function compose() {
    if (!row || !period) return;
    setLoading(true);
    setError(null);
    setCopyOk(false);
    draftDisputeResponse({
      distributor_code: row.distributor_code,
      mon_period: period,
      dispute_text: disputeText.trim() || null,
      amount_paid: row.amount_paid != null ? Number(row.amount_paid) : null,
    })
      .then((d) => {
        setData(d);
        setComposed(true);
      })
      .catch((e) => setError(e?.response?.data?.detail || e?.message || String(e)))
      .finally(() => setLoading(false));
  }

  async function copyMarkdown() {
    if (!data?.markdown) return;
    try {
      await navigator.clipboard.writeText(data.markdown);
      setCopyOk(true);
      setTimeout(() => setCopyOk(false), 2000);
    } catch (e) {
      setError('Clipboard write failed: ' + String(e));
    }
  }

  function downloadMarkdown() {
    if (!data?.markdown) return;
    const blob = new Blob([data.markdown], { type: 'text/markdown;charset=utf-8' });
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = `${data.summary.reference}.md`;
    document.body.appendChild(a);
    a.click();
    document.body.removeChild(a);
    URL.revokeObjectURL(url);
  }

  if (!open) return null;

  const s = data?.summary;
  const positionTone = s ? POSITION_TONE[s.position_code] || 'bg-gray-100 text-gray-700 border-gray-200' : '';

  return (
    <div
      role="dialog"
      aria-modal="true"
      className="fixed inset-0 z-50 flex items-center justify-center bg-black/40 p-4"
      onClick={(e) => e.target === e.currentTarget && onClose?.()}
    >
      <div className="bg-white rounded-lg shadow-2xl w-full max-w-4xl max-h-[90vh] flex flex-col">
        <div className="px-5 py-3 border-b border-gray-200 flex items-center justify-between">
          <div>
            <h2 className="text-sm font-semibold text-gray-900">
              Compose dispute response — {row?.distributor_name || row?.distributor_code}
            </h2>
            <div className="text-[11px] text-gray-500 mt-0.5">
              Period {formatPeriod(period)} · Statement {formatNGN(row?.commission_owed)} · Outstanding {formatNGN(row?.amount_unpaid)}
            </div>
          </div>
          <button
            onClick={onClose}
            className="text-gray-400 hover:text-gray-900 text-xl leading-none px-2"
            title="Close"
          >
            ×
          </button>
        </div>

        <div className="flex-1 overflow-auto px-5 py-4">
          {!composed && (
            <>
              <label className="block text-[11px] uppercase tracking-wide text-gray-500 mb-1">
                Dealer's stated position (optional)
              </label>
              <textarea
                value={disputeText}
                onChange={(e) => setDisputeText(e.target.value)}
                rows={4}
                placeholder='e.g. "We activated 1,800 devices but only received commission on 1,200."'
                className="w-full text-sm border border-gray-300 rounded-md px-3 py-2 focus:outline-none focus:ring-2 focus:ring-mtn-yellow focus:border-mtn-yellow"
              />
              <p className="text-[11px] text-gray-500 mt-1">
                Quoted verbatim in the response letter. Leave blank to skip.
              </p>
              <div className="mt-4 flex justify-end">
                <button
                  onClick={compose}
                  disabled={loading}
                  className="px-4 py-2 rounded-md bg-mtn-yellow text-gray-900 text-sm font-semibold hover:brightness-95 disabled:opacity-50"
                >
                  {loading ? 'Composing…' : 'Compose response'}
                </button>
              </div>
            </>
          )}

          {error && (
            <div className="mt-3 text-xs text-red-600 bg-red-50 border border-red-200 rounded-md px-3 py-2">
              {error}
            </div>
          )}

          {composed && s && (
            <>
              {/* Summary band */}
              <div className="bg-gray-50 border border-gray-200 rounded-md px-4 py-3">
                <div className="flex items-center justify-between flex-wrap gap-2">
                  <div className="text-[11px] text-gray-500">
                    Reference <span className="font-mono text-gray-700">{s.reference}</span>
                  </div>
                  <span className={`text-[10px] font-semibold uppercase tracking-wide border rounded-full px-2 py-0.5 ${positionTone}`}>
                    {s.position_code.replace(/_/g, ' ')}
                  </span>
                </div>
                <div className="grid grid-cols-2 sm:grid-cols-4 gap-3 mt-3 text-xs">
                  <Metric label="Total activations" value={s.total_activations.toLocaleString()} />
                  <Metric label="Qualified" value={`${s.qualified_activations.toLocaleString()} (${s.qualification_rate_pct.toFixed(1)}%)`} tone="text-emerald-700" />
                  <Metric label="Unqualified" value={s.unqualified_activations.toLocaleString()} tone="text-amber-700" />
                  <Metric label="Qualified-earned" value={formatNGN(s.qualified_commission_ngn)} />
                  <Metric label="Statement claim" value={formatNGN(s.statement_claim_ngn)} />
                  <Metric label="Paid" value={formatNGN(s.amount_paid_ngn)} tone="text-emerald-700" />
                  <Metric label="Outstanding" value={formatNGN(s.outstanding_ngn)} tone="text-gray-900" />
                  <Metric
                    label="Root causes"
                    value={Object.keys(s.root_cause_classifications).length || '—'}
                  />
                </div>
                {Object.keys(s.root_cause_classifications).length > 0 && (
                  <div className="mt-2 flex flex-wrap gap-1.5">
                    {Object.entries(s.root_cause_classifications).map(([cause, n]) => (
                      <span
                        key={cause}
                        className="inline-block text-[10px] font-semibold uppercase tracking-wide bg-white border border-gray-200 rounded-full px-2 py-0.5 text-gray-700"
                      >
                        {n.toLocaleString()} × {CAUSE_LABEL[cause] || cause}
                      </span>
                    ))}
                  </div>
                )}
              </div>

              {/* Markdown preview — monospace so the formatting reads as-pasted */}
              <div className="mt-4">
                <div className="text-[11px] uppercase tracking-wide text-gray-500 mb-1">
                  Letter (markdown — paste into email or attach)
                </div>
                <pre className="bg-gray-900 text-gray-100 text-[11px] leading-snug rounded-md p-3 max-h-[40vh] overflow-auto whitespace-pre-wrap font-mono">
                  {data.markdown}
                </pre>
              </div>
            </>
          )}
        </div>

        <div className="px-5 py-3 border-t border-gray-200 flex items-center justify-end gap-2">
          {composed && (
            <>
              <button
                onClick={() => setComposed(false)}
                className="text-xs text-gray-700 hover:text-gray-900 px-2 py-1"
              >
                ← Edit & recompose
              </button>
              <button
                onClick={downloadMarkdown}
                className="text-xs text-gray-700 hover:text-gray-900 font-medium border border-gray-200 rounded-md px-3 py-1 hover:bg-gray-50"
              >
                ⬇ Download .md
              </button>
              <button
                onClick={copyMarkdown}
                className="text-xs text-gray-900 font-semibold bg-mtn-yellow border border-mtn-yellow rounded-md px-3 py-1 hover:brightness-95"
              >
                {copyOk ? '✓ Copied' : 'Copy to clipboard'}
              </button>
            </>
          )}
          <button
            onClick={onClose}
            className="text-xs text-gray-600 hover:text-gray-900 px-3 py-1"
          >
            Close
          </button>
        </div>
      </div>
    </div>
  );
}

function Metric({ label, value, tone = 'text-gray-900' }) {
  return (
    <div>
      <div className="text-[10px] uppercase tracking-wide text-gray-500">{label}</div>
      <div className={`text-sm font-semibold tabular-nums ${tone}`}>{value}</div>
    </div>
  );
}
