// The rules for reading a fictional Partner Commission Account statement, which the
// server supplies one account and month at a time. Opening balances, dates and
// references are authored fixture values, never derived from monthly totals.
// Invoices and collections never reach this module, so they cannot change it.

export const STREAMS = [['activation', 'Activation commission'], ['subscription', 'Subscription commission']];

// Absence of an entry is missing evidence. Only a recorded zero entry is a zero.
function streamAmount(statement, stream, kind) {
  if (stream === 'subscription' && !statement.subscription_recorded) return { status: 'not_recorded', minor: null };
  const entries = statement.activity.filter((item) => item.stream === stream && item.kind === kind);
  if (!entries.length) return { status: 'unavailable', minor: null };
  return { status: 'recorded', minor: entries.reduce((sum, item) => sum + item.amount_minor, 0) };
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
  const closingMinor = statement.opening_minor === null || periodOutstandingMinor === null ? null : statement.opening_minor + periodOutstandingMinor;
  return { streams, openingMinor: statement.opening_minor, earningsMinor, settlementsMinor, periodOutstandingMinor, closingMinor };
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
  if (recorded.dealer_id !== statement.account_code || recorded.mon_period !== statement.period) return false;
  if (payment.data_source !== 'simulated' || !payment.payment_found) return false;
  if (toMinor(commission.expected_ngn) !== streams.activation.earning.minor || toMinor(payment.amount_paid_ngn) !== streams.activation.settlement.minor) return false;
  if ((orsc ? toMinor(orsc.total_subscription_amount_ngn) : null) !== statement.subscription_revenue_minor) return false;
  if (!statement.subscription_recorded) return subscriptionAccount === null;
  return Boolean(subscriptionAccount?.subscription_commission_complete) && subscriptionAccount.dealer_id === statement.account_code
    && toMinor(subscriptionAccount.subscription_commission_ngn) === streams.subscription.earning.minor && toMinor(subscriptionAccount.subscription_settled_ngn) === streams.subscription.settlement.minor;
}
