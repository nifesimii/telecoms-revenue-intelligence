// A partner's one draft order: the catalogue beside the draft, then a preview before
// it goes to MTN Finance. Edits live with the parent, so changing tab loses nothing.

import { useEffect, useRef, useState } from 'react';
import { useQueryClient } from '@tanstack/react-query';
import { createOwnOrderDraft, deleteOwnOrderDraft, saveOwnOrderDraft, submitOwnOrderDraft } from '../../api/client.js';
import { formatCount, formatMinorNGN } from '../../lib/format.js';
import OrderLines from './OrderLines.jsx';
import { partnerLabel, quantityLabel } from './salesDisplay.js';
import { Figures } from './SalesParts.jsx';
import { ActionFailure, useActionFailure } from './SalesReads.jsx';
import { salesKeys, useOwnOrderDraft } from './useSalesQueries.js';

const ORDER_NOTE = 'Submitting sends this order to MTN Finance for review. A submitted order cannot be changed or withdrawn.';
const UNIT_GROUP = { device: 'Devices', card: 'Physical recharge cards' };
const sameLines = (left, right) => JSON.stringify(left) === JSON.stringify(right);

// `work` is the unsaved draft, kept above this component because the Order tab
// unmounts. It holds the server copy too, whose token the next change must send.
export default function DraftOrder({ account, pricing, maxQuantity, work, onWorkChange }) {
  const queryClient = useQueryClient();
  const draftQuery = useOwnOrderDraft();
  const draft = draftQuery.data?.draft;
  // Remounts the editor, so loading the latest draft discards what was typed.
  const [editorKey, setEditorKey] = useState(0);
  const [submitted, setSubmitted] = useState(null);
  const [deleted, setDeleted] = useState(false);
  const [creating, setCreating] = useState(false);
  const [createFailed, setCreateFailed] = useState(false);
  // Where focus goes once the next draft state has rendered. The cache can update a
  // render after local state, so the request waits until its target exists.
  const focusNext = useRef(null);
  useEffect(() => {
    const target = focusNext.current && document.getElementById(focusNext.current);
    if (!target) return;
    target.focus();
    focusNext.current = null;
  });
  const setDraft = (next) => queryClient.setQueryData(salesKeys.ownDraft(), { draft: next });
  const create = async () => {
    setCreating(true);
    setCreateFailed(false);
    setSubmitted(null);
    setDeleted(false);
    try {
      const created = await createOwnOrderDraft();
      onWorkChange(null);
      focusNext.current = 'sales-catalogue-heading';
      setDraft(created);
    } catch {
      setCreateFailed(true);
    } finally {
      setCreating(false);
    }
  };
  const loadLatest = async () => {
    await queryClient.resetQueries({ queryKey: salesKeys.ownDraft() });
    onWorkChange(null);
    setEditorKey((current) => current + 1);
    // The draft may no longer exist, so its heading cannot take focus. A failed read
    // shows its own retry, and focus stays where it is.
    const latest = queryClient.getQueryData(salesKeys.ownDraft());
    focusNext.current = latest && (latest.draft ? 'sales-draft-heading' : 'sales-no-draft');
  };
  const onSubmitted = (order) => {
    onWorkChange(null);
    setDraft(null);
    queryClient.invalidateQueries({ queryKey: salesKeys.allOwnOrders() });
    setSubmitted(order);
    focusNext.current = 'sales-submitted-notice';
  };
  const onDeleted = () => {
    onWorkChange(null);
    setDraft(null);
    setDeleted(true);
    focusNext.current = 'sales-no-draft';
  };

  if (draftQuery.isError) {
    return <section className="overview-surface sales-card-pad" aria-label="Draft order unavailable">
      <p role="alert" className="sales-alert">Your draft order could not be loaded.</p>
      <button type="button" className="overview-button mt-3" onClick={() => draftQuery.refetch()}>Try again</button>
    </section>;
  }
  if (!draftQuery.data) return <p role="status" className="overview-surface sales-card-pad sales-muted">Loading your draft order…</p>;
  if (!draft) {
    return <div className="sales-stack">
      {submitted && <p id="sales-submitted-notice" role="status" tabIndex={-1} className="overview-notice">Order {submitted.reference} for {formatMinorNGN(submitted.total_minor)} was submitted to MTN Finance for review. It can no longer be changed or withdrawn.</p>}
      <div className="sales-detail">
        <Catalogue pricing={pricing} headingId="sales-catalogue-preview-heading" />
        <section className="overview-surface sales-rail sales-draft" aria-label="No draft order">
          <h2 className="sales-h">Your draft</h2>
          <p id="sales-no-draft" tabIndex={-1} className="sales-muted">{deleted ? 'Draft deleted. Nothing was sent to MTN Finance.' : 'You have no draft order.'}</p>
          {createFailed && <p role="alert" className="sales-alert">The draft could not be started. Try again.</p>}
          <button type="button" className="overview-button overview-primary sales-full" disabled={creating} onClick={create}>Start a draft order</button>
          <p className="sales-note">Private until you submit. MTN Finance sees an order only once you submit it.</p>
        </section>
      </div>
    </div>;
  }
  return <DraftOrderEditor key={editorKey} draft={draft} account={account} pricing={pricing} maxQuantity={maxQuantity} work={work} onWorkChange={onWorkChange} onSaved={setDraft} onSubmitted={onSubmitted} onDeleted={onDeleted} onLoadLatest={loadLatest} />;
}

