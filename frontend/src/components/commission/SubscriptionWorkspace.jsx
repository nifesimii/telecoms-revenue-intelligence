import { useEffect, useRef, useState } from 'react';
import { keepPreviousData, useQuery } from '@tanstack/react-query';
import { getSubscriptionAccounts, getSubscriptionExport } from '../../api/client.js';
import { formatPeriod } from '../../lib/format.js';
import { downloadCsv } from '../../lib/csv.js';
import useDebouncedValue from '../../hooks/useDebouncedValue.js';
import CommissionAssistant from './CommissionAssistant.jsx';
import SubscriptionAccounts from './SubscriptionAccounts.jsx';
import SubscriptionDetail from './SubscriptionDetail.jsx';
import { SubscriptionFigures, SubscriptionProvenance } from './SubscriptionFigures.jsx';

const DEFAULT_FILTERS = { search: '', payment_status: 'all', sort_by: 'simulated_commission_ngn', direction: 'desc', limit: 25, offset: 0 };

export default function SubscriptionWorkspace({ period, selected, setSelected, pendingPrompt, onPromptConsumed }) {
  const [filters, setFilters] = useState(DEFAULT_FILTERS);
  const [showAssistant, setShowAssistant] = useState(Boolean(pendingPrompt));
  const [exporting, setExporting] = useState(false);
  const [exportError, setExportError] = useState('');
  const rowRefs = useRef({});
  const headingRef = useRef(null);
  const returnFocus = useRef(null);
  const search = useDebouncedValue(filters.search);
  const params = { ...filters, search, mon_period: period };
  const query = useQuery({ queryKey: ['subscription-accounts', params], queryFn: ({ signal }) => getSubscriptionAccounts(params, signal), placeholderData: keepPreviousData, enabled: !selected });
  const data = query.data;
  const busy = query.isFetching || search !== filters.search;
  useEffect(() => { if (pendingPrompt) setShowAssistant(true); }, [pendingPrompt]);
  useEffect(() => {
    if (!selected && !busy && returnFocus.current) {
      (rowRefs.current[returnFocus.current] || headingRef.current)?.focus();
      returnFocus.current = null;
    }
  }, [selected, busy]);
  useEffect(() => {
    if (data && !query.isPlaceholderData && filters.offset > 0 && filters.offset >= data.total) setFilters((current) => ({ ...current, offset: 0 }));
  }, [data, query.isPlaceholderData, filters.offset]);
  function filter(key, value) {
    setFilters((current) => key === 'reset' ? DEFAULT_FILTERS : { ...current, [key]: value, offset: 0 });
    setExportError('');
  }
  async function exportMatching() {
    setExporting(true); setExportError('');
    try { downloadCsv(await getSubscriptionExport(params), `subscription_commission_${period}_matching_accounts.csv`); }
    catch { setExportError('Subscription export unavailable. Please retry.'); }
    finally { setExporting(false); }
  }
  if (selected) return <SubscriptionDetail key={`${period}:${selected.dealer_id}`} period={period} account={selected} prompt={pendingPrompt} onPromptConsumed={onPromptConsumed} onBack={() => { returnFocus.current = selected.dealer_id; setSelected(null); }} />;
  return <div className="space-y-5">
    <div className="flex flex-wrap justify-between items-center gap-3">
      <p className="text-sm text-gray-600">{formatPeriod(period)} · Subscription commission</p>
      <div className="flex flex-wrap gap-2">
        <button className="overview-button" disabled={busy} onClick={() => query.refetch()}>Refresh</button>
        <button className="overview-button" disabled={!data?.total || query.isError || busy || exporting} onClick={exportMatching}>{exporting ? 'Exporting…' : 'Export matching accounts ↓'}</button>
        <button className="overview-button" aria-expanded={showAssistant} disabled={!data || query.isError} onClick={() => setShowAssistant(!showAssistant)}>{showAssistant ? 'Hide assistant' : 'Ask a question'}</button>
      </div>
    </div>
    {exportError && <p role="alert" className="text-sm text-red-800">{exportError}</p>}
    {query.isError ? <div role="alert" className="overview-notice">Subscription records unavailable. No balance can be established. <button className="underline" onClick={() => query.refetch()}>Retry subscription records</button></div>
      : !data ? <div role="status" className="overview-surface p-6 animate-pulse">Loading subscription records…</div>
      : <>
        <SubscriptionProvenance data={data} />
        <SubscriptionFigures figures={data.summary} totals available={data.commission_available} title="Reporting month totals" />
        {showAssistant && <CommissionAssistant key={`${period}:${data.synthetic}`} subscription={data} period={period} stream="orsc" prompt={pendingPrompt} onPromptConsumed={onPromptConsumed} />}
        <SubscriptionAccounts data={data} busy={busy} filters={filters} onFilter={filter} onSelect={setSelected} rowRefs={rowRefs} headingRef={headingRef} onPage={(offset) => setFilters((current) => ({ ...current, offset }))} />
      </>}
  </div>;
}
