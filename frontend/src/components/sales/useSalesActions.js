// Partner Sales changes through the server simulation.

import { useQueryClient } from '@tanstack/react-query';
import { createSalesDraft, issueSalesDraft, recordSalesCollection, resetSalesSimulation } from '../../api/client.js';
import { useDraftSaves } from './useDraftSaves.js';
import { isDraftQuery, isSharedQuery, salesKeys } from './useSalesQueries.js';

export function useSalesActions() {
  const queryClient = useQueryClient();
  const refresh = () => queryClient.invalidateQueries({ predicate: isSharedQuery });
  // Totals follow each saved edit. The draft itself is already current in the cache.
  const refreshAfterEdit = () => queryClient.invalidateQueries({ predicate: (query) => isSharedQuery(query) && !isDraftQuery(query) });
  const { finishSaves, discardSaves, discardAllSaves, ...draftEdits } = useDraftSaves(refreshAfterEdit);

  const createDraft = async (accountCode, period) => {
    const draft = await createSalesDraft(accountCode, period);
    queryClient.setQueryData(salesKeys.draft(accountCode, period), { draft });
    refreshAfterEdit();
    return draft;
  };

  // Waits for saved edits first, so the invoice is what the preview showed.
  const issueDraft = async (draft) => {
    const invoice = await issueSalesDraft(draft.reference, await finishSaves(draft));
    await refresh();
    return invoice;
  };

  // The action identifies this attempt, so a retry after a lost response cannot record it twice.
  const recordCollection = async (reference, collection) => {
    const recorded = await recordSalesCollection(reference, collection);
    await refresh();
    return recorded;
  };

  // Clears every cached record, so nothing from before the reset can reappear.
  const reset = async () => {
    const status = await resetSalesSimulation();
    discardAllSaves();
    queryClient.resetQueries({ predicate: isSharedQuery });
    return status;
  };

  // After a refusal: replaces the refused record with the server's, which is the point
  // at which its unsaved edits are discarded. Other drafts keep theirs.
  const loadLatestDraft = (draft) => {
    discardSaves(draft.reference);
    refreshAfterEdit();
    return queryClient.resetQueries({ queryKey: salesKeys.draft(draft.account_code, draft.period) });
  };
  const loadLatestInvoice = (reference) => {
    refreshAfterEdit();
    return queryClient.resetQueries({ queryKey: salesKeys.invoiceAnyPage(reference) });
  };

  return { ...draftEdits, loadLatestDraft, loadLatestInvoice, createDraft, issueDraft, recordCollection, reset };
}
