// Overview — the landing view.
//
// One screen that answers "is the month OK, and if not where do I look first?"
// for Finance and Revenue Assurance. Four content blocks, rendered top-down:
//
//   1. Posture band  — pass/flag/fail tallies + severity totals + Δ vs prior period
//   2. Cross-module roll-up  — dealers appearing in two or more module findings
//   3. Stacked module cards — FLAG first (with inline findings + drill-down),
//                             PASS modules collapse to slim rows
//   4. Toolbar       — CSV export of all findings for the period
//
// Period comes from PeriodProvider (and the prior period drives the deltas).
// onNavigate(viewId) swaps the global tab; onAsk(text) prefills a Commission
// chat question.

import { useEffect, useMemo, useState } from 'react';
import {
  getAssuranceStatus,
  getAuditBreakdown,
  getAuditModules,
  getPaymentSummary,
} from '../../api/client.js';
import { usePeriod } from '../../context/PeriodContext.jsx';
import { formatNGN, formatPeriod } from '../../lib/format.js';
import useDealerVerification from '../../hooks/useDealerVerification.js';
import HelpIcon, { QUALIFICATION_HELP } from '../shared/HelpIcon.jsx';

import { CONCLUSION_TEXT as AUDIT_CONCLUSION_TONE } from '../../lib/tones.js';

const STATUS_TONE = {
  PASS: 'bg-emerald-100 text-emerald-800 border-emerald-200',
  FLAG: 'bg-amber-100 text-amber-800 border-amber-200',
  FAIL: 'bg-red-100 text-red-800 border-red-200',
  NOT_IMPLEMENTED: 'bg-gray-100 text-gray-500 border-gray-200',
};

const SEVERITY_TONE = {
  HIGH: 'bg-red-100 text-red-800 border-red-200',
  MEDIUM: 'bg-amber-100 text-amber-800 border-amber-200',
  LOW: 'bg-blue-100 text-blue-800 border-blue-200',
};

const STATUS_WEIGHT = { FAIL: 0, FLAG: 1, NOT_IMPLEMENTED: 2, PASS: 3 };
const ACCENT_BY_STATUS = {
  FAIL: 'bg-red-500',
  FLAG: 'bg-amber-400',
  PASS: 'bg-emerald-400',
  NOT_IMPLEMENTED: 'bg-gray-300',
};

const VIEW_FOR_MODULE = {
  commission: 'commission',
  activation: 'activation',
  inventory: 'inventory',
  payment: 'payment',
};

// ---------------------------------------------------------------------------
// Small atoms
// ---------------------------------------------------------------------------

function StatusBadge({ status }) {
  const tone = STATUS_TONE[status] || STATUS_TONE.NOT_IMPLEMENTED;
  return (
    <span
      className={`inline-block px-2 py-0.5 text-[10px] font-semibold uppercase tracking-wide border rounded-full ${tone}`}
    >
      {status}
    </span>
  );
}

function SeverityPill({ severity }) {
  const tone = SEVERITY_TONE[severity] || SEVERITY_TONE.LOW;
  return (
    <span
      className={`inline-block px-1.5 py-0 text-[9px] font-bold uppercase tracking-wide border rounded ${tone}`}
    >
      {severity}
    </span>
  );
}

function Counter({ label, value, tone, delta }) {
  return (
    <span className="inline-flex items-baseline gap-1">
      <span className={`text-base font-bold tabular-nums ${tone}`}>{value}</span>
      <span className="text-[10px] uppercase tracking-wide text-gray-500">{label}</span>
      {delta !== undefined && delta !== 0 && (
        <DeltaChip delta={delta} invertColor />
      )}
    </span>
  );
}

function DeltaChip({ delta, invertColor = false }) {
  // For severity counts: more findings = worse, so positive delta is red.
  // Toggle with invertColor to use the "more is better" mapping.
  const positiveIsBad = invertColor;
  const tone =
    delta === 0
      ? 'text-gray-400'
      : (delta > 0) === positiveIsBad
        ? 'text-red-600'
        : 'text-emerald-700';
  const arrow = delta > 0 ? '↑' : delta < 0 ? '↓' : '·';
  return (
    <span className={`text-[10px] font-semibold ${tone}`}>
      {arrow}
      {Math.abs(delta)}
    </span>
  );
}

// ---------------------------------------------------------------------------
// Posture band
// ---------------------------------------------------------------------------

