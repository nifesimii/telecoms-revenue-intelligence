import { useEffect, useRef, useState } from 'react';
import { usePeriod } from '../../context/PeriodContext.jsx';
import { formatPeriod } from '../../lib/format.js';
import { partnerLabel, partnerMatches, quantityLabel } from './salesDisplay.js';
import { useSalesActions } from './useSalesActions.js';
import { useSalesReference, useSalesSimulationStatus } from './useSalesQueries.js';
import { useSelectedPartner } from './useSelectedPartner.js';
import { InvoiceDetail, InvoiceList, PartnerObligations } from './InvoiceViews.jsx';
import CommissionAccount from './CommissionAccount.jsx';
import { ORDER_NOTICE, ORDER_QUEUE_HEADING, OrderQueue, OrderReview } from './OrderReview.jsx';
import './sales.css';

const DETAIL_VIEWS = {
  invoice: { headingId: (entry) => `sales-invoice-heading-${entry.reference}`, backLabel: (entry) => `Back to invoice ${entry.reference}` },
  partner: { headingId: (entry) => `sales-obligations-heading-${entry.accountCode}`, backLabel: () => 'Back to purchase obligations' },
  commission: { headingId: (entry) => `sales-commission-heading-${entry.accountCode}`, backLabel: () => 'Back to commission account' },
  order: { headingId: (entry) => `sales-review-heading-${entry.reference}`, backLabel: (entry) => `Back to order ${entry.reference}`, rootBackLabel: 'Back to orders awaiting review' },
};
const detailHeadingId = (entry) => DETAIL_VIEWS[entry.type].headingId(entry);
const backLabelTo = (entry) => DETAIL_VIEWS[entry.type].backLabel(entry);
const rootBackLabel = (entry) => DETAIL_VIEWS[entry.type].rootBackLabel ?? 'Back to invoices';

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
  const contents = status ? `${quantityLabel(status.invoices, 'invoice')}, ${quantityLabel(status.collections, 'collection')} and ${quantityLabel(status.orders, 'partner order')}` : 'records';
  return <div className="mt-3">
    {!confirming ? <button id="sales-reset" type="button" className="sales-button" onClick={open}>Reset simulation</button>
      : <div role="group" aria-label="Confirm simulation reset" className="sales-paper">
        <p className="text-sm">Reset the simulation to its starting point for everyone using it? This discards the current {contents}, along with every partner's draft order, restores the example invoices, and clears the selected partner and filters. Recorded commission, payment and inventory evidence, other workspaces and the reporting month stay as they are.</p>
        {failed && <p role="alert" className="sales-alert">The simulation could not be reset, so nothing has changed. Try again.</p>}
        <div className="sales-actions">
          <button type="button" className="sales-button sales-primary" disabled={resetting} onClick={reset}>Reset to starting point</button>
          <button id="sales-reset-keep" type="button" className="sales-button" disabled={resetting} onClick={cancel}>Keep simulation</button>
        </div>
      </div>}
  </div>;
}

