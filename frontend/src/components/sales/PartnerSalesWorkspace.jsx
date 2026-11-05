import { useEffect, useRef, useState } from 'react';
import { usePeriod } from '../../context/PeriodContext.jsx';
import { formatDate, formatMinorNGN, formatPeriod } from '../../lib/format.js';
import { draftTotalMinor, invoiceOpenerId, lineTotalMinor, partnerLabel, partnerMatches, quantityLabel } from './salesDisplay.js';
import { dueDateError, issueDateError, lastDayOf, quantityError } from './salesFormChecks.js';
import { failureMessage, isRefusal, useSalesActions } from './useSalesActions.js';
import { useSalesDraft, useSalesReference, useSalesSimulationStatus } from './useSalesQueries.js';
import { useSelectedPartner } from './useSelectedPartner.js';
import { InvoiceDetail, InvoiceList, PartnerObligations, RefusedChange } from './InvoiceViews.jsx';
import CommissionAccount from './CommissionAccount.jsx';
import './sales.css';

const detailHeadingId = (entry) => (entry.type === 'invoice' ? `sales-invoice-heading-${entry.reference}` : entry.type === 'commission' ? `sales-commission-heading-${entry.accountCode}` : `sales-obligations-heading-${entry.accountCode}`);
const backLabelTo = (entry) => (entry.type === 'partner' ? 'Back to purchase obligations' : entry.type === 'commission' ? 'Back to commission account' : `Back to invoice ${entry.reference}`);

export default function PartnerSalesWorkspace({ navigation, onNavigate, onClearNavigation }) {
  const { periods, period, loading, error } = usePeriod();
  // A month seeded from the URL only counts once /periods confirms it.
  if (loading || !periods.includes(period)) return <p role="status" className="p-6">{loading ? 'Loading reporting periods…' : error ? 'Reporting periods unavailable. Reload to retry.' : 'No reporting periods available.'}</p>;
  return <ReferenceGate period={period} navigation={navigation} onNavigate={onNavigate} onClearNavigation={onClearNavigation} />;
}

function ReferenceGate(props) {
  const reference = useSalesReference();
  if (reference.data) return <Workspace {...props} reference={reference.data} />;
  if (!reference.isError) return <p role="status" className="p-6">Loading Partner Sales…</p>;
  return <div role="alert" className="p-6">Partner Sales could not be loaded.
    <div className="mt-2"><button type="button" className="sales-button" onClick={() => reference.refetch()}>Try again</button></div></div>;
}

// Asks first, in place: a browser dialog would stop the presentation, and an
// accidental reset would lose the rehearsal so far.
function SimulationReset({ onReset }) {
  const status = useSalesSimulationStatus().data;
  const [confirming, setConfirming] = useState(false);
  const [resetting, setResetting] = useState(false);
  const [failed, setFailed] = useState(false);
  const cancel = () => {
    setConfirming(false);
    setFailed(false);
    requestAnimationFrame(() => document.getElementById('sales-reset')?.focus());
  };
  const reset = async () => {
    setResetting(true);
    setFailed(false);
    try {
      await onReset();
      setConfirming(false);
    } catch {
      setFailed(true);
    } finally {
      setResetting(false);
    }
  };
  const open = () => {
    setConfirming(true);
    requestAnimationFrame(() => document.getElementById('sales-reset-keep')?.focus());
  };
  const contents = status ? `${quantityLabel(status.drafts, 'draft')}, ${quantityLabel(status.invoices, 'invoice')} and ${quantityLabel(status.collections, 'collection')}` : 'records';
  return <div className="mt-3">
    {!confirming ? <button id="sales-reset" type="button" className="sales-button" onClick={open}>Reset simulation</button>
      : <div role="group" aria-label="Confirm simulation reset" className="sales-paper">
        <p className="text-sm">Reset the simulation to its starting point for everyone using it? This discards the current {contents}, restores the example invoices, and clears the selected partner and filters. Recorded commission, payment and inventory evidence, other workspaces and the reporting month stay as they are.</p>
        {failed && <p role="alert" className="sales-alert">The simulation could not be reset, so nothing has changed. Try again.</p>}
        <div className="sales-actions">
          <button type="button" className="sales-button sales-primary" disabled={resetting} onClick={reset}>Reset to starting point</button>
          <button id="sales-reset-keep" type="button" className="sales-button" disabled={resetting} onClick={cancel}>Keep simulation</button>
        </div>
      </div>}
  </div>;
}

