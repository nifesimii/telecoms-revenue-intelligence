import { useRef, useState } from 'react';
import { usePeriod } from '../../context/PeriodContext.jsx';
import { formatCount, formatDate, formatMinorNGN, formatPeriod } from '../../lib/format.js';
import { CATALOGUE, PARTNERS, defaultIssueDate, draftKey, draftTotalMinor, dueDateError, issueDateError, lineTotalMinor, productByCode, quantityError, referenceFor } from './salesSimulation.js';
import useSalesSimulation from './useSalesSimulation.js';
import './sales.css';

const partnerLabel = (partner) => `${partner.name} · Account ${partner.code}`;
const quantityLabel = (line, product) => `${formatCount(Number(line.quantity))} ${product.unit}${Number(line.quantity) === 1 ? '' : 's'}`;

export default function PartnerSalesWorkspace() {
  const { periods, period, loading, error } = usePeriod();
  // A month seeded from the URL only counts once /periods confirms it.
  if (loading || !periods.includes(period)) return <p role="status" className="p-6">{loading ? 'Loading reporting periods…' : error ? 'Reporting periods unavailable. Reload to retry.' : 'No reporting periods available.'}</p>;
  return <Workspace period={period} />;
}

function Workspace({ period }) {
  const { simulation, setSimulation, saveFailed, incompatible, startOver, retrySave } = useSalesSimulation();
  const [search, setSearch] = useState('');
  const term = search.trim().toLowerCase();
  const matches = PARTNERS.filter((partner) => partner.code.includes(term) || partner.name.toLowerCase().includes(term));
  const partner = PARTNERS.find((candidate) => candidate.code === simulation.partnerCode);
  const key = partner ? draftKey(partner.code, period) : null;
  const draft = key ? simulation.drafts[key] : null;
  const updateDraft = (change) => setSimulation((current) => ({ ...current, drafts: { ...current.drafts, [key]: change(current.drafts[key]) } }));
  const createDraft = () => {
    setSimulation((current) => ({
      ...current,
      nextSequence: current.nextSequence + 1,
      drafts: { ...current.drafts, [key]: { reference: referenceFor(current.nextSequence), partnerCode: partner.code, period, issueDate: defaultIssueDate(period), dueDate: '', lines: [] } },
    }));
    requestAnimationFrame(() => document.getElementById('sales-catalogue-heading')?.focus());
  };
  return <main className="sales-workspace h-full overflow-y-auto bg-gray-50" aria-label="Partner Sales">
    <div className="mx-auto max-w-7xl p-4 sm:p-6 lg:p-8 flex flex-col gap-6">
      <header><p className="text-xs font-semibold tracking-widest uppercase text-gray-500">MTN sales to trade partners</p>
        <h1 className="text-2xl font-semibold tracking-tight mt-1">Partner Sales</h1>
        <p className="text-sm text-gray-600 mt-2">Draft and preview what MTN would invoice a trade partner in {formatPeriod(period)}.</p>
        <p className="sales-notice mt-3">Fictional simulation using sample partner identities and fictional products and prices. Drafts stay in this browser tab, separate from recorded commission, payment and inventory evidence, including when the application reads live data.</p></header>
      {incompatible ? <section className="sales-paper" aria-label="Saved simulation unavailable">
        <p role="alert" className="text-sm">The saved simulation in this tab could not be restored.</p>
        <button type="button" className="sales-button mt-3" onClick={startOver}>Start a new simulation</button>
      </section> : <>
        {saveFailed && <div role="alert" className="sales-alert !mt-0">Session storage is unavailable, so this simulation could not be saved. It will be lost if this tab refreshes or closes.
          <div className="mt-2"><button type="button" className="sales-button" onClick={retrySave}>Try saving again</button></div></div>}
        <section className="sales-paper" aria-labelledby="sales-partner-heading">
          <h2 id="sales-partner-heading" className="text-lg font-semibold">Trade partner</h2>
          <label className="sales-field mt-4">Find a partner
            <input type="search" value={search} maxLength={200} placeholder="Name or account code" onChange={(event) => setSearch(event.target.value)} /></label>
          {matches.length ? <fieldset className="mt-4"><legend className="sr-only">Partner account</legend>
            <div className="grid gap-2 sm:grid-cols-2 lg:grid-cols-3">{matches.map((candidate) => <label key={candidate.code} className="sales-partner">
              <input type="radio" name="sales-partner" checked={simulation.partnerCode === candidate.code} onChange={() => setSimulation((current) => ({ ...current, partnerCode: candidate.code }))} />
              <span>{partnerLabel(candidate)}</span>
            </label>)}</div>
          </fieldset> : <p role="status" className="text-sm text-gray-600 mt-4">No partners match your search. Try another name or account code.</p>}
        </section>
        {!partner ? <p className="sales-paper text-sm text-gray-600">Select a trade partner to create a draft.</p>
          : !draft ? <section className="sales-paper" aria-label="No draft">
            <p className="text-sm text-gray-600">No draft for {partnerLabel(partner)} in {formatPeriod(period)}.</p>
            <button type="button" className="sales-button sales-primary mt-3" onClick={createDraft}>Create draft</button>
          </section>
          : <DraftEditor key={key} draft={draft} partner={partner} onChange={updateDraft} />}
      </>}
    </div>
  </main>;
}

