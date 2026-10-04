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

export const SORT_OPTIONS = [
  ['inventory_gap', 'desc', 'Excess units (high → low)'],
  ['activation_count', 'desc', 'Activations (high → low)'],
  ['dealer_name', 'asc', 'Dealer name (A → Z)'],
  ['product_code', 'asc', 'Product code (A → Z)'],
].map(([sort_by, sort_direction, label]) => ({ value: `${sort_by}:${sort_direction}`, sort_by, sort_direction, label }));

// Excess is unknown without an invoice record, so coverage gaps cannot be ranked by it.
export function sortOptionsFor(view) {
  return view === 'coverage' ? SORT_OPTIONS.filter((o) => o.sort_by !== 'inventory_gap') : SORT_OPTIONS;
}

export function sortValue(sort_by, sort_direction, options = SORT_OPTIONS) {
  const match = options.find((o) => o.sort_by === sort_by && o.sort_direction === sort_direction)
    || options.find((o) => o.sort_by === sort_by) || options[0];
  return match.value;
}

export function parseSort(value) {
  const [sort_by, sort_direction] = String(value).split(':');
  return { sort_by, sort_direction };
}

const COLUMNS = [
  { id: 'subject', label: 'Dealer / product' },
  { id: 'purchases', label: 'Recorded purchases', numeric: true },
  { id: 'activations', label: 'Activations', numeric: true },
  { id: 'excess', label: 'Excess units', numeric: true },
  { id: 'excess_pct', label: 'Excess %', numeric: true },
  { id: 'comparison', label: 'Comparison' },
  { id: 'evidence', label: 'Evidence' },
];

export function columnsFor(view) {
  return view === 'coverage' ? COLUMNS.filter((c) => !['purchases', 'excess', 'excess_pct'].includes(c.id)) : COLUMNS;
}

export function subjectFor(row) {
  return `${row.dealer_id}:${row.product_code}`;
}
