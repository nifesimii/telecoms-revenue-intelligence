import { buildCsv } from '../../lib/csv.js';
import { formatNGN } from '../../lib/format.js';

export function metricValue(value, unit) {
  if (value == null || !Number.isFinite(Number(value))) return 'Unavailable';
  if (unit === 'ngn') return formatNGN(value);
  return `${Number(value).toFixed(2)}${unit === 'percent' ? '%' : '×'}`;
}

export function financialReportCsv(report) {
  const evidenceNames = Object.fromEntries(report.evidence.map((source) => [source.id, source.label]));
  const metadata = { dealer: report.dealer_name, dealer_id: report.dealer_id, period: report.mon_period,
    prior_period: report.prior_period || '', provenance: 'SYNTHETIC DEMONSTRATION', as_of: report.as_of };
  const rows = report.statements.flatMap((statement) => statement.rows.map((row) => ({
    ...metadata, statement: statement.label, section: row.section, line_item: row.label,
    value: row.amount, prior_value: row.prior_amount, unit: 'NGN', status: 'Synthetic',
    evidence: row.evidence.map((id) => evidenceNames[id]).join('; '),
  })));
  for (const metric of report.kpis) rows.push({ ...metadata, statement: 'KPIs', line_item: metric.label,
    value: metric.value, prior_value: metric.prior_value, unit: metric.unit, status: metric.status,
    evidence: `${metric.formula}; ${Object.entries(metric.inputs).map(([key, value]) => `${key}: ${value ?? 'Unavailable'}`).join('; ')}; ${metric.reason}` });
  for (const source of report.evidence) rows.push({ ...metadata, statement: 'Source evidence', line_item: source.label,
    as_of: source.as_of || '', status: source.status, evidence: source.detail });
  for (const note of report.assumptions) rows.push({ ...metadata, statement: 'Assumptions', evidence: note });
  const fields = ['provenance', 'dealer', 'dealer_id', 'period', 'prior_period', 'as_of', 'statement', 'section', 'line_item', 'value', 'prior_value', 'unit', 'status', 'evidence'];
  // Protect spreadsheet text cells while preserving negative numeric amounts.
  const safeRows = rows.map((row) => Object.fromEntries(Object.entries(row).map(([key, value]) =>
    [key, typeof value === 'string' && /^[\s]*[=+@-]/.test(value) ? `'${value}` : value])));
  return buildCsv(fields.map((key) => ({ key, header: key.replaceAll('_', ' ') })), safeRows);
}
