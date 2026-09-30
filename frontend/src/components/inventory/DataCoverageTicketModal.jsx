import useQuery from '../../hooks/useWorkspaceQuery.js';
import { useEffect, useRef, useState } from 'react';
import { getDataCoverageIssues } from '../../api/client.js';
import { formatPeriod } from '../../lib/format.js';

export default function DataCoverageTicketModal({ period, open, onClose }) {
  const dialog = useRef(null);
  const body = useRef(null);
  const [source, setSource] = useState('ifs');
  const [copyStatus, setCopyStatus] = useState('');
  const query = useQuery({ queryKey: ['inventory-coverage-ticket', period, source],
    queryFn: () => getDataCoverageIssues(period, source), enabled: open });
  const data = query.data;
  useEffect(() => {
    if (!open) return;
    const opener = document.activeElement;
    const element = dialog.current;
    element.showModal();
    return () => { element.close(); opener?.focus(); };
  }, [open]);
  async function copyTicket() {
    try {
      await navigator.clipboard.writeText(data.ticket_body);
      setCopyStatus('Ticket draft copied.');
    } catch {
      body.current?.focus(); body.current?.select();
      setCopyStatus('Automatic copy unavailable. The draft is selected; copy it using your keyboard.');
    }
  }
  return <dialog ref={dialog} aria-labelledby="coverage-ticket-title" aria-describedby="coverage-ticket-scope"
    className="overview commission-workspace m-auto w-full max-w-3xl max-h-[90vh] rounded-lg border border-gray-200 p-0 backdrop:bg-black/40"
    onCancel={(event) => { event.preventDefault(); onClose(); }}>
    <div className="p-5 sm:p-6 space-y-5">
      <header className="flex items-start justify-between gap-3"><div><h2 id="coverage-ticket-title" className="text-lg font-semibold">Prepare coverage ticket</h2>
        <p className="mt-2 text-sm text-gray-600">{formatPeriod(period)} · Copy a draft for ServiceNow</p></div>
        <button className="overview-button" onClick={onClose} autoFocus>Close</button>
      </header>
      <p id="coverage-ticket-scope" className="text-sm text-gray-600">Includes all affected dealers in this reporting period for the selected source. Table filters and the selected dealer-product do not restrict this draft.</p>
      <fieldset className="flex flex-wrap gap-4 text-sm"><legend className="mb-2 font-medium">Data sources</legend>
        {[['ifs', 'IFS invoices'], ['usp', 'USP qualification'], ['both', 'IFS and USP']].map(([value, label]) => <label key={value} className="flex items-center gap-2">
          <input type="radio" name="coverage-source" checked={source === value} onChange={() => { setSource(value); setCopyStatus(''); }} className="accent-mtn-yellow" />{label}
        </label>)}
      </fieldset>
      {query.isFetching && <p role="status" className="text-sm">Compiling coverage draft…</p>}
      {query.isError && <p role="alert" className="text-sm text-red-800">Coverage draft unavailable. <button className="underline" onClick={() => query.refetch()}>Retry draft</button></p>}
      {data && !query.isError && !query.isFetching && <>
        <p className="text-sm"><strong>{data.affected_dealers.toLocaleString()}</strong> affected dealers · IFS missing: {data.ifs_missing.length} · USP missing: {data.usp_missing.length}</p>
        {data.affected_dealers === 0 ? <p role="status" className="text-sm text-gray-600">No coverage issues identified for this source and period in the available data.</p> : <>
          <label className="block text-sm font-medium" htmlFor="coverage-ticket-body">Ticket draft</label>
          <textarea ref={body} id="coverage-ticket-body" readOnly value={data.ticket_body} className="w-full h-64 border border-gray-300 rounded-md p-3 text-sm font-mono bg-gray-50" />
          <p className="text-sm text-gray-600">{data.severity_action}</p>
          <button className="overview-button overview-primary" onClick={copyTicket}>Copy ticket draft</button>
        </>}
      </>}
      <p role="status" className="text-sm text-gray-600">{copyStatus}</p>
      <p className="text-xs text-gray-500 border-t border-gray-200 pt-4">Copy the draft into ServiceNow for review. Nothing is submitted from this page.</p>
    </div>
  </dialog>;
}
