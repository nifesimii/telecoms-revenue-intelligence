// Exceptions-only payment table.
// Replaces the old passive "Recommended action" prose with an inline
// Verify expandable that shows the actual activation evidence behind the
// claim. The verdict line tells the finance officer whether the activations
// actually support what the statement says they're owed.
//
// Data sources used for verification:
//   /activations/summary?mon_period=<period>   ← qualified vs unqualified
//   /dealers?mon_period=<period>               ← zero-commission count
// Both fetched once when the table mounts; verification is instant on expand.

import { useMemo, useState } from 'react';
import { formatNGN } from '../../lib/format.js';
import useDealerVerification from '../../hooks/useDealerVerification.js';
import HelpIcon, {
  LEAKAGE_HELP,
  QUALIFICATION_HELP,
} from '../shared/HelpIcon.jsx';

const STATUS_TONE = {
  PARTIALLY_PAID: 'bg-amber-100 text-amber-800 border-amber-200',
  DISPUTED: 'bg-red-100 text-red-800 border-red-200',
  PENDING: 'bg-gray-100 text-gray-700 border-gray-200',
};

const FLAG_INFO = {
  ALL_UNQUALIFIED: { tone: 'bg-red-100 text-red-800 border-red-200', phase: 'Phase 2' },
  CONFIRMED_MISMATCH: {
    tone: 'bg-amber-100 text-amber-800 border-amber-200',
    phase: 'Phase 3',
  },
  HIGH_UNQUALIFIED_RATE: {
    tone: 'bg-amber-100 text-amber-800 border-amber-200',
    phase: 'Phase 2',
  },
};

function StatusBadge({ status }) {
  const tone = STATUS_TONE[status] || STATUS_TONE.PENDING;
  return (
    <span
      className={`inline-block px-2 py-0.5 text-[10px] font-semibold uppercase tracking-wide border rounded-full ${tone}`}
    >
      {status}
    </span>
  );
}

function FlagBadge({ flag }) {
  if (!flag) {
    return <span className="text-[10px] text-gray-400 italic">none</span>;
  }
  const info = FLAG_INFO[flag] || { tone: 'bg-gray-100 text-gray-700 border-gray-200', phase: '' };
  return (
    <span className="inline-flex items-center gap-1.5">
      <span
        className={`inline-block px-2 py-0.5 text-[10px] font-semibold uppercase tracking-wide border rounded-full ${info.tone}`}
      >
        {flag}
      </span>
      {info.phase && (
        <span className="text-[10px] text-gray-400 uppercase tracking-wide">
          {info.phase}
        </span>
      )}
    </span>
  );
}

// ---------------------------------------------------------------------------
// Verification panel
// ---------------------------------------------------------------------------
// Renders the activation evidence behind one exception row. Computes
// variance = (commission earned from qualified activations) − (statement claim).
// Verdict logic (with a 1 NGN tolerance for rounding):
//   |variance| ≤ 1   →  ✓ Matches statement
//   variance >  1    →  ⚠ Under-claimed (dealer earned more than claimed)
//   variance < -1    →  ✗ Statement exceeds what activations support

