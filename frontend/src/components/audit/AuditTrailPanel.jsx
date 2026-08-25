// Audit Trails — generic, module-driven view over persisted verification
// chains. Module-agnostic on purpose: it reads the generic trail shape
// (partner_code, conclusion, confidence, caveat_steps, steps[]) so any
// registered audit module renders here with no code changes. Zero-commission
// is the only module today; inventory/payment drop in via the dropdown later.
//
// Nothing is written on view. The explicit "Run" button triggers the run
// job; GET endpoints just read what's persisted.

import { useEffect, useMemo, useState } from 'react';
import { usePeriod } from '../../context/PeriodContext.jsx';
import { formatNGN, formatPeriod } from '../../lib/format.js';
import {
  getAuditModules,
  runAuditModule,
  getAuditTrails,
  getAuditBreakdown,
} from '../../api/client.js';

import { CONCLUSION_BADGE as CONCLUSION_TONE } from '../../lib/tones.js';
const CONFIDENCE_TONE = {
  HIGH: 'text-emerald-700',
  MEDIUM: 'text-amber-700',
  LOW: 'text-red-700',
};

function Badge({ label, tone }) {
  return (
    <span className={`inline-block px-2 py-0.5 text-[10px] font-semibold uppercase tracking-wide border rounded-full ${tone}`}>
      {label}
    </span>
  );
}

// One trail's step chain — the "checklist". Renders from the generic steps
// array, so it works for any module.
function StepChecklist({ steps }) {
  const parsed = useMemo(() => {
    if (Array.isArray(steps)) return steps;
    try { return JSON.parse(steps || '[]'); } catch { return []; }
  }, [steps]);

  return (
    <ol className="space-y-2">
      {parsed.map((s) => (
        <li key={s.step} className="flex items-start gap-2">
          <span className={`mt-0.5 shrink-0 inline-flex items-center justify-center w-5 h-5 rounded-full text-[10px] font-bold ${
            s.passed ? 'bg-emerald-100 text-emerald-700' : 'bg-amber-100 text-amber-700'
          }`}>
            {s.passed ? '✓' : '!'}
          </span>
          <div className="min-w-0 flex-1">
            <div className="text-xs font-semibold text-gray-900">
              Step {s.step}: {s.name}
            </div>
            <div className="text-[11px] text-gray-500">{s.checked}</div>
            <div className="text-xs text-gray-700 mt-0.5">{s.result}</div>
            {s.caveat && (
              <div className="text-[11px] text-amber-800 bg-amber-50 border border-amber-200 rounded px-2 py-1 mt-1">
                ⚠ {s.caveat}
              </div>
            )}
          </div>
        </li>
      ))}
    </ol>
  );
}

function TrailRow({ trail, expanded, onToggle }) {
  const expectedNgn = trail.step3_expected_ngn;
  return (
    <>
      <tr
        className="border-b border-gray-100 hover:bg-gray-50 cursor-pointer align-top"
        onClick={onToggle}
      >
        <td className="px-2 py-1.5 w-6">
          <button
            aria-expanded={expanded}
            aria-label={expanded ? 'Collapse' : 'Expand'}
            className="text-gray-400 hover:text-gray-700 select-none"
          >
            {expanded ? '▼' : '▶'}
          </button>
        </td>
        <td className="px-2 py-1.5">
          <div className="text-sm text-gray-800 truncate max-w-[220px]" title={trail.partner_name}>
            {trail.partner_name}
          </div>
          <div className="text-[10px] text-gray-400">{trail.partner_code}</div>
        </td>
        <td className="px-2 py-1.5">
          <Badge label={trail.conclusion} tone={CONCLUSION_TONE[trail.conclusion] || CONCLUSION_TONE.INSUFFICIENT_DATA} />
        </td>
        <td className={`px-2 py-1.5 text-xs font-semibold ${CONFIDENCE_TONE[trail.confidence] || 'text-gray-600'}`}>
          {trail.confidence}
        </td>
        <td className="px-2 py-1.5 text-right tabular-nums text-gray-700 text-xs">
          {expectedNgn != null ? formatNGN(expectedNgn) : '—'}
        </td>
        <td className="px-2 py-1.5">
          <div className="flex flex-wrap gap-1">
            {(trail.caveat_steps || []).length === 0
              ? <span className="text-[10px] text-gray-400">clean</span>
              : trail.caveat_steps.map((c) => (
                  <span key={c} className="inline-block text-[9px] uppercase tracking-wide bg-amber-100 text-amber-800 border border-amber-200 rounded px-1.5 py-0.5">
                    {c}
                  </span>
                ))}
          </div>
        </td>
      </tr>
      {expanded && (
        <tr className="bg-gray-50">
          <td colSpan={6} className="px-4 py-3">
            <StepChecklist steps={trail.steps} />
          </td>
        </tr>
      )}
    </>
  );
}