function Workspace({ reference: { partners, statuses }, period, navigation, onNavigate, onClearNavigation }) {
  const actions = useSalesActions();
  const [selectedCode, setSelectedCode] = useSelectedPartner();
  // Remounts the invoice list, so a reset also drops its filters and page.
  const [invoiceListKey, setInvoiceListKey] = useState(0);
  // The notice lasts until the next thing the presenter does here.
  const [resetStatus, setResetStatus] = useState(null);
  // What Finance last decided, until the next decision or reset.
  const [orderNotice, setOrderNotice] = useState(null);
  const [search, setSearch] = useState('');
  const term = search.trim().toLowerCase();
  const matches = partners.filter((partner) => partnerMatches(partner, term));
  const partnerByCode = (code) => partners.find((candidate) => candidate.code === code);
  const partner = partnerByCode(selectedCode);
  const selectPartner = (code) => {
    setSelectedCode(code);
    setResetStatus(null);
  };
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
    const accountCode = navigation?.commission_account_code;
    if (!partnerByCode(accountCode)) return;
    const entry = { type: 'commission', accountCode };
    focusAfterTrail.current = [navigation.opener_id, detailHeadingId(entry)];
    setTrail((current) => {
      const open = current.find((other) => detailHeadingId(other) === detailHeadingId(entry));
      return [...current.filter((other) => other !== open), open ?? { ...entry, openerId: 'sales-partner-commission' }];
    });
  }, [navigation?.revision]);
  const reviewOrder = (order, openerId) => {
    setOrderNotice(null);
    openDetail({ type: 'order', reference: order.reference, order }, openerId);
  };
  const issueOrder = async (reference, decision) => {
    const invoice = await actions.issueOrder(reference, decision);
    setResetStatus(null);
    setOrderNotice(`Order ${reference} was issued as invoice ${invoice.reference}.`);
    // Leaving the invoice returns to what says where the order went.
    const entry = { type: 'invoice', reference: invoice.reference, openerId: ORDER_NOTICE };
    focusAfterTrail.current = [detailHeadingId(entry)];
    setTrail([entry]);
  };
  // The order has left the queue, so focus goes to what says what happened to it.
  const rejectOrder = async (reference, decision) => {
    await actions.rejectOrder(reference, decision);
    setResetStatus(null);
    setOrderNotice(`Order ${reference} was rejected. The partner sees your reason when they next refresh.`);
    focusAfterTrail.current = [ORDER_NOTICE];
    setTrail([]);
  };
  const loadLatestOrders = async () => {
    await actions.loadLatestOrders();
    setOrderNotice(null);
    focusAfterTrail.current = [ORDER_QUEUE_HEADING];
    setTrail([]);
  };
  const recordInvoiceCollection = (reference, collection) => {
    setResetStatus(null);
    return actions.recordCollection(reference, collection);
  };
  const openInvoice = (reference, openerId) => openDetail({ type: 'invoice', reference }, openerId);
  const openPartner = (accountCode, openerId) => openDetail({ type: 'partner', accountCode }, openerId);
  const openCommission = (accountCode, openerId) => openDetail({ type: 'commission', accountCode }, openerId);
  const reset = async () => {
    const status = await actions.reset();
    setResetStatus(status);
    setOrderNotice(null);
    setSelectedCode('');
    setSearch('');
    focusAfterTrail.current = ['sales-reset-notice'];
    setTrail([]);
    setInvoiceListKey((current) => current + 1);
    onClearNavigation();
  };
  const detailViews = {
    commission: (entry, shared) => <CommissionAccount {...shared} partner={partnerByCode(entry.accountCode)} period={period} onOpenObligations={openPartner}
      onExplain={(view, context, openerId) => onNavigate(view, { ...context, origin: { commission_account_code: entry.accountCode, opener_id: openerId } })} />,
    invoice: (entry, shared) => <InvoiceDetail {...shared} reference={entry.reference} onOpenPartner={openPartner} onRecordCollection={recordInvoiceCollection} onLoadLatest={actions.loadLatestInvoice} />,
    order: (entry, shared) => <OrderReview {...shared} order={entry.order} period={period} onIssue={issueOrder} onReject={rejectOrder} onLoadLatest={loadLatestOrders} />,
    partner: (entry, shared) => <PartnerObligations {...shared} partner={partnerByCode(entry.accountCode)} onOpenInvoice={openInvoice} onOpenCommission={openCommission} />,
  };
  return <main className="sales-workspace h-full overflow-y-auto bg-gray-50" aria-label="Partner Sales">
    <div className="mx-auto max-w-7xl p-4 sm:p-6 lg:p-8 flex flex-col gap-6">
      <header><p className="text-xs font-semibold tracking-widest uppercase text-gray-500">MTN sales to trade partners</p>
        <h1 id="sales-workspace-heading" tabIndex={-1} className="text-2xl font-semibold tracking-tight mt-1">Partner Sales</h1>
        <p className="text-sm text-gray-600 mt-2">Review the orders partners submit and issue them as what MTN would invoice a trade partner in {formatPeriod(period)}, record fictional collections against issued invoices, and explain a partner's fictional commission account.</p>
        <p className="sales-notice mt-3">Fictional simulation using sample partner identities and fictional products and prices. It starts with example invoices in May 2026. Partner orders, simulated invoices and collections are shared by everyone signed in and last until the server restarts or the simulation is reset. They stay separate from recorded commission, payment and inventory evidence, including when the application reads live data.</p>
        <SimulationReset onReset={reset} />
        {resetStatus && <p id="sales-reset-notice" role="status" tabIndex={-1} className="sales-notice mt-3">Simulation reset to its starting point: {resetStatus.invoices} example invoices in May 2026, and the next invoice will be {resetStatus.next_invoice_reference}.</p>}</header>
      {trail.map((entry, index) => {
        const active = index === trail.length - 1;
        const shared = { headingId: detailHeadingId(entry), backLabel: !index ? rootBackLabel(entry) : backLabelTo(trail[index - 1]), onBack: () => closeDetail(entry.openerId) };
        return <div key={shared.headingId} className={active ? '' : 'hidden'}>{detailViews[entry.type](entry, shared)}</div>;
      })}
      <div className={trail.length ? 'hidden' : 'flex flex-col gap-6'}>
      <OrderQueue notice={orderNotice} onReview={reviewOrder} />
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
        {!partner ? <p className="text-sm text-gray-600 mt-4">Select a trade partner to view its purchase obligations and commission account.</p> : <div className="sales-actions">
          <button id="sales-partner-obligations" type="button" className="sales-button" onClick={() => openPartner(partner.code, 'sales-partner-obligations')}>View purchase obligations for {partnerLabel(partner)}</button>
          <button id="sales-partner-commission" type="button" className="sales-button" onClick={() => openCommission(partner.code, 'sales-partner-commission')}>View commission account for {partnerLabel(partner)}</button>
        </div>}
      </section>
      <InvoiceList key={invoiceListKey} period={period} statuses={statuses} onOpenInvoice={openInvoice} onOpenPartner={openPartner} />
      </div>
    </div>
  </main>;
}