function PostureBand({ totals, deltas, priorPeriod }) {
  const { modules, pass, flag, fail, high, medium, low } = totals;
  const dominant = fail > 0 ? 'FAIL' : flag > 0 ? 'FLAG' : 'PASS';
  const tone =
    dominant === 'FAIL'
      ? 'border-red-200 bg-red-50'
      : dominant === 'FLAG'
        ? 'border-amber-200 bg-amber-50'
        : 'border-emerald-200 bg-emerald-50';

  const headline =
    dominant === 'FAIL'
      ? 'Critical findings — immediate review required'
      : dominant === 'FLAG'
        ? 'Findings flagged for review'
        : 'All checks passing';

  return (
    <div className={`border rounded-lg px-4 py-3 ${tone}`}>
      <div className="flex items-center justify-between flex-wrap gap-3">
        <div className="flex items-baseline gap-3">
          <span className="text-sm font-semibold text-gray-900">{headline}</span>
          <span className="text-xs text-gray-600">
            across {modules} module{modules === 1 ? '' : 's'}
            {priorPeriod && (
              <span className="ml-2 text-gray-500">
                · vs {formatPeriod(priorPeriod)}
              </span>
            )}
          </span>
        </div>
        <div className="flex items-center gap-3 text-xs">
          <Counter label="PASS" value={pass} tone="text-emerald-700" />
          <Counter label="FLAG" value={flag} tone="text-amber-700" />
          {fail > 0 && <Counter label="FAIL" value={fail} tone="text-red-700" />}
          <span className="w-px h-4 bg-gray-300" />
          <Counter
            label="High"
            value={high}
            tone="text-red-700"
            delta={deltas?.high}
          />
          <Counter
            label="Medium"
            value={medium}
            tone="text-amber-700"
            delta={deltas?.medium}
          />
          <Counter
            label="Low"
            value={low}
            tone="text-blue-700"
            delta={deltas?.low}
          />
        </div>
      </div>
    </div>
  );
}

// ---------------------------------------------------------------------------
// Cross-module dealer roll-up
// ---------------------------------------------------------------------------

function CrossModuleRollup({ rows, periodLabel, onAsk }) {
  if (!rows.length) return null;
  return (
    <div className="bg-white border border-gray-200 rounded-lg shadow-sm">
      <div className="px-4 py-2 border-b border-gray-100">
        <h3 className="text-xs font-semibold uppercase tracking-wide text-gray-700">
          Dealers across multiple modules
        </h3>
        <p className="text-[11px] text-gray-500 mt-0.5">
          {rows.length} dealer{rows.length === 1 ? '' : 's'} appearing in two or more module findings this period — investigate first.
        </p>
      </div>
      <ul className="divide-y divide-gray-100">
        {rows.map((r) => (
          <li
            key={r.dealer_id}
            className="px-4 py-2 flex items-center gap-3 hover:bg-gray-50"
          >
            <div className="min-w-0 flex-1">
              <div className="text-sm font-semibold text-gray-900 truncate">
                {r.dealer_name}
              </div>
              <div className="text-[11px] text-gray-500 mt-0.5 flex flex-wrap items-center gap-1.5">
                <span>{r.modules.length} modules:</span>
                {r.modules.map((m) => (
                  <span
                    key={m}
                    className="inline-block bg-gray-100 text-gray-700 px-1.5 py-0 rounded capitalize"
                  >
                    {m}
                  </span>
                ))}
                <span className="text-gray-400">·</span>
                {r.high > 0 && <SeverityPill severity="HIGH" />}
                {r.medium > 0 && <SeverityPill severity="MEDIUM" />}
                {r.low > 0 && <SeverityPill severity="LOW" />}
              </div>
            </div>
            {onAsk && (
              <button
                onClick={() =>
                  onAsk(
                    `Tell me everything about ${r.dealer_name} for ${periodLabel || 'this period'} — combine commission, activation, inventory and payment context.`,
                  )
                }
                className="shrink-0 text-xs text-gray-700 hover:text-gray-900 font-medium border border-gray-200 rounded-md px-2 py-1 hover:bg-yellow-50 hover:border-mtn-yellow transition"
              >
                Ask Claude
              </button>
            )}
          </li>
        ))}
      </ul>
    </div>
  );
}

// ---------------------------------------------------------------------------
// Current Position — platform-wide payment reconciliation summary
// ---------------------------------------------------------------------------

