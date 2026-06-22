// Small ⓘ icon with a hover/focus tooltip. Used wherever a term needs an
// inline definition without cluttering the UI (e.g. "qualified",
// "unqualified", "reconciliation_status").
//
// Centralised glossary lives in QUALIFICATION_HELP / RECONCILIATION_HELP
// below so the same definition is reused everywhere — change one place,
// every panel updates.

const baseTooltip =
  'invisible group-hover:visible group-focus-within:visible absolute z-30 bottom-full left-1/2 -translate-x-1/2 mb-1 px-3 py-2 bg-gray-900 text-white text-[11px] leading-snug rounded-md shadow-lg w-[280px] whitespace-normal';

export default function HelpIcon({ label, children, side = 'top' }) {
  return (
    <span
      tabIndex={0}
      role="img"
      aria-label={label || 'Help'}
      className="group relative inline-flex items-center justify-center w-3.5 h-3.5 ml-1 rounded-full border border-gray-300 text-[9px] font-bold text-gray-400 hover:text-gray-700 hover:border-gray-500 cursor-help select-none align-middle focus:outline-none focus:ring-2 focus:ring-mtn-yellow"
    >
      i
      <span className={`${baseTooltip} ${side === 'top' ? '' : 'bottom-auto top-full mt-1'}`}>
        {children}
      </span>
    </span>
  );
}

// ---------------------------------------------------------------------------
// Canonical glossary — keep in sync with the FBB Commission KB
// ---------------------------------------------------------------------------

export const QUALIFICATION_HELP = (
  <span>
    <strong>Qualified activation:</strong> earned commission. The dealer's{' '}
    <code>account_profile_class</code> exists in the USP snapshot, the device
    was activated within the 6-month eligibility window, and the product has a
    non-zero commission rate.
    <br />
    <br />
    <strong>Unqualified:</strong> did NOT earn commission. Per the FBB
    Commission KB, the four documented root causes are: USP snapshot miss;
    outside the 6-month window; NULL <code>account_profile_class</code>; or a
    known denomination split (Hynex / Hynex_1).
  </span>
);

export const RECONCILIATION_HELP = (
  <span>
    <strong>Reconciliation status</strong> is computed from APDP's{' '}
    <code>normalized.partner_settlements</code> view per dealer-period:
    <br />
    <strong>RECONCILED</strong> — sales, statement, and settlement all line up.
    <br />
    <strong>PARTIALLY_PAID</strong> — settlement is in flight but incomplete.
    <br />
    <strong>DISPUTED</strong> — settlement failed; needs investigation.
    <br />
    <strong>SALES_WITHOUT_STATEMENT</strong> — dealer sold but MTN hasn't
    issued a commission statement (potential leakage).
    <br />
    <strong>STATEMENT_WITHOUT_PAYMENT</strong> — statement issued but no
    settlement yet.
    <br />
    <strong>AMOUNT_MISMATCH</strong> — settled amount differs from statement.
  </span>
);

export const LEAKAGE_HELP = (
  <span>
    <strong>Payment leakage check:</strong> compares <em>amount paid</em>{' '}
    against the commission the dealer's <em>qualified</em> activations
    actually earned. If MTN paid more than the qualified activations support,
    the excess was paid on unqualified records — i.e. commission was paid on
    activations that should not have earned it. Tolerance ±NGN 1 for rounding.
  </span>
);
