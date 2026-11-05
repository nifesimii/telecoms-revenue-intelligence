// Fictional Partner Commission Account statements and their rules. Opening balances,
// dates and references are authored fixture values, never derived from monthly
// totals. Invoices and collections never reach this module, so they cannot change it.

import linkedStatements from './linkedCommissionStatements.json';

const entry = (date, reference, stream, kind, amountMinor) => ({ date, reference, stream, kind, amountMinor });

// 110 earnings of NGN 1,000.00 and 10 settlements of NGN 500.00, so paging has to
// span more than the largest page of 100 rows.
const longActivity = Array.from({ length: 120 }, (_, index) => {
  const sequence = String(index + 1).padStart(4, '0');
  const date = `2026-05-${String((index % 31) + 1).padStart(2, '0')}`;
  return index % 12 === 11 ? entry(date, `SIM-SET-295083-${sequence}`, 'activation', 'settlement', 50000) : entry(date, `SIM-COM-295083-${sequence}`, 'activation', 'earning', 100000);
});

// Statements in the JSON file reconcile to the same account's recorded sample
// statement (backend/tests/test_partner_commission_fixtures.py). These do not, so
// they offer no explanation links.
const standaloneStatements = [
  { accountCode: '74050', period: '202605', openingMinor: 2000000, openingReference: 'SIM-OPEN-74050-202605', subscriptionRecorded: true, subscriptionRevenueMinor: 24000000, activity: [
    entry('2026-05-12', 'SIM-COM-74050-0501', 'activation', 'earning', 900000),
    entry('2026-05-18', 'SIM-SET-74050-0501', 'activation', 'settlement', 750000),
    entry('2026-05-25', 'SIM-COM-74050-0502', 'subscription', 'earning', 600000),
    entry('2026-05-28', 'SIM-SET-74050-0502', 'subscription', 'settlement', 250000),
  ] },
  // A recorded zero settlement: evidence of nothing paid, unlike a missing settlement.
  { accountCode: '98052', period: '202605', openingMinor: 500000, openingReference: 'SIM-OPEN-98052-202605', subscriptionRecorded: false, subscriptionRevenueMinor: null, activity: [
    entry('2026-05-14', 'SIM-COM-98052-0501', 'activation', 'earning', 1200000),
    entry('2026-05-30', 'SIM-SET-98052-0501', 'activation', 'settlement', 0),
  ] },
  // No subscription entries: activation alone would be a misleading partial total.
  { accountCode: '98052', period: '202606', openingMinor: 1700000, openingReference: 'SIM-OPEN-98052-202606', subscriptionRecorded: true, subscriptionRevenueMinor: null, activity: [
    entry('2026-06-10', 'SIM-COM-98052-0601', 'activation', 'earning', 800000),
    entry('2026-06-20', 'SIM-SET-98052-0601', 'activation', 'settlement', 300000),
  ] },
  { accountCode: '205044', period: '202605', openingMinor: 1000000, openingReference: 'SIM-OPEN-205044-202605', subscriptionRecorded: false, subscriptionRevenueMinor: null, activity: [
    entry('2026-05-16', 'SIM-COM-205044-0501', 'activation', 'earning', 3000000),
  ] },
  { accountCode: '295083', period: '202605', openingMinor: 100000, openingReference: 'SIM-OPEN-295083-202605', subscriptionRecorded: false, subscriptionRevenueMinor: null, activity: longActivity },
];

const linked = linkedStatements.map((statement) => ({ ...statement, linked: true }));
const STATEMENTS = [...linked, ...standaloneStatements.map((statement) => ({ ...statement, linked: false }))];

export const statementFor = (accountCode, period) => STATEMENTS.find((statement) => statement.accountCode === accountCode && statement.period === period) ?? null;

export const STREAMS = [['activation', 'Activation commission'], ['subscription', 'Subscription commission']];

// Absence of an entry is missing evidence. Only a recorded zero entry is a zero.
function streamAmount(statement, stream, kind) {
  if (stream === 'subscription' && !statement.subscriptionRecorded) return { status: 'not_recorded', minor: null };
  const entries = statement.activity.filter((item) => item.stream === stream && item.kind === kind);
  if (!entries.length) return { status: 'unavailable', minor: null };
  return { status: 'recorded', minor: entries.reduce((sum, item) => sum + item.amountMinor, 0) };
}

// A stream with no source records stays out of the total, as in the existing
// statement. A stream with missing evidence leaves the whole total unknown.
function totalOf(amounts) {
  if (amounts.some((amount) => amount.status === 'unavailable')) return null;
  return amounts.reduce((sum, amount) => sum + (amount.minor ?? 0), 0);
}

// Every figure is null when its evidence is missing, never zero.
export function summarizeStatement(statement) {
  if (!statement) return { openingMinor: null, earningsMinor: null, settlementsMinor: null, periodOutstandingMinor: null, closingMinor: null };
  const streams = Object.fromEntries(STREAMS.map(([stream]) => [stream, { earning: streamAmount(statement, stream, 'earning'), settlement: streamAmount(statement, stream, 'settlement') }]));
  const earningsMinor = totalOf(STREAMS.map(([stream]) => streams[stream].earning));
  const settlementsMinor = totalOf(STREAMS.map(([stream]) => streams[stream].settlement));
  const periodOutstandingMinor = earningsMinor === null || settlementsMinor === null ? null : earningsMinor - settlementsMinor;
  const closingMinor = statement.openingMinor === null || periodOutstandingMinor === null ? null : statement.openingMinor + periodOutstandingMinor;
  return { streams, openingMinor: statement.openingMinor, earningsMinor, settlementsMinor, periodOutstandingMinor, closingMinor };
}

export function closingGaps({ openingMinor, earningsMinor, settlementsMinor }) {
  return [[openingMinor, 'the opening balance'], [earningsMinor, 'earnings'], [settlementsMinor, 'settlements']].filter(([minor]) => minor === null).map(([, label]) => label);
}

// References are unique within a statement, so this is a total order.
export const sortedActivity = (statement) => [...statement.activity].sort((a, b) => a.date.localeCompare(b.date) || a.reference.localeCompare(b.reference));

const toMinor = (ngn) => Math.round(ngn * 100);

// Whether recorded evidence is the same account, month and commission basis as this
// fixture, to the kobo. Only then can an existing explanation stand behind it. The
// statement carries activation and revenue; the subscription account, null when it
// has no records, is the account the subscription explanation itself shows.
export function reconcilesWithRecorded(statement, recorded, subscriptionAccount) {
  const { streams } = summarizeStatement(statement);
  const { commission, payment, orsc } = recorded;
  if (recorded.dealer_id !== statement.accountCode || recorded.mon_period !== statement.period) return false;
  if (payment.data_source !== 'simulated' || !payment.payment_found) return false;
  if (toMinor(commission.expected_ngn) !== streams.activation.earning.minor || toMinor(payment.amount_paid_ngn) !== streams.activation.settlement.minor) return false;
  if ((orsc ? toMinor(orsc.total_subscription_amount_ngn) : null) !== statement.subscriptionRevenueMinor) return false;
  if (!statement.subscriptionRecorded) return subscriptionAccount === null;
  return Boolean(subscriptionAccount?.subscription_commission_complete) && subscriptionAccount.dealer_id === statement.accountCode
    && toMinor(subscriptionAccount.subscription_commission_ngn) === streams.subscription.earning.minor && toMinor(subscriptionAccount.subscription_settled_ngn) === streams.subscription.settlement.minor;
}