function CurrentPositionBand({ period, onNavigate }) {
  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(false);

  useEffect(() => {
    if (!period) return;
    let cancelled = false;
    setLoading(true);
    getPaymentSummary(period)
      .then((d) => !cancelled && setData(d))
      .catch(() => !cancelled && setData(null))
      .finally(() => !cancelled && setLoading(false));
    return () => { cancelled = true; };
  }, [period]);

  if (!data) {
    return loading ? (
      <div className="bg-white border border-gray-200 rounded-lg shadow-sm px-4 py-3 text-xs text-gray-500 italic">
        Loading current position…
      </div>
    ) : null;
  }

  const owed     = Number(data.total_commission_owed || 0);
  const paid     = Number(data.total_amount_paid || 0);
  const unpaid   = Number(data.total_amount_unpaid || 0);
  const coverage = Number(data.payment_coverage_pct || 0);
  const isApdp   = data.data_source === 'APDP';

  const disputed  = Number(data.disputed_count || 0);
  const partial   = Number(data.partially_paid_count || 0);
  const pending   = Number(data.pending_count || 0);
  const exceptions = disputed + partial + pending;

  return (
    <div className="bg-white border border-gray-200 rounded-lg shadow-sm">
      <div className="px-4 py-2 border-b border-gray-100 flex items-center justify-between">
        <div>
          <h3 className="text-xs font-semibold uppercase tracking-wide text-gray-700">
            Current Position · {formatPeriod(period) || '—'}
          </h3>
          <p className="text-[11px] text-gray-500 mt-0.5">
            Platform-wide reconciliation — what we owe partners, what we've settled, what's outstanding.
          </p>
        </div>
        <span
          className={`inline-block px-2 py-0.5 text-[9px] font-semibold uppercase tracking-wide border rounded-full ${
            isApdp
              ? 'bg-emerald-100 text-emerald-800 border-emerald-200'
              : 'bg-amber-100 text-amber-800 border-amber-200'
          }`}
          title={isApdp
            ? 'Reading normalized.partner_settlements from APDP'
            : 'Demo — synthetically generated data. No real MTN data used.'}
        >
          {isApdp ? 'Live · APDP' : 'Demo · Synthetic'}
        </span>
      </div>

      <div className="p-4 grid grid-cols-2 md:grid-cols-4 gap-3">
        <PositionTile
          label="Total commission owed"
          value={formatNGN(owed)}
          tone="text-gray-900"
        />
        <PositionTile
          label="Amount settled"
          value={formatNGN(paid)}
          tone="text-emerald-700"
          sub={`${coverage.toFixed(1)}% coverage`}
        />
        <PositionTile
          label="Outstanding"
          value={formatNGN(unpaid)}
          tone={unpaid > 0 ? 'text-red-700' : 'text-gray-900'}
        />
        <PositionTile
          label="Exceptions"
          value={exceptions.toLocaleString()}
          tone={exceptions > 0 ? 'text-amber-700' : 'text-gray-900'}
          sub={`${disputed} disputed · ${partial} partial · ${pending} pending`}
          onClick={onNavigate ? () => onNavigate('payment') : undefined}
        />
      </div>
    </div>
  );
}

function PositionTile({ label, value, tone = 'text-gray-900', sub, onClick }) {
  const Wrapper = onClick ? 'button' : 'div';
  return (
    <Wrapper
      onClick={onClick}
      className={`text-left px-3 py-2 rounded-md ${
        onClick ? 'hover:bg-yellow-50 transition cursor-pointer' : ''
      }`}
    >
      <div className="text-[10px] uppercase tracking-wide text-gray-500 font-semibold">
        {label}
      </div>
      <div className={`text-lg font-bold tabular-nums ${tone} mt-0.5`}>
        {value}
      </div>
      {sub && (
        <div className="text-[10px] text-gray-500 mt-0.5">{sub}</div>
      )}
    </Wrapper>
  );
}

// ---------------------------------------------------------------------------
// Audit coverage — trail counts per audit module for the current period
// ---------------------------------------------------------------------------

