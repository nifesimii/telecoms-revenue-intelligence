// One partner's fictional commission statement for the selected reporting month.

import useQuery from '../../hooks/useWorkspaceQuery.js';
import { getCommissionDetail, getDealerStatement, getHealth } from '../../api/client.js';
import { formatCount, formatDate, formatMinorNGN, formatPeriod } from '../../lib/format.js';
import { displayAmount, useBoundedPage } from './InvoiceViews.jsx';
import { partnerLabel } from './salesDisplay.js';
import { STREAMS, closingGaps, reconcilesWithRecorded, sortedActivity, statementFor, summarizeStatement } from './commissionAccount.js';

const displayStreamAmount = ({ status, minor }) => (status === 'not_recorded' ? 'No source records' : displayAmount(minor));
const STREAM_LABEL = Object.fromEntries(STREAMS);
const entryLabel = (item) => (item.amountMinor === 0 ? `Recorded zero ${item.kind}` : item.kind === 'earning' ? 'Earning' : 'Settlement');

function ClosingNote({ summary }) {
  const gaps = closingGaps(summary);
  if (gaps.length) return <p className="text-xs text-gray-600 mt-2">Closing outstanding is unavailable because {gaps.join(' and ')} {gaps.length === 1 && gaps[0] === 'the opening balance' ? 'lacks' : 'lack'} evidence. The amounts shown are not a partial balance.</p>;
  return <p className="text-xs text-gray-600 mt-2">Closing outstanding is opening outstanding plus period earnings less period settlements.</p>;
}

function StreamTable({ summary }) {
  return <table className="sales-table mt-5">
    <caption className="sr-only">Commission by stream</caption>
    <thead><tr><th scope="col">Stream</th><th scope="col" className="sales-amount hidden sm:table-cell">Earnings</th><th scope="col" className="sales-amount hidden sm:table-cell">Settlements</th></tr></thead>
    <tbody>{STREAMS.map(([stream, label]) => {
      const { earning, settlement } = summary.streams[stream];
      return <tr key={stream}>
        <th scope="row"><span className="block font-semibold">{label}</span>
          <span className="block sm:hidden mt-1">Earnings <span className="whitespace-nowrap">{displayStreamAmount(earning)}</span></span>
          <span className="block sm:hidden mt-1">Settlements <span className="whitespace-nowrap">{displayStreamAmount(settlement)}</span></span></th>
        <td className="sales-amount hidden sm:table-cell">{displayStreamAmount(earning)}</td>
        <td className="sales-amount hidden sm:table-cell">{displayStreamAmount(settlement)}</td>
      </tr>;
    })}</tbody>
    <tfoot><tr><th scope="row"><span className="block">Total</span>
      <span className="block sm:hidden mt-1">Earnings <span className="whitespace-nowrap">{displayAmount(summary.earningsMinor)}</span></span>
      <span className="block sm:hidden mt-1">Settlements <span className="whitespace-nowrap">{displayAmount(summary.settlementsMinor)}</span></span></th>
      <td className="sales-amount hidden sm:table-cell">{displayAmount(summary.earningsMinor)}</td>
      <td className="sales-amount hidden sm:table-cell">{displayAmount(summary.settlementsMinor)}</td></tr></tfoot>
  </table>;
}

