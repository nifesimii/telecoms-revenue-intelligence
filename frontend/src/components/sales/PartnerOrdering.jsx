// A partner's own ordering: one draft order built from the fictional catalogue, then
// submitted to MTN Finance as a read-only order, the invoices Finance issued, and the
// partner's own commission account. The server takes the account from the session, so
// nothing here names or chooses one.

import { useEffect, useRef, useState } from 'react';
import { useQuery, useQueryClient } from '@tanstack/react-query';
import { createOwnOrderDraft, deleteOwnOrderDraft, saveOwnOrderDraft, submitOwnOrderDraft } from '../../api/client.js';
import { formatDate, formatMinorNGN } from '../../lib/format.js';
import { draftPricing } from './draftPricing.js';
import { ActionFailure, InvoiceDetail, ReadState, useActionFailure, usePagedQuery } from './InvoiceViews.jsx';
import OrderLines from './OrderLines.jsx';
import PartnerCommission from './PartnerCommission.jsx';
import PartnerInvoices from './PartnerInvoices.jsx';
import { partnerLabel } from './salesDisplay.js';
import { ownInvoiceQuery, ownOrdersQuery, salesKeys, useOwnOrder, useOwnOrderDraft, useOwnOrderingReference } from './useSalesQueries.js';
import './sales.css';

const ORDER_NOTE = 'Submitting sends this order to MTN Finance for review. A submitted order cannot be changed or withdrawn.';
const sameLines = (left, right) => JSON.stringify(left) === JSON.stringify(right);

export default function PartnerOrdering() {
  const reference = useOwnOrderingReference();
  if (reference.data) return <Ordering reference={reference.data} />;
  if (!reference.isError) return <p role="status" className="mt-4 text-sm text-gray-600">Loading Partner Sales…</p>;
  return <div role="alert" className="sales-alert">Partner Sales could not be loaded.
    <div className="mt-2"><button type="button" className="sales-button" onClick={() => reference.refetch()}>Try again</button></div></div>;
}

// Where focus returns when the opener has gone, such as after a refresh changed the list.
const LIST_HEADING = { order: 'sales-orders-heading', invoice: 'sales-own-invoices-heading' };
const detailHeadingId = ({ type, reference }) => `sales-${type}-heading-${reference}`;

function Ordering({ reference: { account, catalogue, max_quantity: maxQuantity, invoice_statuses: invoiceStatuses, statement_periods: statementPeriods } }) {
  const pricing = draftPricing(catalogue, maxQuantity);
  // An open order or invoice hides the rest, which stays mounted so returning finds its page.
  const [open, setOpen] = useState(null);
  const openDetail = (type) => (reference, openerId) => {
    const next = { type, reference, openerId };
    setOpen(next);
    requestAnimationFrame(() => document.getElementById(detailHeadingId(next))?.focus());
  };
  const closeDetail = () => {
    const { type, openerId } = open;
    setOpen(null);
    requestAnimationFrame(() => (document.getElementById(openerId) ?? document.getElementById(LIST_HEADING[type]))?.focus());
  };
  return <div className="sales-workspace mt-2 flex flex-col gap-6">
    <div>
      <p className="text-sm text-gray-700">Order fictional FBB devices and physical recharge cards from MTN for {partnerLabel(account)}.</p>
      <p className="sales-notice mt-3">Fictional simulation using sample partner identities and fictional products and prices. Your draft is private to you until you submit it. Nothing here is an actual order, invoice or commission.</p>
    </div>
    {open?.type === 'order' && <OrderDetail reference={open.reference} onBack={closeDetail} />}
    {open?.type === 'invoice' && <InvoiceDetail reference={open.reference} headingId={detailHeadingId(open)} backLabel="Back to your invoices" onBack={closeDetail}
      queryFor={ownInvoiceQuery} useRead={useQuery} />}
    <div className={open ? 'hidden' : 'flex flex-col gap-6'}>
      <DraftOrder account={account} pricing={pricing} />
      <OrderList onOpen={openDetail('order')} />
      <PartnerInvoices statuses={invoiceStatuses} onOpen={openDetail('invoice')} />
      <PartnerCommission partner={account} periods={statementPeriods} />
    </div>
  </div>;
}