function AuditModuleTile({ module, breakdown, onOpen }) {
  const total = breakdown.reduce((n, b) => n + (b.n || 0), 0);
  // Sort by count desc, show top 2 buckets — enough to convey the shape
  // ("mostly UNDERPAID" or "MIXED_ATTRIBUTION dominant") at a glance.
  const top = [...breakdown]
    .sort((a, b) => (b.n || 0) - (a.n || 0))
    .slice(0, 2);
  return (
    <button
      onClick={onOpen}
      className="text-left bg-white border border-gray-200 rounded-lg shadow-sm px-3 py-2 hover:border-mtn-yellow hover:bg-yellow-50 transition"
      title={`Open ${module.label} in the Audit Trails tab`}
    >
      <div className="text-[11px] font-semibold text-gray-900 truncate">
        {module.label}
      </div>
      {total === 0 ? (
        <div className="text-[10px] text-gray-400 italic mt-0.5">
          Not run this period
        </div>
      ) : (
        <>
          <div className="text-sm font-bold tabular-nums text-gray-900 mt-0.5">
            {total.toLocaleString()}{' '}
            <span className="text-[10px] font-normal text-gray-500">
              trail{total === 1 ? '' : 's'}
            </span>
          </div>
          <div className="mt-1 flex flex-wrap items-center gap-1.5 text-[10px]">
            {top.map((b, i) => (
              <span key={i} className="inline-flex items-center gap-0.5">
                <span
                  className={`font-semibold ${
                    AUDIT_CONCLUSION_TONE[b.conclusion] || 'text-gray-700'
                  }`}
                >
                  {b.conclusion}
                </span>
                <span className="tabular-nums text-gray-500">{b.n}</span>
              </span>
            ))}
          </div>
        </>
      )}
    </button>
  );
}

function AuditCoverageBand({ period, onNavigate }) {
  const [modules, setModules] = useState([]);
  const [breakdowns, setBreakdowns] = useState({}); // { moduleName: [{conclusion, n}, ...] }
  const [loading, setLoading] = useState(false);

  useEffect(() => {
    let cancelled = false;
    getAuditModules()
      .then((ms) => !cancelled && setModules(Array.isArray(ms) ? ms : []))
      .catch(() => !cancelled && setModules([]));
    return () => {
      cancelled = true;
    };
  }, []);

  useEffect(() => {
    if (!period || modules.length === 0) return;
    let cancelled = false;
    setLoading(true);
    // Best-effort fetch per module — a missing Postgres shouldn't blank the
    // whole Overview, and a 503 on one module shouldn't blank the others.
    Promise.all(
      modules.map((m) =>
        getAuditBreakdown(m.name, period)
          .then((rows) => ({ name: m.name, rows: Array.isArray(rows) ? rows : [] }))
          .catch(() => ({ name: m.name, rows: [] })),
      ),
    )
      .then((results) => {
        if (cancelled) return;
        const next = {};
        for (const r of results) next[r.name] = r.rows;
        setBreakdowns(next);
      })
      .finally(() => !cancelled && setLoading(false));
    return () => {
      cancelled = true;
    };
  }, [period, modules]);

  if (modules.length === 0) return null;

  return (
    <div className="bg-white border border-gray-200 rounded-lg shadow-sm">
      <div className="px-4 py-2 border-b border-gray-100 flex items-center justify-between">
        <div>
          <h3 className="text-xs font-semibold uppercase tracking-wide text-gray-700">
            Audit coverage
          </h3>
          <p className="text-[11px] text-gray-500 mt-0.5">
            {modules.length} verification-chain module{modules.length === 1 ? '' : 's'} · click a tile to open the Audit Trails tab.
          </p>
        </div>
        {onNavigate && (
          <button
            onClick={() => onNavigate('audit')}
            className="text-xs text-gray-700 hover:text-gray-900 font-medium border border-gray-200 rounded-md px-2 py-1 hover:bg-yellow-50 hover:border-mtn-yellow transition"
          >
            Open Audit Trails →
          </button>
        )}
      </div>
      <div className="p-3 grid grid-cols-2 sm:grid-cols-4 gap-2">
        {modules.map((m) => (
          <AuditModuleTile
            key={m.name}
            module={m}
            breakdown={breakdowns[m.name] || []}
            onOpen={() => onNavigate && onNavigate('audit')}
          />
        ))}
      </div>
      {loading && (
        <div className="px-4 py-1 text-[10px] text-gray-400 italic border-t border-gray-100">
          Loading breakdowns…
        </div>
      )}
    </div>
  );
}

// ---------------------------------------------------------------------------
// Module cards
// ---------------------------------------------------------------------------

function FindingMetric({ label, value, tone = 'text-gray-900' }) {
  return (
    <div>
      <div className="text-[10px] uppercase tracking-wide text-gray-500">{label}</div>
      <div className={`text-sm font-semibold tabular-nums ${tone}`}>{value}</div>
    </div>
  );
}

