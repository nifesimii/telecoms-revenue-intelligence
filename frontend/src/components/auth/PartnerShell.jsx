// A partner's whole application: their own account and nothing internal. It mounts
// no internal workspace and requests no internal data.

import { SignedInAs } from './SessionGate.jsx';
import PartnerOrdering from '../sales/PartnerOrdering.jsx';

export default function PartnerShell({ session, onSignOut }) {
  return <div className="flex h-full flex-col">
    <header className="app-header shrink-0 bg-white">
      <div className="mx-auto flex max-w-7xl flex-wrap items-center justify-between gap-x-6 gap-y-3 px-4 py-3 sm:px-6 lg:px-8">
        <div className="flex min-w-0 items-center gap-3">
          <span aria-hidden="true" className="h-8 w-1 shrink-0 rounded-sm bg-mtn-yellow" />
          <span className="text-base font-semibold tracking-tight text-gray-900">FBB <span className="max-sm:hidden">Trade </span>Partner<span className="max-sm:hidden"> Intelligence</span></span>
        </div>
        <div className="flex flex-wrap items-center gap-3 sm:gap-5">
          <span role="status" className="inline-flex items-center gap-1.5 whitespace-nowrap text-xs text-amber-700"><span className="h-1.5 w-1.5 rounded-full bg-amber-500" /><span className="max-sm:sr-only">Synthetic demonstration</span><span aria-hidden="true" className="sm:hidden">Demo</span></span>
          <SignedInAs session={session} onSignOut={onSignOut} labelClassName="max-sm:sr-only" />
        </div>
      </div>
    </header>
    <main aria-label="Partner Sales" className="w-full flex-1 overflow-auto">
      <PartnerOrdering />
    </main>
  </div>;
}
