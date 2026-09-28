import { useEffect, useRef, useState } from 'react';
import { useQuery } from '@tanstack/react-query';
import { getPaymentAccount, getDealerVerification, getAuditTrail } from '../../api/client.js';
import { formatPeriod } from '../../lib/format.js';
import { money, statusLabel, findingLabel } from './paymentPresentation.js';
import CommissionAssistant from '../commission/CommissionAssistant.jsx';
import DisputeDraftModal from './DisputeDraftModal.jsx';

export default function PaymentDetail({ dealerId, period, comparison, onBack, onNavigate }) {
  const heading = useRef(null);
  const disputeButton = useRef(null);
  const [showTrail, setShowTrail] = useState(false);
  const [composerRequest, setComposerRequest] = useState(null);
  const [dispute, setDispute] = useState(false);
  const query = useQuery({ queryKey: ['payment-account', period, dealerId], queryFn: ({ signal }) => getPaymentAccount(dealerId, period, signal) });
  const evidence = useQuery({ queryKey: ['dealer-verification', period, dealerId], queryFn: () => getDealerVerification(dealerId, period), retry: false });
  const account = query.data?.account;
  useEffect(() => { heading.current?.focus(); }, []);
  const navigate = (view) => onNavigate?.(view, { dealer_id: dealerId, search: dealerId, mon_period: period, prior_period: comparison });
  return <div className="space-y-5">
    <button className="overview-button" onClick={onBack}>← Back to accounts</button>
    <h2 ref={heading} tabIndex={-1} className="text-2xl font-semibold break-words">{account?.dealer_name || `Account ${dealerId}`}</h2>
    <p className="text-sm text-gray-600">Exact account {dealerId} · {formatPeriod(period)}{comparison && ` · Comparison ${formatPeriod(comparison)}`}</p>
    {query.isFetching && <p role="status">Loading payment position…</p>}
    {query.isError && <p role="alert" className="overview-notice">{query.error?.response?.status === 404 ? 'No payment account recorded for this period.' : 'Payment position unavailable.'} <button className="underline" onClick={() => query.refetch()}>Retry payment</button></p>}
    {account && !query.isError && <>
      <section className="overview-surface p-5 sm:p-6">
        <h3 className="text-sm text-gray-600">Outstanding</h3><p className="overview-headline mt-2 font-semibold">{money(account.amount_unpaid)}</p>
        <dl className="grid sm:grid-cols-3 gap-5 mt-5 text-sm">{[['Commission owed', money(account.commission_owed)], ['Amount settled', money(account.amount_paid)], ['Payment status', statusLabel(account.payment_status)]].map(([label, value]) => <div key={label}><dt className="text-gray-600">{label}</dt><dd className="font-semibold mt-2">{value}</dd></div>)}</dl>
        <p className="text-sm mt-5">{findingLabel(account.exception_flag)}. Source observation; review supporting evidence.</p>
        {account.reconciliation_status && <p className="text-sm mt-3">Source reconciliation status: {account.reconciliation_status.replaceAll('_', ' ').toLowerCase()} · Sales captured {money(account.total_sales_ngn)} · Settled minus owed {money(account.payment_variance_ngn)}</p>}
        <p className="text-xs text-gray-500 mt-4">{query.data.data_source} · Retrieved {new Date(query.data.generated_at).toLocaleString()}. Retrieval time does not establish source freshness.</p>
        <div className="flex flex-wrap gap-3 mt-5">
          <button className="overview-button" onClick={() => navigate('commission')}>View commission</button><button className="overview-button" onClick={() => navigate('activation')}>View activations</button>
          <button className="overview-button" aria-expanded={Boolean(composerRequest)} onClick={() => setComposerRequest({ prompt: 'Explain this account’s recorded commission, paid amount and outstanding balance. State what remains unverified.' })}>Ask about this payment</button>
          <button ref={disputeButton} className="overview-button overview-primary" onClick={() => setDispute(true)}>Prepare dispute response</button>
        </div>
      </section>
      <section className="overview-surface p-5 sm:p-6" aria-label="Recorded activation evidence" aria-busy={evidence.isFetching}>
        <div className="flex flex-wrap items-center justify-between gap-3"><h3 className="font-semibold">Recorded activation evidence</h3><button className="overview-button" disabled={evidence.isFetching} onClick={() => evidence.refetch()}>Refresh activation evidence</button></div>
        {evidence.isFetching && <p role="status" className="animate-pulse mt-4">Loading activation evidence…</p>}
        {evidence.isError && <p role={evidence.error?.response?.status === 404 ? 'status' : 'alert'} className="mt-4">{evidence.error?.response?.status === 404 ? 'No activation records found for this account and period. The payment position cannot be verified from these records.' : 'Activation evidence could not be loaded. No conclusion can be established.'} <button className="underline" onClick={() => evidence.refetch()}>Retry evidence</button></p>}
        {evidence.data && !evidence.isError && <ActivationEvidence record={evidence.data} account={account} />}
      </section>
      <section className="overview-surface p-5 sm:p-6"><h3 className="font-semibold">Saved payment reconciliation</h3>
        <p className="text-sm text-gray-600 mt-2">{showTrail ? 'Existing account-period assessment. Opening evidence does not run an audit.' : 'Not checked. Load a saved assessment to see whether reconciliation was previously run.'}</p>
        <button className="overview-button mt-4" aria-expanded={showTrail} onClick={() => setShowTrail(!showTrail)}>{showTrail ? 'Hide saved trail' : 'Load saved trail'}</button>
        {showTrail && <SavedTrail dealerId={dealerId} period={period} />}
      </section>
      {composerRequest && <CommissionAssistant account={account} period={period} comparison={comparison} stream="payment" composerRequest={composerRequest} />}
      <DisputeDraftModal open={dispute} row={account} period={period} onClose={() => { setDispute(false); disputeButton.current?.focus(); }} />
    </>}
  </div>;
}

