// One partner's fictional commission statement for one month, read from the server.
// Finance sees it with explanation links; a partner sees the same statement without.

import useQuery from '../../hooks/useWorkspaceQuery.js';
import { getCommissionDetail, getDealerStatement, getHealth } from '../../api/client.js';
import { formatCount, formatDate, formatMinorNGN, formatPeriod } from '../../lib/format.js';
import { partnerLabel } from './salesDisplay.js';
import { DetailHeader, Disclaimer } from './SalesParts.jsx';
import { ReadState, displayAmount, useBoundedPage } from './SalesReads.jsx';
import { STREAMS, closingGaps, reconcilesWithRecorded, sortedActivity, summarizeStatement } from './commissionAccount.js';
import { statementQuery } from './useSalesQueries.js';

const displayStreamAmount = ({ status, minor }) => (status === 'not_recorded' ? 'No source records' : displayAmount(minor));
const STREAM_LABEL = Object.fromEntries(STREAMS);
const entryLabel = (item) => (item.amount_minor === 0 ? `Recorded zero ${item.kind}` : item.kind === 'earning' ? 'Earning' : 'Settlement');

function ClosingNote({ summary }) {
  const gaps = closingGaps(summary);
  if (gaps.length) return <p className="sales-note mt-3.5">Closing outstanding is unavailable because {gaps.join(' and ')} {gaps.length === 1 && gaps[0] === 'the opening balance' ? 'lacks' : 'lack'} evidence. The amounts shown are not a partial balance.</p>;
  return <p className="sales-note mt-3.5">Closing outstanding is opening outstanding plus period earnings less period settlements.</p>;
}

function StreamTable({ summary }) {
  return <table className="sales-table">
    <caption className="sr-only">Commission by stream</caption>
    <thead><tr><th scope="col">Stream</th><th scope="col" className="sales-num hidden sm:table-cell">Earnings</th><th scope="col" className="sales-num hidden sm:table-cell">Settlements</th></tr></thead>
    <tbody>{STREAMS.map(([stream, label]) => {
      const { earning, settlement } = summary.streams[stream];
      return <tr key={stream}>
        <th scope="row"><span className="block font-semibold">{label}</span>
          <span className="block sm:hidden mt-1">Earnings <span className="whitespace-nowrap">{displayStreamAmount(earning)}</span></span>
          <span className="block sm:hidden mt-1">Settlements <span className="whitespace-nowrap">{displayStreamAmount(settlement)}</span></span></th>
        <td className="sales-num hidden sm:table-cell">{displayStreamAmount(earning)}</td>
        <td className="sales-num hidden sm:table-cell">{displayStreamAmount(settlement)}</td>
      </tr>;
    })}</tbody>
    <tfoot><tr><th scope="row"><span className="block">Total</span>
      <span className="block sm:hidden mt-1">Earnings <span className="whitespace-nowrap">{displayAmount(summary.earningsMinor)}</span></span>
      <span className="block sm:hidden mt-1">Settlements <span className="whitespace-nowrap">{displayAmount(summary.settlementsMinor)}</span></span></th>
      <td className="sales-num hidden sm:table-cell">{displayAmount(summary.earningsMinor)}</td>
      <td className="sales-num hidden sm:table-cell">{displayAmount(summary.settlementsMinor)}</td></tr></tfoot>
  </table>;
}

