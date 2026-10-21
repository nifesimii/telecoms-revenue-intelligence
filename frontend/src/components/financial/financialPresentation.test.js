import test from 'node:test';
import assert from 'node:assert/strict';
import { financialReportCsv, metricValue } from './financialPresentation.js';

test('missing values remain unavailable and negative cash remains a monetary amount', () => {
  assert.equal(metricValue(null, 'percent'), 'Unavailable');
  assert.equal(metricValue(0, 'percent'), '0.00%');
  assert.equal(metricValue(-1234, 'ngn'), 'NGN -1,234.00');
  assert.equal(metricValue(1.234, 'multiple'), '1.23×');
});

test('report export preserves comparison, all statements, absent debt evidence and provenance', () => {
  const csv = financialReportCsv({ dealer_name: '=UNTRUSTED()', dealer_id: 'DEMO-001',
    mon_period: '202603', prior_period: '202602', as_of: '2026-03-31',
    statements: ['Income statement', 'Balance sheet', 'Cash flow statement'].map((label) => ({ label,
      rows: [{ label: 'Example', section: 'Section', amount: -250, prior_amount: 0, evidence: ['ledger'] }] })),
    kpis: [{ label: 'DSCR', value: null, prior_value: null, unit: 'multiple', status: 'unavailable',
      formula: 'EBITDA / debt service', inputs: { scheduled_principal: null }, reason: 'Missing schedule' }],
    evidence: [{ id: 'ledger', label: 'Prepared monthly records', as_of: '2026-03-31', status: 'Synthetic', detail: 'Fictional' }],
    assumptions: ['Monthly, not YTD'],
  });
  assert.ok(csv.includes('SYNTHETIC DEMONSTRATION'));
  assert.ok(csv.includes("'=UNTRUSTED()"));
  assert.ok(csv.includes('202603,202602'));
  assert.ok(csv.includes('Cash flow statement'));
  assert.ok(csv.includes('Balance sheet'));
  assert.ok(csv.includes('Income statement'));
  assert.ok(csv.includes(',-250,0,NGN,'));
  assert.ok(csv.includes('scheduled_principal: Unavailable'));
  assert.ok(csv.includes('Missing schedule'));
  assert.ok(csv.includes('Monthly, not YTD'));
});