function ActivationEvidence({ record, account }) {
  const earned = record.activation_commission_amount;
  return <>
    <dl className="grid sm:grid-cols-2 xl:grid-cols-4 gap-5 mt-5 text-sm">{[['Activation records', record.activation_count], ['Qualified records', record.qualified_activation_count], ['Zero-commission records', record.non_qualified_activation_count], ['Recorded commission', money(earned)]].map(([label, value]) => <div key={label}><dt className="text-gray-600">{label}</dt><dd className="font-semibold mt-2">{value ?? 'Unavailable'}</dd></div>)}</dl>
    <p className="mt-5 text-sm">Payment-source commission owed minus recorded activation commission: {earned == null ? 'Unavailable' : money(account.commission_owed - earned)}.</p>
    <p className="mt-3 text-sm">{earned == null ? 'Recorded activation commission unavailable.' : account.amount_paid > earned ? `Paid exceeds recorded activation commission by ${money(account.amount_paid - earned)}; investigate the difference.` : `Recorded activation commission minus paid: ${money(earned - account.amount_paid)}.`} Aggregate differences do not establish payment on zero-commission records or a cause.</p>
  </>;
}

function SavedTrail({ dealerId, period }) {
  const query = useQuery({ queryKey: ['payment-trail', period, dealerId], queryFn: ({ signal }) => getAuditTrail(dealerId, 'payment_reconciliation', period, signal), retry: false });
  const data = query.data;
  const matches = data?.partner_code === dealerId && data?.mon_period === period;
  return <div className="mt-4 text-sm space-y-4">
    {query.isFetching && <p role="status">Loading saved reconciliation…</p>}
    {query.isError && <p role={query.error?.response?.status === 404 ? 'status' : 'alert'}>{query.error?.response?.status === 404 ? 'No saved reconciliation found. A run for this account and period has not been established.' : 'Saved reconciliation retrieval failed.'} <button className="underline" onClick={() => query.refetch()}>Retry saved trail</button></p>}
    {data && !query.isError && !matches && <p role="alert">Saved evidence does not match this account and period.</p>}
    {matches && !query.isError && <>
      <p className="font-semibold">Saved conclusion: {data.conclusion?.replaceAll('_', ' ')} · Confidence {data.confidence || 'unavailable'}</p>
      <p>Source: {data.payment_source || 'unavailable'} · Recorded {data.generated_at ? new Date(data.generated_at).toLocaleString() : 'date unavailable'}</p>
      <p className="text-gray-600">This saved assessment may predate the current payment position. Confidence applies to the saved checks and their evidence; it does not establish current settlement or source completeness.</p>
      <ol className="space-y-4">{data.steps?.map((step) => <li key={step.step} className="border-l-2 pl-4"><h4 className="font-semibold">{step.step}. {step.name?.replaceAll('_', ' ')}</h4><p>{step.checked}</p><p className="mt-2">{step.result}</p>{step.caveat && <p className="mt-2 text-amber-900">Limitation: {step.caveat}</p>}</li>)}</ol>
    </>}
  </div>;
}
