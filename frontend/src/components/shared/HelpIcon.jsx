// Small "?" icon with a floating tooltip.
//
// The tooltip is rendered through a React Portal at document.body so it
// escapes the overflow:hidden / overflow:auto boundaries of every parent
// (tables, scrollable panels, modals). Positioned via fixed coordinates
// from the icon's bounding rect — auto-flips below the icon when too
// close to the viewport top.
//
// Centralised glossary lives in QUALIFICATION_HELP / RECONCILIATION_HELP /
// LEAKAGE_HELP below so the same definition is reused everywhere.

import { useCallback, useEffect, useRef, useState } from 'react';
import { createPortal } from 'react-dom';

const TOOLTIP_WIDTH = 320;
const TOOLTIP_OFFSET = 10;
const MIN_HEIGHT = 140;        // never collapse below this even in cramped viewports
const VIEWPORT_PADDING = 8;    // breathing room at viewport edges

export default function HelpIcon({ label, children }) {
  const iconRef = useRef(null);
  const [open, setOpen] = useState(false);
  const [pos, setPos] = useState(null);

  // Open state is held by EITHER the icon hover OR the tooltip hover. Two
  // refs + a deferred close so the cursor can move from icon → tooltip
  // without the tooltip vanishing mid-flight.
  const overIcon = useRef(false);
  const overTooltip = useRef(false);
  const closeTimer = useRef(null);

  const compute = useCallback(() => {
    const el = iconRef.current;
    if (!el) return;
    const r = el.getBoundingClientRect();
    const half = TOOLTIP_WIDTH / 2;
    const cx = r.left + r.width / 2;
    const left = Math.max(VIEWPORT_PADDING, Math.min(window.innerWidth - half - VIEWPORT_PADDING, cx)) - half;

    const spaceAbove = r.top - VIEWPORT_PADDING;
    const spaceBelow = window.innerHeight - r.bottom - VIEWPORT_PADDING;
    // Show on whichever side has more vertical room.
    const flip = spaceBelow >= spaceAbove;
    const top = flip ? r.bottom + TOOLTIP_OFFSET : r.top - TOOLTIP_OFFSET;
    // Cap max-height to available space minus offset; never smaller than MIN_HEIGHT
    // (which means the tooltip itself becomes internally scrollable if needed).
    const maxHeight = Math.max(
      MIN_HEIGHT,
      (flip ? spaceBelow : spaceAbove) - TOOLTIP_OFFSET,
    );
    setPos({ left, top, flip, maxHeight });
  }, []);

  const scheduleClose = useCallback(() => {
    if (closeTimer.current) clearTimeout(closeTimer.current);
    closeTimer.current = setTimeout(() => {
      if (!overIcon.current && !overTooltip.current) setOpen(false);
    }, 80);
  }, []);

  const cancelClose = useCallback(() => {
    if (closeTimer.current) {
      clearTimeout(closeTimer.current);
      closeTimer.current = null;
    }
  }, []);

  const onIconEnter = useCallback(() => {
    overIcon.current = true;
    cancelClose();
    compute();
    setOpen(true);
  }, [compute, cancelClose]);

  const onIconLeave = useCallback(() => {
    overIcon.current = false;
    scheduleClose();
  }, [scheduleClose]);

  const onTooltipEnter = useCallback(() => {
    overTooltip.current = true;
    cancelClose();
  }, [cancelClose]);

  const onTooltipLeave = useCallback(() => {
    overTooltip.current = false;
    scheduleClose();
  }, [scheduleClose]);

  // Reposition on scroll/resize; close if the icon scrolls out of view.
  useEffect(() => {
    if (!open) return;
    function update() {
      const el = iconRef.current;
      if (!el) return setOpen(false);
      const r = el.getBoundingClientRect();
      if (r.bottom < 0 || r.top > window.innerHeight) return setOpen(false);
      compute();
    }
    window.addEventListener('scroll', update, true);
    window.addEventListener('resize', update);
    return () => {
      window.removeEventListener('scroll', update, true);
      window.removeEventListener('resize', update);
    };
  }, [open, compute]);

  return (
    <>
      <span
        ref={iconRef}
        tabIndex={0}
        role="img"
        aria-label={label || 'Help'}
        onMouseEnter={onIconEnter}
        onMouseLeave={onIconLeave}
        onFocus={onIconEnter}
        onBlur={onIconLeave}
        className="inline-flex items-center justify-center w-4 h-4 ml-1 rounded-full bg-gray-200 text-gray-600 text-[10px] font-bold hover:bg-mtn-yellow hover:text-gray-900 cursor-help select-none align-middle focus:outline-none focus:ring-2 focus:ring-mtn-yellow"
      >
        ?
      </span>
      {open && pos && createPortal(
        <div
          role="tooltip"
          onMouseEnter={onTooltipEnter}
          onMouseLeave={onTooltipLeave}
          style={{
            position: 'fixed',
            left: pos.left,
            top: pos.top,
            width: TOOLTIP_WIDTH,
            maxHeight: pos.maxHeight,
            transform: pos.flip ? 'none' : 'translateY(-100%)',
            zIndex: 9999,
            overflowY: 'auto',
          }}
          className="px-3 py-2 bg-gray-900 text-white text-xs leading-snug rounded-md shadow-xl"
        >
          {children}
        </div>,
        document.body,
      )}
    </>
  );
}

