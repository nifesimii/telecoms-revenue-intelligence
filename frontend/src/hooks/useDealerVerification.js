// Shared hook used by every "Verify" expandable across the app
// (PaymentExceptions, InventoryComparison, Assurance findings).
//
// One fetch per period change: /activations/summary + /dealers. Returns
// dealer-keyed lookups so child components can render verification panels
// instantly on expand without per-row API calls.

import { useEffect, useState } from 'react';
import { getActivationSummary, getDealers } from '../api/client.js';

export default function useDealerVerification(period) {
  const [activationByDealer, setActivationByDealer] = useState({});
  const [dealerByCode, setDealerByCode] = useState({});
  const [loading, setLoading] = useState(false);

  useEffect(() => {
    if (!period) return;
    let cancelled = false;
    setLoading(true);
    Promise.all([
      getActivationSummary(period).catch(() => []),
      getDealers(period).catch(() => []),
    ])
      .then(([acts, dealers]) => {
        if (cancelled) return;
        const aMap = {};
        for (const a of Array.isArray(acts) ? acts : []) {
          if (a.dealer_id) aMap[a.dealer_id] = a;
        }
        const dMap = {};
        for (const d of Array.isArray(dealers) ? dealers : []) {
          if (d.dealer_id) dMap[d.dealer_id] = d;
        }
        setActivationByDealer(aMap);
        setDealerByCode(dMap);
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, [period]);

  return { activationByDealer, dealerByCode, loading };
}
