// Decides whether a session exists before any workspace mounts, so nothing is
// requested on behalf of someone who has not signed in. Leaving a session clears
// cached query results, so the next login in this browser cannot see them.

import { useCallback, useEffect, useState } from 'react';
import { useQueryClient } from '@tanstack/react-query';
import { getSession, SESSION_ENDED_EVENT, signOut } from '../../api/client.js';
import LoginPage from './LoginPage.jsx';

const ENDED_NOTICE = 'Your session has ended. Sign in again to continue.';

export function SignedInAs({ session, onSignOut }) {
  const label = session.role === 'partner' ? `Partner account ${session.account_code}` : `Internal · ${session.username}`;
  return <div className="flex items-center gap-3 text-xs text-gray-600">
    <span className="whitespace-nowrap">Signed in as {label}</span>
    <button type="button" className="min-h-9 rounded-md border border-gray-300 bg-white px-3 py-1 text-sm text-gray-900" onClick={onSignOut}>Sign out</button>
  </div>;
}

export default function SessionGate({ children }) {
  const queryClient = useQueryClient();
  const [session, setSession] = useState();
  const [loadFailed, setLoadFailed] = useState(false);
  const [notice, setNotice] = useState('');
  const [signOutFailed, setSignOutFailed] = useState(false);

  const load = useCallback(() => {
    setLoadFailed(false);
    return getSession().then(setSession).catch(() => setLoadFailed(true));
  }, []);

  useEffect(() => { load(); }, [load]);

  useEffect(() => {
    const ended = () => {
      setSession((current) => {
        if (current) setNotice(ENDED_NOTICE);
        return null;
      });
      queryClient.clear();
    };
    window.addEventListener(SESSION_ENDED_EVENT, ended);
    return () => window.removeEventListener(SESSION_ENDED_EVENT, ended);
  }, [queryClient]);

  const signedIn = (next) => {
    queryClient.clear();
    setNotice('');
    setSession(next);
  };

  const leave = async () => {
    setSignOutFailed(false);
    try {
      await signOut();
    } catch {
      setSignOutFailed(true);
      return;
    }
    queryClient.clear();
    setNotice('');
    setSession(null);
  };

  if (loadFailed) {
    return <main className="flex h-full flex-col items-center justify-center gap-3 p-6 text-sm text-gray-700">
      <p role="alert">The application could not be reached. This does not mean you are signed out.</p>
      <button type="button" className="min-h-11 rounded-md border border-gray-300 bg-white px-4 py-2" onClick={load}>Try again</button>
    </main>;
  }
  if (session === undefined) return <main className="flex h-full items-center justify-center p-6 text-sm text-gray-600"><p role="status">Loading…</p></main>;
  if (session === null) return <LoginPage notice={notice} onSignedIn={signedIn} />;
  return <>
    {signOutFailed && <p role="alert" className="bg-red-50 px-4 py-2 text-sm text-red-800">Sign out failed, so you are still signed in. Please try again.</p>}
    {children(session, leave)}
  </>;
}
