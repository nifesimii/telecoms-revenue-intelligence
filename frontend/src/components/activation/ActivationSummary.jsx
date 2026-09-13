import { formatNGN } from '../../lib/format.js';

export const count = (value) => value == null ? '—' : value.toLocaleString();
export const rate = (value) => value == null ? '—' : `${value.toFixed(2)}%`;
export const change = (value, suffix = '') => value == null ? '—' : `${value > 0 ? '+' : ''}${count(value)}${suffix}`;

export default function ActivationSummary({ summary: s, onFilter }) {
  return <section className="overview-surface overflow-hidden" aria-label="Full-period activation summary">
    <div className="grid lg:grid-cols-2">
      <div className="p-5 sm:p-6 bg-yellow-50 border-b lg:border-b-0 lg:border-r border-gray-200">
        <h2 className="text-sm text-gray-700">Activation records this period</h2>
        <p className="overview-headline font-semibold tracking-tight mt-2 tabular-nums">{s.account_count ? count(s.activation_count) : 'No source records'}</p>
        <p className="mt-3 text-sm text-gray-600">Across {count(s.account_count)} dealer accounts · {count(s.qualified_activation_count)} qualified records</p>
        <p className="mt-2 text-xs text-gray-600">Full-period totals remain unchanged by list filters.</p>
      </div>
      <div className="p-5 sm:p-6 grid sm:grid-cols-2 gap-5">
        <div><h3 className="text-sm text-gray-600">Weighted qualification rate</h3><p className="text-2xl font-semibold mt-2 tabular-nums">{rate(s.qualification_rate_pct)}</p><p className="mt-2 text-xs text-gray-500">Qualified records / total records</p></div>
        <div><h3 className="text-sm text-gray-600">Zero-commission records</h3><p className="text-2xl font-semibold mt-2 tabular-nums">{count(s.non_qualified_activation_count)}</p><button className="mt-2 text-sm underline underline-offset-4" onClick={() => onFilter('with_zero')}>Across {count(s.accounts_with_zero)} accounts →</button></div>
        <div><h3 className="text-sm text-gray-600">Entirely zero accounts</h3><button className="mt-2 text-lg font-semibold underline underline-offset-4" onClick={() => onFilter('all_zero')}>{count(s.all_zero_accounts)} accounts →</button></div>
        <div><h3 className="text-sm text-gray-600">Recorded commission</h3><p className="mt-2 text-sm font-semibold tabular-nums break-words">{s.account_count ? formatNGN(s.activation_commission_amount) : '—'}</p></div>
      </div>
    </div>
    <p className="border-t border-gray-200 px-5 py-4 text-xs text-gray-600">Qualification follows the existing source calculation. Zero commission is a starting point for investigation; it does not establish an error or an amount owed.</p>
  </section>;
}