function FindingVerificationPanel({ finding, activation, dealer, periodLabel }) {
  // Dealer snapshot — answers "what does this dealer actually look like
  // this period?" so the finding can be read in context, not in isolation.
  const totalActs  = Number(activation?.activation_count || 0);
  const qualified  = Number(activation?.qualified_activation_count || 0);
  const unqualif   = Number(activation?.non_qualified_activation_count || 0);
  const qualRate   = Number(activation?.qualification_rate_pct || 0);
  const earned     = Number(activation?.activation_commission_amount || 0);
  const zeroCount  = Number(dealer?.zero_commission_count || 0);

  if (!activation && !dealer) {
    return (
      <div className="mt-2 ml-7 p-3 bg-gray-50 border border-gray-200 rounded text-[11px] text-gray-500 italic">
        No matching activation / dealer record for {finding.dealer_name} in {periodLabel}.
        {finding.recommended_action && (
          <div className="mt-1 not-italic text-gray-700">
            → {finding.recommended_action}
          </div>
        )}
      </div>
    );
  }

  return (
    <div className="mt-2 ml-7 p-3 bg-gray-50 border border-gray-200 rounded">
      <div className="text-[10px] uppercase tracking-wide text-gray-500 mb-2">
        Dealer snapshot · {periodLabel || '—'}
      </div>
      <div className="grid grid-cols-2 sm:grid-cols-4 gap-3">
        <FindingMetric label="Activations" value={totalActs.toLocaleString()} />
        <FindingMetric
          label={<>Qualified <HelpIcon label="What is a qualified activation?">{QUALIFICATION_HELP}</HelpIcon></>}
          value={qualified.toLocaleString()}
          tone="text-emerald-700"
        />
        <FindingMetric
          label={<>Unqualified <HelpIcon label="What is an unqualified activation?">{QUALIFICATION_HELP}</HelpIcon></>}
          value={unqualif.toLocaleString()}
          tone="text-amber-700"
        />
        <FindingMetric
          label="Qual rate"
          value={`${qualRate.toFixed(1)}%`}
          tone={qualRate >= 80 ? 'text-emerald-700' : qualRate >= 50 ? 'text-amber-700' : 'text-red-700'}
        />
        <FindingMetric label="Commission earned" value={formatNGN(earned)} />
        <FindingMetric
          label="Zero-comm records"
          value={zeroCount.toLocaleString()}
          tone={zeroCount > 0 ? 'text-amber-700' : 'text-gray-500'}
        />
      </div>
      {finding.recommended_action && (
        <div className="mt-2 text-[11px] text-gray-600 border-t border-gray-200 pt-2">
          <span className="font-semibold uppercase tracking-wide text-gray-500">Next step:</span>{' '}
          {finding.recommended_action}
        </div>
      )}
    </div>
  );
}

function FindingRow({ finding, onAsk, periodLabel, activation, dealer }) {
  const [open, setOpen] = useState(false);
  return (
    <li className="py-2 first:pt-0 last:pb-0 border-b border-gray-100 last:border-b-0">
      <div className="flex items-start gap-2">
        <SeverityPill severity={finding.severity} />
        <div className="min-w-0 flex-1">
          <div className="text-xs font-semibold text-gray-900 truncate">
            {finding.dealer_name}
            <span className="ml-2 text-[10px] font-normal text-gray-400">
              {finding.type}
            </span>
          </div>
          <div className="text-xs text-gray-700 leading-snug">
            {finding.description}
          </div>
          <div className="mt-1 flex items-center gap-3">
            <button
              onClick={() => setOpen((o) => !o)}
              aria-expanded={open}
              className="text-[10px] text-gray-600 hover:text-gray-900 hover:underline"
            >
              {open ? '▼ Hide verification' : '▶ Verify'}
            </button>
            {onAsk && (
              <button
                onClick={() =>
                  onAsk(
                    `Investigate ${finding.dealer_name} for ${periodLabel || 'this period'}: ${finding.description}`,
                  )
                }
                className="text-[10px] text-gray-500 hover:text-gray-900 hover:underline"
                title="Ask Claude about this finding"
              >
                Ask Claude
              </button>
            )}
          </div>
        </div>
      </div>
      {open && (
        <FindingVerificationPanel
          finding={finding}
          activation={activation}
          dealer={dealer}
          periodLabel={periodLabel}
        />
      )}
    </li>
  );
}

