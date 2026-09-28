import test from 'node:test';
import assert from 'node:assert/strict';
import { subscriptionMoney, subscriptionTotal, subscriptionContext, churnLabel } from './subscriptionPresentation.js';

test('subscription amounts distinguish missing evidence, recorded zero and negative variance', () => {
  assert.equal(subscriptionMoney(null), 'Unknown');
  assert.equal(subscriptionMoney(undefined), 'Unknown');
  assert.equal(subscriptionMoney(0), 'NGN 0.00');
  assert.equal(subscriptionMoney(-250), 'NGN -250.00');
});

test('subscription investigation carries exact dealer, synthetic policy and subscription tool scope', () => {
  const context = subscriptionContext({ synthetic: true, commission_available: true, source: 'Synthetic subscription commission fixtures', evidence_as_of: '2026-07-15' }, '202606', { dealer_id: 'SUB-001', dealer_name: 'Demo dealer' });
  assert.match(context, /Illustrative subscription commission policy—not confirmed MTN terms\./);
  assert.match(context, /Synthetic demonstration/);
  assert.match(context, /202606/);
  assert.match(context, /SUB-001/);
  assert.match(context, /2026-07-15/);
  assert.match(context, /get_subscription_summary/);
  assert.match(context, /get_subscription_devices/);
  assert.match(context, /never combine.*activation/i);
  assert.match(subscriptionContext({ synthetic: false, commission_available: false }, '202606'), /revenue only.*commission is unavailable/i);
});

test('churn stays contextual and insufficient history never becomes a negative indicator', () => {
  assert.equal(churnLabel({ history_complete: false, churn_indicator: null }), 'Unknown · insufficient history');
  assert.equal(churnLabel({ history_complete: false, churn_indicator: false }), 'Unknown · insufficient history');
  assert.equal(churnLabel({ history_complete: true, churn_indicator: true }), 'Indicator present · three months without paid subscriptions');
  assert.equal(churnLabel({ history_complete: true, churn_indicator: false }), 'Indicator absent');
});

test('incomplete portfolio figures label the known subtotal without presenting it as the total', () => {
  assert.equal(subscriptionTotal({ simulated_commission_ngn: null, known_simulated_commission_ngn: 1250 }, 'simulated_commission_ngn'), 'Unknown total · NGN 1,250.00 known subtotal');
  assert.equal(subscriptionTotal({ simulated_commission_ngn: 0 }, 'simulated_commission_ngn'), 'NGN 0.00');
  assert.equal(subscriptionTotal({ amount_paid_ngn: null }, 'amount_paid_ngn'), 'Unknown');
});
