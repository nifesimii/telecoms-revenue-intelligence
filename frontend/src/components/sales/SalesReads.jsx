// Bounded reads and the failure messages every Partner Sales screen shows the same way.

import { useState } from 'react';
import useQuery from '../../hooks/useWorkspaceQuery.js';
import PaginationControls from '../shared/PaginationControls.jsx';
import { formatMinorNGN } from '../../lib/format.js';
import { describeFailure } from './salesDisplay.js';

const SMALLEST_PAGE = 25;

export const displayAmount = (minor) => (minor === null ? 'Unavailable' : formatMinorNGN(minor));

// One bounded page of an in-browser set. A new scope starts at the first page; a
// set that shrinks falls back to its last page.
export function useBoundedPage(items, scope, headingId) {
  const [limit, setLimit] = useState(SMALLEST_PAGE);
  const [position, setPosition] = useState({ scope, offset: 0 });
  const wanted = position.scope === scope ? position.offset : 0;
  const offset = Math.min(wanted, Math.max(0, Math.floor((items.length - 1) / limit) * limit));
  // Record the correction, so changing back or regrowing never revives an old page.
  if (position.scope !== scope || position.offset !== offset) setPosition({ scope, offset });
  const visible = items.slice(offset, offset + limit);
  return {
    visible,
    controls: <PageControls pagination={{ total: items.length, returned: visible.length, offset, limit, has_more: offset + visible.length < items.length }} headingId={headingId}
      onOffsetChange={(next) => setPosition({ scope, offset: next })} onLimitChange={(next) => { setLimit(next); setPosition({ scope, offset: 0 }); }} />,
  };
}

function PageControls({ pagination, headingId, onOffsetChange, onLimitChange }) {
  // Judged against the smallest size, so choosing a larger one cannot remove the control.
  if (pagination.total <= SMALLEST_PAGE && !pagination.offset) return null;
  // Previous/Next can disable themselves on arrival, so focus moves to the results.
  const focusResults = () => requestAnimationFrame(() => document.getElementById(headingId)?.focus());
  return <div className="sales-pagination"><PaginationControls pagination={pagination} pageSize={pagination.limit}
    onOffsetChange={(next) => { onOffsetChange(next); focusResults(); }} onPageSizeChange={onLimitChange} /></div>;
}

// Reads one page from the server. A new scope starts at the first page, and the
// server moves a page past the end of a shrunken set back to its last. Recording that
// move means a set that regrows never revives the old page. A placeholder still
// describes the previous request, so it says nothing about this one. A read outside
// the reporting-month workspaces, such as a partner's own orders, passes its own query hook.
export function usePagedQuery(scope, headingId, optionsFor, paginationOf, useRead = useQuery) {
  const [limit, setLimit] = useState(SMALLEST_PAGE);
  const [position, setPosition] = useState({ scope, offset: 0 });
  const offset = position.scope === scope ? position.offset : 0;
  if (position.scope !== scope) setPosition({ scope, offset });
  const query = useRead(optionsFor({ limit, offset }));
  const pagination = query.data && paginationOf(query.data);
  if (pagination && !query.isPlaceholderData && pagination.offset !== offset) setPosition({ scope, offset: pagination.offset });
  return {
    query,
    controls: pagination && <PageControls pagination={pagination} headingId={headingId}
      onOffsetChange={(next) => setPosition({ scope, offset: next })} onLimitChange={(next) => { setLimit(next); setPosition({ scope, offset: 0 }); }} />,
  };
}

export function ReadState({ query, what }) {
  if (query.isError) {
    return <div role="alert" className="sales-alert">{query.error.response?.status === 404 ? `This ${what} is no longer in the simulation.` : `This ${what} could not be loaded.`}
      {query.error.response?.status !== 404 && <div className="mt-2"><button type="button" className="overview-button" onClick={() => query.refetch()}>Try again</button></div>}</div>;
  }
  return query.data ? null : <p role="status" className="sales-muted">Loading {what}…</p>;
}

// Shown in place of the failed action, on the same screen, so nothing is lost until
// the person chooses to load the latest records.
export function RefusedChange({ onLoadLatest }) {
  return <div role="alert" className="sales-alert">This changed elsewhere or the simulation was reset, so nothing here was applied. Loading the latest discards what you typed on this page.
    <div className="mt-2"><button type="button" className="overview-button" onClick={onLoadLatest}>Load latest</button></div></div>;
}

// What went wrong with the last attempt at an action. A refusal stays until the latest
// records are loaded, because no retry or edit can succeed before then; a message
// describes only the latest attempt.
export function useActionFailure() {
  const [failure, setFailure] = useState({ refused: false });
  return {
    failure,
    clearFailure: () => setFailure(({ refused }) => ({ refused })),
    noteFailure: (error, fallback) => setFailure(({ refused }) => {
      const latest = describeFailure(error, fallback);
      return { refused: refused || latest.refused, message: latest.message };
    }),
  };
}

export function ActionFailure({ failure, onLoadLatest }) {
  return <>
    {failure.message && <p role="alert" className="sales-alert">{failure.message}</p>}
    {failure.refused && <RefusedChange onLoadLatest={onLoadLatest} />}
  </>;
}
