// Partner Sales changes through the server simulation.

import { useQueryClient } from '@tanstack/react-query';
import { issueOrder, recordSalesCollection, rejectOrder, resetSalesSimulation } from '../../api/client.js';
import { isSharedQuery, salesKeys } from './useSalesQueries.js';

export function useSalesActions() {
  const queryClient = useQueryClient();
  const refresh = () => queryClient.invalidateQueries({ predicate: isSharedQuery });

  // The action identifies this attempt, so a retry after a lost response cannot record it twice.
  const recordCollection = async (reference, collection) => {
    const recorded = await recordSalesCollection(reference, collection);
    await refresh();
    return recorded;
  };

  // A decided order leaves the queue, and an issued one adds an invoice.
  const decideOrder = (decide) => async (reference, decision) => {
    const decided = await decide(reference, decision);
    await refresh();
    return decided;
  };

  // Clears every cached record, so nothing from before the reset can reappear.
  const reset = async () => {
    const status = await resetSalesSimulation();
    queryClient.resetQueries({ predicate: isSharedQuery });
    return status;
  };

  // After a refusal: replaces the refused invoice with the server's.
  const loadLatestInvoice = (reference) => {
    refresh();
    return queryClient.resetQueries({ queryKey: salesKeys.invoiceAnyPage(reference) });
  };

  return { loadLatestInvoice, recordCollection, issueOrder: decideOrder(issueOrder), rejectOrder: decideOrder(rejectOrder), loadLatestOrders: refresh, reset };
}
