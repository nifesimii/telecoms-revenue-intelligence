import { useEffect, useRef, useState } from 'react';
import { useQuery } from '@tanstack/react-query';
import { getSubscriptionDetail } from '../../api/client.js';
import { formatPeriod } from '../../lib/format.js';
import CommissionAssistant from './CommissionAssistant.jsx';
import SubscriptionDevices from './SubscriptionDevices.jsx';
import { SubscriptionFigures, SubscriptionProvenance } from './SubscriptionFigures.jsx';
import { REASON_LABELS } from './subscriptionPresentation.js';

export default function SubscriptionDetail({ account, period, onBack, prompt, onPromptConsumed }) {
  const headingRef = useRef(null);
  const [expanded, setExpanded] = useState(false);
  const [reason, setReason] = useState('all');
  const params = { mon_period: period };
  const query = useQuery({ queryKey: ['subscription-detail', account.dealer_id, params], queryFn: ({ signal }) => getSubscriptionDetail(account.dealer_id, params, signal) });
  const data = query.data;
  useEffect(() => { headingRef.current?.focus(); }, []);
  return <div className="space-y-5">
    <button className="overview-button" onClick={onBack}>← Back to subscription accounts</button>
    <header ref={headingRef} tabIndex={-1}>
      <p className="text-xs text-gray-500 uppercase font-semibold tracking-widest">Subscription account investigation</p>
      <h2 className="text-2xl font-semibold mt-1 break-words">{data?.account.dealer_name || account.dealer_name}</h2>
      <p className="text-sm text-gray-600 mt-2">Account {account.dealer_id} · {formatPeriod(period)} · {data ? data.account.account_profile_class || 'Class not recorded' : 'Class unavailable'}</p>
    </header>
    {query.isPending && <div role="status" className="overview-surface p-6 animate-pulse">Loading subscription account figures…</div>}
    {query.isError && <div role="alert" className="overview-notice">{query.error?.response?.status === 404 ? 'No subscription records for this account and reporting month. This is not a zero balance.' : 'Subscription account evidence unavailable. No balance can be established.'} <button className="underline" onClick={() => query.refetch()}>Retry account evidence</button></div>}
    {data && !query.isError && <>
      <SubscriptionProvenance data={data} />
      <SubscriptionFigures figures={data.account} available={data.commission_available} />
      {data.commission_available ? <section className="overview-surface p-5" aria-label="Subscription device evidence">
        <h3 className="font-semibold">Eligibility and supporting devices</h3>
        <p className="text-sm text-gray-600 mt-2">{data.account.device_count} devices attributed to this original selling dealer. Select a result to inspect its supplied evidence.</p>
        <div className="flex flex-wrap gap-2 mt-4">{Object.entries(data.account.reason_counts).map(([key, count]) => <button key={key} className="overview-button" onClick={() => { setReason(key); setExpanded(true); }}>{REASON_LABELS[key] || key}: {count}</button>)}</div>
        <button className="overview-button mt-4" aria-expanded={expanded} aria-controls="subscription-device-evidence" onClick={() => { setReason('all'); setExpanded(!expanded); }}>{expanded ? 'Hide device evidence' : 'Expand device evidence'}</button>
        <p className="text-xs text-gray-600 mt-3">No paid subscription this month is separate from churn. Churn needs sufficient history and never determines an exclusion.</p>
      </section> : <p className="overview-notice">Device commission and subscription settlement evidence are unavailable in this source. Revenue alone does not establish commission payable.</p>}
      {expanded && data.commission_available && <div id="subscription-device-evidence"><SubscriptionDevices dealerId={account.dealer_id} period={period} reason={reason} onReasonChange={setReason} /></div>}
      <CommissionAssistant key={`${period}:${account.dealer_id}:${data.synthetic}`} subscription={data} account={data.account} period={period} stream="orsc" prompt={prompt} onPromptConsumed={onPromptConsumed} />
    </>}
  </div>;
}
