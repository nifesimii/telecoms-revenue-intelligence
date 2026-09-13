import { useQuery } from '@tanstack/react-query';
import { money, statusLabel, findingLabel } from './paymentPresentation.js';

export default function PaymentSummaryTable({ rows, onSelect, rowRefs, period }) {
  return <div className="overflow-auto max-h-[640px]" tabIndex={0} role="region" aria-label="Scrollable payment accounts">
    <table className="commission-table w-full text-sm text-left">
      <thead className="sticky top-0 z-10"><tr><th>Dealer</th>{['Commission owed', 'Amount settled', 'Outstanding'].map((label) => <th key={label} className="text-right">{label}</th>)}<th>Payment status</th><th>Finding</th><th>Evidence</th></tr></thead>
      <tbody>{rows.map((row) => <tr key={row.dealer_id}>
        <td><p className="font-medium min-w-40">{row.dealer_name}</p><p className="text-xs text-gray-500 mt-1">{row.dealer_id}</p></td>
        {[row.commission_owed, row.amount_paid, row.amount_unpaid].map((v, i) => <td key={i} className="text-right whitespace-nowrap tabular-nums">{money(v)}</td>)}
        <td>{statusLabel(row.payment_status)}</td><td className="min-w-48">{findingLabel(row.exception_flag)}<p className="text-xs text-gray-500 mt-1"><EvidenceState dealerId={row.dealer_id} period={period} /></p></td>
        <td><button ref={(node) => { rowRefs.current[row.dealer_id] = node; }} className="overview-button whitespace-nowrap" aria-label={`View evidence for ${row.dealer_name}, ${row.dealer_id}`} onClick={() => onSelect(row.dealer_id)}>View evidence</button></td>
      </tr>)}</tbody>
    </table>
  </div>;
}

function EvidenceState({ dealerId, period }) {
  const query = useQuery({ queryKey: ['dealer-verification', period, dealerId], enabled: false });
  const label = query.isFetching ? 'Loading' : query.isError ? (query.error?.response?.status === 404 ? 'No records found' : 'Request failed; retry in evidence') : query.data ? 'Records available' : 'Not checked';
  return <>Activation evidence: {label}</>;
}