export default function AuditTrailPanel() {
  const { period } = usePeriod();
  const [modules, setModules] = useState([]);
  const [module, setModule] = useState('zero_commission');
  const [caveatFilter, setCaveatFilter] = useState('');
  const [partnerQuery, setPartnerQuery] = useState('');
  const [trails, setTrails] = useState([]);
  const [breakdown, setBreakdown] = useState([]);
  const [expanded, setExpanded] = useState({});
  const [loading, setLoading] = useState(false);
  const [running, setRunning] = useState(false);
  const [error, setError] = useState(null);
  const [notice, setNotice] = useState(null);

  const activeModule = modules.find((m) => m.name === module);

  // Load the module registry once.
  useEffect(() => {
    getAuditModules()
      .then((ms) => {
        setModules(ms);
        if (ms.length && !ms.some((m) => m.name === module)) setModule(ms[0].name);
      })
      .catch((e) => setError(e?.response?.data?.detail || e?.message || String(e)));
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const load = () => {
    if (!period || !module) return;
    setLoading(true);
    setError(null);
    Promise.all([
      getAuditTrails(module, period, caveatFilter || null),
      getAuditBreakdown(module, period),
    ])
      .then(([ts, bd]) => {
        setTrails(Array.isArray(ts) ? ts : []);
        setBreakdown(Array.isArray(bd) ? bd : []);
      })
      .catch((e) => {
        setTrails([]);
        setBreakdown([]);
        setError(e?.response?.data?.detail || e?.message || String(e));
      })
      .finally(() => setLoading(false));
  };

  // Reload trails whenever module / period / filter changes.
  useEffect(() => { load(); /* eslint-disable-next-line */ }, [module, period, caveatFilter]);

  const runJob = () => {
    if (!period || !module) return;
    setRunning(true);
    setError(null);
    setNotice(null);
    runAuditModule(module, period)
      .then((r) => {
        setNotice(`Run ${r.run_id.slice(0, 8)} — ${r.trail_count} trails generated.`);
        load();
      })
      .catch((e) => setError(e?.response?.data?.detail || e?.message || String(e)))
      .finally(() => setRunning(false));
  };

  const stepOptions = activeModule?.step_names || [];

  // Client-side partner search — case-insensitive substring over
  // partner_code + partner_name. Trails are already loaded, so this is
  // a pure display filter (fast even with the 4000+ inventory trails).
  const filteredTrails = useMemo(() => {
    const q = partnerQuery.trim().toLowerCase();
    if (!q) return trails;
    return trails.filter((t) =>
      String(t.partner_code || '').toLowerCase().includes(q)
      || String(t.partner_name || '').toLowerCase().includes(q)
    );
  }, [trails, partnerQuery]);

  const total = filteredTrails.length;
  const totalUnfiltered = trails.length;

  return (
    <div className="h-full flex flex-col bg-gray-50 text-gray-800">
      {/* Header controls */}
      <div className="px-5 py-3 bg-white border-b border-gray-200 flex flex-wrap items-end gap-4">
        <div className="text-sm font-semibold text-gray-800">
          Audit Trails
          <span className="ml-2 text-xs font-normal text-gray-500">· {formatPeriod(period) || '—'}</span>
        </div>

        <label className="flex flex-col gap-1">
          <span className="text-[11px] uppercase tracking-wide text-gray-500">Module</span>
          <select
            value={module}
            onChange={(e) => { setModule(e.target.value); setExpanded({}); }}
            className="text-sm border border-gray-300 rounded-md px-2 py-1.5 bg-white focus:outline-none focus:ring-2 focus:ring-mtn-yellow"
          >
            {modules.map((m) => (
              <option key={m.name} value={m.name}>{m.label}</option>
            ))}
          </select>
        </label>

        <label className="flex flex-col gap-1">
          <span className="text-[11px] uppercase tracking-wide text-gray-500">Caveat step filter</span>
          <select
            value={caveatFilter}
            onChange={(e) => setCaveatFilter(e.target.value)}
            className="text-sm border border-gray-300 rounded-md px-2 py-1.5 bg-white focus:outline-none focus:ring-2 focus:ring-mtn-yellow"
          >
            <option value="">— all trails —</option>
            {stepOptions.map((s) => (
              <option key={s} value={s}>caveat in: {s}</option>
            ))}
          </select>
        </label>

        <label className="flex flex-col gap-1">
          <span className="text-[11px] uppercase tracking-wide text-gray-500">Partner search</span>
          <input
            type="search"
            value={partnerQuery}
            onChange={(e) => setPartnerQuery(e.target.value)}
            placeholder="code or name…"
            className="text-sm border border-gray-300 rounded-md px-2 py-1.5 bg-white focus:outline-none focus:ring-2 focus:ring-mtn-yellow w-52"
          />
        </label>

        <div className="flex-1" />

        <button
          onClick={runJob}
          disabled={running || !period}
          className="px-4 py-2 rounded-md bg-mtn-yellow text-gray-900 text-sm font-semibold hover:brightness-95 disabled:opacity-50"
        >
          {running ? 'Running…' : `Run ${activeModule?.label || module} for ${formatPeriod(period) || '—'}`}
        </button>
      </div>

      {activeModule?.claim && (
        <div className="px-5 py-2 bg-white border-b border-gray-100 text-[11px] text-gray-500">
          Auditing the claim: <span className="italic text-gray-700">"{activeModule.claim}"</span>
        </div>
      )}

      {/* Breakdown band */}
      {breakdown.length > 0 && (
        <div className="px-5 py-2 bg-white border-b border-gray-100 flex flex-wrap items-center gap-4 text-xs">
          <span className="text-gray-500">
            {total} trail{total === 1 ? '' : 's'}
            {partnerQuery && total !== totalUnfiltered && ` (of ${totalUnfiltered})`}
          </span>
          {breakdown.map((b, i) => (
            <span key={i} className="inline-flex items-center gap-1.5">
              <Badge label={b.conclusion} tone={CONCLUSION_TONE[b.conclusion] || CONCLUSION_TONE.INSUFFICIENT_DATA} />
              <span className={`font-semibold ${CONFIDENCE_TONE[b.confidence] || 'text-gray-600'}`}>{b.confidence}</span>
              <span className="tabular-nums text-gray-700">{b.n}</span>
            </span>
          ))}
        </div>
      )}

      {notice && (
        <div className="mx-5 mt-3 text-xs text-emerald-800 bg-emerald-50 border border-emerald-200 rounded-md px-3 py-2">
          {notice}
        </div>
      )}
      {error && (
        <div className="mx-5 mt-3 text-xs text-red-600 bg-red-50 border border-red-200 rounded-md px-3 py-2">
          {error}
        </div>
      )}

      {/* Trails table */}
      <div className="flex-1 min-h-0 p-5 flex flex-col overflow-hidden">
        <div className="flex-1 min-h-0 bg-white border border-gray-200 rounded-lg shadow-sm overflow-auto">
          {loading ? (
            <div className="p-4 text-sm text-gray-500 italic">Loading trails…</div>
          ) : total === 0 ? (
            <div className="p-6 text-sm text-gray-500">
              No trails for this module/period.{' '}
              <button onClick={runJob} className="text-mtn-yellow font-semibold hover:underline">
                Run the job
              </button>{' '}
              to generate them.
            </div>
          ) : (
            <table className="w-full text-sm border-collapse">
              <thead className="sticky top-0 bg-gray-50 z-10">
                <tr className="text-gray-600 text-xs">
                  <th className="px-2 py-2 w-6" />
                  <th className="px-2 py-2 text-left font-semibold">Partner</th>
                  <th className="px-2 py-2 text-left font-semibold">Conclusion</th>
                  <th className="px-2 py-2 text-left font-semibold">Confidence</th>
                  <th className="px-2 py-2 text-right font-semibold">Expected</th>
                  <th className="px-2 py-2 text-left font-semibold">Caveats</th>
                </tr>
              </thead>
              <tbody>
                {filteredTrails.map((t) => {
                  const key = t.trail_id ?? `${t.partner_code}-${t.mon_period}`;
                  return (
                    <TrailRow
                      key={key}
                      trail={t}
                      expanded={!!expanded[key]}
                      onToggle={() => setExpanded((e) => ({ ...e, [key]: !e[key] }))}
                    />
                  );
                })}
              </tbody>
            </table>
          )}
        </div>
      </div>
    </div>
  );
}
