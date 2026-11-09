// A partner's own application: one draft order built from the fictional catalogue, the
// orders it became, the invoices Finance issued and the partner's commission account.
// The server takes the account from the session, so nothing here names or chooses one.

import { useState } from 'react';
import { useQuery } from '@tanstack/react-query';
import { draftPricing } from './draftPricing.js';
import DraftOrder from './DraftOrder.jsx';
import InvoiceDetail from './InvoiceDetail.jsx';
import PartnerBalances, { OWN_INVOICE_COUNT } from './PartnerBalances.jsx';
import PartnerCommission from './PartnerCommission.jsx';
import PartnerInvoices from './PartnerInvoices.jsx';
import { OWN_ORDER_COUNT, OrderDetail, OrderList } from './PartnerOrders.jsx';
import { Disclaimer } from './SalesParts.jsx';
import { ownInvoiceQuery, ownInvoicesQuery, ownOrdersQuery, useOwnOrderingReference } from './useSalesQueries.js';
import './sales.css';

export default function PartnerOrdering() {
  const reference = useOwnOrderingReference();
  if (reference.data) return <Ordering reference={reference.data} />;
  if (!reference.isError) return <p role="status" className="p-6 text-sm text-gray-600">Loading Partner Sales…</p>;
  return <div role="alert" className="p-6 text-sm">Partner Sales could not be loaded.
    <div className="mt-2"><button type="button" className="overview-button" onClick={() => reference.refetch()}>Try again</button></div></div>;
}

// Where focus returns when the opener has gone, such as after a refresh changed the list.
const LIST_HEADING = { order: 'sales-orders-heading', invoice: 'sales-own-invoices-heading' };
const detailHeadingId = ({ type, reference }) => `sales-${type}-heading-${reference}`;

const tabClass = (active) => `min-h-11 whitespace-nowrap border-b-4 py-2 text-sm transition-colors ${active ? 'border-mtn-yellow text-gray-900 font-bold' : 'border-transparent text-gray-600 hover:text-gray-900 hover:border-gray-300'}`;

function Ordering({ reference: { account, catalogue, max_quantity: maxQuantity, invoice_statuses: invoiceStatuses, statement_periods: statementPeriods } }) {
  const pricing = draftPricing(catalogue, maxQuantity);
  const [tab, setTab] = useState('order');
  const [draftWork, setDraftWork] = useState(null);
  // An open order or invoice hides the rest, which stays mounted so returning finds its page.
  const [open, setOpen] = useState(null);
  const orderCount = useQuery(ownOrdersQuery(OWN_ORDER_COUNT)).data?.pagination.total;
  const invoiceCount = useQuery(ownInvoicesQuery(OWN_INVOICE_COUNT)).data?.summary.count;
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
  const changeTab = (next) => {
    setTab(next);
    setOpen(null);
  };
  const withCount = (label, count) => (count === undefined ? label : `${label} (${count})`);
  const tabs = [['order', 'Order'], ['orders', withCount('My orders', orderCount), withCount('Orders', orderCount)], ['invoices', withCount('Invoices', invoiceCount)], ['commission', 'Commission']];
  return <div className="sales-workspace min-h-full bg-gray-50">
    <div className="border-b border-gray-200 bg-white">
      <nav aria-label="Partner Sales sections" className="sales-partner-tabs mx-auto max-w-7xl px-4 sm:px-6 lg:px-8">
        {tabs.map(([id, label, short]) => <button key={id} type="button" className={tabClass(tab === id && !open)} aria-label={label} aria-current={tab === id && !open ? 'page' : undefined} onClick={() => changeTab(id)}>{short ? <><span className="sm:hidden">{short}</span><span className="max-sm:hidden">{label}</span></> : label}</button>)}
      </nav>
    </div>
    <div className="mx-auto flex max-w-7xl flex-col gap-6 p-4 sm:p-6 lg:p-8">
      {open?.type === 'order' && <OrderDetail reference={open.reference} headingId={detailHeadingId(open)} onBack={closeDetail} />}
      {open?.type === 'invoice' && <InvoiceDetail reference={open.reference} headingId={detailHeadingId(open)} backLabel="Back to your invoices" onBack={closeDetail}
        queryFor={ownInvoiceQuery} useRead={useQuery} />}
      <div className={open ? 'hidden' : 'contents'}>
        <header>
          <p className="sales-eyebrow">Account {account.code}</p>
          <h1 className="sales-title">{account.name}</h1>
          <Disclaimer className="mt-2" summary="Fictional simulation, nothing here is an actual order, invoice or commission">Fictional simulation using sample partner identities and fictional products and prices. Your draft is private to you until you submit it.</Disclaimer>
        </header>
        <PartnerBalances periods={statementPeriods} />
        {tab === 'order' && <DraftOrder account={account} pricing={pricing} maxQuantity={maxQuantity} work={draftWork} onWorkChange={setDraftWork} />}
        {tab === 'orders' && <OrderList onOpen={openDetail('order')} />}
        {tab === 'invoices' && <PartnerInvoices statuses={invoiceStatuses} onOpen={openDetail('invoice')} />}
        {tab === 'commission' && <PartnerCommission partner={account} periods={statementPeriods} />}
      </div>
    </div>
  </div>;
}