function Activity({ statement, summary, partner, period, headingId }) {
  const activity = sortedActivity(statement);
  const statedTotal = (minor) => (minor === null ? 'unavailable' : formatMinorNGN(minor));
  const { visible, controls } = useBoundedPage(activity, `${partner.code}|${period}`, headingId);
  const entries = `${formatCount(activity.length)} ${activity.length === 1 ? 'entry' : 'entries'}`;
  return <section className="overview-surface" aria-labelledby={headingId}>
    <div className="sales-sec"><h3 id={headingId} tabIndex={-1} className="sales-h">Dated activity</h3>
      {activity.length > 0 && <span className="sales-muted">{entries}</span>}</div>
    {activity.length ? <>
      <p className="sales-body sales-note !pb-3">All {entries} across every page: earnings {statedTotal(summary.earningsMinor)}, settlements {statedTotal(summary.settlementsMinor)}.</p>
      <table className="sales-table">
        <caption className="sr-only">Dated commission activity for {partnerLabel(partner)}, {formatPeriod(period)}</caption>
        <thead><tr><th scope="col">Date</th><th scope="col" className="hidden md:table-cell">Reference</th><th scope="col" className="hidden md:table-cell">Stream</th><th scope="col" className="hidden md:table-cell">Entry</th><th scope="col" className="sales-num hidden md:table-cell">Amount</th></tr></thead>
        <tbody>{visible.map((item) => <tr key={item.reference}>
          <th scope="row"><span className="block whitespace-nowrap">{formatDate(item.date)}</span>
            <span className="block md:hidden font-semibold mt-1">{item.reference}</span>
            <span className="block md:hidden mt-1">{STREAM_LABEL[item.stream]} · {entryLabel(item)}</span>
            <span className="block md:hidden sales-strong mt-1 whitespace-nowrap">{formatMinorNGN(item.amount_minor)}</span></th>
          <td className="hidden md:table-cell sales-strong">{item.reference}</td>
          <td className="hidden md:table-cell">{STREAM_LABEL[item.stream]}</td>
          <td className="hidden md:table-cell">{entryLabel(item)}</td>
          <td className="sales-num hidden md:table-cell">{formatMinorNGN(item.amount_minor)}</td>
        </tr>)}</tbody>
      </table>
      {controls}
    </> : <p className="sales-body sales-muted">No dated activity in this fictional statement.</p>}
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
  const button = (id, label, view, context) => <button key={id} id={`sales-explain-${id}-${partner.code}`} type="button" className="overview-button" onClick={() => explain(`sales-explain-${id}-${partner.code}`, view, context)}>{label}</button>;
  return <section className="overview-surface sales-card-pad" aria-label="Existing explanations">
    <h3 className="sales-h">Existing explanations</h3>
    {!statement ? <p className="sales-muted mt-2">Unavailable: without a statement for {accountLabel} in {periodLabel}, there is nothing to reconcile.</p>
      : !linkable ? <p className="sales-muted mt-2">Unavailable: this fictional statement is not connected to a recorded statement, so no explanation stands behind it.</p>
      : failed.length ? <div role="alert" className="sales-alert mt-2">Unavailable: recorded evidence for {accountLabel}, {periodLabel} could not be checked.
        <div className="mt-2"><button type="button" className="overview-button" onClick={retry}>Retry evidence check</button></div></div>
      : pending ? <p role="status" className="sales-muted mt-2">Checking recorded evidence…</p>
      : !sampleMode ? <p className="sales-muted mt-2">Unavailable: the application is reading live data, and this fictional statement is never compared with or added to it.</p>
      : missing ? <p className="sales-muted mt-2">Unavailable: No recorded statement exists for {accountLabel} in {periodLabel}.</p>
      : !ready ? <p className="sales-muted mt-2">Unavailable: this fictional statement does not reconcile with recorded evidence for {accountLabel}, {periodLabel}.</p>
      : <>
        <p className="sales-muted mt-2">Period earnings and settlements match recorded evidence for {accountLabel}, {periodLabel}, stream by stream. Existing explanations show period-only totals, so they {summary.openingMinor === null ? 'carry no opening balance. The opening balance is unavailable here too' : `do not include the fictional opening carry-forward of ${formatMinorNGN(summary.openingMinor)}`}.</p>
        <div className="sales-actions mt-4">
          {button('activation', 'Explain activation commission', 'commission', { stream: 'activation' })}
          {statement.subscription_recorded && button('subscription', 'Explain subscription commission', 'commission', { stream: 'orsc' })}
          {button('settlement', 'Explain settlement', 'payment', { tab: 'all' })}
        </div>
      </>}
  </section>;
}

