// Inventory comparison table — one row per (dealer, product) combination.
//
// Visual cues:
//   * CONFIRMED_MISMATCH   → amber left border, red gap_pct text if >= 100%
//   * NO_INVOICE_RECORD    → blue left border, italicised note
//   * WITHIN_ALLOCATION    → green left border
//
// CONFIRMED_MISMATCH and NO_INVOICE_RECORD rows have an inline Verify
// expandable that cross-references the dealer's commission earned this
// period — answering "are we paying commission on these unauthorised /
// unrecorded units?". WITHIN_ALLOCATION rows don't need verification.

import { useState } from 'react';
import { formatNGN } from '../../lib/format.js';
import HelpIcon, { QUALIFICATION_HELP } from '../shared/HelpIcon.jsx';
import useLazyDealerVerification from '../../hooks/useLazyDealerVerification.js';

const BADGE_STYLE = {
  CONFIRMED_MISMATCH: 'bg-amber-100 text-amber-800 border-amber-200',
  NO_INVOICE_RECORD: 'bg-blue-100 text-blue-800 border-blue-200',
  WITHIN_ALLOCATION: 'bg-emerald-100 text-emerald-800 border-emerald-200',
};

const BORDER_STYLE = {
  CONFIRMED_MISMATCH: 'border-l-4 border-l-amber-400',
  NO_INVOICE_RECORD: 'border-l-4 border-l-blue-400',
  WITHIN_ALLOCATION: 'border-l-4 border-l-emerald-400',
};

const BADGE_TOOLTIP = {
  CONFIRMED_MISMATCH:
    'IFS invoice records exist AND activations exceed purchased units. Requires investigation.',
  NO_INVOICE_RECORD:
    'Activations exist but no IFS invoice record was found in the available window. NOT a confirmed mismatch.',
  WITHIN_ALLOCATION:
    'Activations are within the dealer’s purchased unit count.',
};

function fmtUnits(v) {
  if (v === null || v === undefined) return '—';
  const n = Number(v);
  if (!isFinite(n)) return '—';
  return Number.isInteger(n) ? n.toLocaleString() : n.toFixed(2);
}

function fmtGap(v) {
  if (v === null || v === undefined) return '—';
  const n = Number(v);
  if (!isFinite(n)) return '—';
  const sign = n > 0 ? '+' : n < 0 ? '−' : '';
  return `${sign}${Math.abs(n).toFixed(0)}`;
}

function gapPctTone(v, finding) {
  if (finding === 'WITHIN_ALLOCATION') return 'text-gray-400';
  if (v === null || v === undefined) return 'text-gray-400';
  const n = Number(v);
  if (n >= 100) return 'text-red-700 font-semibold';
  if (n >= 50) return 'text-amber-700 font-semibold';
  return 'text-gray-600';
}

function FindingBadge({ type }) {
  const style = BADGE_STYLE[type] || 'bg-gray-100 text-gray-700 border-gray-200';
  return (
    <span
      className={`inline-block px-2 py-0.5 text-[10px] font-semibold uppercase tracking-wide border rounded-full ${style}`}
      title={BADGE_TOOLTIP[type] || ''}
    >
      {type}
    </span>
  );
}

// ---------------------------------------------------------------------------
// Verification panel
// ---------------------------------------------------------------------------
// Cross-references the inventory gap against the dealer's commission earned
// this period. The headline question for finance: "Are we paying out on
// unauthorised activations?" If commission was earned on the gap units, that's
// a hard issue. If the gap units are exactly the zero-commission ones, the
// system already withheld payment correctly (but the activations still ran).

function Metric({ label, value, tone = 'text-gray-900' }) {
  return (
    <div>
      <div className="text-[10px] uppercase tracking-wide text-gray-500">{label}</div>
      <div className={`text-sm font-semibold tabular-nums ${tone}`}>{value}</div>
    </div>
  );
}

