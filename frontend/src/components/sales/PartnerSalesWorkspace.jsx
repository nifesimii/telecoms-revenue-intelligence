import { useEffect, useRef, useState } from 'react';
import { usePeriod } from '../../context/PeriodContext.jsx';
import { formatPeriod } from '../../lib/format.js';
import { useSalesActions } from './useSalesActions.js';
import { useSalesPeriodSummary, useSalesReference } from './useSalesQueries.js';
import CommissionAccount from './CommissionAccount.jsx';
import FinanceHeadline from './FinanceHeadline.jsx';
import InvoiceDetail from './InvoiceDetail.jsx';
import InvoiceList, { INVOICES_HEADING } from './InvoiceList.jsx';
import { ORDER_NOTICE, ORDER_QUEUE_HEADING, OrderQueue, OrderReview } from './OrderReview.jsx';
import PartnerAccounts, { PARTNERS_HEADING, partnerCommissionOpener } from './PartnerAccounts.jsx';
import PartnerObligations from './PartnerObligations.jsx';
import { Disclaimer } from './SalesParts.jsx';
import SimulationControls from './SimulationControls.jsx';
import './sales.css';

const DETAIL_VIEWS = {
  invoice: { headingId: (entry) => `sales-invoice-heading-${entry.reference}`, backLabel: (entry) => `Back to invoice ${entry.reference}` },
  partner: { headingId: (entry) => `sales-obligations-heading-${entry.accountCode}`, backLabel: () => 'Back to purchase obligations' },
  commission: { headingId: (entry) => `sales-commission-heading-${entry.accountCode}`, backLabel: () => 'Back to commission account' },
  order: { headingId: (entry) => `sales-review-heading-${entry.reference}`, backLabel: (entry) => `Back to order ${entry.reference}` },
};
const detailHeadingId = (entry) => DETAIL_VIEWS[entry.type].headingId(entry);
const backLabelTo = (entry) => DETAIL_VIEWS[entry.type].backLabel(entry);

const TABS = {
  orders: { label: 'Orders to review', backLabel: 'Back to orders', heading: ORDER_QUEUE_HEADING },
  invoices: { label: 'Invoices', backLabel: 'Back to invoices', heading: INVOICES_HEADING },
  partners: { label: 'Partner accounts', backLabel: 'Back to partner accounts', heading: PARTNERS_HEADING },
};
const NO_INVOICE_FILTERS = { search: '', status: '' };

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
    <div className="mt-2"><button type="button" className="overview-button" onClick={() => reference.refetch()}>Try again</button></div></div>;
}