// Grouped by unit, with prices fixed by the server. Without onAdd it is read-only.
function Catalogue({ pricing, headingId, lines = [], onAdd }) {
  const units = [...new Set(pricing.catalogue.map((product) => product.unit))];
  return <section className="overview-surface" aria-labelledby={headingId}>
    <div className="sales-sec sales-catalogue-head"><div>
      <h2 id={headingId} tabIndex={-1} aria-label="Fictional product catalogue" className="sales-h">Products</h2>
      <p className="sales-muted">Fixed prices from MTN.</p>
    </div></div>
    <table className="sales-table" aria-label="Fictional product catalogue">
      <thead className="max-sm:hidden"><tr><th scope="col">Product</th><th scope="col" className="sales-num hidden sm:table-cell">Fixed price</th>{onAdd && <th scope="col"><span className="sr-only">Action</span></th>}</tr></thead>
      {units.map((unit) => <tbody key={unit}>
        <tr className="sales-group"><th colSpan={3} scope="colgroup">{UNIT_GROUP[unit] ?? unit}</th></tr>
        {pricing.catalogue.filter((product) => product.unit === unit).map((product) => {
          const onDraft = lines.some((line) => line.product_code === product.code);
          return <tr key={product.code}>
            <th scope="row"><span className="block sales-strong">{product.code}</span><span className="sales-sub sales-product-note">{product.description}</span>
              <span className="block sm:hidden sales-muted mt-1">{formatMinorNGN(product.price_minor)} per {product.unit}</span></th>
            <td className="sales-num hidden sm:table-cell">{formatMinorNGN(product.price_minor)}<span className="sales-sub">per {product.unit}</span></td>
            {onAdd && <td className="sales-row-actions"><button type="button" className={`overview-button ${onDraft ? 'sales-done' : ''}`} disabled={onDraft} aria-label={`Add ${product.code} to draft order`} onClick={() => onAdd(product.code)}>{onDraft ? 'On draft' : 'Add'}</button></td>}
          </tr>;
        })}
      </tbody>)}
    </table>
  </section>;
}

function DraftLine({ line, pricing, maxQuantity, inputRef, onQuantityChange, onRemove }) {
  const product = pricing.productByCode(line.product_code);
  const lineTotal = pricing.lineTotalMinor(line);
  const error = pricing.quantityError(line.quantity);
  const errorId = `sales-quantity-error-${line.product_code}`;
  const quantity = Number(line.quantity);
  const step = (by) => onQuantityChange(String(quantity + by));
  return <li className="sales-draft-line">
    <div className="min-w-0"><span className="block sales-strong text-sm">{product.code}</span><span className="sales-sub">{formatMinorNGN(product.price_minor)} per {product.unit}</span></div>
    <p className="text-sm font-semibold whitespace-nowrap">{lineTotal === null ? 'Unavailable' : formatMinorNGN(lineTotal)}</p>
    <div className="col-span-2 flex items-center justify-between gap-2">
      <div className="sales-stepper">
        <button type="button" aria-label={`Decrease ${product.code} by one`} disabled={Boolean(error) || quantity <= 1} onClick={() => step(-1)}>−</button>
        <input ref={inputRef} type="text" inputMode="numeric" autoComplete="off" maxLength={20} aria-label={`Quantity for ${product.code}`} aria-invalid={Boolean(error)} aria-describedby={error ? errorId : undefined} value={line.quantity} onChange={(event) => onQuantityChange(event.target.value.trim())} />
        <button type="button" aria-label={`Increase ${product.code} by one`} disabled={Boolean(error) || quantity >= maxQuantity} onClick={() => step(1)}>+</button>
      </div>
      <button type="button" className="overview-button sales-quiet" aria-label={`Remove ${product.code} from draft order`} onClick={onRemove}>Remove</button>
    </div>
    {error && <span id={errorId} className="sales-error col-span-2">{error}</span>}
  </li>;
}