function VerificationPanel({ row, activation, dealer, onAsk, period }) {
  const isNoInvoice = row.finding_type === 'NO_INVOICE_RECORD';
  const gap         = Number(row.inventory_gap || 0);
  const gapPct      = row.gap_pct === null || row.gap_pct === undefined
    ? null : Number(row.gap_pct);

  const totalActs   = Number(activation?.activation_count || 0);
  const qualified   = Number(activation?.qualified_activation_count || 0);
  const qualRate    = Number(activation?.qualification_rate_pct || 0);
  const earned      = Number(activation?.activation_commission_amount || 0);
  const zeroCount   = Number(dealer?.zero_commission_count || 0);

  // Verdict heuristic — based on what data we have at the dealer level,
  // not per-product (per-product commission isn't exposed as an endpoint).
  let verdict, verdictTone;
  if (isNoInvoice) {
    verdict =
      'ℹ Caveat: no IFS invoice record found in the 6-month window. ' +
      'This is a data-coverage gap, not a confirmed mismatch. Verify ' +
      'whether the dealer purchased these units in a prior period before flagging.';
    verdictTone = 'text-blue-800 bg-blue-50 border-blue-200';
  } else if (zeroCount > 0 && gap > 0) {
    verdict =
      `✓ ${zeroCount} zero-commission record${zeroCount === 1 ? '' : 's'} present — ` +
      `system already withheld commission on at least some unauthorised activations. ` +
      `Confirm the gap units overlap with the zero-commission set.`;
    verdictTone = 'text-emerald-700 bg-emerald-50 border-emerald-200';
  } else if (gap > 0 && earned > 0 && zeroCount === 0) {
    verdict =
      `✗ Dealer earned ${formatNGN(earned)} this period and there are no zero-commission ` +
      `records to offset the gap. Likely paying commission on unauthorised activations — ` +
      `investigate before next settlement.`;
    verdictTone = 'text-red-700 bg-red-50 border-red-200';
  } else {
    verdict =
      `⚠ Gap of ${Math.abs(gap)} units. Cross-reference dealer's zero-commission records ` +
      `to confirm exposure.`;
    verdictTone = 'text-amber-800 bg-amber-50 border-amber-200';
  }

  return (
    <div className="bg-gray-50 border border-gray-200 rounded-md px-4 py-3 m-2">
      <div className="text-[10px] uppercase tracking-wide text-gray-500 mb-2">
        Inventory verification · {row.dealer_name} · {row.product_code}
      </div>

      <div className="grid grid-cols-2 sm:grid-cols-4 gap-3 text-xs">
        <Metric label="Purchased units" value={fmtUnits(row.total_units_purchased)} />
        <Metric label="Activated units" value={fmtUnits(row.activation_count)} />
        <Metric
          label="Inventory gap"
          value={fmtGap(gap)}
          tone={gap > 0 ? 'text-red-700' : 'text-gray-700'}
        />
        <Metric
          label="Gap %"
          value={gapPct === null ? '—' : `${gapPct.toFixed(1)}%`}
          tone={gapPct >= 100 ? 'text-red-700' : gapPct >= 50 ? 'text-amber-700' : 'text-gray-700'}
        />
        <Metric label="Dealer total activations" value={totalActs.toLocaleString()} />
        <Metric
          label={<>Dealer qualified <HelpIcon label="What is a qualified activation?">{QUALIFICATION_HELP}</HelpIcon></>}
          value={qualified.toLocaleString()}
          tone="text-emerald-700"
        />
        <Metric
          label="Dealer commission earned"
          value={formatNGN(earned)}
        />
        <Metric
          label="Zero-commission records"
          value={zeroCount.toLocaleString()}
          tone={zeroCount > 0 ? 'text-amber-700' : 'text-gray-500'}
        />
      </div>

      <div className={`mt-3 text-xs font-semibold border rounded px-3 py-2 ${verdictTone}`}>
        {verdict}
      </div>

      {onAsk && (
        <div className="mt-2 flex justify-end">
          <button
            onClick={() => onAsk(
              isNoInvoice
                ? `Investigate ${row.dealer_name}'s ${row.product_code} activations in ${period}. There are ${row.activation_count} activations but no IFS invoice record in the 6-month window. Could these units have been purchased outside the data window? What's the dealer's commission for this period?`
                : `Investigate ${row.dealer_name}'s ${row.product_code} inventory in ${period}. They activated ${row.activation_count} units but only purchased ${fmtUnits(row.total_units_purchased)} — a gap of ${Math.abs(gap)} units. Are these unauthorised activations earning commission? Cross-reference against zero-commission records (${zeroCount} for this dealer this period) and classify by KB root cause.`
            )}
            className="text-xs text-gray-700 hover:text-gray-900 font-medium border border-gray-200 rounded-md px-2 py-1 hover:bg-yellow-50 hover:border-mtn-yellow transition"
          >
            Ask Claude →
          </button>
        </div>
      )}
    </div>
  );
}

