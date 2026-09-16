import { useEffect, useRef, useState } from 'react';
import { useQuery } from '@tanstack/react-query';
import { getFinancialDealers } from '../../api/client.js';
import { usePeriod } from '../../context/PeriodContext.jsx';
import { formatNGN, formatPeriod } from '../../lib/format.js';
import useDebouncedValue from '../../hooks/useDebouncedValue.js';
import FinancialDetail from './FinancialDetail.jsx';
import './financial.css';

export default function FinancialHealthWorkspace() {
  const { period, loading, error } = usePeriod();
  if (!period) return <p role="status" className="p-6">{loading ? 'Loading reporting periods…' : error ? 'Reporting periods unavailable. Reload to retry.' : 'No reporting periods available.'}</p>;
  return <Workspace key={period} period={period} />;
}

function Workspace({ period }) {
  const [search, setSearch] = useState('');
  const [sort, setSort] = useState('dealer_name');
  const [offset, setOffset] = useState(0);
  const [selected, setSelected] = useState(null);
  const rowRefs = useRef({});
  const returnFocus = useRef(null);
  const debouncedSearch = useDebouncedValue(search);
  const params = { mon_period: period, search: debouncedSearch, sort_by: sort,
    direction: sort === 'dealer_name' ? 'asc' : 'desc', limit: 25, offset };
  const query = useQuery({ queryKey: ['financial-dealers', params], queryFn: ({ signal }) => getFinancialDealers(params, signal), enabled: !selected });
  const data = query.data;
  const busy = query.isFetching || search !== debouncedSearch;
  useEffect(() => {
    if (!selected && !busy && returnFocus.current) {
      rowRefs.current[returnFocus.current]?.focus();
      returnFocus.current = null;
    }
  }, [selected, busy]);
  return <main className="fh-workspace h-full overflow-y-auto bg-gray-50" aria-label="Dealer financial health">
    <div className="mx-auto max-w-7xl p-4 sm:p-6 lg:p-8 flex flex-col gap-6">
      <header><p className="text-xs font-semibold tracking-widest uppercase text-gray-500">Dealer business intelligence</p>
        <h1 className="text-2xl font-semibold tracking-tight mt-1">Financial Health</h1>
        <p className="text-sm text-gray-600 mt-2">Understand the business behind the dealer. Review profitability, cash and financial position.</p></header>
      {selected ? <FinancialDetail dealer={selected} period={period} onBack={() => { returnFocus.current = selected.dealer_id; setSelected(null); }} /> : <>
        <section className="fh-paper" aria-label="Dealer businesses">
          <div className="p-5 sm:p-6 border-b border-gray-200">
            <div className="flex flex-wrap justify-between items-start gap-3"><div><h2 className="text-lg font-semibold">Dealer businesses</h2><p className="text-sm text-gray-600 mt-1">Open a dealer to review three statements, six indicators and the supporting records.</p></div><button className="fh-button" disabled={busy} onClick={() => query.refetch()}>Refresh</button></div>
            <div className="flex flex-wrap gap-4 mt-5">
              <label className="fh-filter flex-1">Find a dealer<input type="search" value={search} maxLength={200} placeholder="Name, dealer ID or scenario" onChange={(event) => { setSearch(event.target.value); setOffset(0); }} /></label>
              <label className="fh-filter">Sort by<select value={sort} onChange={(event) => { setSort(event.target.value); setOffset(0); }}><option value="dealer_name">Dealer name · A–Z</option><option value="revenue">Revenue · high to low</option><option value="net_profit">Net profit · high to low</option></select></label>
            </div>
          </div>
          {query.isError ? <div className="p-6" role="alert"><p>Dealer financial reports are unavailable.</p><button className="fh-button mt-3" onClick={() => query.refetch()}>Retry dealer reports</button></div>
            : query.isPending || search !== debouncedSearch ? <div className="p-6 animate-pulse" role="status">Loading dealer reports…</div>
            : !data?.items.length ? <div className="p-6" role="status"><h3 className="font-semibold">{data?.available_periods.includes(period) ? 'No dealers match your search' : 'No statements for this month'}</h3><p className="text-sm text-gray-600 mt-2">{data?.available_periods.includes(period) ? 'Try another name, dealer ID or scenario.' : `Available months: ${data?.available_periods.map(formatPeriod).join(', ')}.`}</p>{search && <button className="fh-button mt-3" onClick={() => { setSearch(''); setOffset(0); }}>Clear search</button>}</div>
            : <>
              <div className="fh-table-scroll" role="region" aria-label="Scrollable dealer businesses" tabIndex={0}>
                <table className="fh-table"><caption className="sr-only">Dealer businesses for {formatPeriod(period)}</caption>
                  <thead><tr><th scope="col">Dealer / scenario</th><th scope="col">Revenue</th><th scope="col">Net profit</th><th scope="col">Operating cash flow</th><th scope="col">Review</th></tr></thead>
                  <tbody>{data.items.map((dealer) => <tr key={dealer.dealer_id}>
                    <th scope="row"><span className="block font-semibold">{dealer.dealer_name}</span><span className="block text-xs text-gray-500 mt-1">{dealer.dealer_id}</span><span className="block text-xs text-gray-600 mt-2 font-normal">{dealer.scenario}</span></th>
                    <td>{formatNGN(dealer.revenue)}</td><td className={dealer.net_profit < 0 ? 'text-red-800' : ''}>{formatNGN(dealer.net_profit)}</td><td className={dealer.operating_cash_flow < 0 ? 'text-red-800' : ''}>{formatNGN(dealer.operating_cash_flow)}</td>
                    <td><button className="fh-review" ref={(element) => { rowRefs.current[dealer.dealer_id] = element; }} aria-label={`Review ${dealer.dealer_name}`} onClick={() => setSelected(dealer)}>View statements <span aria-hidden="true">→</span></button></td>
                  </tr>)}</tbody>
                </table>
              </div>
              <div className="p-4 flex flex-wrap items-center justify-between gap-3 text-xs text-gray-600"><p>{data.pagination.total} matching businesses · All amounts in NGN</p><div className="flex gap-2"><button className="fh-button" disabled={offset === 0 || busy} onClick={() => setOffset(Math.max(0, offset - 25))}>Previous</button><button className="fh-button" disabled={!data.pagination.has_more || busy} onClick={() => setOffset(offset + 25)}>Next</button></div></div>
            </>}
        </section>
        <p className="text-xs text-gray-500">Statements cover the whole dealer business, including non-MTN activity.</p>
      </>}
    </div>
  </main>;
}
