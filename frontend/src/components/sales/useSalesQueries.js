// Partner Sales reads through the server simulation, which every session shares.

import { keepPreviousData, useQuery as useMonthlessQuery } from '@tanstack/react-query';
import useQuery from '../../hooks/useWorkspaceQuery.js';
import { getOrderQueue, getOwnOrder, getOwnOrderDraft, getOwnOrderingReference, getOwnOrders, getSalesInvoice, getSalesObligations, getSalesRecords, getSalesReference, getSalesStatus } from '../../api/client.js';

const SALES = 'partner-sales';

export const salesKeys = {
  reference: () => [SALES, 'reference'],
  status: () => [SALES, 'status'],
  records: (params) => [SALES, 'records', params],
  obligations: (accountCode, params) => [SALES, 'obligations', accountCode, params],
  invoiceAnyPage: (reference) => [SALES, 'invoice', reference],
  invoice: (reference, params) => [SALES, 'invoice', reference, params],
  orderQueue: (params) => [SALES, 'order-queue', params],
  ownReference: () => [SALES, 'reference', 'own'],
  ownDraft: () => [SALES, 'own-draft'],
  ownOrders: (params) => [SALES, 'own-orders', params],
  // Every page of a partner's order list, for invalidating them together.
  allOwnOrders: () => [SALES, 'own-orders'],
  ownOrder: (reference) => [SALES, 'own-order', reference],
};

// Everything that can change while the page is open. The reference data cannot.
export const isSharedQuery = ({ queryKey }) => queryKey[0] === SALES && queryKey[1] !== 'reference';

// A missing record will not appear by asking again.
const retryUnlessMissing = (failures, error) => error.response?.status !== 404 && failures < 1;

export const useSalesReference = () => useQuery({ queryKey: salesKeys.reference(), queryFn: ({ signal }) => getSalesReference(signal), staleTime: Infinity });
export const useSalesSimulationStatus = () => useQuery({ queryKey: salesKeys.status(), queryFn: ({ signal }) => getSalesStatus(signal) });

// The paged reads, for usePagedQuery to run once it knows the page.
export const recordsQuery = (params) => ({ queryKey: salesKeys.records(params), queryFn: ({ signal }) => getSalesRecords(params, signal), placeholderData: keepPreviousData });
export const obligationsQuery = (accountCode, params) => ({ queryKey: salesKeys.obligations(accountCode, params), queryFn: ({ signal }) => getSalesObligations(accountCode, params, signal), placeholderData: keepPreviousData });
export const orderQueueQuery = (params) => ({ queryKey: salesKeys.orderQueue(params), queryFn: ({ signal }) => getOrderQueue(params, signal), placeholderData: keepPreviousData });
export const invoiceQuery = (reference, params) => ({ queryKey: salesKeys.invoice(reference, params), queryFn: ({ signal }) => getSalesInvoice(reference, params, signal), placeholderData: keepPreviousData, retry: retryUnlessMissing });

// A partner's own ordering, which belongs to no reporting month.
export const useOwnOrderingReference = () => useMonthlessQuery({ queryKey: salesKeys.ownReference(), queryFn: ({ signal }) => getOwnOrderingReference(signal), staleTime: Infinity });
export const useOwnOrderDraft = () => useMonthlessQuery({ queryKey: salesKeys.ownDraft(), queryFn: ({ signal }) => getOwnOrderDraft(signal) });
export const useOwnOrder = (reference) => useMonthlessQuery({ queryKey: salesKeys.ownOrder(reference), queryFn: ({ signal }) => getOwnOrder(reference, signal), retry: retryUnlessMissing });
export const ownOrdersQuery = (params) => ({ queryKey: salesKeys.ownOrders(params), queryFn: ({ signal }) => getOwnOrders(params, signal), placeholderData: keepPreviousData });
