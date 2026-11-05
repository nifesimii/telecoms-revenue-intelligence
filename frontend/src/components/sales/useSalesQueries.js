// Partner Sales reads through the server simulation, which every session shares.

import useQuery from '../../hooks/useWorkspaceQuery.js';
import { getSalesDraft, getSalesReference, getSalesStatus } from '../../api/client.js';

const SALES = 'partner-sales';

export const salesKeys = {
  reference: () => [SALES, 'reference'],
  status: () => [SALES, 'status'],
  draft: (accountCode, period) => [SALES, 'draft', accountCode, period],
  records: (params) => [SALES, 'records', params],
  obligations: (accountCode, params) => [SALES, 'obligations', accountCode, params],
  invoice: (reference, params) => [SALES, 'invoice', reference, params],
};

// Everything that can change while the page is open. The reference data cannot.
export const isSharedRecord = ({ queryKey }) => queryKey[0] === SALES && queryKey[1] !== 'reference';
export const isDraft = ({ queryKey }) => queryKey[1] === 'draft';

// A missing record will not appear by asking again.
export const retryUnlessMissing = (failures, error) => error.response?.status !== 404 && failures < 1;

export const useSalesReference = () => useQuery({ queryKey: salesKeys.reference(), queryFn: ({ signal }) => getSalesReference(signal), staleTime: Infinity });
export const useSalesSimulationStatus = () => useQuery({ queryKey: salesKeys.status(), queryFn: ({ signal }) => getSalesStatus(signal) });
export const useSalesDraft = (accountCode, period) => useQuery({ queryKey: salesKeys.draft(accountCode, period), queryFn: ({ signal }) => getSalesDraft(accountCode, period, signal), enabled: Boolean(accountCode) });
