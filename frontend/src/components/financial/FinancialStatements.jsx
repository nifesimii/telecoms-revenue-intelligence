import { Fragment, useState } from 'react';
import { formatNGN, formatNGNDelta, formatPeriod } from '../../lib/format.js';

export default function FinancialStatements({ report }) {
  const [active, setActive] = useState('income');
  const statement = report.statements.find((item) => item.id === active);
  const evidence = Object.fromEntries(report.evidence.map((item) => [item.id, item.label]));
  return <section className="fh-paper" aria-label="Financial statements">
    <div className="fh-statement-nav" role="group" aria-label="Choose financial statement">
      {report.statements.map((item) => <button key={item.id} aria-pressed={active === item.id}
        onClick={() => setActive(item.id)}>{item.label}</button>)}
    </div>
    <div className="p-5 sm:p-6 border-b border-gray-200">
      <h2 className="text-lg font-semibold">{statement.label}</h2>
      <p className="text-sm text-gray-600 mt-1">{active === 'balance' ? `As at ${report.as_of}` : `For the month ended ${report.as_of}`} · NGN</p>
      <p className="text-xs text-gray-500 mt-2">{active === 'income' ? 'Expenses are positive deductions from revenue.' : active === 'cashflow' ? 'Indirect method. Negative amounts are cash outflows.' : 'Assets, liabilities and equity for the whole business.'} Open a line item for its source.</p>
    </div>
    <div className="fh-table-scroll" tabIndex={0} role="region" aria-label={`Scrollable ${statement.label.toLowerCase()}`}>
      <table className="fh-table fh-statement-table">
        <caption className="sr-only">{report.dealer_name} — {statement.label}, {formatPeriod(report.mon_period)}</caption>
        <thead><tr><th scope="col">Line item</th><th scope="col">{formatPeriod(report.mon_period)}</th><th scope="col">{report.prior_period ? formatPeriod(report.prior_period) : 'Prior month'}</th><th scope="col">Change</th></tr></thead>
        <tbody>{statement.rows.map((row, index) => <Fragment key={row.id}>
          {(index === 0 || row.section !== statement.rows[index - 1].section) && <tr className="fh-section-row"><th colSpan={4} scope="colgroup">{row.section}</th></tr>}
          <tr className={row.total ? 'fh-total-row' : ''}>
            <th scope="row"><details><summary>{row.label}</summary><p className="fh-line-evidence">{row.evidence.map((id) => evidence[id]).join(' + ')}<br />Through {report.as_of}</p></details></th>
            <td className={row.amount < 0 ? 'text-red-800' : ''}>{formatNGN(row.amount)}</td>
            <td>{row.prior_amount == null ? '—' : formatNGN(row.prior_amount)}</td>
            <td>{row.prior_amount == null ? '—' : formatNGNDelta(row.amount - row.prior_amount)}</td>
          </tr>
        </Fragment>)}</tbody>
      </table>
    </div>
    <div className="px-5 py-3 border-t border-gray-200 text-xs text-gray-600">
      {active === 'balance' ? 'Assets equal liabilities plus equity.' : active === 'cashflow' ? 'Closing cash matches cash and bank balances on the balance sheet.' : 'Net profit carries into retained earnings on the balance sheet.'}
    </div>
  </section>;
}