function FlagCard({ module, onNavigate, onAsk, periodLabel, expanded, onToggle, activationByDealer, dealerByCode }) {
  const accent = ACCENT_BY_STATUS[module.status] || 'bg-gray-300';
  const findings = module.findings || [];
  const sevRank = { HIGH: 0, MEDIUM: 1, LOW: 2 };
  const sorted = [...findings].sort(
    (a, b) => (sevRank[a.severity] ?? 9) - (sevRank[b.severity] ?? 9),
  );
  const visible = expanded ? sorted : sorted.slice(0, 3);
  const remaining = sorted.length - visible.length;
  const targetView = VIEW_FOR_MODULE[module.module];

  return (
    <div className="bg-white border border-gray-200 rounded-lg shadow-sm relative overflow-hidden">
      <div className={`absolute top-0 left-0 h-full w-1 ${accent}`} />
      <div className="px-5 py-4">
        <div className="flex items-start justify-between gap-3">
          <div>
            <div className="text-[11px] uppercase tracking-wide text-gray-500">
              Phase {module.phase}
            </div>
            <h3 className="text-base font-semibold capitalize text-gray-900">
              {module.module} assurance
            </h3>
          </div>
          <div className="flex items-center gap-2">
            <StatusBadge status={module.status} />
            {targetView && onNavigate && (
              <button
                onClick={() => onNavigate(targetView)}
                className="text-xs text-gray-700 hover:text-gray-900 font-medium border border-gray-200 rounded-md px-2 py-1 hover:bg-yellow-50 hover:border-mtn-yellow transition"
              >
                Investigate →
              </button>
            )}
          </div>
        </div>
        <p className="mt-2 text-sm text-gray-700 leading-snug">{module.summary}</p>

        <div className="mt-3 flex items-center gap-3 text-[11px]">
          {module.high_count > 0 && (
            <Counter label="High" value={module.high_count} tone="text-red-700" />
          )}
          {module.medium_count > 0 && (
            <Counter
              label="Medium"
              value={module.medium_count}
              tone="text-amber-700"
            />
          )}
          {module.low_count > 0 && (
            <Counter label="Low" value={module.low_count} tone="text-blue-700" />
          )}
        </div>

        {sorted.length > 0 && (
          <div className="mt-3 pt-3 border-t border-gray-100">
            <ul>
              {visible.map((f, i) => (
                <FindingRow
                  key={`${f.dealer_id}-${f.type}-${i}`}
                  finding={f}
                  onAsk={onAsk}
                  periodLabel={periodLabel}
                  activation={activationByDealer?.[f.dealer_id]}
                  dealer={dealerByCode?.[f.dealer_id]}
                />
              ))}
            </ul>
            {remaining > 0 && (
              <button
                onClick={onToggle}
                className="mt-2 text-xs text-gray-600 hover:text-gray-900 hover:underline"
              >
                Show {remaining} more finding{remaining === 1 ? '' : 's'} →
              </button>
            )}
            {expanded && sorted.length > 3 && (
              <button
                onClick={onToggle}
                className="mt-2 text-xs text-gray-500 hover:text-gray-900 hover:underline"
              >
                Show less
              </button>
            )}
          </div>
        )}
      </div>
    </div>
  );
}

function PassCard({ module, onNavigate }) {
  const targetView = VIEW_FOR_MODULE[module.module];
  return (
    <div className="bg-white border border-gray-200 rounded-lg shadow-sm flex items-center gap-3 px-4 py-2">
      <span className="w-2 h-2 rounded-full bg-emerald-500" />
      <span className="text-[10px] uppercase tracking-wide text-gray-400">
        Phase {module.phase}
      </span>
      <span className="text-sm font-semibold capitalize text-gray-900">
        {module.module} assurance
      </span>
      <StatusBadge status={module.status} />
      <span className="text-xs text-gray-500 truncate flex-1">
        {module.summary}
      </span>
      {targetView && onNavigate && (
        <button
          onClick={() => onNavigate(targetView)}
          className="text-xs text-gray-500 hover:text-gray-900 hover:underline shrink-0"
        >
          Open →
        </button>
      )}
    </div>
  );
}

function StubCard({ module }) {
  return (
    <div className="bg-gray-50 border border-dashed border-gray-300 rounded-lg flex items-center gap-3 px-4 py-2">
      <span className="text-[10px] uppercase tracking-wide text-gray-400">
        Phase {module.phase}
      </span>
      <span className="text-sm font-semibold capitalize text-gray-400">
        {module.module} assurance
      </span>
      <StatusBadge status={module.status} />
      <span className="text-xs text-gray-400 italic truncate flex-1">
        {module.summary}
      </span>
    </div>
  );
}