// The statement itself, the same for Finance and the partner, under the heading each
// supplies. A missing statement leaves every figure unavailable, never zero.
export function CommissionStatement({ statement, partner, period, heading }) {
  const periodLabel = formatPeriod(period);
  const summary = summarizeStatement(statement);
  return <>
    <div className="overview-surface">
      {heading}
      <div className="sales-body">
        <Disclaimer summary="Fictional statement, not recorded evidence or an amount owed">Its opening balance, dates, references and the way amounts divide into entries are demonstration values. Commission here is what MTN would owe the partner. Purchase obligations are a separate balance, and invoices and collections never change this account. Recharge-card commissions are excluded.</Disclaimer>
        {!statement && <p role="status" className="sales-muted mt-3.5">No fictional statement exists for {partnerLabel(partner)} in {periodLabel}. These amounts are unavailable, not zero.</p>}
        <dl className="sales-figures" aria-label="Statement reconciliation">
          <div><dt>Opening outstanding</dt><dd className="sales-figure">{displayAmount(summary.openingMinor)}</dd>
            {statement?.opening_reference && <dd className="sales-note !font-normal">Source reference {statement.opening_reference}</dd>}</div>
          <div><dt>Period earnings</dt><dd className="sales-figure">{displayAmount(summary.earningsMinor)}</dd></div>
          <div><dt>Period settlements</dt><dd className="sales-figure">{displayAmount(summary.settlementsMinor)}</dd></div>
          <div><dt>Closing outstanding</dt><dd className="sales-figure">{displayAmount(summary.closingMinor)}</dd></div>
        </dl>
        {statement && <ClosingNote summary={summary} />}
      </div>
      {statement && <>
        <StreamTable summary={summary} />
        <dl className="sales-figures sales-foot !mt-0">
          <div className="col-span-2"><dt>Period-only outstanding</dt><dd>{displayAmount(summary.periodOutstandingMinor)}</dd>
            <dd className="sales-note !font-normal">Period earnings less period settlements, before any opening balance.</dd></div>
          <div className="col-span-2"><dt>Subscription revenue</dt><dd>{statement.subscription_revenue_minor !== null ? formatMinorNGN(statement.subscription_revenue_minor) : statement.subscription_recorded ? 'Unavailable' : 'No source records'}</dd>
            <dd className="sales-note !font-normal">Revenue is not commission entitlement, and it is in no total on this statement.</dd></div>
        </dl>
      </>}
    </div>
    {statement && <Activity statement={statement} summary={summary} partner={partner} period={period} headingId={`sales-commission-activity-${partner.code}`} />}
  </>;
}

export default function CommissionAccount({ partner, period, headingId, backLabel, onBack, onExplain, onOpenObligations }) {
  const read = useQuery(statementQuery(partner.code, period));
  const statement = read.data?.statement ?? null;
  const obligationsOpener = `sales-commission-obligations-${partner.code}`;
  return <section className="flex flex-col gap-6" aria-labelledby={headingId}>
    <DetailHeader eyebrow="Fictional simulation" title={partner.name} headingId={headingId} headingLabel={`Partner Commission Account for ${partnerLabel(partner)}`} backLabel={backLabel} onBack={onBack} meta={`Commission account · Account ${partner.code}`} />
    <div className="sales-detail">
      <div className="sales-stack">
        {(!read.data || read.isError) && <div className="overview-surface sales-card-pad"><ReadState query={read} what="commission statement" /></div>}
        {read.data && <>
          <CommissionStatement statement={statement} partner={partner} period={period} heading={<div className="sales-sec"><div>
            <h2 className="sales-h">Commission statement</h2>
            <p className="sales-muted">Statement for {formatPeriod(period)}</p>
          </div></div>} />
          <ExplanationLinks statement={statement} summary={summarizeStatement(statement)} partner={partner} period={period} onExplain={onExplain} />
        </>}
      </div>
      <div className="overview-surface sales-rail">
        <h2 className="sales-h">{partner.name}</h2>
        <button id={obligationsOpener} type="button" className="overview-button sales-full" aria-label={`View purchase obligations for ${partnerLabel(partner)}`} onClick={() => onOpenObligations(partner.code, obligationsOpener)}>View all purchase obligations</button>
      </div>
    </div>
  </section>;
}
