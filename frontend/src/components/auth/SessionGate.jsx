// Decides whether a session exists before any workspace mounts, so nothing is
// requested on behalf of someone who has not signed in. Leaving a session clears
// cached query results, so the next login in this browser cannot see them.
//
// Every tab in a browser profile shares one session cookie, so signing in elsewhere
// replaces this page's login. Requests name the login shown, so the server refuses
// them for anyone else; a refusal or a return to the window then checks who is
// signed in now, and stops this page rather than act for the wrong account.

import { useCallback, useEffect, useRef, useState } from 'react';
import { useQueryClient } from '@tanstack/react-query';
import { getSession, SESSION_CHECK_EVENT, SESSION_ENDED_EVENT, setExpectedUser, signOut } from '../../api/client.js';
import LoginPage from './LoginPage.jsx';

const ENDED_NOTICE = 'Your session has ended. Sign in again to continue.';
const CHANGED_NOTICE = 'This browser is now signed in as a different user, from another tab or window, so this page stopped before acting for the wrong account. Sign in again to continue. To keep two logins open at once, use a private window for one of them.';

const samePrincipal = (left, right) => left.username === right.username && left.role === right.role && left.account_code === right.account_code;

export function SignedInAs({ session, onSignOut, labelClassName = '' }) {
  const label = session.role === 'partner' ? `Partner account ${session.account_code}` : `Internal · ${session.username}`;
  return <div className="flex items-center gap-3 text-xs text-gray-600">
    <span className={`whitespace-nowrap ${labelClassName}`}>Signed in as {label}</span>
    <button type="button" className="min-h-9 rounded-md border border-gray-300 bg-white px-3 py-1 text-sm text-gray-900" onClick={onSignOut}>Sign out</button>
  </div>;
}

export default function SessionGate({ children }) {
  const queryClient = useQueryClient();
  const [session, setSession] = useState();
  const [loadFailed, setLoadFailed] = useState(false);
  const [notice, setNotice] = useState('');
  const [signOutFailed, setSignOutFailed] = useState(false);
  // The login this page shows, read by checks that outlive a render.
  const shownRef = useRef();

  // Requests name the login being shown from the moment it is shown, so the server
  // refuses anything this page sends after another tab signs in as someone else.
  const show = useCallback((next, message = '') => {
    shownRef.current = next;
    setExpectedUser(next?.username ?? null);
    setNotice(message);
    setSession(next);
  }, []);

  const load = useCallback(() => {
    setLoadFailed(false);
    return getSession().then((next) => show(next)).catch(() => setLoadFailed(true));
  }, [show]);

  useEffect(() => { load(); }, [load]);

  const leaveWith = useCallback((message) => {
    if (shownRef.current) show(null, message);
    queryClient.clear();
  }, [queryClient, show]);

  useEffect(() => {
    const ended = () => leaveWith(ENDED_NOTICE);
    window.addEventListener(SESSION_ENDED_EVENT, ended);
    return () => window.removeEventListener(SESSION_ENDED_EVENT, ended);
  }, [leaveWith]);

  // One check at a time; a request made during one runs once it finishes, so a
  // refusal that arrives mid-check is still checked.
  const checking = useRef(false);
  const checkAgain = useRef(false);
  useEffect(() => {
    const check = async () => {
      if (checking.current) {
        checkAgain.current = true;
        return;
      }
      checking.current = true;
      try {
        do {
          checkAgain.current = false;
          const shown = shownRef.current;
          if (!shown) return;
          let current;
          try {
            current = await getSession();
          } catch {
            return; // An unreachable server says nothing about who is signed in.
          }
          // A sign-in or sign-out here while asking makes the answer out of date.
          if (shownRef.current !== shown) continue;
          if (current === null) leaveWith(ENDED_NOTICE);
          else if (!samePrincipal(current, shown)) leaveWith(CHANGED_NOTICE);
        } while (checkAgain.current);
      } finally {
        checking.current = false;
      }
    };
    const checkWhenVisible = () => { if (document.visibilityState === 'visible') check(); };
    window.addEventListener(SESSION_CHECK_EVENT, check);
    window.addEventListener('focus', check);
    document.addEventListener('visibilitychange', checkWhenVisible);
    return () => {
      window.removeEventListener(SESSION_CHECK_EVENT, check);
      window.removeEventListener('focus', check);
      document.removeEventListener('visibilitychange', checkWhenVisible);
    };
  }, [leaveWith]);

  const signedIn = (next) => {
    queryClient.clear();
    show(next);
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
    show(null);
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
