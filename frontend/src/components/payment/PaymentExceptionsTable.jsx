// Exceptions-only payment table.
// Exception flag badges link back to Phase 2/3:
//   ALL_UNQUALIFIED       → red    "Phase 2"
//   CONFIRMED_MISMATCH    → amber  "Phase 3"
//   HIGH_UNQUALIFIED_RATE → amber  "Phase 2"

function fmtNaira(n) {
  const v = Number(n) || 0;
  return (
    '₦' +
    v.toLocaleString('en-NG', {
      minimumFractionDigits: 2,
      maximumFractionDigits: 2,
    })
  );
}

const STATUS_TONE = {
  PARTIALLY_PAID: 'bg-amber-100 text-amber-800 border-amber-200',
  DISPUTED: 'bg-red-100 text-red-800 border-red-200',
  PENDING: 'bg-gray-100 text-gray-700 border-gray-200',
};

const FLAG_INFO = {
  ALL_UNQUALIFIED: { tone: 'bg-red-100 text-red-800 border-red-200', phase: 'Phase 2' },
  CONFIRMED_MISMATCH: {
    tone: 'bg-amber-100 text-amber-800 border-amber-200',
    phase: 'Phase 3',
  },
  HIGH_UNQUALIFIED_RATE: {
    tone: 'bg-amber-100 text-amber-800 border-amber-200',
    phase: 'Phase 2',
  },
};

function StatusBadge({ status }) {
  const tone = STATUS_TONE[status] || STATUS_TONE.PENDING;
  return (
    <span
      className={`inline-block px-2 py-0.5 text-[10px] font-semibold uppercase tracking-wide border rounded-full ${tone}`}
    >
      {status}
    </span>
  );
}

function FlagBadge({ flag }) {
  if (!flag) {
    return <span className="text-[10px] text-gray-400 italic">none</span>;
  }
  const info = FLAG_INFO[flag] || { tone: 'bg-gray-100 text-gray-700 border-gray-200', phase: '' };
  return (
    <span className="inline-flex items-center gap-1.5">
      <span
        className={`inline-block px-2 py-0.5 text-[10px] font-semibold uppercase tracking-wide border rounded-full ${info.tone}`}
      >
        {flag}
      </span>
      {info.phase && (
        <span className="text-[10px] text-gray-400 uppercase tracking-wide">
          {info.phase}
        </span>
      )}
    </span>
  );
}

function actionFor(row) {
  const amount = fmtNaira(row.amount_unpaid);
  const name = row.distributor_name;
  if (row.payment_status === 'DISPUTED')
    return `${amount} disputed for ${name}. Linked to ${row.exception_flag} exception. Verify activation records before settlement.`;
  if (row.payment_status === 'PARTIALLY_PAID')
    return `${amount} outstanding for ${name}. Partial payment processed. Review qualification rate.`;
  return `${amount} pending settlement for ${name}. Within normal payment window.`;
}

export default function PaymentExceptionsTable({ rows = [], loading = false }) {
  if (loading) {
    return (
      <div className="p-4 text-sm text-gray-500 italic">
        Loading payment exceptions…
      </div>
    );
  }
  if (!rows.length) {
    return (
      <div className="p-4 text-sm text-gray-500 italic">
        No outstanding payments.
      </div>
    );
  }

  return (
    <div className="overflow-auto h-full">
      <table className="w-full text-xs border-collapse">
        <thead className="sticky top-0 bg-gray-50 z-10">
          <tr className="text-gray-600">
            <th className="border-b border-gray-200 px-2 py-1.5 text-left font-semibold">
              Dealer
            </th>
            <th className="border-b border-gray-200 px-2 py-1.5 text-left font-semibold">
              Status
            </th>
            <th className="border-b border-gray-200 px-2 py-1.5 text-right font-semibold">
              Owed
            </th>
            <th className="border-b border-gray-200 px-2 py-1.5 text-right font-semibold">
              Outstanding
            </th>
            <th className="border-b border-gray-200 px-2 py-1.5 text-left font-semibold">
              Exception flag
            </th>
            <th className="border-b border-gray-200 px-2 py-1.5 text-left font-semibold">
              Recommended action
            </th>
          </tr>
        </thead>
        <tbody>
          {rows.map((r, i) => (
            <tr
              key={`${r.distributor_code}-${i}`}
              className="hover:bg-gray-50 border-b border-gray-100 last:border-b-0 align-top"
            >
              <td
                className="px-2 py-1.5 text-gray-800 truncate max-w-[180px]"
                title={r.distributor_name}
              >
                {r.distributor_name}
              </td>
              <td className="px-2 py-1.5">
                <StatusBadge status={r.payment_status} />
              </td>
              <td className="px-2 py-1.5 text-right tabular-nums text-gray-700">
                {fmtNaira(r.commission_owed)}
              </td>
              <td className="px-2 py-1.5 text-right tabular-nums font-semibold text-gray-900">
                {fmtNaira(r.amount_unpaid)}
              </td>
              <td className="px-2 py-1.5">
                <FlagBadge flag={r.exception_flag} />
              </td>
              <td className="px-2 py-1.5 text-[11px] text-gray-600 max-w-[420px]">
                {actionFor(r)}
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
