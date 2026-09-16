import { formatNGN, formatPeriod } from '../../lib/format.js';

export function MoneyChange({ value }) {
  if (value == null) return <span className="text-gray-500">—</span>;
  return <span className="tabular-nums whitespace-nowrap">{value > 0 ? '+' : ''}{formatNGN(value)}</span>;
}

export default function CommissionSummary({ data, onFilter }) {
  const s = data.summary;
  const orsc = data.stream === 'orsc';
  return <section className="overview-surface overflow-hidden" aria-label="Full-period summary">
    <div className="grid lg:grid-cols-2">
      <div className="p-5 sm:p-6 bg-yellow-50 border-b lg:border-b-0 lg:border-r border-gray-200">
        <h2 className="text-sm text-gray-700">{orsc ? 'Recorded subscription revenue' : 'Recorded activation commission'}</h2>
        <p className="overview-headline font-semibold tracking-tight mt-2 tabular-nums">{s.account_count ? formatNGN(s.amount_ngn) : 'No source records'}</p>
        <p className="mt-3 text-sm text-gray-600">Across {s.account_count.toLocaleString()} dealer accounts · {s.record_count.toLocaleString()} {orsc ? 'device records' : 'activation records'}</p>
        <p className="mt-2 text-xs text-gray-600">{orsc ? 'Subscription revenue is not commission payable.' : 'Existing calculated commission, not a recalculation or settlement balance.'}</p>
      </div>
      <div className="p-5 sm:p-6 grid sm:grid-cols-2 gap-5">
        <div><h3 className="text-sm text-gray-600">{orsc ? 'Zero-amount records' : 'Zero-commission records'}</h3>
          <p className="text-2xl font-semibold mt-2 tabular-nums">{s.zero_count.toLocaleString()}</p>
          <button className="mt-2 text-sm underline underline-offset-4" onClick={() => onFilter('with_zero')}>Across {s.accounts_with_zero.toLocaleString()} accounts →</button>
        </div>
        <div><h3 className="text-sm text-gray-600">Accounts with entirely zero {orsc ? 'revenue' : 'commission'}</h3>
          <p className="text-2xl font-semibold mt-2 tabular-nums">{s.all_zero_accounts.toLocaleString()}</p>
          <button className="mt-2 text-sm underline underline-offset-4" onClick={() => onFilter('all_zero')}>Review accounts →</button>
        </div>
        <p className="sm:col-span-2 text-xs text-gray-600">Zero amounts are a starting point for investigation, not proof of an error or money owed.</p>
      </div>
    </div>
    <div className="border-t border-gray-200 px-5 py-4 flex flex-wrap items-center gap-x-6 gap-y-2 text-sm">
      {data.prior_period ? <>
        <span className="text-gray-600">vs {formatPeriod(data.prior_period)}</span>
        <span className="font-semibold"><MoneyChange value={s.delta_ngn} /></span>
        <span className="text-gray-600">{s.prior_account_count ? `Prior total ${formatNGN(s.prior_amount_ngn)}` : 'No source records in the comparison period'}</span>
        <span className="text-xs text-gray-500">Full-period totals include changes in the account population.</span>
      </> : <span className="text-gray-500">No comparison selected. Choose an available earlier period to compare.</span>}
    </div>
  </section>;
}
