export const COMPARISON_STATUS = {
  CONFIRMED_MISMATCH: { label: 'Observed excess', tone: 'bg-amber-50 text-amber-900 border-amber-200' },
  NO_INVOICE_RECORD: { label: 'Invoice coverage gap', tone: 'bg-blue-50 text-blue-900 border-blue-200' },
  WITHIN_ALLOCATION: { label: 'Within recorded purchases', tone: 'bg-emerald-50 text-emerald-900 border-emerald-200' },
};

export function units(value) {
  if (value == null || !Number.isFinite(Number(value))) return '—';
  return Number(value).toLocaleString(undefined, { maximumFractionDigits: 2 });
}

export function gapUnits(value) {
  if (value == null || !Number.isFinite(Number(value))) return '—';
  return `${value > 0 ? '+' : ''}${units(value)}`;
}

export function gapPercent(value) {
  return value == null || !Number.isFinite(Number(value)) ? '—' : `${Number(value).toFixed(1)}%`;
}

export function subjectFor(row) {
  return `${row.dealer_id}:${row.product_code}`;
}
