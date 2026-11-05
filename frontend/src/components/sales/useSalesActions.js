// Partner Sales changes through the server simulation.

import { useRef, useState } from 'react';
import { useQueryClient } from '@tanstack/react-query';
import { createSalesDraft, issueSalesDraft, recordSalesCollection, resetSalesSimulation, updateSalesDraft } from '../../api/client.js';
import { isDraftQuery, isSharedQuery, salesKeys } from './useSalesQueries.js';

// The server refused a change to a record that changed elsewhere or is gone. Nothing was overwritten.
export const isRefusal = (error) => [404, 409].includes(error.response?.status);

export const failureMessage = (error, fallback) => (error.response?.status === 422 && typeof error.response.data?.detail === 'string' ? error.response.data.detail : fallback);

export function useSalesActions() {
  const queryClient = useQueryClient();
  // Per draft, so working on one account leaves another's warning in place.
  const [saveStates, setSaveStates] = useState({});
  const setSaveState = (reference, state) => setSaveStates((current) => ({ ...current, [reference]: state }));
  const forgetSaveState = (reference) => setSaveStates(({ [reference]: _forgotten, ...others }) => others);
  // One save per draft runs at a time and only the newest waiting edit follows, so
  // requests cannot arrive out of order and overwrite newer typing.
  const saves = useRef(new Map());

  const refresh = () => queryClient.invalidateQueries({ predicate: isSharedQuery });
  // Totals follow each saved edit. The draft itself is already current in the cache.
  const refreshAfterEdit = () => queryClient.invalidateQueries({ predicate: (query) => isSharedQuery(query) && !isDraftQuery(query) });

  const runSaves = async (draft, entry) => {
    while (entry.waiting) {
      const change = entry.waiting;
      entry.waiting = null;
      try {
        const saved = await updateSalesDraft(draft.reference, { token: entry.token, ...change });
        entry.token = saved.token;
        queryClient.setQueryData(salesKeys.draft(draft.account_code, draft.period), (current) => (current?.draft?.reference === saved.reference ? { draft: { ...current.draft, token: saved.token } } : current));
      } catch (error) {
        entry.waiting ??= change;
        entry.failure = error;
        entry.refused = isRefusal(error);
        setSaveState(draft.reference, entry.refused ? { state: 'refused' } : { state: 'failed', message: failureMessage(error, 'This draft could not be saved, so your latest changes are only on this page.') });
        return false;
      }
    }
    setSaveState(draft.reference, { state: 'saved' });
    refreshAfterEdit();
    return true;
  };
  const startSaves = (draft, entry) => {
    entry.running ??= runSaves(draft, entry).finally(() => { entry.running = null; });
    return entry.running;
  };
  // Each save answers with the token the next must send. An editor keeps its first
  // token, so it stays tied to the version it loaded, not one that arrives later.
  const changeDraft = (draft) => {
    const entry = saves.current.get(draft.reference) ?? { token: draft.token };
    saves.current.set(draft.reference, entry);
    queryClient.setQueryData(salesKeys.draft(draft.account_code, draft.period), { draft: { ...draft, token: entry.token } });
    entry.waiting = { issue_date: draft.issue_date, due_date: draft.due_date, lines: draft.lines };
    entry.latest = entry.waiting;
    // Asking again cannot succeed, so typing stays on this page until Load latest.
    if (entry.refused) return;
    setSaveState(draft.reference, { state: 'saving' });
    startSaves(draft, entry);
  };
  const retryDraftSave = (draft) => {
    const entry = saves.current.get(draft.reference);
    if (!entry?.waiting) return;
    setSaveState(draft.reference, { state: 'saving' });
    startSaves(draft, entry);
  };

  // An editor reopened over edits not yet saved shows them, because they are what
  // would be saved and issued, whatever the server's copy now says.
  const withUnsavedEdits = (draft) => {
    const entry = saves.current.get(draft.reference);
    return entry?.running || entry?.waiting ? { ...draft, ...entry.latest } : draft;
  };

  // A newly opened editor starts from what it just read, not from finished saves.
  const forgetFinishedSaves = (reference) => {
    const entry = saves.current.get(reference);
    if (entry && !entry.running && !entry.waiting) saves.current.delete(reference);
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
    if (entry?.waiting && !(await startSaves(draft, entry))) throw entry.failure;
    const invoice = await issueSalesDraft(draft.reference, entry?.token ?? draft.token);
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
    setSaveStates({});
    queryClient.resetQueries({ predicate: isSharedQuery });
    return status;
  };

  // After a refusal: replaces the refused record with the server's, which is the point
  // at which its unsaved edits are discarded. Other drafts keep theirs.
  const loadLatestDraft = (draft) => {
    saves.current.delete(draft.reference);
    forgetSaveState(draft.reference);
    refreshAfterEdit();
    return queryClient.resetQueries({ queryKey: salesKeys.draft(draft.account_code, draft.period) });
  };
  const loadLatestInvoice = (reference) => {
    refreshAfterEdit();
    return queryClient.resetQueries({ queryKey: salesKeys.invoiceAnyPage(reference) });
  };

  const saveStateOf = (reference) => saveStates[reference] ?? { state: 'idle' };

  return { saveStateOf, changeDraft, retryDraftSave, withUnsavedEdits, forgetFinishedSaves, loadLatestDraft, loadLatestInvoice, createDraft, issueDraft, recordCollection, reset };
}