function DraftOrderEditor({ draft, account, pricing, maxQuantity, work, onWorkChange, onSaved, onSubmitted, onDeleted, onLoadLatest }) {
  const [initial] = useState(() => work ?? { lines: draft.lines, saved: draft });
  const { lines, saved } = work ?? initial;
  const [saving, setSaving] = useState(false);
  const [savedNotice, setSavedNotice] = useState(false);
  const [previewing, setPreviewing] = useState(false);
  const [attempted, setAttempted] = useState(false);
  const [confirmingDelete, setConfirmingDelete] = useState(false);
  const { failure, clearFailure, noteFailure } = useActionFailure();
  const quantityInputs = useRef({});
  const linesHeading = useRef(null);
  const dirty = !sameLines(lines, saved.lines);
  const empty = lines.length === 0;
  const invalidLine = lines.find((line) => pricing.quantityError(line.quantity));
  const total = pricing.draftTotalMinor({ lines });
  const totalLabel = total === null ? 'Unavailable until quantities are corrected' : formatMinorNGN(total);

  const edit = (next) => {
    onWorkChange((current) => ({ saved: (current ?? initial).saved, lines: next }));
    setSavedNotice(false);
    if (!failure.refused) clearFailure();
  };
  const addLine = (code) => {
    edit([...lines, { product_code: code, quantity: '1' }]);
    requestAnimationFrame(() => quantityInputs.current[code]?.focus());
  };
  const removeLine = (code) => {
    edit(lines.filter((line) => line.product_code !== code));
    linesHeading.current?.focus();
  };
  // Answers with the server's copy, or null when it was refused or failed. Previewing
  // saves even unchanged lines, so a copy changed in another tab is refused here
  // rather than previewed.
  const save = async ({ unchanged = false } = {}) => {
    if (!dirty && !unchanged) return saved;
    setSaving(true);
    clearFailure();
    try {
      const next = await saveOwnOrderDraft({ token: saved.token, lines });
      onWorkChange((current) => ({ lines: (current ?? initial).lines, saved: next }));
      onSaved(next);
      return next;
    } catch (error) {
      noteFailure(error, 'Your draft could not be saved, so your changes are only on this page. Try again.');
      return null;
    } finally {
      setSaving(false);
    }
  };
  const saveDraft = async () => {
    if (await save()) setSavedNotice(true);
  };
  const preview = async () => {
    setAttempted(true);
    if (empty || invalidLine) {
      (invalidLine ? quantityInputs.current[invalidLine.product_code] : linesHeading.current)?.focus();
      return;
    }
    if (!(await save({ unchanged: true }))) return;
    setPreviewing(true);
    requestAnimationFrame(() => document.getElementById('sales-order-preview-heading')?.focus());
  };
  const remove = async () => {
    clearFailure();
    try {
      await deleteOwnOrderDraft(saved.token);
      onDeleted();
    } catch (error) {
      noteFailure(error, 'Your draft could not be deleted, so it is unchanged. Try again.');
    }
  };

  if (previewing) {
    return <OrderPreview draft={saved} account={account} pricing={pricing} onSubmitted={onSubmitted} onLoadLatest={onLoadLatest} onBack={() => {
      setPreviewing(false);
      requestAnimationFrame(() => document.getElementById('sales-order-preview')?.focus());
    }} />;
  }
  return <>
    <div className="sales-detail">
      <Catalogue pricing={pricing} headingId="sales-catalogue-heading" lines={lines} onAdd={addLine} />
      <section className="overview-surface sales-rail sales-draft" aria-labelledby="sales-draft-heading">
        <h2 id="sales-draft-heading" ref={linesHeading} tabIndex={-1} aria-label="Your draft order" className="sales-h">Your draft</h2>
        {empty ? <p className="sales-muted">No lines yet. Add a product from the catalogue.</p>
          : <ul aria-label="Draft order lines">{lines.map((line) => <DraftLine key={line.product_code} line={line} pricing={pricing} maxQuantity={maxQuantity}
            inputRef={(element) => { quantityInputs.current[line.product_code] = element; }}
            onQuantityChange={(quantity) => edit(lines.map((current) => (current.product_code === line.product_code ? { ...current, quantity } : current)))}
            onRemove={() => removeLine(line.product_code)} />)}</ul>}
        <div className="sales-draft-total"><span>Order total</span><span>{totalLabel}</span></div>
        {saving && <p role="status" className="sales-note">Saving draft…</p>}
        {!saving && dirty && <p className="sales-note">Unsaved changes.</p>}
        {savedNotice && !dirty && <p role="status" className="sales-note">Draft saved. Nothing has been sent to MTN Finance.</p>}
        <ActionFailure failure={failure} onLoadLatest={onLoadLatest} />
        {attempted && (empty || invalidLine) && <p role="alert" className="sales-alert">{invalidLine ? 'Correct the highlighted quantities before previewing.' : 'Add at least one product before previewing.'}</p>}
        <button id="sales-order-preview" type="button" className="overview-button overview-primary sales-full" disabled={saving || failure.refused} onClick={preview}>Preview order</button>
        <div className="flex gap-2">
          <button type="button" className="overview-button flex-1" disabled={saving || !dirty || failure.refused} onClick={saveDraft}>Save draft</button>
          {!confirmingDelete && <button id="sales-order-delete" type="button" className="overview-button flex-1" disabled={saving || failure.refused} onClick={() => {
            setConfirmingDelete(true);
            requestAnimationFrame(() => document.getElementById('sales-order-delete-keep')?.focus());
          }}>Delete draft</button>}
        </div>
        <p className="sales-note">Private until you submit. MTN Finance sees an order only once you submit it.</p>
        {confirmingDelete && <div role="group" aria-label="Confirm draft deletion" className="flex flex-col gap-3 border-t border-gray-200 pt-3">
          <p className="text-sm">Delete this draft order? Its lines are discarded. Nothing has been sent to MTN Finance.</p>
          <div className="sales-actions">
            <button type="button" className="overview-button sales-danger" onClick={remove}>Delete draft order</button>
            <button id="sales-order-delete-keep" type="button" className="overview-button" onClick={() => {
              setConfirmingDelete(false);
              requestAnimationFrame(() => document.getElementById('sales-order-delete')?.focus());
            }}>Keep draft</button>
          </div>
        </div>}
      </section>
    </div>
    {!empty && <div className="sales-draft-bar">
      <div className="min-w-0 text-sm"><span className="block text-xs">{quantityLabel(lines.length, 'item')}</span><span className="font-semibold">{total === null ? 'Unavailable' : formatMinorNGN(total)}</span></div>
      <button type="button" className="overview-button overview-primary shrink-0" onClick={() => linesHeading.current?.focus()}>View draft</button>
    </div>}
  </>;
}