function Workspace({ reference: { partners, catalogue, max_quantity: maxQuantity, statuses }, period, navigation, onNavigate, onClearNavigation }) {
  const actions = useSalesActions();
  const [selectedCode, setSelectedCode] = useSelectedPartner();
  // Remounts the invoice list, so a reset also drops its filters and page.
  const [invoiceListKey, setInvoiceListKey] = useState(0);
  // The notice lasts until the next thing the presenter does here.
  const [resetStatus, setResetStatus] = useState(null);
  const [search, setSearch] = useState('');
  const term = search.trim().toLowerCase();
  const matches = partners.filter((partner) => partnerMatches(partner, term));
  const partnerByCode = (code) => partners.find((candidate) => candidate.code === code);
  const partner = partnerByCode(selectedCode);
  const draftQuery = useSalesDraft(partner?.code, period);
  const draft = draftQuery.data?.draft;
  // Where focus goes once a draft that is still loading appears.
  const draftFocus = useRef(null);
  const selectPartner = (code) => {
    setSelectedCode(code);
    setResetStatus(null);
  };
  const [creating, setCreating] = useState(false);
  const [createFailed, setCreateFailed] = useState(false);
  const createDraft = async () => {
    setCreating(true);
    setCreateFailed(false);
    setResetStatus(null);
    try {
      draftFocus.current = 'sales-catalogue-heading';
      await actions.createDraft(partner.code, period);
    } catch {
      setCreateFailed(true);
    } finally {
      setCreating(false);
    }
  };
  const latestRequested = useRef(false);
  const loadLatestDraft = (reference) => {
    latestRequested.current = true;
    draftFocus.current = 'sales-draft-heading';
    return actions.loadLatest(reference);
  };
  // The draft may no longer exist, so its heading cannot take focus.
  useEffect(() => {
    if (!latestRequested.current || !draftQuery.data) return;
    latestRequested.current = false;
    if (draft) return;
    draftFocus.current = null;
    document.getElementById('sales-no-draft')?.focus();
  }, [draftQuery.data]);
  // Open detail views, innermost last. Views underneath stay mounted but hidden,
  // so returning finds their filters, page and opener exactly as they were.
  const [trail, setTrail] = useState([]);
  const focusDetail = (entry) => requestAnimationFrame(() => document.getElementById(detailHeadingId(entry))?.focus());
  // Reopening a view already on the trail brings it forward rather than stacking
  // a copy, so every view underneath stays mounted with its page.
  const openDetail = (entry, openerId) => {
    setTrail((current) => [...current.filter((other) => detailHeadingId(other) !== detailHeadingId(entry)), { ...entry, openerId }]);
    focusDetail(entry);
  };
  const closeDetail = (openerId) => {
    setTrail((current) => current.slice(0, -1));
    requestAnimationFrame(() => (document.getElementById(openerId) ?? document.getElementById('sales-invoices-heading'))?.focus());
  };
  // Focus for a change that follows a server call or a refresh, first id that rendered wins.
  // It waits for the render itself: a frame later is not always late enough.
  const focusAfterTrail = useRef([]);
  useEffect(() => {
    const ids = focusAfterTrail.current;
    focusAfterTrail.current = [];
    ids.map((id) => document.getElementById(id)).find(Boolean)?.focus();
  }, [trail]);
  // The explanation's history entry names the account, so returning restores it even
  // after a refresh emptied the trail. An account still open keeps its opener.
  useEffect(() => {
    const accountCode = navigation?.commission_partner;
    if (!partnerByCode(accountCode)) return;
    const entry = { type: 'commission', accountCode };
    focusAfterTrail.current = [navigation.opener_id, detailHeadingId(entry)];
    setTrail((current) => {
      const open = current.find((other) => detailHeadingId(other) === detailHeadingId(entry));
      return [...current.filter((other) => other !== open), open ?? { ...entry, openerId: 'sales-partner-commission' }];
    });
  }, [navigation?.revision]);
  const issue = async (issuing) => {
    const invoice = await actions.issueDraft(issuing);
    setResetStatus(null);
    const entry = { type: 'invoice', reference: invoice.reference, openerId: invoiceOpenerId(invoice.reference) };
    focusAfterTrail.current = [detailHeadingId(entry)];
    setTrail([entry]);
  };
  const recordInvoiceCollection = (reference, collection) => {
    setResetStatus(null);
    return actions.recordCollection(reference, collection);
  };
  const openDraft = (record) => {
    const focusOpenDraft = () => requestAnimationFrame(() => (document.getElementById('sales-draft-heading') ?? document.getElementById('sales-preview-heading'))?.focus());
    if (record.partner.code === partner?.code) focusOpenDraft();
    else draftFocus.current = 'sales-draft-heading';
    selectPartner(record.partner.code);
  };
  const openInvoice = (reference, openerId) => openDetail({ type: 'invoice', reference }, openerId);
  const openPartner = (accountCode, openerId) => openDetail({ type: 'partner', accountCode }, openerId);
  const openCommission = (accountCode, openerId) => openDetail({ type: 'commission', accountCode }, openerId);
  const reset = async () => {
    const status = await actions.reset();
    setResetStatus(status);
    setSelectedCode('');
    setSearch('');
    focusAfterTrail.current = ['sales-reset-notice'];
    setTrail([]);
    setInvoiceListKey((current) => current + 1);
    onClearNavigation();
  };
  return <main className="sales-workspace h-full overflow-y-auto bg-gray-50" aria-label="Partner Sales">
    <div className="mx-auto max-w-7xl p-4 sm:p-6 lg:p-8 flex flex-col gap-6">
      <header><p className="text-xs font-semibold tracking-widest uppercase text-gray-500">MTN sales to trade partners</p>
        <h1 id="sales-workspace-heading" tabIndex={-1} className="text-2xl font-semibold tracking-tight mt-1">Partner Sales</h1>
        <p className="text-sm text-gray-600 mt-2">Draft, preview and issue what MTN would invoice a trade partner in {formatPeriod(period)}, record fictional collections against issued invoices, and explain a partner's fictional commission account.</p>
        <p className="sales-notice mt-3">Fictional simulation using sample partner identities and fictional products and prices. It starts with example invoices in May 2026. Drafts, simulated invoices and collections are shared by everyone signed in and last until the server restarts or the simulation is reset. They stay separate from recorded commission, payment and inventory evidence, including when the application reads live data.</p>
        <SimulationReset onReset={reset} />
        {resetStatus && <p id="sales-reset-notice" role="status" tabIndex={-1} className="sales-notice mt-3">Simulation reset to its starting point: {resetStatus.invoices} example invoices in May 2026, and the next draft will be {resetStatus.next_draft_reference}.</p>}</header>
      {trail.map((entry, index) => {
        const active = index === trail.length - 1;
        const onBack = () => closeDetail(entry.openerId);
        const backLabel = !index ? 'Back to invoices' : backLabelTo(trail[index - 1]);
        return <div key={detailHeadingId(entry)} className={active ? '' : 'hidden'}>
          {entry.type === 'commission'
            ? <CommissionAccount partner={partnerByCode(entry.accountCode)} period={period} headingId={detailHeadingId(entry)} backLabel={backLabel} onBack={onBack} onOpenObligations={openPartner}
              onExplain={(view, context, openerId) => onNavigate(view, { ...context, origin: { commission_partner: entry.accountCode, opener_id: openerId } })} />
            : entry.type === 'invoice'
            ? <InvoiceDetail reference={entry.reference} headingId={detailHeadingId(entry)} backLabel={backLabel} onBack={onBack} onOpenPartner={openPartner} onRecordCollection={recordInvoiceCollection} onLoadLatest={actions.loadLatest} />
            : <PartnerObligations partner={partnerByCode(entry.accountCode)} headingId={detailHeadingId(entry)} backLabel={backLabel} onBack={onBack} onOpenInvoice={openInvoice} onOpenCommission={openCommission} />}
        </div>;
      })}
      <div className={trail.length ? 'hidden' : 'flex flex-col gap-6'}>
      <section className="sales-paper" aria-labelledby="sales-partner-heading">
        <h2 id="sales-partner-heading" className="text-lg font-semibold">Trade partner</h2>
        <label className="sales-field mt-4">Find a partner
          <input type="search" value={search} maxLength={200} placeholder="Name or account code" onChange={(event) => setSearch(event.target.value)} /></label>
        {matches.length ? <fieldset className="mt-4"><legend className="sr-only">Partner account</legend>
          <div className="grid gap-2 sm:grid-cols-2 lg:grid-cols-3">{matches.map((candidate) => <label key={candidate.code} className="sales-partner">
            <input type="radio" name="sales-partner" checked={selectedCode === candidate.code} onChange={() => selectPartner(candidate.code)} />
            <span>{partnerLabel(candidate)}</span>
          </label>)}</div>
        </fieldset> : <p role="status" className="text-sm text-gray-600 mt-4">No partners match your search. Try another name or account code.</p>}
        {partner && <div className="sales-actions">
          <button id="sales-partner-obligations" type="button" className="sales-button" onClick={() => openPartner(partner.code, 'sales-partner-obligations')}>View purchase obligations for {partnerLabel(partner)}</button>
          <button id="sales-partner-commission" type="button" className="sales-button" onClick={() => openCommission(partner.code, 'sales-partner-commission')}>View commission account for {partnerLabel(partner)}</button>
        </div>}
      </section>
      {!partner ? <p className="sales-paper text-sm text-gray-600">Select a trade partner to create a draft.</p>
        : draftQuery.isError ? <section className="sales-paper" aria-label="Draft unavailable">
          <p role="alert" className="sales-alert !mt-0">This partner's draft could not be loaded.</p>
          <button type="button" className="sales-button mt-3" onClick={() => draftQuery.refetch()}>Try again</button>
        </section>
        : !draftQuery.data ? <p role="status" className="sales-paper text-sm text-gray-600">Loading draft…</p>
        : !draft ? <section className="sales-paper" aria-label="No draft">
          <p id="sales-no-draft" tabIndex={-1} className="text-sm text-gray-600">No draft for {partnerLabel(partner)} in {formatPeriod(period)}.</p>
          {createFailed && <p role="alert" className="sales-alert">The draft could not be created. Try again.</p>}
          <button type="button" className="sales-button sales-primary mt-3" disabled={creating} onClick={createDraft}>Create draft</button>
        </section>
        : <DraftEditor key={draft.reference} draft={draft} partner={partner} catalogue={catalogue} maxQuantity={maxQuantity} focusRequest={draftFocus} saved={actions.draftSave.reference === draft.reference ? actions.draftSave : { state: 'idle' }} onChange={actions.changeDraft} onRetrySave={actions.retryDraftSave} onOpen={actions.forgetFinishedSaves} onLoadLatest={loadLatestDraft} onIssue={issue} />}
      <InvoiceList key={invoiceListKey} period={period} statuses={statuses} onOpenInvoice={openInvoice} onOpenPartner={openPartner} onOpenDraft={openDraft} />
      </div>
    </div>
  </main>;
}

