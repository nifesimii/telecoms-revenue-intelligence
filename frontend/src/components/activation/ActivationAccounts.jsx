import { formatNGN, formatPeriod } from '../../lib/format.js';
import PaginationControls from '../shared/PaginationControls.jsx';
import ActivationFilters, { VIEWS } from './ActivationFilters.jsx';
import { count, rate, change } from './ActivationSummary.jsx';

export function Findings({ findings }) {
  if (!findings.length) return <span className="text-gray-500">No findings</span>;
  return <ul className="space-y-3">{findings.map((f) => <li key={f.type}><p className="font-medium">{f.label} <span className="text-xs font-normal text-gray-600">· {f.severity}</span></p><p className="mt-1 text-xs text-gray-600">{f.recommended_action}</p></li>)}</ul>;
}

export default function ActivationAccounts({ data, busy, filters, onFilter, onPage, onSelect, rowRefs }) {
  const comparison = data.view === 'comparison';
  const exceptions = data.view === 'exceptions';
  const s = data.filtered_summary;
  let emptyTitle = 'No matching accounts';
  let emptyText = 'Try another name, account code or filter. Full-period totals above remain unchanged.';
  if (!data.summary.account_count) { emptyTitle = 'No source accounts for this period'; emptyText = 'Choose another reporting period. An empty source does not establish zero activation activity.'; }
  else if (comparison && !data.prior_period) { emptyTitle = 'No comparison selected'; emptyText = 'Choose an earlier reporting period to compare accounts.'; }
  else if (comparison && !data.comparison_account_count) { emptyTitle = 'No accounts present in both periods'; emptyText = 'The selected periods have no shared accounts. Missing prior records are not zero activity.'; }
  else if (exceptions && !data.summary.flagged_accounts) { emptyTitle = 'No exceptions for this period'; emptyText = 'No accounts match the existing exception rules. This does not certify every record as correct.'; }
  return <section className="overview-surface min-w-0 overflow-hidden" aria-label="Activation account collection" aria-busy={busy}>
    <div className="p-5 space-y-4">
      <div className="flex flex-wrap justify-between gap-2"><div><h2 className="text-lg font-semibold">{VIEWS.find(([id]) => id === data.view)[1]}</h2><p className="mt-1 text-sm text-gray-600">{comparison ? `${count(data.comparison_account_count)} accounts present in both periods before list filters. Changes describe observations, not causes.` : exceptions ? 'Findings are grouped by account. Inspect evidence before drawing a conclusion.' : 'Select an account to investigate activation volume and qualification.'}</p></div><p className="text-sm text-gray-600">{count(data.total)} matching accounts</p></div>
      <ActivationFilters filters={filters} classes={data.partner_classes} onFilter={onFilter} />
      <div role="status" className="text-xs text-gray-600 flex flex-wrap gap-x-5 gap-y-2">{busy ? 'Updating accounts…' : <><span>Matching records: {count(s.activation_count)}</span><span>Qualified: {count(s.qualified_activation_count)}</span><span>Zero commission: {count(s.non_qualified_activation_count)}</span><span>Weighted qualification: {rate(s.qualification_rate_pct)}</span><span>Recorded commission: {formatNGN(s.activation_commission_amount)}</span>{exceptions && <span>{count(s.finding_count)} findings across {count(s.flagged_accounts)} distinct accounts</span>}</>}</div>
    </div>
    <div className="overflow-x-auto" tabIndex={0} role="region" aria-label="Scrollable activation account table">
      <table className="commission-table w-full text-sm text-left"><thead><tr><th scope="col">Dealer / account</th>
        {comparison ? <><th scope="col" className="text-right">{formatPeriod(data.mon_period)} activations</th><th scope="col" className="text-right">{data.prior_period ? formatPeriod(data.prior_period) : 'Prior period'} activations</th><th scope="col" className="text-right">Activation change</th><th scope="col" className="text-right">Qualification change (pp)</th><th scope="col" className="text-right">Commission change</th></> : <><th scope="col" className="text-right">Activations</th><th scope="col" className="text-right">Qualified</th><th scope="col" className="text-right">Zero commission</th><th scope="col" className="text-right">Qualification</th><th scope="col">{exceptions ? 'Findings / next action' : 'Recorded commission'}</th></>}
        <th scope="col"><span className="sr-only">Investigation</span></th></tr></thead>
        <tbody>{data.items.map((r) => <tr key={r.dealer_id}><td><div className="font-medium">{r.dealer_name}</div><div className="text-xs text-gray-500 mt-1">{r.dealer_id} · {r.account_profile_class || 'Class not recorded'}</div></td>
          <td className="text-right tabular-nums font-semibold">{count(r.activation_count)}</td>
          {comparison ? <><td className="text-right tabular-nums">{r.prior_activation_count == null ? 'No prior record' : count(r.prior_activation_count)}</td><td className="text-right tabular-nums">{change(r.delta_activations)}</td><td className="text-right tabular-nums">{change(r.delta_qualification_rate, ' pp')}</td><td className="text-right tabular-nums whitespace-nowrap">{r.delta_commission_ngn == null ? '—' : `${r.delta_commission_ngn > 0 ? '+' : ''}${formatNGN(r.delta_commission_ngn)}`}</td></> : <><td className="text-right tabular-nums">{count(r.qualified_activation_count)}</td><td className="text-right tabular-nums">{count(r.non_qualified_activation_count)}</td><td className="text-right tabular-nums">{rate(r.qualification_rate_pct)}</td><td className={exceptions ? '' : 'text-right tabular-nums whitespace-nowrap'}>{exceptions ? <Findings findings={r.findings} /> : formatNGN(r.activation_commission_amount)}</td></>}
          <td><button ref={(el) => { rowRefs.current[r.dealer_id] = el; }} aria-label={`Investigate account ${r.dealer_id}`} className="overview-button whitespace-nowrap" disabled={busy} onClick={() => onSelect(r)}>Investigate →</button></td>
        </tr>)}</tbody>
      </table>
    </div>
    {!data.items.length && <div className="p-8 text-center" role="status"><h3 className="font-medium">{emptyTitle}</h3><p className="mt-2 text-sm text-gray-600">{emptyText}</p></div>}
    <fieldset disabled={busy} className="p-4 border-t border-gray-200 commission-pagination"><legend className="sr-only">Account pagination</legend><PaginationControls pagination={{ total: data.total, returned: data.items.length, offset: data.offset, limit: data.limit, has_more: data.offset + data.items.length < data.total }} pageSize={filters.limit} onPageSizeChange={(value) => onFilter('limit', value)} onOffsetChange={onPage} /></fieldset>
  </section>;
}
