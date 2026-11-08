// Refresh and reset, at the top of the Finance tab. Both children sit directly in the
// header's row, so the confirmation can take the full width beneath it.

import { useState } from 'react';
import { quantityLabel } from './salesDisplay.js';
import { useSalesSimulationStatus } from './useSalesQueries.js';

// Asks first, in place: a browser dialog would stop the presentation, and an
// accidental reset would lose the rehearsal so far.
export default function SimulationControls({ onRefresh, onReset }) {
  const status = useSalesSimulationStatus().data;
  const [confirming, setConfirming] = useState(false);
  const [resetting, setResetting] = useState(false);
  const [failed, setFailed] = useState(false);
  const cancel = () => {
    setConfirming(false);
    setFailed(false);
    requestAnimationFrame(() => document.getElementById('sales-reset')?.focus());
  };
  const reset = async () => {
    setResetting(true);
    setFailed(false);
    try {
      await onReset();
      setConfirming(false);
    } catch {
      setFailed(true);
    } finally {
      setResetting(false);
    }
  };
  const open = () => {
    setConfirming(true);
    requestAnimationFrame(() => document.getElementById('sales-reset-keep')?.focus());
  };
  const contents = status ? `${quantityLabel(status.invoices, 'invoice')}, ${quantityLabel(status.collections, 'collection')} and ${quantityLabel(status.orders, 'partner order')}` : 'records';
  return <>
    <div className="flex flex-wrap items-center gap-2">
      {!confirming && <button id="sales-reset" type="button" className="overview-button sales-quiet" onClick={open}>Reset simulation</button>}
      <button type="button" className="overview-button" onClick={onRefresh}>Refresh</button>
    </div>
    {confirming && <div role="group" aria-label="Confirm simulation reset" className="overview-surface sales-card-pad w-full">
      <p className="text-sm">Reset the simulation to its starting point for everyone using it? This discards the current {contents}, along with every partner's draft order, restores the example invoices, and clears the invoice and partner filters. Recorded commission, payment and inventory evidence, other workspaces and the reporting month stay as they are.</p>
      {failed && <p role="alert" className="sales-alert mt-3">The simulation could not be reset, so nothing has changed. Try again.</p>}
      <div className="sales-actions mt-4">
        <button type="button" className="overview-button overview-primary" disabled={resetting} onClick={reset}>Reset to starting point</button>
        <button id="sales-reset-keep" type="button" className="overview-button" disabled={resetting} onClick={cancel}>Keep simulation</button>
      </div>
    </div>}
  </>;
}
