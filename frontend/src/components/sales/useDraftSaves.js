// Saving draft edits through the server simulation as they are typed.

import { useRef, useState } from 'react';
import { useQueryClient } from '@tanstack/react-query';
import { updateSalesDraft } from '../../api/client.js';
import { describeFailure } from './salesDisplay.js';
import { salesKeys } from './useSalesQueries.js';

export function useDraftSaves(onSaved) {
  const queryClient = useQueryClient();
  // Per draft, so working on one account leaves another's warning in place.
  const [saveStates, setSaveStates] = useState({});
  const setSaveState = (reference, state) => setSaveStates((current) => ({ ...current, [reference]: state }));
  // One save per draft runs at a time and only the newest waiting edit follows, so
  // requests cannot arrive out of order and overwrite newer typing.
  const saves = useRef(new Map());

  const runSaves = async (draft, entry) => {
    while (entry.waiting) {
      const change = entry.waiting;
      entry.waiting = null;
      try {
        const saved = await updateSalesDraft(draft.reference, { token: entry.token, ...change });
        entry.token = saved.token;
        queryClient.setQueryData(salesKeys.draft(draft.account_code, draft.period), (current) => (current?.draft?.reference === saved.reference ? { draft: { ...current.draft, token: saved.token } } : current));
      } catch (error) {
        const failure = describeFailure(error, 'This draft could not be saved, so your latest changes are only on this page.');
        entry.waiting ??= change;
        entry.failure = error;
        entry.refused = failure.refused;
        setSaveState(draft.reference, failure.refused ? { state: 'refused' } : { state: 'failed', message: failure.message });
        return false;
      }
    }
    setSaveState(draft.reference, { state: 'saved' });
    onSaved();
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

  // Saves every waiting edit and answers with the token of the last one, or throws
  // what stopped them.
  const finishSaves = async (draft) => {
    const entry = saves.current.get(draft.reference);
    if (entry?.running) await entry.running;
    if (entry?.waiting && !(await startSaves(draft, entry))) throw entry.failure;
    return entry?.token ?? draft.token;
  };

  const discardSaves = (reference) => {
    saves.current.delete(reference);
    setSaveStates(({ [reference]: _discarded, ...others }) => others);
  };
  const discardAllSaves = () => {
    saves.current.clear();
    setSaveStates({});
  };

  const saveStateOf = (reference) => saveStates[reference] ?? { state: 'idle' };

  return { saveStateOf, changeDraft, retryDraftSave, withUnsavedEdits, forgetFinishedSaves, finishSaves, discardSaves, discardAllSaves };
}