function VerificationPanel({ row, activation, dealer, onAsk, period }) {
  // No activation record for this dealer in this period — that IS the verdict.
  if (!activation) {
    return (
      <div className="bg-amber-50 border border-amber-200 rounded-md px-4 py-3 m-2 text-xs">
        <div className="font-semibold text-amber-900">
          ⚠ No activation record found for {row.distributor_name} in this period
        </div>
        <div className="mt-1 text-amber-800">
          A commission claim of <strong>{formatNGN(row.commission_owed)}</strong>{' '}
          has no matching activation data. This is a SALES_WITHOUT_STATEMENT-style
          discrepancy and needs investigation before settlement.
        </div>
        {onAsk && (
          <div className="mt-2">
            <AskButton onAsk={onAsk} row={row} period={period} />
          </div>
        )}
      </div>
    );
  }

  const total      = Number(activation.activation_count || 0);
  const qualified  = Number(activation.qualified_activation_count || 0);
  const unqualified = Number(activation.non_qualified_activation_count || 0);
  const rate       = Number(activation.qualification_rate_pct || 0);
  const earned     = Number(activation.activation_commission_amount || 0);
  const claimed    = Number(row.commission_owed || 0);
  const paid       = Number(row.amount_paid || 0);
  const variance   = earned - claimed;
  const overpay    = paid - earned;   // > 0 ⇒ paid on unqualified activations
  const zeroCount  = Number(dealer?.zero_commission_count || 0);

  let verdict, verdictTone;
  if (Math.abs(variance) <= 1) {
    verdict = `✓ Activations support the NGN ${claimed.toLocaleString('en-NG', { minimumFractionDigits: 2 })} claim`;
    verdictTone = 'text-emerald-700 bg-emerald-50 border-emerald-200';
  } else if (variance > 1) {
    verdict = `⚠ Dealer appears under-claimed by ${formatNGN(variance)} — activations earned more than the statement shows`;
    verdictTone = 'text-amber-800 bg-amber-50 border-amber-200';
  } else {
    verdict = `✗ Statement exceeds activation support by ${formatNGN(Math.abs(variance))} — investigate before settlement`;
    verdictTone = 'text-red-700 bg-red-50 border-red-200';
  }

  // Payment leakage check — did MTN pay commission for activations that
  // didn't qualify? Distinct from the statement-vs-activations variance
  // above. Compares actual paid amount against qualified-earned.
  let leakageVerdict, leakageTone;
  if (Math.abs(overpay) <= 1) {
    leakageVerdict = `✓ Paid amount within qualified-commission limit — no payment detected on unqualified activations`;
    leakageTone = 'text-emerald-700 bg-emerald-50 border-emerald-200';
  } else if (overpay > 1) {
    leakageVerdict = `⚠ ${formatNGN(overpay)} paid beyond qualified activations — likely commission paid on unqualified records. Cross-reference ${zeroCount} zero-commission record${zeroCount === 1 ? '' : 's'} for this dealer.`;
    leakageTone = 'text-red-700 bg-red-50 border-red-200';
  } else {
    leakageVerdict = `ℹ Paid amount is below the qualified commission — dealer is under-paid by ${formatNGN(Math.abs(overpay))}, not a leakage concern.`;
    leakageTone = 'text-gray-700 bg-gray-50 border-gray-200';
  }

  return (
    <div className="bg-gray-50 border border-gray-200 rounded-md px-4 py-3 m-2">
      <div className="text-[10px] uppercase tracking-wide text-gray-500 mb-2">
        Activation verification · {row.distributor_name}
      </div>

      {/* 4-column metric grid */}
      <div className="grid grid-cols-2 sm:grid-cols-4 gap-3 text-xs">
        <Metric label="Total activations"   value={total.toLocaleString()} />
        <Metric
          label={<>Qualified <HelpIcon label="What is a qualified activation?">{QUALIFICATION_HELP}</HelpIcon></>}
          value={qualified.toLocaleString()}
          tone="text-emerald-700"
        />
        <Metric
          label={<>Unqualified <HelpIcon label="What is an unqualified activation?">{QUALIFICATION_HELP}</HelpIcon></>}
          value={unqualified.toLocaleString()}
          tone="text-amber-700"
        />
        <Metric label="Qualification rate"  value={`${rate.toFixed(1)}%`} tone={rate >= 80 ? 'text-emerald-700' : rate >= 50 ? 'text-amber-700' : 'text-red-700'} />
        <Metric label="Earned from qualified" value={formatNGN(earned)} />
        <Metric label="Statement claims"      value={formatNGN(claimed)} />
        <Metric label="Amount paid"           value={formatNGN(paid)} tone="text-gray-700" />
        <Metric
          label="Zero-commission records"
          value={zeroCount.toLocaleString()}
          tone={zeroCount > 0 ? 'text-amber-700' : 'text-gray-500'}
        />
      </div>

      {/* Verdict — does the statement match what the activations earned? */}
      <div className={`mt-3 text-[10px] uppercase tracking-wide text-gray-500`}>
        Statement vs activations
      </div>
      <div className={`mt-1 text-xs font-semibold border rounded px-3 py-2 ${verdictTone}`}>
        {verdict}
      </div>

      {/* Leakage verdict — did we pay commission on unqualified records? */}
      <div className={`mt-2 text-[10px] uppercase tracking-wide text-gray-500 flex items-center`}>
        Payment leakage check
        <HelpIcon label="What is payment leakage?">{LEAKAGE_HELP}</HelpIcon>
      </div>
      <div className={`mt-1 text-xs font-semibold border rounded px-3 py-2 ${leakageTone}`}>
        {leakageVerdict}
      </div>

      {/* Action */}
      {onAsk && (
        <div className="mt-2 flex justify-end">
          <AskButton onAsk={onAsk} row={row} period={period} zeroCount={zeroCount} />
        </div>
      )}
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

function AskButton({ onAsk, row, period, zeroCount = 0 }) {
  const text = zeroCount > 0
    ? `Verify the activations for ${row.distributor_name} in ${period}. How many activations, qualified vs unqualified, and what's the expected commission? There are ${zeroCount} zero-commission records — classify each by KB root cause (USP snapshot miss, outside 6-month window, NULL account_profile_class, or Hynex/Hynex_1 split).`
    : `Verify the activations for ${row.distributor_name} in ${period}. How many activations qualified, what's the expected commission, and does it match the statement claim of ${formatNGN(row.commission_owed)}?`;

  return (
    <button
      onClick={() => onAsk(text)}
      className="text-xs text-gray-700 hover:text-gray-900 font-medium border border-gray-200 rounded-md px-2 py-1 hover:bg-yellow-50 hover:border-mtn-yellow transition"
    >
      Ask Claude →
    </button>
  );
}

// ---------------------------------------------------------------------------
// Main table
// ---------------------------------------------------------------------------

export default function PaymentExceptionsTable({
  rows = [],
  loading = false,
  period = null,
  onAsk = null,
}) {
  const { activationByDealer, dealerByCode } = useDealerVerification(period);
  const [expanded, setExpanded] = useState({}); // { distributor_code: bool }

  if (loading) {
    return (
      <div className="p-4 text-sm text-gray-500 italic">
        Loading payment exceptions…
      </div>
    );
  }
  if (!rows.length) {
    return (
      <div className="p-4 text-sm text-gray-500 italic">
        No outstanding payments.
      </div>
    );
  }

  const toggle = (code) =>
    setExpanded((e) => ({ ...e, [code]: !e[code] }));

  return (
    <div className="overflow-auto h-full">
      <table className="w-full text-xs border-collapse">
        <thead className="sticky top-0 bg-gray-50 z-10">
          <tr className="text-gray-600">
            <th className="border-b border-gray-200 px-2 py-1.5 text-left font-semibold w-6"></th>
            <th className="border-b border-gray-200 px-2 py-1.5 text-left font-semibold">
              Dealer
            </th>
            <th className="border-b border-gray-200 px-2 py-1.5 text-left font-semibold">
              Status
            </th>
            <th className="border-b border-gray-200 px-2 py-1.5 text-right font-semibold">
              Owed
            </th>
            <th className="border-b border-gray-200 px-2 py-1.5 text-right font-semibold">
              Outstanding
            </th>
            <th className="border-b border-gray-200 px-2 py-1.5 text-left font-semibold">
              Exception flag
            </th>
            <th className="border-b border-gray-200 px-2 py-1.5 text-left font-semibold">
              Verify
            </th>
          </tr>
        </thead>
        <tbody>
          {rows.map((r, i) => {
            const code     = r.distributor_code;
            const isOpen   = !!expanded[code];
            const arrow    = isOpen ? '▼' : '▶';
            return [
              <tr
                key={`${code}-${i}`}
                className="hover:bg-gray-50 border-b border-gray-100 align-top"
              >
                <td className="px-2 py-1.5 text-gray-400 cursor-pointer select-none"
                    onClick={() => toggle(code)}
                    title={isOpen ? 'Collapse' : 'Expand verification'}>
                  {arrow}
                </td>
                <td
                  className="px-2 py-1.5 text-gray-800 truncate max-w-[180px]"
                  title={r.distributor_name}
                >
                  {r.distributor_name}
                </td>
                <td className="px-2 py-1.5">
                  <StatusBadge status={r.payment_status} />
                </td>
                <td className="px-2 py-1.5 text-right tabular-nums text-gray-700">
                  {formatNGN(r.commission_owed)}
                </td>
                <td className="px-2 py-1.5 text-right tabular-nums font-semibold text-gray-900">
                  {formatNGN(r.amount_unpaid)}
                </td>
                <td className="px-2 py-1.5">
                  <FlagBadge flag={r.exception_flag} />
                </td>
                <td className="px-2 py-1.5">
                  <button
                    onClick={() => toggle(code)}
                    className="text-xs text-gray-700 hover:text-gray-900 font-medium border border-gray-200 rounded px-2 py-0.5 hover:bg-yellow-50 hover:border-mtn-yellow transition"
                  >
                    {isOpen ? 'Hide' : 'Verify'}
                  </button>
                </td>
              </tr>,
              isOpen && (
                <tr key={`${code}-${i}-detail`} className="bg-gray-50">
                  <td colSpan={7} className="p-0">
                    <VerificationPanel
                      row={r}
                      activation={activationByDealer[code]}
                      dealer={dealerByCode[code]}
                      onAsk={onAsk}
                      period={period}
                    />
                  </td>
                </tr>
              ),
            ];
          })}
        </tbody>
      </table>
    </div>
  );
}
