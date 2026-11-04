// A partner's whole application: their own account and nothing internal. It mounts
// no internal workspace and requests no internal data.

import { SignedInAs } from './SessionGate.jsx';

export default function PartnerShell({ session, onSignOut }) {
  return <div className="flex h-full flex-col">
    <header className="app-header shrink-0 border-b border-gray-200 bg-white">
      <div className="mx-auto flex max-w-7xl flex-wrap items-center justify-between gap-x-6 gap-y-3 px-4 py-3 sm:px-6 lg:px-8">
        <div className="flex min-w-0 items-center gap-3">
          <span aria-hidden="true" className="h-8 w-1 shrink-0 rounded-sm bg-mtn-yellow" />
          <span className="text-base font-semibold tracking-tight text-gray-900">FBB Trade Partner Intelligence</span>
        </div>
        <div className="flex flex-wrap items-center gap-3 sm:gap-5">
          <span role="status" className="inline-flex items-center gap-1.5 whitespace-nowrap text-xs text-amber-700"><span className="h-1.5 w-1.5 rounded-full bg-amber-500" />Synthetic demonstration</span>
          <SignedInAs session={session} onSignOut={onSignOut} />
        </div>
      </div>
    </header>
    <main aria-label="Partner Sales" className="mx-auto w-full max-w-7xl flex-1 overflow-auto px-4 py-6 sm:px-6 lg:px-8">
      <h1 className="text-lg font-semibold text-gray-900">Partner Sales</h1>
      <p className="mt-2 text-sm text-gray-700">You are signed in to fictional account {session.account_code}. Ordering is not available yet.</p>
    </main>
  </div>;
}
