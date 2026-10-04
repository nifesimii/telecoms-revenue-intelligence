import test from 'node:test';
import assert from 'node:assert/strict';
import { SORT_OPTIONS, columnsFor, parseSort, sortOptionsFor, sortValue } from './inventoryPresentation.js';

test('combined sort list covers both panel defaults and round-trips', () => {
  assert.deepEqual(SORT_OPTIONS.map((o) => o.label), ['Excess units (high → low)', 'Activations (high → low)', 'Dealer name (A → Z)', 'Product code (A → Z)']);
  assert.equal(sortValue('inventory_gap', 'desc'), 'inventory_gap:desc');
  assert.equal(sortValue('activation_count', 'desc'), 'activation_count:desc');
  for (const option of SORT_OPTIONS) {
    const { sort_by, sort_direction } = parseSort(option.value);
    assert.equal(sortValue(sort_by, sort_direction), option.value);
  }
  assert.deepEqual(parseSort('dealer_name:asc'), { sort_by: 'dealer_name', sort_direction: 'asc' });
});

test('sortValue falls back to a selectable option for unlisted pairs', () => {
  assert.equal(sortValue('dealer_name', 'desc'), 'dealer_name:asc');
  assert.equal(sortValue('unknown', 'asc'), SORT_OPTIONS[0].value);
  assert.equal(sortValue('inventory_gap', 'asc', sortOptionsFor('coverage')), 'activation_count:desc');
});

test('coverage view hides the excess sort because excess is unknown there', () => {
  assert.ok(!sortOptionsFor('coverage').some((o) => o.sort_by === 'inventory_gap'));
  assert.ok(sortOptionsFor('coverage').some((o) => o.value === 'activation_count:desc'));
  assert.deepEqual(sortOptionsFor('exceptions'), SORT_OPTIONS);
  assert.deepEqual(sortOptionsFor('within'), SORT_OPTIONS);
});

test('coverage columns omit purchase and excess measures', () => {
  assert.deepEqual(columnsFor('coverage').map((c) => c.label), ['Dealer / product', 'Activations', 'Comparison', 'Evidence']);
  for (const view of ['exceptions', 'within']) {
    assert.deepEqual(columnsFor(view).map((c) => c.label), ['Dealer / product', 'Recorded purchases', 'Activations', 'Excess units', 'Excess %', 'Comparison', 'Evidence']);
  }
  assert.ok(columnsFor('exceptions').filter((c) => c.numeric).every((c) => ['purchases', 'activations', 'excess', 'excess_pct'].includes(c.id)));
});
