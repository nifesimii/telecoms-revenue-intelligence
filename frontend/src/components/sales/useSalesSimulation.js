// Partner Sales reads and changes through the server simulation. Every session
// sees the same records. The partner selected here is only this tab's view of them.

import { useRef, useState } from 'react';
import { useQueryClient } from '@tanstack/react-query';
import useQuery from '../../hooks/useWorkspaceQuery.js';
import { createSalesDraft, getSalesDraft, getSalesReference, getSalesStatus, issueSalesDraft, recordSalesCollection, resetSalesSimulation, updateSalesDraft } from '../../api/client.js';

const SELECTED_PARTNER_KEY = 'fbb.partner-sales.partner';
const SALES = 'partner-sales';
const draftQueryKey = (partnerCode, period) => [SALES, 'draft', partnerCode, period];

// A missing record will not appear by asking again.
export const retryUnlessMissing = (failures, error) => error.response?.status !== 404 && failures < 1;

export const useSalesReference = () => useQuery({ queryKey: [SALES, 'reference'], queryFn: ({ signal }) => getSalesReference(signal), staleTime: Infinity });
export const useSalesSimulationStatus = () => useQuery({ queryKey: [SALES, 'status'], queryFn: ({ signal }) => getSalesStatus(signal) });
export const useSalesDraft = (partnerCode, period) => useQuery({ queryKey: draftQueryKey(partnerCode, period), queryFn: ({ signal }) => getSalesDraft(partnerCode, period, signal), enabled: Boolean(partnerCode) });

function readSelectedPartner() {
  try {
    return window.sessionStorage.getItem(SELECTED_PARTNER_KEY) ?? '';
  } catch {
    return '';
  }
}

export function useSelectedPartner() {
  const [partnerCode, setPartnerCode] = useState(readSelectedPartner);
  const select = (next) => {
    setPartnerCode(next);
    try {
      if (next) window.sessionStorage.setItem(SELECTED_PARTNER_KEY, next);
      else window.sessionStorage.removeItem(SELECTED_PARTNER_KEY);
    } catch { /* The selection then lasts until this page refreshes. */ }
  };
  return [partnerCode, select];
}

const failureMessage = (error, fallback) => (error.response?.status === 422 && typeof error.response.data?.detail === 'string' ? error.response.data.detail : fallback);

export function useSalesActions() {
  const queryClient = useQueryClient();
  const [draftSave, setDraftSave] = useState({ state: 'idle' });
  // One save per draft runs at a time and only the newest waiting edit follows, so
  // requests cannot arrive out of order and overwrite newer typing.
  const saves = useRef(new Map());

  const isShared = ({ queryKey }) => queryKey[0] === SALES && queryKey[1] !== 'reference';
  const refresh = () => queryClient.invalidateQueries({ predicate: isShared });
  // Totals follow each saved edit. The draft itself is already current in the cache.
  const refreshAfterEdit = () => queryClient.invalidateQueries({ predicate: (query) => isShared(query) && query.queryKey[1] !== 'draft' });

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
    queryClient.setQueryData(draftQueryKey(draft.partner_code, draft.period), { draft });
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

  const createDraft = async (partnerCode, period) => {
    const draft = await createSalesDraft(partnerCode, period);
    queryClient.setQueryData(draftQueryKey(partnerCode, period), { draft });
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
    queryClient.resetQueries({ predicate: isShared });
    return status;
  };

  return { draftSave, changeDraft, retryDraftSave, createDraft, issueDraft, recordCollection, reset };
}

export { failureMessage };