function DraftOrder({ account, pricing }) {
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
      focusNext.current = 'sales-catalogue-heading';
      setDraft(await createOwnOrderDraft());
    } catch {
      focusNext.current = null;
      setCreateFailed(true);
    } finally {
      setCreating(false);
    }
  };
  const loadLatest = async () => {
    await queryClient.resetQueries({ queryKey: salesKeys.ownDraft() });
    setEditorKey((current) => current + 1);
    // The draft may no longer exist, so its heading cannot take focus. A failed read
    // shows its own retry, and focus stays where it is.
    const latest = queryClient.getQueryData(salesKeys.ownDraft());
    focusNext.current = latest && (latest.draft ? 'sales-draft-heading' : 'sales-no-draft');
  };
  const onSubmitted = (order) => {
    setDraft(null);
    queryClient.invalidateQueries({ queryKey: salesKeys.allOwnOrders() });
    setSubmitted(order);
    focusNext.current = 'sales-submitted-notice';
  };
  const onDeleted = () => {
    setDraft(null);
    setDeleted(true);
    focusNext.current = 'sales-no-draft';
  };

  if (draftQuery.isError) {
    return <section className="sales-paper" aria-label="Draft order unavailable">
      <p role="alert" className="sales-alert !mt-0">Your draft order could not be loaded.</p>
      <button type="button" className="sales-button mt-3" onClick={() => draftQuery.refetch()}>Try again</button>
    </section>;
  }
  if (!draftQuery.data) return <p role="status" className="sales-paper text-sm text-gray-600">Loading your draft order…</p>;
  if (!draft) {
    return <section className="sales-paper" aria-label="No draft order">
      {submitted && <p id="sales-submitted-notice" role="status" tabIndex={-1} className="sales-notice mb-4">Order {submitted.reference} for {formatMinorNGN(submitted.total_minor)} was submitted to MTN Finance for review. It can no longer be changed or withdrawn.</p>}
      <p id="sales-no-draft" tabIndex={-1} className="text-sm text-gray-600">{deleted ? 'Draft deleted. Nothing was sent to MTN Finance.' : 'You have no draft order.'}</p>
      {createFailed && <p role="alert" className="sales-alert">The draft could not be started. Try again.</p>}
      <button type="button" className="sales-button sales-primary mt-3" disabled={creating} onClick={create}>Start a draft order</button>
    </section>;
  }
  return <DraftOrderEditor key={editorKey} draft={draft} account={account} pricing={pricing} onSaved={setDraft} onSubmitted={onSubmitted} onDeleted={onDeleted} onLoadLatest={loadLatest} />;
}