function AllClearState({ period, onNavigate, modules }) {
  return (
    <div className="bg-white border border-emerald-200 rounded-lg shadow-sm p-8 text-center">
      <div className="w-12 h-12 mx-auto rounded-full bg-emerald-100 flex items-center justify-center text-emerald-700 text-2xl font-bold">
        ✓
      </div>
      <h2 className="mt-3 text-lg font-semibold text-gray-900">
        All clear for {formatPeriod(period)}
      </h2>
      <p className="mt-1 text-sm text-gray-600">
        Every assurance module passed. No findings require review.
      </p>
      <div className="mt-4 flex flex-wrap justify-center gap-2">
        {modules.map((m) => {
          const target = VIEW_FOR_MODULE[m.module];
          return (
            <button
              key={m.module}
              onClick={() => target && onNavigate?.(target)}
              className="text-xs text-gray-700 border border-gray-200 rounded-md px-2 py-1 capitalize hover:bg-gray-50"
            >
              {m.module} ✓
            </button>
          );
        })}
      </div>
    </div>
  );
}

// ---------------------------------------------------------------------------
// CSV export
// ---------------------------------------------------------------------------

function downloadFindingsCsv(modules, period) {
  const header = [
    'module',
    'phase',
    'severity',
    'dealer_id',
    'dealer_name',
    'type',
    'description',
    'recommended_action',
  ];
  const rows = [header.join(',')];
  const esc = (v) => {
    const s = String(v ?? '');
    return s.includes(',') || s.includes('"') || s.includes('\n')
      ? `"${s.replace(/"/g, '""')}"`
      : s;
  };
  for (const m of modules) {
    for (const f of m.findings || []) {
      rows.push(
        [
          m.module,
          m.phase,
          f.severity,
          f.dealer_id,
          f.dealer_name,
          f.type,
          f.description,
          f.recommended_action || '',
        ]
          .map(esc)
          .join(','),
      );
    }
  }
  const blob = new Blob([rows.join('\n')], { type: 'text/csv;charset=utf-8' });
  const url = URL.createObjectURL(blob);
  const a = document.createElement('a');
  a.href = url;
  a.download = `assurance_findings_${period || 'all'}.csv`;
  document.body.appendChild(a);
  a.click();
  document.body.removeChild(a);
  URL.revokeObjectURL(url);
}

// ---------------------------------------------------------------------------
// Panel
// ---------------------------------------------------------------------------

