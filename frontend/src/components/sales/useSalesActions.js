// Partner Sales changes through the server simulation.

import { useRef, useState } from 'react';
import { useQueryClient } from '@tanstack/react-query';
import { createSalesDraft, issueSalesDraft, recordSalesCollection, resetSalesSimulation, updateSalesDraft } from '../../api/client.js';
import { isDraft, isSharedRecord, salesKeys } from './useSalesQueries.js';

export const failureMessage = (error, fallback) => (error.response?.status === 422 && typeof error.response.data?.detail === 'string' ? error.response.data.detail : fallback);

export function useSalesActions() {
  const queryClient = useQueryClient();
  const [draftSave, setDraftSave] = useState({ state: 'idle' });
  // One save per draft runs at a time and only the newest waiting edit follows, so
  // requests cannot arrive out of order and overwrite newer typing.
  const saves = useRef(new Map());

  const refresh = () => queryClient.invalidateQueries({ predicate: isSharedRecord });
  // Totals follow each saved edit. The draft itself is already current in the cache.
  const refreshAfterEdit = () => queryClient.invalidateQueries({ predicate: (query) => isSharedRecord(query) && !isDraft(query) });

  const runSaves = async (draft, entry) => {
    while (entry.waiting) {
      const change = entry.waiting;
      entry.waiting = null;
      try {
        await updateSalesDraft(draft.reference, change);
      } catch (error) {
        entry.waiting ??= change;
        setDraftSave({ state: 'failed', reference: draft.reference, message: failureMessage(error, 'This draft could not be saved, so your latest changes are only on this page.') });
        return false;
      }
    }
    setDraftSave({ state: 'saved', reference: draft.reference });
    refreshAfterEdit();
    return true;
  };
  const startSaves = (draft, entry) => {
    entry.running ??= runSaves(draft, entry).finally(() => { entry.running = null; });
    return entry.running;
  };
  const changeDraft = (draft) => {
    queryClient.setQueryData(salesKeys.draft(draft.account_code, draft.period), { draft });
    const entry = saves.current.get(draft.reference) ?? {};
    saves.current.set(draft.reference, entry);
    entry.waiting = { issue_date: draft.issue_date, due_date: draft.due_date, lines: draft.lines };
    setDraftSave({ state: 'saving', reference: draft.reference });
    startSaves(draft, entry);
  };
  const retryDraftSave = (draft) => {
    const entry = saves.current.get(draft.reference);
    if (!entry?.waiting) return;
    setDraftSave({ state: 'saving', reference: draft.reference });
    startSaves(draft, entry);
  };

  const createDraft = async (accountCode, period) => {
    const draft = await createSalesDraft(accountCode, period);
    queryClient.setQueryData(salesKeys.draft(accountCode, period), { draft });
    refreshAfterEdit();
    return draft;
  };

  // Waits for saved edits first, so the invoice is what the preview showed.
  const issueDraft = async (draft) => {
    const entry = saves.current.get(draft.reference);
    if (entry?.running) await entry.running;
    if (entry?.waiting && !(await startSaves(draft, entry))) throw new Error('Unsaved draft');
    const invoice = await issueSalesDraft(draft.reference);
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
    saves.current.clear();
    setDraftSave({ state: 'idle' });
    queryClient.resetQueries({ predicate: isSharedRecord });
    return status;
  };

  return { draftSave, changeDraft, retryDraftSave, createDraft, issueDraft, recordCollection, reset };
}