function Workspace({ reference: { partners, statuses }, period, navigation, onNavigate, onClearNavigation }) {
  const actions = useSalesActions();
  const summary = useSalesPeriodSummary(period);
  const [tab, setTab] = useState('orders');
  // Kept here because only the active sub-tab is mounted.
  const [invoiceFilters, setInvoiceFilters] = useState(NO_INVOICE_FILTERS);
  const [partnerSearch, setPartnerSearch] = useState('');
  // The notice lasts until the next thing the presenter does here.
  const [resetStatus, setResetStatus] = useState(null);
  // What Finance last decided, until the next decision or reset.
  const [orderNotice, setOrderNotice] = useState(null);
  const partnerByCode = (code) => partners.find((candidate) => candidate.code === code);
  // Open detail views, innermost last. Views underneath stay mounted but hidden,
  // so returning finds their filters, page and opener exactly as they were.
  const [trail, setTrail] = useState([]);
  const focusDetail = (entry) => requestAnimationFrame(() => document.getElementById(detailHeadingId(entry))?.focus());
  // Reopening a view already on the trail brings it forward rather than stacking
  // a copy, so every view underneath stays mounted with its page.
  const openDetail = (entry, openerId) => {
    setResetStatus(null);
    setTrail((current) => [...current.filter((other) => detailHeadingId(other) !== detailHeadingId(entry)), { ...entry, openerId }]);
    focusDetail(entry);
  };
  const closeDetail = (openerId) => {
    setTrail((current) => current.slice(0, -1));
    requestAnimationFrame(() => (document.getElementById(openerId) ?? document.getElementById(TABS[tab].heading))?.focus());
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
    if (!trail.some((other) => detailHeadingId(other) === detailHeadingId(entry))) setTab('partners');
    setTrail((current) => {
      const open = current.find((other) => detailHeadingId(other) === detailHeadingId(entry));
      return [...current.filter((other) => other !== open), open ?? { ...entry, openerId: partnerCommissionOpener(accountCode) }];
    });
  }, [navigation?.revision]);
  const changeTab = (next) => {
    setTab(next);
    setResetStatus(null);
  };
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
  const goToOrders = () => {
    changeTab('orders');
    requestAnimationFrame(() => document.getElementById(ORDER_QUEUE_HEADING)?.focus());
  };
  const reset = async () => {
    const status = await actions.reset();
    setResetStatus(status);
    setOrderNotice(null);
    setPartnerSearch('');
    setInvoiceFilters(NO_INVOICE_FILTERS);
    setTab('orders');
    focusAfterTrail.current = ['sales-reset-notice'];
    setTrail([]);
    onClearNavigation();
  };
  const detailViews = {
    commission: (entry, shared) => <CommissionAccount {...shared} partner={partnerByCode(entry.accountCode)} period={period} onOpenObligations={openPartner}
      onExplain={(view, context, openerId) => onNavigate(view, { ...context, origin: { commission_account_code: entry.accountCode, opener_id: openerId } })} />,
    invoice: (entry, shared) => <InvoiceDetail {...shared} reference={entry.reference} onOpenPartner={openPartner} onOpenCommission={openCommission} onRecordCollection={recordInvoiceCollection} onLoadLatest={actions.loadLatestInvoice} />,
    order: (entry, shared) => <OrderReview {...shared} order={entry.order} period={period} onIssue={issueOrder} onReject={rejectOrder} onLoadLatest={loadLatestOrders} />,
    partner: (entry, shared) => <PartnerObligations {...shared} partner={partnerByCode(entry.accountCode)} onOpenInvoice={openInvoice} onOpenCommission={openCommission} />,
  };
  const counts = { orders: summary.data?.orders_awaiting.count, invoices: summary.data?.invoices, partners: partners.length };
  const periodLabel = formatPeriod(period);
  return <main className="sales-workspace h-full overflow-y-auto bg-gray-50" aria-label="Partner Sales">
    <div className="mx-auto max-w-7xl p-4 sm:p-6 lg:p-8 flex flex-col gap-6">
      <div className={trail.length ? 'hidden' : 'contents'}>
        <header className="flex flex-wrap items-start justify-between gap-x-6 gap-y-4">
          <div className="min-w-0 flex-1 basis-96">
            <p className="sales-eyebrow">Finance &amp; Revenue Assurance</p>
            <h1 id="sales-workspace-heading" tabIndex={-1} className="sales-title">Partner Sales <span className="sales-title-period">/ {periodLabel}</span></h1>
            <p className="sales-muted mt-1.5">Issue partner orders as invoices, record collections and explain each partner's account.</p>
            <Disclaimer className="mt-2" summary="Fictional simulation, separate from recorded evidence">Fictional simulation using sample partner identities and fictional products and prices. It starts with example invoices in May 2026. Partner orders, simulated invoices and collections are shared by everyone signed in and last until the server restarts or the simulation is reset. They stay separate from recorded commission, payment and inventory evidence, including when the application reads live data.</Disclaimer>
          </div>
          <SimulationControls onRefresh={actions.refresh} onReset={reset} />
        </header>
        {resetStatus && <p id="sales-reset-notice" role="status" tabIndex={-1} className="overview-notice">Simulation reset to its starting point: {resetStatus.invoices} example invoices in May 2026, and the next invoice will be {resetStatus.next_invoice_reference}.</p>}
        <FinanceHeadline query={summary} period={period} onReview={goToOrders} />
      </div>
      {trail.map((entry, index) => {
        const active = index === trail.length - 1;
        const shared = { headingId: detailHeadingId(entry), backLabel: !index ? TABS[tab].backLabel : backLabelTo(trail[index - 1]), onBack: () => closeDetail(entry.openerId) };
        return <div key={shared.headingId} className={active ? '' : 'hidden'}>{detailViews[entry.type](entry, shared)}</div>;
      })}
      <div className={`overview-surface ${trail.length ? 'hidden' : ''}`}>
        <div className="sales-tabs" role="group" aria-label="Partner Sales views">{Object.entries(TABS).map(([id, { label }]) => <button key={id} type="button" className={`overview-button ${tab === id ? 'overview-primary' : ''}`} aria-pressed={tab === id} onClick={() => changeTab(id)}>{label}{counts[id] === undefined ? '' : ` (${counts[id]})`}</button>)}</div>
        {tab === 'orders' && <OrderQueue notice={orderNotice} onReview={reviewOrder} />}
        {tab === 'invoices' && <InvoiceList period={period} statuses={statuses} filters={invoiceFilters} onFiltersChange={setInvoiceFilters} onOpenInvoice={openInvoice} />}
        {tab === 'partners' && <PartnerAccounts search={partnerSearch} onSearchChange={setPartnerSearch} onOpenObligations={openPartner} onOpenCommission={openCommission} />}
      </div>
    </div>
  </main>;
}