export default function AssuranceStatusPanel({ onNavigate, onAsk }) {
  const { period, priorPeriod } = usePeriod();
  const [payload, setPayload] = useState(null);
  const [priorPayload, setPriorPayload] = useState(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState(null);
  const [expanded, setExpanded] = useState({});
  // Dealer-keyed lookup for inline finding verification panels. One fetch
  // per period change — used by every FlagCard's FindingRow on expand.
  const { activationByDealer, dealerByCode } = useDealerVerification(period);

  useEffect(() => {
    if (!period) return;
    let cancelled = false;
    setLoading(true);
    setError(null);
    getAssuranceStatus(period)
      .then((data) => !cancelled && setPayload(data))
      .catch((e) => {
        if (!cancelled) setError(e?.response?.data?.detail || e?.message || String(e));
      })
      .finally(() => !cancelled && setLoading(false));
    return () => {
      cancelled = true;
    };
  }, [period]);

  // Prior period — load best-effort, don't surface its errors.
  useEffect(() => {
    if (!priorPeriod || priorPeriod === period) {
      setPriorPayload(null);
      return;
    }
    let cancelled = false;
    getAssuranceStatus(priorPeriod)
      .then((data) => !cancelled && setPriorPayload(data))
      .catch(() => !cancelled && setPriorPayload(null));
    return () => {
      cancelled = true;
    };
  }, [priorPeriod, period]);

  const modules = useMemo(() => {
    const raw = payload?.modules || [];
    return [...raw].sort((a, b) => {
      const sw = (STATUS_WEIGHT[a.status] ?? 9) - (STATUS_WEIGHT[b.status] ?? 9);
      if (sw !== 0) return sw;
      return (a.phase ?? 0) - (b.phase ?? 0);
    });
  }, [payload]);

  const totals = useMemo(() => {
    const t = { modules: modules.length, pass: 0, flag: 0, fail: 0, high: 0, medium: 0, low: 0 };
    for (const m of modules) {
      if (m.status === 'PASS') t.pass++;
      else if (m.status === 'FLAG') t.flag++;
      else if (m.status === 'FAIL') t.fail++;
      t.high += m.high_count || 0;
      t.medium += m.medium_count || 0;
      t.low += m.low_count || 0;
    }
    return t;
  }, [modules]);

  const deltas = useMemo(() => {
    if (!priorPayload) return null;
    const p = { high: 0, medium: 0, low: 0 };
    for (const m of priorPayload.modules || []) {
      p.high += m.high_count || 0;
      p.medium += m.medium_count || 0;
      p.low += m.low_count || 0;
    }
    return {
      high: totals.high - p.high,
      medium: totals.medium - p.medium,
      low: totals.low - p.low,
    };
  }, [priorPayload, totals]);

  const crossModule = useMemo(() => {
    // Group all findings across all modules by dealer_id; keep only dealers
    // appearing in 2+ modules.
    const byDealer = new Map();
    for (const m of modules) {
      for (const f of m.findings || []) {
        if (!f.dealer_id) continue;
        const entry = byDealer.get(f.dealer_id) || {
          dealer_id: f.dealer_id,
          dealer_name: f.dealer_name,
          modules: new Set(),
          high: 0,
          medium: 0,
          low: 0,
          count: 0,
        };
        entry.modules.add(m.module);
        entry.count++;
        if (f.severity === 'HIGH') entry.high++;
        else if (f.severity === 'MEDIUM') entry.medium++;
        else if (f.severity === 'LOW') entry.low++;
        byDealer.set(f.dealer_id, entry);
      }
    }
    return [...byDealer.values()]
      .filter((e) => e.modules.size >= 2)
      .map((e) => ({ ...e, modules: [...e.modules].sort() }))
      .sort((a, b) => b.high - a.high || b.count - a.count);
  }, [modules]);

  const periodLabel = formatPeriod(period);
  const findingsCount = modules.reduce((n, m) => n + (m.findings?.length || 0), 0);
  const allPass = modules.length > 0 && totals.pass === modules.length;

  return (
    <div className="h-full flex flex-col bg-gray-50 text-gray-800">
      <div className="px-5 py-3 bg-white border-b border-gray-200 flex flex-wrap items-end gap-4">
        <div className="text-sm font-semibold text-gray-800">
          Overview
          <span className="ml-2 text-xs font-normal text-gray-500">
            · {periodLabel || '—'}
          </span>
        </div>
        <div className="flex-1" />
        <div className="flex items-center gap-3">
          <span className="text-[11px] text-gray-500">
            {modules.length} modules · {findingsCount} finding
            {findingsCount === 1 ? '' : 's'}
          </span>
          <button
            onClick={() => downloadFindingsCsv(modules, period)}
            disabled={findingsCount === 0}
            className="text-xs text-gray-700 hover:text-gray-900 font-medium border border-gray-200 rounded-md px-2 py-1 hover:bg-yellow-50 hover:border-mtn-yellow transition disabled:opacity-40 disabled:hover:bg-white disabled:hover:border-gray-200"
            title="Download all findings as CSV"
          >
            ⬇ Export CSV
          </button>
        </div>
      </div>

      {error && (
        <div className="mx-5 mt-3 text-xs text-red-600 bg-red-50 border border-red-200 rounded-md px-3 py-2">
          {error}
        </div>
      )}

      <div className="flex-1 overflow-auto p-5">
        {loading && !modules.length ? (
          <div className="text-sm text-gray-500 italic">Loading overview…</div>
        ) : (
          <div className="max-w-4xl mx-auto flex flex-col gap-3">
            {modules.length > 0 && (
              <PostureBand
                totals={totals}
                deltas={deltas}
                priorPeriod={priorPayload ? priorPeriod : null}
              />
            )}

            <CurrentPositionBand period={period} onNavigate={onNavigate} />

            <AuditCoverageBand period={period} onNavigate={onNavigate} />

            {allPass ? (
              <AllClearState
                period={period}
                onNavigate={onNavigate}
                modules={modules}
              />
            ) : (
              <>
                <CrossModuleRollup
                  rows={crossModule}
                  periodLabel={periodLabel}
                  onAsk={onAsk}
                />

                {modules.map((m) => {
                  if (!m.implemented) {
                    return <StubCard key={m.module} module={m} />;
                  }
                  if (m.status === 'PASS') {
                    return (
                      <PassCard key={m.module} module={m} onNavigate={onNavigate} />
                    );
                  }
                  return (
                    <FlagCard
                      key={m.module}
                      module={m}
                      onNavigate={onNavigate}
                      onAsk={onAsk}
                      periodLabel={periodLabel}
                      expanded={!!expanded[m.module]}
                      onToggle={() =>
                        setExpanded((e) => ({ ...e, [m.module]: !e[m.module] }))
                      }
                      activationByDealer={activationByDealer}
                      dealerByCode={dealerByCode}
                    />
                  );
                })}
              </>
            )}
          </div>
        )}
      </div>
    </div>
  );
}
