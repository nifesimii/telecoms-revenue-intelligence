import { formatNGN } from '../../lib/format.js';

export const label = (value) => value ? String(value).toLowerCase().replaceAll('_', ' ').replace(/^./, (c) => c.toUpperCase()) : 'Unavailable';
export const savedTime = (value) => value ? new Date(value).toLocaleString() : 'Unavailable';
const MEASURE_LABELS = {
  total_units_purchased: 'Recorded purchases (units)', activation_count: 'Activation records', inventory_gap: 'Activations minus purchases (units)',
  zero_commission_count: 'Zero-commission records', inside_window_count: 'Inside window', outside_window_count: 'Outside window',
  future_dated_count: 'Future-dated records', without_dates_count: 'Missing dates', attributed_count: 'Other documented causes', unexplained_count: 'Unexplained inside window',
  expected_commission_ngn: 'Saved expected commission', amount_paid_ngn: 'Recorded payment', delta_ngn: 'Saved payment difference',
};
export const measureLabel = (key) => MEASURE_LABELS[key] || label(key);
export function measureValue(key, value) {
  if (value == null || !Number.isFinite(Number(value))) return '—';
  return key.endsWith('_ngn') ? formatNGN(Number(value)) : Number(value).toLocaleString();
}
export function qualifications(trail) {
  const notes = [...(trail.limitations || [])];
  if (trail.module === 'inventory_mismatch') notes.push('Carryover and alias checks can miss products with purchases but no activations. Invoice data presence does not establish complete period coverage. Excess units do not establish commission owed.');
  if (trail.module === 'eligibility_window') notes.push('Inside the window; other eligibility checks required. Window classification alone does not establish commission entitlement.');
  if (trail.conclusion === 'NOT_PAID' && Number(trail.measures?.amount_paid_ngn) > 0) notes.push(`${trail.partial_payment ? 'Partial payment' : 'Positive payment'} recorded: ${formatNGN(Number(trail.measures.amount_paid_ngn))}. The saved NOT_PAID label does not mean no payment occurred. Manual review is required.`);
  return notes;
}
export function detailText(value, indent = '') {
  if (value == null) return 'Unavailable';
  if (Array.isArray(value)) return value.map((v) => `${indent}- ${detailText(v, indent + '  ')}`).join('\n') || 'None recorded';
  if (typeof value === 'object') return Object.entries(value).filter(([k]) => k !== 'query').map(([k, v]) => `${indent}${label(k)}: ${k.endsWith('_ngn') ? measureValue(k, v) : detailText(v, indent + '  ')}`).join('\n');
  return String(value);
}
export function evidenceReport(trail) {
  return [
    'AUDIT TRAILS — SAVED EVIDENCE', `${trail.partner_name} · ${trail.partner_code}`,
    `Module: ${label(trail.module)} (${trail.module})`, `Reporting period: ${trail.mon_period}`,
    `Recorded conclusion: ${label(trail.conclusion)} (${trail.conclusion})`, `Recorded confidence: ${trail.confidence}`,
    '\nSUPPORTING MEASURES', ...Object.entries(trail.measures || {}).map(([k, v]) => `${measureLabel(k)}: ${measureValue(k, v)}`),
    '\nCHECKS', ...(trail.steps || []).flatMap((step) => [
      `${step.step}. ${label(step.name)} — recorded check ${step.passed ? 'passed' : 'did not pass'}`,
      step.checked, step.presentation_result || step.result,
      ...(step.presentation_qualification ? [step.presentation_qualification, `Original recorded wording: ${step.result}`] : []),
      `Caveat: ${step.caveat || 'No recorded caveat'}`, detailText(step.detail),
    ]), '\nLIMITATIONS', ...qualifications(trail),
    '\nPROVENANCE', `Saved: ${trail.generated_at || 'Unavailable'}`, `Source: ${trail.payment_source || 'Unavailable'}`,
    `Run: ${trail.run_id || 'Unavailable'}`, `Pipeline: ${trail.pipeline_version || 'Unavailable'}`, `Trail: ${trail.trail_id || 'Unavailable'}`,
    'Save/retrieval time is not source freshness. Earlier trail versions are not retained. Recorded assessments are not independently verified financial outcomes.',
  ].join('\n');
}
export function downloadEvidence(trail) {
  const url = URL.createObjectURL(new Blob([evidenceReport(trail)], { type: 'text/plain;charset=utf-8' }));
  const a = document.createElement('a');
  a.href = url;
  a.download = `audit-${trail.module}-${trail.mon_period}-${trail.partner_code.replace(/[^a-zA-Z0-9_-]/g, '_')}.txt`;
  a.click();
  URL.revokeObjectURL(url);
}
