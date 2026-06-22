// Stage-1 ServiceNow ticket draft modal.
//
// Fetches /inventory/data-coverage-issues for the given period, shows the
// formatted ticket body in a copyable preview, and surfaces the affected
// dealer summary (IFS missing + USP missing). The finance officer copies
// the body and pastes it into ServiceNow themselves — no API write.
//
// Stage 2 (when ServiceNow credentials are configured) will add a Submit
// button that POSTs to the ServiceNow Table API directly.

import { useEffect, useState } from 'react';
import { getDataCoverageIssues } from '../../api/client.js';
import { formatPeriod } from '../../lib/format.js';

const SEVERITY_TONE = {
  LOW: 'bg-blue-100 text-blue-800 border-blue-200',
  MEDIUM: 'bg-amber-100 text-amber-800 border-amber-200',
  HIGH: 'bg-red-100 text-red-800 border-red-200',
};

export default function DataCoverageTicketModal({ period, open, onClose }) {
  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState(null);
  const [source, setSource] = useState('both');
  const [copyOk, setCopyOk] = useState(false);

  useEffect(() => {
    if (!open || !period) return;
    let cancelled = false;
    setLoading(true);
    setError(null);
    setCopyOk(false);
    getDataCoverageIssues(period, source)
      .then((d) => !cancelled && setData(d))
      .catch((e) => !cancelled && setError(e?.response?.data?.detail || e?.message || String(e)))
      .finally(() => !cancelled && setLoading(false));
    return () => {
      cancelled = true;
    };
  }, [open, period, source]);

  if (!open) return null;

  async function handleCopy() {
    if (!data?.ticket_body) return;
    try {
      await navigator.clipboard.writeText(data.ticket_body);
      setCopyOk(true);
      setTimeout(() => setCopyOk(false), 2000);
    } catch {
      // Fallback: select-all in textarea
      const ta = document.getElementById('ticket-body-textarea');
      if (ta) {
        ta.select();
        document.execCommand('copy');
        setCopyOk(true);
        setTimeout(() => setCopyOk(false), 2000);
      }
    }
  }

  return (
    <div
      className="fixed inset-0 z-50 bg-black/40 flex items-center justify-center p-4"
      onClick={onClose}
    >
      <div
        className="bg-white rounded-lg shadow-xl max-w-4xl w-full max-h-[90vh] flex flex-col overflow-hidden"
        onClick={(e) => e.stopPropagation()}
      >
        {/* Header */}
        <div className="px-5 py-3 border-b border-gray-200 flex items-center gap-3">
          <div className="w-1.5 h-7 bg-mtn-yellow rounded-sm" />
          <div className="flex-1">
            <h2 className="text-sm font-semibold text-gray-900">
              ServiceNow Ticket Draft — Data Coverage Issue
            </h2>
            <p className="text-[11px] text-gray-500">
              Period {formatPeriod(period)} · Stage 1 (copy + paste into ServiceNow)
            </p>
          </div>
          <button
            onClick={onClose}
            className="text-gray-400 hover:text-gray-700 text-xl leading-none"
            title="Close"
          >
            ×
          </button>
        </div>

        {/* Source filter */}
        <div className="px-5 py-2 border-b border-gray-100 bg-gray-50 flex items-center gap-3 text-xs">
          <span className="text-gray-500 uppercase tracking-wide text-[10px]">Include</span>
          {['both', 'ifs', 'usp'].map((s) => (
            <label key={s} className="flex items-center gap-1 cursor-pointer">
              <input
                type="radio"
                name="source"
                checked={source === s}
                onChange={() => setSource(s)}
                className="accent-mtn-yellow"
              />
              <span className="uppercase tracking-wide">
                {s === 'both' ? 'IFS + USP' : s}
              </span>
            </label>
          ))}
        </div>

        {/* Body */}
        <div className="flex-1 overflow-auto">
          {error && (
            <div className="mx-5 mt-3 text-xs text-red-600 bg-red-50 border border-red-200 rounded-md px-3 py-2">
              {error}
            </div>
          )}

          {loading && (
            <div className="p-6 text-sm text-gray-500 italic">Compiling ticket…</div>
          )}

          {!loading && data && (
            <div className="p-5 space-y-4">
              {/* Headline */}
              <div className="flex flex-wrap items-center gap-3">
                <span
                  className={`inline-block px-2 py-0.5 text-[10px] font-semibold uppercase tracking-wide border rounded-full ${SEVERITY_TONE[data.severity]}`}
                >
                  {data.severity}
                </span>
                <span className="text-sm text-gray-800">
                  <strong className="tabular-nums">{data.affected_dealers}</strong>{' '}
                  dealers affected
                </span>
                <span className="text-xs text-gray-500">·</span>
                <span className="text-xs text-gray-500">
                  IFS missing: <strong>{data.ifs_missing.length}</strong> · USP missing:{' '}
                  <strong>{data.usp_missing.length}</strong>
                </span>
              </div>

              {data.affected_dealers === 0 ? (
                <div className="bg-emerald-50 border border-emerald-200 rounded-md p-4 text-sm text-emerald-800">
                  ✓ No data coverage gaps for {formatPeriod(period)}. Nothing to escalate.
                </div>
              ) : (
                <>
                  {/* Markdown body preview */}
                  <div>
                    <div className="flex items-center justify-between mb-1">
                      <label className="text-[11px] uppercase tracking-wide text-gray-500">
                        Ticket body (markdown)
                      </label>
                      <button
                        onClick={handleCopy}
                        className={`text-xs font-medium border rounded-md px-2 py-1 transition ${
                          copyOk
                            ? 'border-emerald-300 bg-emerald-50 text-emerald-800'
                            : 'border-gray-200 text-gray-700 hover:bg-yellow-50 hover:border-mtn-yellow'
                        }`}
                      >
                        {copyOk ? '✓ Copied' : '⧉ Copy to clipboard'}
                      </button>
                    </div>
                    <textarea
                      id="ticket-body-textarea"
                      readOnly
                      value={data.ticket_body}
                      className="w-full h-72 text-[11px] font-mono border border-gray-200 rounded p-2 bg-gray-50 text-gray-800 leading-snug"
                    />
                  </div>

                  {/* Suggested action */}
                  <div className="text-xs text-gray-600 bg-gray-50 border border-gray-200 rounded p-3">
                    <span className="font-semibold uppercase tracking-wide text-gray-500 text-[10px]">
                      Suggested action ·
                    </span>{' '}
                    {data.severity_action}
                  </div>
                </>
              )}
            </div>
          )}
        </div>

        {/* Footer */}
        <div className="px-5 py-3 border-t border-gray-200 bg-gray-50 flex items-center justify-between">
          <span className="text-[11px] text-gray-500 italic">
            Stage 1: ticket is copied manually. Live ServiceNow submission lands in Stage 2.
          </span>
          <button
            onClick={onClose}
            className="text-xs text-gray-700 hover:text-gray-900 font-medium border border-gray-200 rounded-md px-3 py-1.5 hover:bg-white transition"
          >
            Close
          </button>
        </div>
      </div>
    </div>
  );
}