// Shows the saved copy, and submits exactly that copy's token.
function OrderPreview({ draft, account, pricing, onSubmitted, onLoadLatest, onBack }) {
  const [submitting, setSubmitting] = useState(false);
  const { failure, clearFailure, noteFailure } = useActionFailure();
  // Kept until the server accepts it, so a repeated click or a retry after a lost
  // response submits one order.
  const action = useRef(null);
  const busy = useRef(false);
  const lines = draft.lines.map((line) => {
    const product = pricing.productByCode(line.product_code);
    return { product_code: product.code, description: product.description, unit: product.unit, unit_price_minor: product.price_minor, quantity: Number(line.quantity), line_total_minor: pricing.lineTotalMinor(line) };
  });
  const submit = async () => {
    if (busy.current) return;
    busy.current = true;
    action.current ??= crypto.randomUUID();
    setSubmitting(true);
    clearFailure();
    try {
      onSubmitted(await submitOwnOrderDraft({ token: draft.token, action_id: action.current }));
    } catch (error) {
      noteFailure(error, 'Your order could not be submitted, so your draft is unchanged. Try again.');
      busy.current = false;
      setSubmitting(false);
    }
  };
  const totalMinor = pricing.draftTotalMinor(draft);
  return <section className="flex flex-col gap-6" aria-labelledby="sales-order-preview-heading">
    <div>
      <p className="sales-eyebrow">Fictional simulation</p>
      <h2 id="sales-order-preview-heading" tabIndex={-1} className="sales-title">Order preview</h2>
    </div>
    <div className="sales-detail">
      <div className="sales-stack">
        <div className="overview-surface sales-card-pad">
          <p>Order total</p>
          <p className="sales-big overview-headline">{formatMinorNGN(totalMinor)}</p>
          <Figures items={[['Seller', 'MTN'], ['Buyer', partnerLabel(account)], ['Currency', 'NGN'], ['Lines', formatCount(lines.length)]]} />
        </div>
        <OrderLines caption="Lines in this order" lines={lines} totalMinor={totalMinor} />
      </div>
      <div className="overview-surface sales-rail">
        <h2 className="sales-h">Submit</h2>
        <ActionFailure failure={failure} onLoadLatest={onLoadLatest} />
        <button type="button" className="overview-button overview-primary sales-full" disabled={submitting || failure.refused} onClick={submit}>Submit order</button>
        <button type="button" className="overview-button sales-full" disabled={submitting} onClick={onBack}>Back to draft</button>
        <p className="sales-note">{ORDER_NOTE} MTN Finance sets the invoice dates if it issues the order. Taxes and discounts are not modeled.</p>
      </div>
    </div>
  </section>;
}