function DraftEditor({ draft, partner, onChange }) {
  const [previewing, setPreviewing] = useState(false);
  const [attempted, setAttempted] = useState(false);
  const previewOpener = useRef(null);
  const previewHeading = useRef(null);
  const linesHeading = useRef(null);
  const issueInput = useRef(null);
  const dueInput = useRef(null);
  const quantityInputs = useRef({});
  const setLines = (change) => onChange((current) => ({ ...current, lines: change(current.lines) }));
  const addLine = (code) => {
    setLines((lines) => [...lines, { productCode: code, quantity: '1' }]);
    requestAnimationFrame(() => quantityInputs.current[code]?.focus());
  };
  const removeLine = (code) => {
    setLines((lines) => lines.filter((line) => line.productCode !== code));
    linesHeading.current?.focus();
  };
  const periodLabel = formatPeriod(draft.period);
  const total = draftTotalMinor(draft);
  const issueError = issueDateError(draft, periodLabel);
  const dueError = dueDateError(draft);
  const invalidLine = draft.lines.find((line) => quantityError(line.quantity));
  const empty = draft.lines.length === 0;
  const invalid = Boolean(invalidLine || issueError || dueError);
  const requestPreview = () => {
    setAttempted(true);
    if (empty || invalid) {
      (invalidLine ? quantityInputs.current[invalidLine.productCode] : issueError ? issueInput.current : dueError ? dueInput.current : linesHeading.current)?.focus();
      return;
    }
    setPreviewing(true);
    requestAnimationFrame(() => previewHeading.current?.focus());
  };
  if (previewing) {
    return <InvoicePreview draft={draft} partner={partner} total={total} headingRef={previewHeading} onBack={() => {
      setPreviewing(false);
      requestAnimationFrame(() => previewOpener.current?.focus());
    }} />;
  }
  return <>
    <section className="sales-paper" aria-labelledby="sales-catalogue-heading">
      <h2 id="sales-catalogue-heading" tabIndex={-1} className="text-lg font-semibold">Fictional product catalogue</h2>
      <table className="sales-table mt-3" aria-label="Fictional product catalogue">
        <thead><tr><th scope="col">Product</th><th scope="col" className="hidden sm:table-cell">Unit</th><th scope="col" className="sales-amount hidden sm:table-cell">Fixed price</th><th scope="col"><span className="sr-only">Action</span></th></tr></thead>
        <tbody>{CATALOGUE.map((product) => {
          const onDraft = draft.lines.some((line) => line.productCode === product.code);
          return <tr key={product.code}>
            <th scope="row"><span className="block font-semibold">{product.code}</span> <span className="block">{product.description}</span>
              <span className="block sm:hidden text-gray-600 mt-1">{product.unit} · {formatMinorNGN(product.priceMinor)}</span></th>
            <td className="hidden sm:table-cell">{product.unit}</td>
            <td className="sales-amount hidden sm:table-cell">{formatMinorNGN(product.priceMinor)}</td>
            <td className="text-right"><button type="button" className="sales-button" disabled={onDraft} aria-label={`Add ${product.code} to draft`} onClick={() => addLine(product.code)}>{onDraft ? 'On draft' : 'Add'}</button></td>
          </tr>;
        })}</tbody>
      </table>
    </section>
    <section className="sales-paper" aria-labelledby="sales-draft-heading">
      <h2 id="sales-draft-heading" ref={linesHeading} tabIndex={-1} className="text-lg font-semibold">Draft for {partnerLabel(partner)}</h2>
      <p className="text-xs text-gray-600 mt-1">{draft.reference} · {periodLabel}</p>
      <div className="sales-dates">
        <div className="flex flex-col gap-2"><label className="sales-field">Intended issue date<input ref={issueInput} type="date" min={`${defaultIssueDate(draft.period).slice(0, 8)}01`} max={defaultIssueDate(draft.period)} aria-invalid={Boolean(issueError)} aria-describedby={issueError ? 'sales-issue-error' : undefined} value={draft.issueDate} onChange={(event) => onChange((current) => ({ ...current, issueDate: event.target.value }))} /></label>
          {issueError && <span id="sales-issue-error" className="sales-error">{issueError}</span>}</div>
        <div className="flex flex-col gap-2"><label className="sales-field">Due date (optional)<input ref={dueInput} type="date" aria-invalid={Boolean(dueError)} aria-describedby={dueError ? 'sales-due-error' : undefined} value={draft.dueDate} onChange={(event) => onChange((current) => ({ ...current, dueDate: event.target.value }))} /></label>
          {dueError && <span id="sales-due-error" className="sales-error">{dueError}</span>}</div>
      </div>
      {empty ? <p className="text-sm text-gray-600 mt-4">No lines yet. Add a product from the catalogue.</p>
        : <ul aria-label="Draft lines" className="mt-2">{draft.lines.map((line) => {
          const product = productByCode(line.productCode);
          const lineTotal = lineTotalMinor(line);
          const error = quantityError(line.quantity);
          const errorId = `sales-quantity-error-${line.productCode}`;
          return <li key={line.productCode} className="sales-line">
            <div><span className="block font-semibold">{product.code}</span><span className="block">{product.description}</span><span className="block text-gray-600 mt-1">{formatMinorNGN(product.priceMinor)} per {product.unit}</span></div>
            <p className="sales-line-total">{lineTotal === null ? 'Unavailable' : formatMinorNGN(lineTotal)}</p>
            <div className="sales-line-controls">
              <label className="sales-field">Quantity<input ref={(element) => { quantityInputs.current[line.productCode] = element; }} type="text" inputMode="numeric" autoComplete="off" aria-label={`Quantity for ${product.code}`} aria-invalid={Boolean(error)} aria-describedby={error ? errorId : undefined} value={line.quantity}
                onChange={(event) => setLines((lines) => lines.map((current) => current.productCode === line.productCode ? { ...current, quantity: event.target.value.trim() } : current))} />
                {error && <span id={errorId} className="sales-error">{error}</span>}</label>
              <button type="button" className="sales-button self-end" aria-label={`Remove ${product.code} from draft`} onClick={() => removeLine(product.code)}>Remove</button>
            </div>
          </li>;
        })}</ul>}
      <div className="sales-total mt-4"><span>Draft total</span><span>{total === null ? 'Unavailable until quantities are corrected' : formatMinorNGN(total)}</span></div>
      {attempted && (empty || invalid) && <p role="alert" className="sales-alert">{empty && !invalid ? 'Add at least one product line before previewing.' : 'Correct the highlighted fields before previewing.'}</p>}
      <div className="sales-actions"><button ref={previewOpener} type="button" className="sales-button sales-primary" onClick={requestPreview}>Preview invoice</button>
        <p className="text-xs text-gray-600">Drafts do not create an invoice obligation or commission.</p></div>
    </section>
  </>;
}

