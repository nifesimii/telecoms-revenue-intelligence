import { useEffect, useRef, useState } from 'react';
import { signIn } from '../../api/client.js';

function failureMessage(error) {
  const status = error.response?.status;
  if (status === 401) return 'Incorrect username or password.';
  if (status === 503) return 'Sign-in is not configured on this server. See the demo login setup in the README.';
  return 'Sign-in is unavailable right now. Please try again.';
}

export default function LoginPage({ notice, onSignedIn }) {
  const [username, setUsername] = useState('');
  const [password, setPassword] = useState('');
  const [error, setError] = useState('');
  const [busy, setBusy] = useState(false);
  const usernameInput = useRef(null);

  useEffect(() => { usernameInput.current?.focus(); }, []);

  const submit = async (event) => {
    event.preventDefault();
    setBusy(true);
    setError('');
    try {
      onSignedIn(await signIn(username, password));
    } catch (failure) {
      setError(failureMessage(failure));
      setPassword('');
      setBusy(false);
    }
  };

  const field = 'mt-1 block w-full min-h-11 rounded-md border border-gray-300 bg-white px-3 py-2 text-sm';
  return <main aria-label="Sign in" className="flex min-h-full items-center justify-center overflow-auto bg-gray-50 p-4">
    <div className="w-full max-w-sm rounded-lg border border-gray-200 bg-white p-6">
      <div className="flex items-center gap-3">
        <span aria-hidden="true" className="h-8 w-1 shrink-0 rounded-sm bg-mtn-yellow" />
        <h1 className="text-base font-semibold tracking-tight text-gray-900">Trade Partner Intelligence Platform</h1>
      </div>
      <p className="mt-3 rounded-md border border-amber-200 bg-amber-50 px-3 py-2 text-sm text-amber-900">Demonstration only. Partner Sales records are fictional and are not actual obligations.</p>
      {notice && <p role="status" className="mt-3 text-sm text-gray-700">{notice}</p>}
      <form className="mt-4 space-y-3" onSubmit={submit}>
        <label className="block text-sm text-gray-700">Username
          <input ref={usernameInput} className={field} name="username" autoComplete="username" required value={username} onChange={(event) => setUsername(event.target.value)} />
        </label>
        <label className="block text-sm text-gray-700">Password
          <input className={field} name="password" type="password" autoComplete="current-password" required value={password} onChange={(event) => setPassword(event.target.value)} />
        </label>
        {error && <p role="alert" className="text-sm text-red-800">{error}</p>}
        <button type="submit" disabled={busy} className="min-h-11 w-full rounded-md bg-gray-900 px-4 py-2 text-sm font-medium text-white disabled:opacity-60">{busy ? 'Signing in…' : 'Sign in'}</button>
      </form>
    </div>
  </main>;
}
