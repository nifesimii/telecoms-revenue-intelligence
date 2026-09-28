import { formatNGN } from '../../lib/format.js';

export function subscriptionMoney(value) {
  return value == null ? 'Unknown' : formatNGN(value);
}

export function subscriptionTotal(totals, field) {
  if (totals[field] != null) return subscriptionMoney(totals[field]);
  const known = totals[`known_${field}`];
  return known == null ? 'Unknown' : `Unknown total · ${subscriptionMoney(known)} known subtotal`;
}

export const PAYMENT_LABELS = { paid: 'Paid', overdue: 'Overdue', not_yet_due: 'Not yet due', unknown: 'Unknown evidence', mixed: 'Mixed payment states', not_applicable: 'Not applicable' };
export const REASON_LABELS = { eligible: 'Eligible', below_minimum: 'Below monthly minimum', no_paid_subscription: 'No paid subscription this month', expired_eligibility: 'Eligibility expired', unknown_evidence: 'Unknown evidence' };

export function churnLabel(device) {
  if (!device.history_complete) return 'Unknown · insufficient history';
  if (device.churn_indicator == null) return 'Unknown';
  return device.churn_indicator ? 'Indicator present · three months without paid subscriptions' : 'Indicator absent';
}

export function subscriptionContext(data, period, account) {
  return `Subscription investigation for reporting period ${period}. ${account ? `Exact selling dealer ${account.dealer_id} (${account.dealer_name}); do not combine accounts.` : 'Portfolio-level investigation.'} ${data.synthetic ? `Synthetic demonstration; fictional records are not evidence of actual MTN amounts owed. ${data.policy_label}` : 'Live recorded subscription revenue only; commission is unavailable.'} Source: ${data.source || 'subscription records'}. Evidence as of: ${data.evidence_as_of || 'unknown'}. Use get_subscription_summary and get_subscription_devices for this scope. Preserve provenance and the exact policy label in every answer carrying illustrative figures. Distinguish recorded revenue, eligible revenue, simulated commission, dealer expectation and variance (recorded minus expectation). Never combine subscription settlements with activation payments. Use supplied payment evidence; unknown remains unknown. Paid activity, eligibility and exclusion are separate from contextual churn; churn is never an exclusion. ${!data.commission_available ? 'Commission evidence is unavailable; do not invent commission, expectations or payments.' : 'Explain supplied recorded calculations; do not recalculate policy.'}`;
}