// ---------------------------------------------------------------------------
// Canonical glossary — keep in sync with the FBB Commission KB
// ---------------------------------------------------------------------------

export const QUALIFICATION_HELP = (
  <div className="space-y-2">
    <div>
      <strong className="text-mtn-yellow">Qualified activation</strong>
      <div className="mt-0.5">
        An activation MTN pays commission on. All three must be true:
      </div>
      <ul className="list-disc ml-4 mt-1 space-y-0.5">
        <li>The dealer is on file with a valid profile class</li>
        <li>The device was activated within 6 months of MTN invoicing it to the dealer</li>
        <li>The product carries a commission rate above zero</li>
      </ul>
    </div>
    <div>
      <strong className="text-mtn-yellow">Unqualified activation</strong>
      <div className="mt-0.5">
        An activation that earns no commission. There are four documented reasons:
      </div>
      <ul className="list-disc ml-4 mt-1 space-y-0.5">
        <li>The dealer's profile is missing from MTN's snapshot</li>
        <li>The activation fell outside the 6-month eligibility window</li>
        <li>The dealer's profile class is blank</li>
        <li>The product is a known edge case the commission engine treats separately (Hynex variants)</li>
      </ul>
    </div>
    <div className="pt-1 border-t border-gray-700 text-gray-300">
      <em>Why it matters:</em> unqualified activations are the main reason
      dealers dispute their payouts. The four reasons above guide where to
      look when investigating.
    </div>
  </div>
);

export const RECONCILIATION_HELP = (
  <div className="space-y-2">
    <div>
      <strong className="text-mtn-yellow">Reconciliation status</strong>
      <div className="mt-0.5">
        How well a dealer's sales, commission statement, and settlement line
        up for the period. One of six values:
      </div>
    </div>
    <ul className="list-none space-y-1">
      <li><strong>RECONCILED</strong> — all three legs match. No action needed.</li>
      <li><strong>PARTIALLY_PAID</strong> — settlement started but the dealer hasn't been paid in full yet.</li>
      <li><strong>DISPUTED</strong> — settlement failed. Needs investigation before re-issue.</li>
      <li><strong>SALES_WITHOUT_STATEMENT</strong> — the dealer sold devices but MTN hasn't issued a commission statement. Possible commission leakage.</li>
      <li><strong>STATEMENT_WITHOUT_PAYMENT</strong> — MTN owes commission but no payment has been issued.</li>
      <li><strong>AMOUNT_MISMATCH</strong> — the amount settled doesn't match what the statement claims is owed.</li>
    </ul>
  </div>
);

export const LEAKAGE_HELP = (
  <div className="space-y-1.5">
    <div>
      <strong className="text-mtn-yellow">Payment leakage check</strong>
    </div>
    <div>
      Compares what MTN actually paid the dealer against what the dealer's
      qualified activations actually earned.
    </div>
    <div>
      If MTN paid <em>more</em> than the qualified activations support, the
      excess was paid on activations that should not have earned commission —
      that's a leak.
    </div>
    <div className="text-gray-300 text-[11px]">
      Tolerance of ±NGN 1 to absorb rounding.
    </div>
  </div>
);
