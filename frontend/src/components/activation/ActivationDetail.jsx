import { useEffect, useRef, useState } from 'react';
import { useQuery } from '@tanstack/react-query';
import { getActivationDetail } from '../../api/client.js';
import { formatNGN, formatPeriod } from '../../lib/format.js';
import ZeroCommissionEvidence from '../commission/ZeroCommissionEvidence.jsx';
import { Findings } from './ActivationAccounts.jsx';
import { count, rate, change } from './ActivationSummary.jsx';

export default function ActivationDetail({ account, period, comparison, onBack, onNavigate }) {
  const heading = useRef(null);
  const [showEvidence, setShowEvidence] = useState(false);
  const params = { mon_period: period, prior_period: comparison || undefined };
  const query = useQuery({ queryKey: ['activation-detail', account.dealer_id, params], queryFn: ({ signal }) => getActivationDetail(account.dealer_id, params, signal) });
  const data = query.data;
  const r = data?.account;
  useEffect(() => { heading.current?.focus(); }, []);
  return <div className="space-y-5">
    <button className="overview-button" onClick={onBack}>← Back to accounts</button>
    <header ref={heading} tabIndex={-1} className="outline-none"><p className="text-xs font-semibold uppercase tracking-widest text-gray-500">Activation investigation</p><h2 className="mt-1 text-2xl font-semibold break-words">{r?.dealer_name || account.dealer_name}</h2><p className="text-sm text-gray-600 mt-2">Account {account.dealer_id} · {r ? r.account_profile_class || 'Class not recorded' : 'Class unavailable'} · {formatPeriod(period)}</p></header>
    {query.isPending && <div className="h-48 overview-surface bg-gray-100 animate-pulse p-5" role="status">Loading activation account…</div>}
    {query.isError && <p role="alert" className="overview-notice text-red-800">Account figures unavailable. {data && 'Previously loaded figures are shown below.'} <button className="underline" onClick={() => query.refetch()}>Retry</button></p>}
    {r && <>
      <section className="overview-surface p-5 sm:p-6"><h3 className="text-sm text-gray-600">Activation records</h3><p className="overview-headline mt-2 font-semibold tabular-nums">{count(r.activation_count)}</p>
        <dl className="grid sm:grid-cols-2 lg:grid-cols-4 gap-5 mt-5 text-sm">{[['Qualified', count(r.qualified_activation_count)], ['Zero commission', count(r.non_qualified_activation_count)], ['Qualification rate', rate(r.qualification_rate_pct)], ['Recorded commission', formatNGN(r.activation_commission_amount)]].map(([label, value]) => <div key={label}><dt className="text-gray-500">{label}</dt><dd className="mt-1 font-semibold tabular-nums">{value}</dd></div>)}</dl>
      </section>
      <section className="overview-surface p-5"><h3 className="font-semibold">Period comparison</h3>{!comparison ? <p className="mt-3 text-sm text-gray-600">No comparison selected.</p> : r.prior_activation_count == null ? <p className="mt-3 text-sm text-gray-600">No account record in {formatPeriod(comparison)}. Missing prior data is not zero activity.</p> : <>
        <p className="mt-2 text-sm text-gray-600">{formatPeriod(period)} compared with {formatPeriod(comparison)}. This account is present in both periods.</p>
        <dl className="grid sm:grid-cols-2 lg:grid-cols-3 gap-5 mt-4 text-sm">{[[`${formatPeriod(comparison)} activations`, count(r.prior_activation_count)], ['Activation change', change(r.delta_activations)], ['Qualification change', change(r.delta_qualification_rate, ' pp')], [`${formatPeriod(comparison)} qualification`, rate(r.prior_qualification_rate_pct)], [`${formatPeriod(comparison)} commission`, formatNGN(r.prior_commission_amount)], ['Commission change', r.delta_commission_ngn == null ? '—' : `${r.delta_commission_ngn > 0 ? '+' : ''}${formatNGN(r.delta_commission_ngn)}`]].map(([label, value]) => <div key={label}><dt className="text-gray-500">{label}</dt><dd className="mt-1 font-semibold tabular-nums">{value}</dd></div>)}</dl>
      </>}</section>
      <section className="overview-surface p-5"><h3 className="font-semibold">Findings and next actions</h3><p className="mt-2 mb-4 text-sm text-gray-600">Findings describe observed patterns, not verified root causes.</p><Findings findings={r.findings} />
        <div className="mt-5 flex flex-wrap gap-3"><button className="overview-button" aria-expanded={showEvidence} onClick={() => setShowEvidence(!showEvidence)}>{showEvidence ? 'Hide' : 'Inspect'} zero-commission evidence</button>{onNavigate && <button className="overview-button" onClick={() => onNavigate('commission', { dealer_id: r.dealer_id, search: r.dealer_id, prior_period: comparison })}>Open account in Commission →</button>}</div>
      </section>
      {showEvidence && <ZeroCommissionEvidence dealerId={r.dealer_id} period={period} onNavigate={onNavigate} />}
      <p className="text-xs text-gray-500">{data.source} · Retrieved {new Date(data.generated_at).toLocaleString()}. Recorded figures follow existing source calculations.</p>
    </>}
  </div>;
}
