// Activation variance table — one row per dealer present in both periods.
// Delta column: green up arrow if positive, red down arrow if negative.
// Reuses the same colour cues as VarianceCard for consistency.

function formatNaira(n) {
  const v = Math.abs(Number(n) || 0);
  return (
    '₦' +
    v.toLocaleString('en-NG', {
      minimumFractionDigits: 2,
      maximumFractionDigits: 2,
    })
  );
}

function UpArrow() {
  return (
    <svg viewBox="0 0 20 20" fill="currentColor" className="inline-block w-3 h-3 mr-0.5">
      <path
        fillRule="evenodd"
        d="M10 17a.75.75 0 01-.75-.75V5.66l-3.97 3.97a.75.75 0 01-1.06-1.06l5.25-5.25a.75.75 0 011.06 0l5.25 5.25a.75.75 0 11-1.06 1.06L10.75 5.66v10.59A.75.75 0 0110 17z"
        clipRule="evenodd"
      />
    </svg>
  );
}

function DownArrow() {
  return (
    <svg viewBox="0 0 20 20" fill="currentColor" className="inline-block w-3 h-3 mr-0.5">
      <path
        fillRule="evenodd"
        d="M10 3a.75.75 0 01.75.75v10.59l3.97-3.97a.75.75 0 111.06 1.06l-5.25 5.25a.75.75 0 01-1.06 0l-5.25-5.25a.75.75 0 111.06-1.06l3.97 3.97V3.75A.75.75 0 0110 3z"
        clipRule="evenodd"
      />
    </svg>
  );
}

function deltaTone(v) {
  if (!v) return 'text-gray-500';
  return v > 0 ? 'text-emerald-700' : 'text-red-700';
}

export default function ActivationVarianceTable({ rows = [], loading = false }) {
  if (loading) {
    return (
      <div className="p-4 text-sm text-gray-500 italic">
        Loading variance…
      </div>
    );
  }
  if (!rows.length) {
    return (
      <div className="p-4 text-sm text-gray-500 italic">No data.</div>
    );
  }

  return (
    <div className="overflow-auto h-full">
      <table className="w-full text-xs border-collapse">
        <thead className="sticky top-0 bg-gray-50 z-10">
          <tr className="text-gray-600">
            <th className="border-b border-gray-200 px-2 py-1.5 text-left font-semibold w-10">
              #
            </th>
            <th className="border-b border-gray-200 px-2 py-1.5 text-left font-semibold">
              Dealer
            </th>
            <th className="border-b border-gray-200 px-2 py-1.5 text-right font-semibold">
              Period A
            </th>
            <th className="border-b border-gray-200 px-2 py-1.5 text-right font-semibold">
              Period B
            </th>
            <th className="border-b border-gray-200 px-2 py-1.5 text-right font-semibold">
              Δ Activations
            </th>
            <th className="border-b border-gray-200 px-2 py-1.5 text-right font-semibold">
              Δ Commission
            </th>
            <th className="border-b border-gray-200 px-2 py-1.5 text-right font-semibold">
              Δ Rate %
            </th>
          </tr>
        </thead>
        <tbody>
          {rows.map((r, i) => {
            const dAct = Number(r.delta_activations) || 0;
            const dCom = Number(r.delta_commission_ngn) || 0;
            const dRate = Number(r.delta_qualification_rate) || 0;
            return (
              <tr
                key={r.dealer_id || i}
                className="hover:bg-gray-50 border-b border-gray-100 last:border-b-0"
              >
                <td className="px-2 py-1.5 text-gray-400 tabular-nums">
                  {i + 1}
                </td>
                <td
                  className="px-2 py-1.5 text-gray-800 truncate max-w-[220px]"
                  title={r.dealer_name}
                >
                  {r.dealer_name}
                </td>
                <td className="px-2 py-1.5 text-right tabular-nums text-gray-600">
                  {r.activation_count_a}
                </td>
                <td className="px-2 py-1.5 text-right tabular-nums text-gray-800">
                  {r.activation_count_b}
                </td>
                <td
                  className={`px-2 py-1.5 text-right tabular-nums font-semibold ${deltaTone(
                    dAct,
                  )}`}
                >
                  {dAct > 0 ? <UpArrow /> : dAct < 0 ? <DownArrow /> : null}
                  {dAct > 0 ? '+' : dAct < 0 ? '−' : ''}
                  {Math.abs(dAct)}
                </td>
                <td
                  className={`px-2 py-1.5 text-right tabular-nums font-semibold ${deltaTone(
                    dCom,
                  )}`}
                >
                  {dCom > 0 ? <UpArrow /> : dCom < 0 ? <DownArrow /> : null}
                  {dCom === 0 ? '₦0.00' : (dCom > 0 ? '+' : '−') + formatNaira(dCom)}
                </td>
                <td
                  className={`px-2 py-1.5 text-right tabular-nums ${deltaTone(
                    dRate,
                  )}`}
                >
                  {dRate > 0 ? '+' : dRate < 0 ? '−' : ''}
                  {Math.abs(dRate).toFixed(2)}%
                </td>
              </tr>
            );
          })}
        </tbody>
      </table>
    </div>
  );
}