function DraftOrderEditor({ draft, account, pricing, onSaved, onSubmitted, onDeleted, onLoadLatest }) {
  const [lines, setLines] = useState(draft.lines);
  // The server's copy, whose token the next save, delete or submission must send.
  const [saved, setSaved] = useState(draft);
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

  const edit = (next) => {
    setLines(next);
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
      setSaved(next);
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
    <section className="sales-paper" aria-labelledby="sales-catalogue-heading">
      <h2 id="sales-catalogue-heading" tabIndex={-1} className="text-lg font-semibold">Fictional product catalogue</h2>
      <table className="sales-table mt-3" aria-label="Fictional product catalogue">
        <thead><tr><th scope="col">Product</th><th scope="col" className="hidden sm:table-cell">Unit</th><th scope="col" className="sales-amount hidden sm:table-cell">Fixed price</th><th scope="col"><span className="sr-only">Action</span></th></tr></thead>
        <tbody>{pricing.catalogue.map((product) => {
          const onDraft = lines.some((line) => line.product_code === product.code);
          return <tr key={product.code}>
            <th scope="row"><span className="block font-semibold">{product.code}</span> <span className="block">{product.description}</span>
              <span className="block sm:hidden text-gray-600 mt-1">{product.unit} · {formatMinorNGN(product.price_minor)}</span></th>
            <td className="hidden sm:table-cell">{product.unit}</td>
            <td className="sales-amount hidden sm:table-cell">{formatMinorNGN(product.price_minor)}</td>
            <td className="text-right"><button type="button" className="sales-button" disabled={onDraft} aria-label={`Add ${product.code} to draft order`} onClick={() => addLine(product.code)}>{onDraft ? 'On draft' : 'Add'}</button></td>
          </tr>;
        })}</tbody>
      </table>
    </section>
    <section className="sales-paper" aria-labelledby="sales-draft-heading">
      <h2 id="sales-draft-heading" ref={linesHeading} tabIndex={-1} className="text-lg font-semibold">Your draft order</h2>
      {empty ? <p className="text-sm text-gray-600 mt-4">No lines yet. Add a product from the catalogue.</p>
        : <ul aria-label="Draft order lines" className="mt-2">{lines.map((line) => {
          const product = pricing.productByCode(line.product_code);
          const lineTotal = pricing.lineTotalMinor(line);
          const error = pricing.quantityError(line.quantity);
          const errorId = `sales-quantity-error-${line.product_code}`;
          return <li key={line.product_code} className="sales-line">
            <div><span className="block font-semibold">{product.code}</span><span className="block">{product.description}</span><span className="block text-gray-600 mt-1">{formatMinorNGN(product.price_minor)} per {product.unit}</span></div>
            <p className="sales-line-total">{lineTotal === null ? 'Unavailable' : formatMinorNGN(lineTotal)}</p>
            <div className="sales-line-controls">
              <label className="sales-field">Quantity<input ref={(element) => { quantityInputs.current[line.product_code] = element; }} type="text" inputMode="numeric" autoComplete="off" maxLength={20} aria-label={`Quantity for ${product.code}`} aria-invalid={Boolean(error)} aria-describedby={error ? errorId : undefined} value={line.quantity}
                onChange={(event) => edit(lines.map((current) => current.product_code === line.product_code ? { ...current, quantity: event.target.value.trim() } : current))} />
                {error && <span id={errorId} className="sales-error">{error}</span>}</label>
              <button type="button" className="sales-button self-end" aria-label={`Remove ${product.code} from draft order`} onClick={() => removeLine(product.code)}>Remove</button>
            </div>
          </li>;
        })}</ul>}
      <div className="sales-total mt-4"><span>Order total</span><span>{total === null ? 'Unavailable until quantities are corrected' : formatMinorNGN(total)}</span></div>
      {saving && <p role="status" className="text-xs text-gray-600 mt-2">Saving draft…</p>}
      {!saving && dirty && <p className="text-xs text-gray-600 mt-2">Unsaved changes.</p>}
      {savedNotice && !dirty && <p role="status" className="text-xs text-gray-600 mt-2">Draft saved. Nothing has been sent to MTN Finance.</p>}
      <ActionFailure failure={failure} onLoadLatest={onLoadLatest} />
      {attempted && (empty || invalidLine) && <p role="alert" className="sales-alert">{invalidLine ? 'Correct the highlighted quantities before previewing.' : 'Add at least one product before previewing.'}</p>}
      <div className="sales-actions">
        <button id="sales-order-preview" type="button" className="sales-button sales-primary" disabled={saving || failure.refused} onClick={preview}>Preview order</button>
        <button type="button" className="sales-button" disabled={saving || !dirty || failure.refused} onClick={saveDraft}>Save draft</button>
        {!confirmingDelete && <button id="sales-order-delete" type="button" className="sales-button" disabled={saving || failure.refused} onClick={() => {
          setConfirmingDelete(true);
          requestAnimationFrame(() => document.getElementById('sales-order-delete-keep')?.focus());
        }}>Delete draft</button>}
        <p className="text-xs text-gray-600">Saving keeps your draft private. MTN Finance sees an order only once you submit it.</p>
      </div>
      {confirmingDelete && <div role="group" aria-label="Confirm draft deletion" className="sales-paper mt-4">
        <p className="text-sm">Delete this draft order? Its lines are discarded. Nothing has been sent to MTN Finance.</p>
        <div className="sales-actions">
          <button type="button" className="sales-button sales-primary" onClick={remove}>Delete draft order</button>
          <button id="sales-order-delete-keep" type="button" className="sales-button" onClick={() => {
            setConfirmingDelete(false);
            requestAnimationFrame(() => document.getElementById('sales-order-delete')?.focus());
          }}>Keep draft</button>
        </div>
      </div>}
    </section>
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
  return <section className="sales-paper" aria-labelledby="sales-order-preview-heading">
    <p className="text-xs font-semibold tracking-widest uppercase text-amber-800">Fictional simulation</p>
    <h2 id="sales-order-preview-heading" tabIndex={-1} className="text-lg font-semibold mt-1">Order preview</h2>
    <dl className="sales-facts">
      <div><dt>Seller</dt><dd>MTN</dd></div>
      <div><dt>Buyer</dt><dd>{partnerLabel(account)}</dd></div>
      <div><dt>Currency</dt><dd>NGN</dd></div>
    </dl>
    <OrderLines caption="Lines in this order" lines={lines} totalMinor={pricing.draftTotalMinor(draft)} />
    <p className="sales-notice mt-5">{ORDER_NOTE} MTN Finance sets the invoice dates if it issues the order. Taxes and discounts are not modeled.</p>
    <ActionFailure failure={failure} onLoadLatest={onLoadLatest} />
    <div className="sales-actions">
      <button type="button" className="sales-button sales-primary" disabled={submitting || failure.refused} onClick={submit}>Submit order</button>
      <button type="button" className="sales-button" disabled={submitting} onClick={onBack}>Back to draft</button>
    </div>
  </section>;
}

function OrderList({ onOpen }) {
  const { query: orders, controls } = usePagedQuery('own-orders', 'sales-orders-heading', ownOrdersQuery, (data) => data.pagination, useQuery);
  const visible = orders.data?.items ?? [];
  return <section className="sales-paper" aria-labelledby="sales-orders-heading">
    <h2 id="sales-orders-heading" tabIndex={-1} className="text-lg font-semibold">Your orders</h2>
    <p className="text-xs text-gray-600 mt-1">Submitted orders cannot be changed or withdrawn. MTN Finance issues each as an invoice or rejects it with a reason. Refresh to see their decisions.</p>
    <ReadState query={orders} what="order list" />
    {orders.data && (!orders.data.pagination.total ? <p role="status" className="text-sm text-gray-600 mt-4">You have not submitted any orders yet.</p> : <>
      <table className="sales-table mt-4">
        <caption className="sr-only">Your submitted orders</caption>
        <thead><tr><th scope="col">Reference</th><th scope="col">Status</th><th scope="col" className="sales-amount">Total</th><th scope="col"><span className="sr-only">Actions</span></th></tr></thead>
        <tbody>{visible.map((order) => <tr key={order.reference}>
          <th scope="row" className="font-semibold">{order.reference}</th>
          <td>{order.status}</td>
          <td className="sales-amount">{formatMinorNGN(order.total_minor)}</td>
          <td className="text-right"><button id={`sales-order-open-${order.reference}`} type="button" className="sales-button" aria-label={`Open order ${order.reference}`} onClick={() => onOpen(order.reference, `sales-order-open-${order.reference}`)}>Open</button></td>
        </tr>)}</tbody>
      </table>
      {controls}
    </>)}
  </section>;
}

function OrderDetail({ reference, onBack }) {
  const order = useOwnOrder(reference);
  const headingId = detailHeadingId({ type: 'order', reference });
  return <section className="sales-paper" aria-labelledby={headingId}>
    <p className="text-xs font-semibold tracking-widest uppercase text-amber-800">Fictional simulation</p>
    <h2 id={headingId} tabIndex={-1} className="text-lg font-semibold mt-1">Order {reference}</h2>
    <ReadState query={order} what="order" />
    {order.data && <>
      <dl className="sales-facts">
        <div><dt>Status</dt><dd>{order.data.status}</dd></div>
        <div><dt>Seller</dt><dd>MTN</dd></div>
        <div><dt>Buyer</dt><dd>{partnerLabel(order.data.account)}</dd></div>
        <div><dt>Currency</dt><dd>{order.data.currency}</dd></div>
      </dl>
      <OrderLines caption={`Lines in order ${reference}`} lines={order.data.lines} totalMinor={order.data.total_minor} />
      <OrderDecision order={order.data} />
      <p className="sales-notice mt-5">This order is read-only. It is not an invoice or a purchase obligation unless MTN Finance issues it.</p>
    </>}
    <div className="sales-actions"><button type="button" className="sales-button" onClick={onBack}>Back to your orders</button></div>
  </section>;
}

function OrderDecision({ order }) {
  if (order.status === 'Issued') {
    const { reference, issue_date: issued, due_date: due } = order.invoice;
    return <p className="text-sm font-medium mt-5">MTN Finance issued this order as invoice {reference} on {formatDate(issued)}, due {formatDate(due)}.</p>;
  }
  if (order.status === 'Rejected') {
    return <div className="mt-5 text-sm"><p className="font-medium">MTN Finance rejected this order: {order.rejection_reason}</p>
      <p className="text-gray-600 mt-1">A rejected order is final. Start a new draft to order again.</p></div>;
  }
  return <p className="text-sm text-gray-600 mt-5">Awaiting review by MTN Finance.</p>;
}
