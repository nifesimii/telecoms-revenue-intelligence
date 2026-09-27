import test from 'node:test';
import assert from 'node:assert/strict';
import { evidenceReport, qualifications } from './auditPresentation.js';

test('readable evidence preserves the saved conclusion, positive payment and provenance', () => {
  const trail = { partner_name: 'Example dealer', partner_code: 'D1', module: 'zero_commission', mon_period: '202602', conclusion: 'NOT_PAID', confidence: 'LOW', partial_payment: true,
    measures: { expected_commission_ngn: 1000, amount_paid_ngn: 250 }, generated_at: '2026-08-05', run_id: 'run-1', pipeline_version: '1.0.0', payment_source: 'simulated', steps: [{step: 5, name: 'near_match', result: 'Partial payment detected', caveat: 'Manual review', detail: {amount_paid_ngn: 250}}] };
  const report = evidenceReport(trail);
  assert.match(report, /NOT_PAID/);
  assert.match(report, /NGN 250.00/);
  assert.match(report, /does not mean no payment occurred/);
  assert.match(report, /Manual review/);
  assert.match(report, /run-1/);
  assert.match(report, /simulated/);
});

test('high confidence without caveats does not suppress Inventory limitations', () => {
  const notes = qualifications({ module: 'inventory_mismatch', confidence: 'HIGH', caveat_count: 0, limitations: ['Purchase-only records omitted'] });
  assert.equal(notes[0], 'Purchase-only records omitted');
  assert.match(notes[1], /does not establish complete period coverage/);
});

test('historical report qualifies entitlement while preserving recorded wording', () => {
  const report = evidenceReport({ partner_code: 'D1', module: 'eligibility_window', steps: [{step: 4, name: 'classify_against_window', result: 'should have earned commission', presentation_result: 'other eligibility checks required', presentation_qualification: 'Historical wording qualified for display'}] });
  assert.match(report, /other eligibility checks required/);
  assert.match(report, /Being inside the window alone does not establish commission entitlement; other eligibility checks are required\./);
  assert.doesNotMatch(report, /Inside the window; other eligibility checks required/);
  assert.match(report, /Original recorded wording: should have earned commission/);
});