// ---------------------------------------------------------------------------
// Collapsed-row verdict chip — surface the key verdict before expanding.
// ---------------------------------------------------------------------------

function inventoryVerdict(row, activation, dealer) {
  const isNoInvoice = row.finding_type === 'NO_INVOICE_RECORD';
  if (isNoInvoice) return { label: 'ℹ No invoice record', tone: 'bg-blue-100 text-blue-800 border-blue-200' };
  const gap      = Number(row.inventory_gap || 0);
  const earned   = Number(activation?.activation_commission_amount || 0);
  const zeroCount = Number(dealer?.zero_commission_count || 0);
  if (zeroCount > 0 && gap > 0) return { label: '✓ Commission withheld', tone: 'bg-emerald-100 text-emerald-800 border-emerald-200' };
  if (gap > 0 && earned > 0 && zeroCount === 0) return { label: '✗ Possible leakage', tone: 'bg-red-100 text-red-800 border-red-200' };
  return { label: '⚠ Review needed', tone: 'bg-amber-100 text-amber-800 border-amber-200' };
}

function InventoryVerificationChip({ row, activation, dealer }) {
  const { label, tone } = inventoryVerdict(row, activation, dealer);
  return (
    <span className={`inline-block px-2 py-0.5 text-[10px] font-semibold border rounded-full ${tone}`}>
      {label}
    </span>
  );
}

// ---------------------------------------------------------------------------
// Main table
// ---------------------------------------------------------------------------

