import { useId, useState } from 'react';

// Narrative tables retain exact identities in buffered responses and chat history.
// This control selects only an account from the current bounded evidence page.
export default function PortfolioDiscovery({ discovery, onSelect, onNextPage, disabled }) {
  const selectId = useId();
  const [dealerId, setDealerId] = useState('');
  if (discovery.status !== 'available' || !discovery.items?.length) return null;
  const account = discovery.items.find((item) => item.dealer_id === dealerId);
  return <div className="mt-4 pt-3 border-t border-gray-200 space-y-3">
    {onSelect && <>
      <label htmlFor={selectId} className="block text-xs font-medium">Account to investigate</label>
      <select id={selectId} className="overview-select w-full min-w-0" value={dealerId} disabled={disabled} onChange={(event) => setDealerId(event.target.value)}>
        <option value="">Choose an exact account</option>
        {discovery.items.map((item) => <option key={item.dealer_id} value={item.dealer_id}>{item.dealer_id} · {item.dealer_name}</option>)}
      </select>
      <button type="button" className="overview-button" disabled={disabled || !account} onClick={() => onSelect(account, discovery)}>Investigate selected account</button>
    </>}
    {discovery.has_more && onNextPage && <button type="button" className="overview-button block" disabled={disabled} onClick={() => onNextPage(discovery)}>Next affected accounts →</button>}
  </div>;
}