function DraftEditor({ draft: loadedDraft, partner, catalogue, maxQuantity, focusRequest, saved, onChange, onRetrySave, onOpen, onLoadLatest, onIssue }) {
  // Edits apply here at once, so typing keeps its caret and a new line can take focus.
  const [draft, setDraft] = useState(loadedDraft);
  const change = (next) => {
    setDraft(next);
    onChange(next);
  };
  const [previewing, setPreviewing] = useState(false);
  const [attempted, setAttempted] = useState(false);
  const previewOpener = useRef(null);
  const previewHeading = useRef(null);
  const linesHeading = useRef(null);
  const issueInput = useRef(null);
  const dueInput = useRef(null);
  const quantityInputs = useRef({});
  const productByCode = (code) => catalogue.find((product) => product.code === code);
  useEffect(() => {
    onOpen(loadedDraft.reference);
    if (focusRequest.current) document.getElementById(focusRequest.current)?.focus();
    focusRequest.current = null;
  }, []);
  const setLines = (edit) => change({ ...draft, lines: edit(draft.lines) });
  const addLine = (code) => {
    setLines((lines) => [...lines, { product_code: code, quantity: '1' }]);
    requestAnimationFrame(() => quantityInputs.current[code]?.focus());
  };
  const removeLine = (code) => {
    setLines((lines) => lines.filter((line) => line.product_code !== code));
    linesHeading.current?.focus();
  };
  const periodLabel = formatPeriod(draft.period);
  const total = draftTotalMinor(draft, productByCode, maxQuantity);
  const issueError = issueDateError(draft, periodLabel);
  const dueError = dueDateError(draft);
  const invalidLine = draft.lines.find((line) => quantityError(line.quantity, maxQuantity));
  const empty = draft.lines.length === 0;
  const invalid = Boolean(invalidLine || issueError || dueError);
  const requestPreview = () => {
    setAttempted(true);
    if (empty || invalid) {
      (invalidLine ? quantityInputs.current[invalidLine.product_code] : issueError ? issueInput.current : dueError ? dueInput.current : linesHeading.current)?.focus();
      return;
    }
    setPreviewing(true);
    requestAnimationFrame(() => previewHeading.current?.focus());
  };
  if (previewing) {
    return <InvoicePreview draft={draft} partner={partner} productByCode={productByCode} maxQuantity={maxQuantity} total={total} headingRef={previewHeading} onIssue={() => onIssue(draft)} onLoadLatest={() => onLoadLatest(draft.reference)} onBack={() => {
      setPreviewing(false);
      requestAnimationFrame(() => previewOpener.current?.focus());
    }} />;
  }
  return <>
    <section className="sales-paper" aria-labelledby="sales-catalogue-heading">
      <h2 id="sales-catalogue-heading" tabIndex={-1} className="text-lg font-semibold">Fictional product catalogue</h2>
      <table className="sales-table mt-3" aria-label="Fictional product catalogue">
        <thead><tr><th scope="col">Product</th><th scope="col" className="hidden sm:table-cell">Unit</th><th scope="col" className="sales-amount hidden sm:table-cell">Fixed price</th><th scope="col"><span className="sr-only">Action</span></th></tr></thead>
        <tbody>{catalogue.map((product) => {
          const onDraft = draft.lines.some((line) => line.product_code === product.code);
          return <tr key={product.code}>
            <th scope="row"><span className="block font-semibold">{product.code}</span> <span className="block">{product.description}</span>
              <span className="block sm:hidden text-gray-600 mt-1">{product.unit} · {formatMinorNGN(product.price_minor)}</span></th>
            <td className="hidden sm:table-cell">{product.unit}</td>
            <td className="sales-amount hidden sm:table-cell">{formatMinorNGN(product.price_minor)}</td>
            <td className="text-right"><button type="button" className="sales-button" disabled={onDraft} aria-label={`Add ${product.code} to draft`} onClick={() => addLine(product.code)}>{onDraft ? 'On draft' : 'Add'}</button></td>
          </tr>;
        })}</tbody>
      </table>
    </section>
    <section className="sales-paper" aria-labelledby="sales-draft-heading">
      <h2 id="sales-draft-heading" ref={linesHeading} tabIndex={-1} className="text-lg font-semibold">Draft for {partnerLabel(partner)}</h2>
      <p className="text-xs text-gray-600 mt-1">{draft.reference} · {periodLabel}</p>
      <div className="sales-dates">
        <div className="flex flex-col gap-2"><label className="sales-field">Intended issue date<input ref={issueInput} type="date" min={`${lastDayOf(draft.period).slice(0, 8)}01`} max={lastDayOf(draft.period)} aria-invalid={Boolean(issueError)} aria-describedby={issueError ? 'sales-issue-error' : undefined} value={draft.issue_date} onChange={(event) => change({ ...draft, issue_date: event.target.value })} /></label>
          {issueError && <span id="sales-issue-error" className="sales-error">{issueError}</span>}</div>
        <div className="flex flex-col gap-2"><label className="sales-field">Due date (optional)<input ref={dueInput} type="date" aria-invalid={Boolean(dueError)} aria-describedby={dueError ? 'sales-due-error' : undefined} value={draft.due_date} onChange={(event) => change({ ...draft, due_date: event.target.value })} /></label>
          {dueError && <span id="sales-due-error" className="sales-error">{dueError}</span>}</div>
      </div>
      {empty ? <p className="text-sm text-gray-600 mt-4">No lines yet. Add a product from the catalogue.</p>
        : <ul aria-label="Draft lines" className="mt-2">{draft.lines.map((line) => {
          const product = productByCode(line.product_code);
          const lineTotal = lineTotalMinor(line, product, maxQuantity);
          const error = quantityError(line.quantity, maxQuantity);
          const errorId = `sales-quantity-error-${line.product_code}`;
          return <li key={line.product_code} className="sales-line">
            <div><span className="block font-semibold">{product.code}</span><span className="block">{product.description}</span><span className="block text-gray-600 mt-1">{formatMinorNGN(product.price_minor)} per {product.unit}</span></div>
            <p className="sales-line-total">{lineTotal === null ? 'Unavailable' : formatMinorNGN(lineTotal)}</p>
            <div className="sales-line-controls">
              <label className="sales-field">Quantity<input ref={(element) => { quantityInputs.current[line.product_code] = element; }} type="text" inputMode="numeric" autoComplete="off" maxLength={20} aria-label={`Quantity for ${product.code}`} aria-invalid={Boolean(error)} aria-describedby={error ? errorId : undefined} value={line.quantity}
                onChange={(event) => setLines((lines) => lines.map((current) => current.product_code === line.product_code ? { ...current, quantity: event.target.value.trim() } : current))} />
                {error && <span id={errorId} className="sales-error">{error}</span>}</label>
              <button type="button" className="sales-button self-end" aria-label={`Remove ${product.code} from draft`} onClick={() => removeLine(product.code)}>Remove</button>
            </div>
          </li>;
        })}</ul>}
      <div className="sales-total mt-4"><span>Draft total</span><span>{total === null ? 'Unavailable until quantities are corrected' : formatMinorNGN(total)}</span></div>
      {saved.state === 'saving' && <p role="status" className="text-xs text-gray-600 mt-2">Saving draft…</p>}
      {saved.state === 'saved' && <p role="status" className="text-xs text-gray-600 mt-2">Draft saved.</p>}
      {saved.state === 'failed' && <div role="alert" className="sales-alert">{saved.message}
        <div className="mt-2"><button type="button" className="sales-button" onClick={() => onRetrySave(draft)}>Try saving again</button></div></div>}
      {saved.state === 'refused' && <RefusedChange onLoadLatest={() => onLoadLatest(draft.reference)} />}
      {attempted && (empty || invalid) && <p role="alert" className="sales-alert">{empty && !invalid ? 'Add at least one product line before previewing.' : 'Correct the highlighted fields before previewing.'}</p>}
      <div className="sales-actions"><button ref={previewOpener} type="button" className="sales-button sales-primary" onClick={requestPreview}>Preview invoice</button>
        <p className="text-xs text-gray-600">Drafts do not create an invoice obligation or commission.</p></div>
    </section>
  </>;
}

