// Shared formatters. Keep display rules in one place so the UI stays
// consistent with the agent's KB-mandated format ("NGN X,XXX,XXX.XX")
// and so YYYYMM periods are never shown raw to a finance user.

const MONTHS = [
  'Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun',
  'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec',
];

/** Format a number as "NGN 1,234,567.89". Falls back to "NGN 0.00" on bad input. */
export function formatNGN(n) {
  const v = Number(n) || 0;
  return (
    'NGN ' +
    v.toLocaleString('en-NG', {
      minimumFractionDigits: 2,
      maximumFractionDigits: 2,
    })
  );
}

/** Format a signed delta as "+NGN 1,234.56" / "−NGN 1,234.56" / "NGN 0.00". */
export function formatNGNDelta(n) {
  const v = Number(n) || 0;
  if (v === 0) return formatNGN(0);
  const sign = v > 0 ? '+' : '−';
  return sign + formatNGN(Math.abs(v));
}

/** YYYYMM → "Mon YYYY" for display. Returns the raw value if it doesn't match. */
export function formatPeriod(p) {
  if (!p || !/^\d{6}$/.test(String(p))) return p || '';
  const s = String(p);
  const year = s.slice(0, 4);
  const m = parseInt(s.slice(4, 6), 10);
  const label = MONTHS[m - 1] || s.slice(4, 6);
  return `${label} ${year}`;
}

/** Regex matching the canonical agent output "NGN 1,234.56". Capturing group included. */
export const NGN_RE = /(NGN\s[\d,]+\.\d{2})/g;
export const NGN_MATCH_RE = /^NGN\s[\d,]+\.\d{2}$/;