export default function InventoryComparisonTable({
  rows = [],
  loading = false,
  period = null,
  onAsk = null,
}) {
  const [expanded, setExpanded] = useState({}); // { `${dealer}-${product}-${i}`: bool }
  const { records: verificationByDealer, loading: verificationLoading, load } = useLazyDealerVerification(period);

  if (loading) {
    return (
      <div className="p-4 text-sm text-gray-500 italic">
        Loading inventory comparison…
      </div>
    );
  }
  if (!rows.length) {
    return <div className="p-4 text-sm text-gray-500 italic">No data.</div>;
  }

  const toggle = (key, dealerId) => {
    const opening = !expanded[key];
    setExpanded((e) => ({ ...e, [key]: !e[key] }));
    if (opening) load(dealerId).catch(() => {});
  };

  return (
    <div className="overflow-auto h-full">
      <table className="w-full text-xs border-collapse">
        <thead className="sticky top-0 bg-gray-50 z-10">
          <tr className="text-gray-600">
            <th className="border-b border-gray-200 px-2 py-1.5 text-left font-semibold w-6"></th>
            <th className="border-b border-gray-200 px-2 py-1.5 text-left font-semibold">Dealer</th>
            <th className="border-b border-gray-200 px-2 py-1.5 text-left font-semibold">Product</th>
            <th className="border-b border-gray-200 px-2 py-1.5 text-right font-semibold">Purchased</th>
            <th className="border-b border-gray-200 px-2 py-1.5 text-right font-semibold">Activations</th>
            <th className="border-b border-gray-200 px-2 py-1.5 text-right font-semibold">Gap</th>
            <th className="border-b border-gray-200 px-2 py-1.5 text-right font-semibold">Gap %</th>
            <th className="border-b border-gray-200 px-2 py-1.5 text-left font-semibold">Finding</th>
            <th className="border-b border-gray-200 px-2 py-1.5 text-left font-semibold">Verify</th>
          </tr>
        </thead>
        <tbody>
          {rows.map((r, i) => {
            const key = `${r.dealer_id}-${r.product_code}-${i}`;
            const isOpen = !!expanded[key];
            const canVerify = r.finding_type !== 'WITHIN_ALLOCATION';
            return [
              <tr
                key={key}
                className={`hover:bg-gray-50 border-b border-gray-100 align-top ${
                  BORDER_STYLE[r.finding_type] || ''
                }`}
              >
                <td className="px-2 py-1.5 w-6">
                  {canVerify ? (
                    <button
                      onClick={() => toggle(key, r.dealer_id)}
                      aria-expanded={isOpen}
                      aria-label={isOpen ? 'Collapse verification' : 'Expand verification'}
                      className="text-gray-400 hover:text-gray-700 select-none"
                    >
                      {isOpen ? '▼' : '▶'}
                    </button>
                  ) : null}
                </td>
                <td className="px-2 py-1.5 text-gray-800 truncate max-w-[200px]" title={r.dealer_name}>
                  {r.dealer_name}
                </td>
                <td className="px-2 py-1.5 text-gray-600 truncate max-w-[120px]" title={r.product_name}>
                  {r.product_code}
                </td>
                <td className="px-2 py-1.5 text-right tabular-nums text-gray-700">
                  {fmtUnits(r.total_units_purchased)}
                </td>
                <td className="px-2 py-1.5 text-right tabular-nums text-gray-800">
                  {r.activation_count}
                </td>
                <td className="px-2 py-1.5 text-right tabular-nums text-gray-700">
                  {fmtGap(r.inventory_gap)}
                </td>
                <td className={`px-2 py-1.5 text-right tabular-nums ${gapPctTone(r.gap_pct, r.finding_type)}`}>
                  {r.gap_pct === null || r.gap_pct === undefined
                    ? '—'
                    : `${Number(r.gap_pct).toFixed(1)}%`}
                </td>
                <td className="px-2 py-1.5">
                  <FindingBadge type={r.finding_type} />
                </td>
                <td className="px-2 py-1.5">
                  {canVerify ? (
                    <div className="flex flex-col gap-1 items-start">
                      {!isOpen && (
                        <InventoryVerificationChip
                          row={r}
                          activation={verificationByDealer[r.dealer_id]}
                          dealer={verificationByDealer[r.dealer_id]}
                        />
                      )}
                      <button
                        onClick={() => toggle(key)}
                        className="text-xs text-gray-700 hover:text-gray-900 font-medium border border-gray-200 rounded px-2 py-0.5 hover:bg-yellow-50 hover:border-mtn-yellow transition"
                      >
                        {isOpen ? 'Hide' : 'Verify'}
                      </button>
                    </div>
                  ) : (
                    <span className="text-[10px] text-gray-400 italic">n/a</span>
                  )}
                </td>
              </tr>,
              canVerify && isOpen && verificationLoading[r.dealer_id] && (
                <tr key={`${key}-loading`}><td colSpan={9} className="p-3 text-xs text-gray-500 italic">Loading verification evidence…</td></tr>
              ),
              canVerify && isOpen && !verificationLoading[r.dealer_id] && (
                <tr key={`${key}-detail`} className="bg-gray-50">
                  <td colSpan={9} className="p-0">
                    <VerificationPanel
                      row={r}
                      activation={verificationByDealer[r.dealer_id]}
                      dealer={verificationByDealer[r.dealer_id]}
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