function InvoicePreview({ draft, partner, total, headingRef, onBack }) {
  return <section className="sales-paper" aria-labelledby="sales-preview-heading">
    <p className="text-xs font-semibold tracking-widest uppercase text-amber-800">Fictional simulation</p>
    <h2 id="sales-preview-heading" ref={headingRef} tabIndex={-1} className="text-lg font-semibold mt-1">Simulated invoice preview</h2>
    <dl className="sales-facts">
      <div><dt>Seller</dt><dd>MTN</dd></div>
      <div><dt>Buyer</dt><dd>{partnerLabel(partner)}</dd></div>
      <div><dt>Simulation reference</dt><dd>{draft.reference}</dd></div>
      <div><dt>Intended issue date</dt><dd>{formatDate(draft.issueDate)}</dd></div>
      <div><dt>Due date</dt><dd>{draft.dueDate ? formatDate(draft.dueDate) : 'Not set'}</dd></div>
      <div><dt>Currency</dt><dd>NGN</dd></div>
    </dl>
    <table className="sales-table mt-5">
      <caption className="sr-only">Invoice lines for {draft.reference}</caption>
      <thead><tr><th scope="col">Product</th><th scope="col" className="sales-amount hidden sm:table-cell">Quantity</th><th scope="col" className="sales-amount hidden sm:table-cell">Unit price</th><th scope="col" className="sales-amount">Line total</th></tr></thead>
      <tbody>{draft.lines.map((line) => {
        const product = productByCode(line.productCode);
        return <tr key={line.productCode}>
          <th scope="row"><span className="block font-semibold">{product.code}</span> <span className="block">{product.description}</span>
            <span className="block sm:hidden text-gray-600 mt-1">{quantityLabel(line, product)} × {formatMinorNGN(product.priceMinor)}</span></th>
          <td className="sales-amount hidden sm:table-cell">{quantityLabel(line, product)}</td>
          <td className="sales-amount hidden sm:table-cell">{formatMinorNGN(product.priceMinor)}</td>
          <td className="sales-amount">{formatMinorNGN(lineTotalMinor(line))}</td>
        </tr>;
      })}</tbody>
      <tfoot><tr><th scope="row">Total</th><td className="hidden sm:table-cell" /><td className="hidden sm:table-cell" /><td className="sales-amount">{formatMinorNGN(total)}</td></tr></tfoot>
    </table>
    <p className="sales-notice mt-5">Simplified fictional demonstration with fictional prices. Taxes and discounts are not modeled, and this is not an operational tax invoice. This preview does not create an invoice obligation or commission.</p>
    <div className="sales-actions"><button type="button" className="sales-button" onClick={onBack}>Back to draft</button></div>
  </section>;
}