function Activity({ statement, summary, partner, period, headingId }) {
  const activity = sortedActivity(statement);
  const statedTotal = (minor) => (minor === null ? 'unavailable' : formatMinorNGN(minor));
  const { visible, controls } = useBoundedPage(activity, `${partner.code}|${period}`, headingId);
  return <section className="mt-6" aria-labelledby={headingId}>
    <h3 id={headingId} tabIndex={-1} className="text-base font-semibold">Dated activity</h3>
    {activity.length ? <>
      <p className="text-xs text-gray-600 mt-1">All {formatCount(activity.length)} {activity.length === 1 ? 'entry' : 'entries'} across every page: earnings {statedTotal(summary.earningsMinor)}, settlements {statedTotal(summary.settlementsMinor)}.</p>
      <table className="sales-table mt-3">
        <caption className="sr-only">Dated commission activity for {partnerLabel(partner)}, {formatPeriod(period)}</caption>
        <thead><tr><th scope="col">Date</th><th scope="col" className="hidden md:table-cell">Reference</th><th scope="col" className="hidden md:table-cell">Stream</th><th scope="col" className="hidden md:table-cell">Entry</th><th scope="col" className="sales-amount hidden md:table-cell">Amount</th></tr></thead>
        <tbody>{visible.map((item) => <tr key={item.reference}>
          <th scope="row"><span className="block whitespace-nowrap">{formatDate(item.date)}</span>
            <span className="block md:hidden font-semibold mt-1">{item.reference}</span>
            <span className="block md:hidden mt-1">{STREAM_LABEL[item.stream]} · {entryLabel(item)}</span>
            <span className="block md:hidden font-semibold mt-1 whitespace-nowrap">{formatMinorNGN(item.amountMinor)}</span></th>
          <td className="hidden md:table-cell font-semibold">{item.reference}</td>
          <td className="hidden md:table-cell">{STREAM_LABEL[item.stream]}</td>
          <td className="hidden md:table-cell">{entryLabel(item)}</td>
          <td className="sales-amount hidden md:table-cell">{formatMinorNGN(item.amountMinor)}</td>
        </tr>)}</tbody>
      </table>
      {controls}
    </> : <p className="text-sm text-gray-600 mt-3">No dated activity in this fictional statement.</p>}
  </section>;
}

// Links appear only after the recorded statement for this exact account and month
// reconciles to the fixture. Anything else explains why there is no link, and no
// other account is ever offered. The request carries the account and month only.
function ExplanationLinks({ statement, summary, partner, period, onExplain }) {
  const periodLabel = formatPeriod(period);
  const accountLabel = `Account ${partner.code}`;
  const linkable = Boolean(statement?.linked);
  const health = useQuery({ queryKey: ['health'], queryFn: getHealth, enabled: linkable, retry: false });
  const sampleMode = health.data?.sample_data_mode === true;
  const recorded = useQuery({ queryKey: ['dealer-statement', period, partner.code], queryFn: () => getDealerStatement(partner.code, period), enabled: linkable && sampleMode, retry: false });
  const subscriptionParams = { mon_period: period, stream: 'orsc' };
  const subscription = useQuery({ queryKey: ['commission-detail', partner.code, subscriptionParams], queryFn: ({ signal }) => getCommissionDetail(partner.code, subscriptionParams, signal), enabled: linkable && sampleMode, retry: false });
  const missing = recorded.error?.response?.status === 404;
  // A 404 here is the source saying this account has no subscription records.
  const noSubscription = subscription.error?.response?.status === 404;
  const failed = [health, recorded, subscription].filter((query) => query.isError && query.error?.response?.status !== 404);
  const pending = health.isPending || (sampleMode && (recorded.isPending || subscription.isPending));
  const ready = sampleMode && !pending && !failed.length && !missing && reconcilesWithRecorded(statement, recorded.data, noSubscription ? null : subscription.data.account);
  const retry = () => failed.forEach((query) => query.refetch());
  const explain = (id, view, context) => onExplain(view, { ...context, dealer_id: partner.code, search: partner.code, mon_period: period }, id);
  const button = (id, label, view, context) => <button key={id} id={`sales-explain-${id}-${partner.code}`} type="button" className="sales-button" onClick={() => explain(`sales-explain-${id}-${partner.code}`, view, context)}>{label}</button>;
  return <section className="mt-6" aria-label="Existing explanations">
    <h3 className="text-base font-semibold">Existing explanations</h3>
    {!statement ? <p className="text-sm text-gray-600 mt-2">Unavailable: without a statement for {accountLabel} in {periodLabel}, there is nothing to reconcile.</p>
      : !linkable ? <p className="text-sm text-gray-600 mt-2">Unavailable: this fictional statement is not connected to a recorded statement, so no explanation stands behind it.</p>
      : failed.length ? <div role="alert" className="sales-alert">Unavailable: recorded evidence for {accountLabel}, {periodLabel} could not be checked.
        <div className="mt-2"><button type="button" className="sales-button" onClick={retry}>Retry evidence check</button></div></div>
      : pending ? <p role="status" className="text-sm text-gray-600 mt-2">Checking recorded evidence…</p>
      : !sampleMode ? <p className="text-sm text-gray-600 mt-2">Unavailable: the application is reading live data, and this fictional statement is never compared with or added to it.</p>
      : missing ? <p className="text-sm text-gray-600 mt-2">Unavailable: No recorded statement exists for {accountLabel} in {periodLabel}.</p>
      : !ready ? <p className="text-sm text-gray-600 mt-2">Unavailable: this fictional statement does not reconcile with recorded evidence for {accountLabel}, {periodLabel}.</p>
      : <>
        <p className="text-sm text-gray-600 mt-2">Period earnings and settlements match recorded evidence for {accountLabel}, {periodLabel}, stream by stream. Existing explanations show period-only totals, so they {summary.openingMinor === null ? 'carry no opening balance. The opening balance is unavailable here too' : `do not include the fictional opening carry-forward of ${formatMinorNGN(summary.openingMinor)}`}.</p>
        <div className="sales-actions">
          {button('activation', 'Explain activation commission', 'commission', { stream: 'activation' })}
          {statement.subscriptionRecorded && button('subscription', 'Explain subscription commission', 'commission', { stream: 'orsc' })}
          {button('settlement', 'Explain settlement', 'payment', { tab: 'all' })}
        </div>
      </>}
  </section>;
}

