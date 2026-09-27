import { useEffect, useRef, useState } from 'react';
import { useQuery } from '@tanstack/react-query';
import { getCommissionDetail } from '../../api/client.js';
import { formatNGN, formatPeriod } from '../../lib/format.js';
import { MoneyChange } from './CommissionSummary.jsx';
import CommissionAssistant from './CommissionAssistant.jsx';
import ZeroCommissionEvidence from './ZeroCommissionEvidence.jsx';

export default function CommissionDetail({ account, period, comparison, stream, onBack, onNavigate }) {
  const headingRef = useRef(null);
  const [showRecords, setShowRecords] = useState(false);
  const [prompt, setPrompt] = useState('');
  const params = { mon_period: period, prior_period: comparison || undefined, stream };
  const query = useQuery({ queryKey: ['commission-detail', account.dealer_id, params],
    queryFn: ({ signal }) => getCommissionDetail(account.dealer_id, params, signal) });
  const data = query.data;
  const currentAccount = data?.account;
  const orsc = stream === 'orsc';
  useEffect(() => { headingRef.current?.focus(); }, []);
  return <div className="space-y-5">
    <button className="overview-button" onClick={onBack}>← Back to accounts</button>
    <header ref={headingRef} tabIndex={-1} className="outline-none">
      <p className="text-xs font-semibold uppercase tracking-widest text-gray-500">Account investigation</p>
      <h2 className="mt-1 text-2xl font-semibold break-words">{currentAccount?.dealer_name || account.dealer_name}</h2>
      <p className="text-sm text-gray-600 mt-2">Account {account.dealer_id} · {currentAccount ? currentAccount.account_profile_class || 'Class not recorded' : 'Class unavailable'} · {formatPeriod(period)}</p>
    </header>
    <div className="grid grid-cols-1 xl:grid-cols-3 gap-6 items-start">
      <div className="xl:col-span-2 min-w-0 space-y-5">
        {query.isPending && <div role="status" className="overview-surface h-48 animate-pulse bg-gray-100 p-5">Loading recorded figures…</div>}
        {query.isError && <div className="overview-notice text-red-800" role="alert">Account figures unavailable. This is not a zero balance. <button className="underline" onClick={() => query.refetch()}>Retry</button></div>}
        {data && <>
          <section className="overview-surface p-5 sm:p-6" aria-label="Account figures">
            <h3 className="text-sm text-gray-600">{orsc ? 'Recorded subscription revenue' : 'Recorded activation commission'}</h3>
            <p className="overview-headline mt-2 font-semibold tabular-nums">{formatNGN(data.account.amount_ngn)}</p>
            <dl className="grid sm:grid-cols-3 gap-4 mt-5 text-sm">
              <div><dt className="text-gray-500">{orsc ? 'Device records' : 'Activation records'}</dt><dd className="font-semibold mt-1">{data.account.record_count.toLocaleString()}</dd></div>
              <div><dt className="text-gray-500">{orsc ? 'Zero-amount records' : 'Zero-commission records'}</dt><dd className="font-semibold mt-1">{data.account.zero_count.toLocaleString()}</dd></div>
              <div><dt className="text-gray-500">Change {comparison ? `vs ${formatPeriod(comparison)}` : ''}</dt><dd className="font-semibold mt-1"><MoneyChange value={data.account.delta_ngn} /></dd></div>
            </dl>
            {comparison && data.account.prior_amount_ngn == null && <p className="text-sm text-gray-600 mt-4">No account record in {formatPeriod(comparison)}. A percentage change cannot be established.</p>}
            <p className="mt-5 text-xs text-gray-500">{data.source} · Retrieved {new Date(data.generated_at).toLocaleString()}. {orsc ? 'Subscription revenue is not commission payable.' : 'Recorded commission is not a dealer-submitted expectation or confirmed settlement.'}</p>
          </section>
          {!orsc && <section className="overview-surface overflow-hidden" aria-label="Denomination breakdown">
            <div className="p-5"><h3 className="font-semibold">Commission by denomination</h3><p className="mt-2 text-sm text-gray-600">The components of the recorded figure. Differences describe change, not its cause.</p></div>
            <div className="overflow-x-auto" tabIndex={0} role="region" aria-label="Scrollable denomination comparison"><table className="commission-table w-full text-sm text-left">
              <thead><tr><th>Denomination</th><th className="text-right">{formatPeriod(period)}</th><th className="text-right">{comparison ? formatPeriod(comparison) : 'Prior period'}</th><th className="text-right">Change</th></tr></thead>
              <tbody>{data.denominations.map((r) => <tr key={r.denomination}><td>{r.denomination}</td><td className="text-right whitespace-nowrap tabular-nums">{formatNGN(r.amount_ngn)}</td><td className="text-right whitespace-nowrap tabular-nums">{r.prior_amount_ngn == null ? '—' : formatNGN(r.prior_amount_ngn)}</td><td className="text-right"><MoneyChange value={r.delta_ngn} /></td></tr>)}</tbody>
            </table></div>
            {!data.denominations.length && <p className="p-5 text-sm text-gray-500">No denomination breakdown recorded.</p>}
            <div className="p-5 flex flex-wrap gap-3 border-t border-gray-200"><button className="overview-button" onClick={() => setPrompt(comparison ? 'Explain the change by denomination between the selected periods. Distinguish observed changes from verified causes.' : 'Explain this account’s recorded commission by denomination.')}>Explain {comparison ? 'change' : 'breakdown'} →</button>
              <button className="overview-button" aria-expanded={showRecords} onClick={() => setShowRecords(!showRecords)}>{showRecords ? 'Hide' : 'Inspect'} zero-commission records</button></div>
          </section>}
          {orsc && <div className="overview-notice text-gray-600">This view reports recorded subscription amounts and zero-amount counts. The current source does not establish a subscription commission payable figure.</div>}
          {showRecords && !orsc && <ZeroCommissionEvidence dealerId={account.dealer_id} period={period} onNavigate={onNavigate} />}
        </>}
      </div>
      <CommissionAssistant key={`${account.dealer_id}:${period}:${comparison}:${stream}`} account={currentAccount || account} period={period} comparison={comparison} stream={stream} prompt={prompt} onPromptConsumed={() => setPrompt('')} />
    </div>
  </div>;
}