function InvoicePreview({ draft, partner, productByCode, maxQuantity, total, headingRef, onIssue, onLoadLatest, onBack }) {
  const [issuing, setIssuing] = useState(false);
  const [failure, setFailure] = useState(null);
  const [refused, setRefused] = useState(false);
  const busy = useRef(false);
  // A repeated click finds the first still running. A failed issue changes nothing.
  const issue = async () => {
    if (busy.current) return;
    busy.current = true;
    setIssuing(true);
    setFailure(null);
    try {
      await onIssue();
    } catch (error) {
      if (isRefusal(error)) setRefused(true);
      else setFailure(failureMessage(error, 'This invoice could not be issued, so the draft is unchanged. Try again.'));
    } finally {
      busy.current = false;
      setIssuing(false);
    }
  };
  return <section className="sales-paper" aria-labelledby="sales-preview-heading">
    <p className="text-xs font-semibold tracking-widest uppercase text-amber-800">Fictional simulation</p>
    <h2 id="sales-preview-heading" ref={headingRef} tabIndex={-1} className="text-lg font-semibold mt-1">Simulated invoice preview</h2>
    <dl className="sales-facts">
      <div><dt>Seller</dt><dd>MTN</dd></div>
      <div><dt>Buyer</dt><dd>{partnerLabel(partner)}</dd></div>
      <div><dt>Simulation reference</dt><dd>{draft.reference}</dd></div>
      <div><dt>Intended issue date</dt><dd>{formatDate(draft.issue_date)}</dd></div>
      <div><dt>Due date</dt><dd>{draft.due_date ? formatDate(draft.due_date) : 'Not set'}</dd></div>
      <div><dt>Currency</dt><dd>NGN</dd></div>
    </dl>
    <table className="sales-table mt-5">
      <caption className="sr-only">Invoice lines for {draft.reference}</caption>
      <thead><tr><th scope="col">Product</th><th scope="col" className="sales-amount hidden sm:table-cell">Quantity</th><th scope="col" className="sales-amount hidden sm:table-cell">Unit price</th><th scope="col" className="sales-amount">Line total</th></tr></thead>
      <tbody>{draft.lines.map((line) => {
        const product = productByCode(line.product_code);
        return <tr key={line.product_code}>
          <th scope="row"><span className="block font-semibold">{product.code}</span> <span className="block">{product.description}</span>
            <span className="block sm:hidden text-gray-600 mt-1">{quantityLabel(Number(line.quantity), product.unit)} × {formatMinorNGN(product.price_minor)}</span></th>
          <td className="sales-amount hidden sm:table-cell">{quantityLabel(Number(line.quantity), product.unit)}</td>
          <td className="sales-amount hidden sm:table-cell">{formatMinorNGN(product.price_minor)}</td>
          <td className="sales-amount">{formatMinorNGN(lineTotalMinor(line, product, maxQuantity))}</td>
        </tr>;
      })}</tbody>
      <tfoot><tr><th scope="row">Total</th><td className="hidden sm:table-cell" /><td className="hidden sm:table-cell" /><td className="sales-amount">{formatMinorNGN(total)}</td></tr></tfoot>
    </table>
    <p className="sales-notice mt-5">Simplified fictional demonstration with fictional prices. Taxes and discounts are not modeled, and this is not an operational tax invoice. This preview does not create an invoice obligation or commission.</p>
    {failure && <p role="alert" className="sales-alert">{failure}</p>}
    {refused && <RefusedChange onLoadLatest={onLoadLatest} />}
    <div className="sales-actions"><button type="button" className="sales-button sales-primary" disabled={issuing} onClick={issue}>Issue simulated invoice</button>
      <button type="button" className="sales-button" onClick={onBack}>Back to draft</button>
      <p className="text-xs text-gray-600">Issuing fixes the buyer, lines and total and starts an unpaid purchase obligation. It never creates commission.</p></div>
  </section>;
}