export default function CommissionAccount({ partner, period, headingId, backLabel, onBack, onExplain, onOpenObligations }) {
  const statement = statementFor(partner.code, period);
  const periodLabel = formatPeriod(period);
  const summary = summarizeStatement(statement);
  return <section className="sales-paper" aria-labelledby={headingId}>
    <p className="text-xs font-semibold tracking-widest uppercase text-amber-800">Fictional simulation</p>
    <h2 id={headingId} tabIndex={-1} className="text-lg font-semibold mt-1">Partner Commission Account for {partnerLabel(partner)}</h2>
    <p className="text-xs text-gray-600 mt-1">Statement for {periodLabel}</p>
    <p className="sales-notice mt-3">Fictional statement: its opening balance, dates, references and the way amounts divide into entries are demonstration values, not recorded evidence or amounts owed. Commission here is what MTN would owe the partner. Purchase obligations are a separate balance, and invoices and collections never change this account. Recharge-card commissions are excluded.</p>
    {!statement && <p role="status" className="text-sm text-gray-600 mt-4">No fictional statement exists for {partnerLabel(partner)} in {periodLabel}. These amounts are unavailable, not zero.</p>}
    <dl className="sales-facts" aria-label="Statement reconciliation">
      <div><dt>Opening outstanding</dt><dd>{displayAmount(summary.openingMinor)}</dd>
        {statement?.openingReference && <dd className="text-xs !font-normal text-gray-600">Source reference {statement.openingReference}</dd>}</div>
      <div><dt>Period earnings</dt><dd>{displayAmount(summary.earningsMinor)}</dd></div>
      <div><dt>Period settlements</dt><dd>{displayAmount(summary.settlementsMinor)}</dd></div>
      <div><dt>Closing outstanding</dt><dd>{displayAmount(summary.closingMinor)}</dd></div>
    </dl>
    {statement && <>
      <ClosingNote summary={summary} />
      <StreamTable summary={summary} />
      <dl className="sales-facts">
        <div><dt>Period-only outstanding</dt><dd>{displayAmount(summary.periodOutstandingMinor)}</dd>
          <dd className="text-xs !font-normal text-gray-600">Period earnings less period settlements, before any opening balance.</dd></div>
        <div><dt>Subscription revenue</dt><dd>{statement.subscriptionRevenueMinor !== null ? formatMinorNGN(statement.subscriptionRevenueMinor) : statement.subscriptionRecorded ? 'Unavailable' : 'No source records'}</dd>
          <dd className="text-xs !font-normal text-gray-600">Revenue is not commission entitlement, and it is in no total on this statement.</dd></div>
      </dl>
      <Activity statement={statement} summary={summary} partner={partner} period={period} headingId={`sales-commission-activity-${partner.code}`} />
    </>}
    <ExplanationLinks statement={statement} summary={summary} partner={partner} period={period} onExplain={onExplain} />
    <div className="sales-actions"><button type="button" className="sales-button" onClick={onBack}>{backLabel}</button>
      <button id={`sales-commission-obligations-${partner.code}`} type="button" className="sales-button" onClick={() => onOpenObligations(partner.code, `sales-commission-obligations-${partner.code}`)}>View purchase obligations for {partnerLabel(partner)}</button></div>
  </section>;
}
