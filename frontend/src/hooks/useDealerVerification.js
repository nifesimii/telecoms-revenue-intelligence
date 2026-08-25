// Shared hook used by every "Verify" expandable across the app
// (PaymentExceptions, InventoryComparison, Assurance findings).
//
// Module-level cache: the first caller for a given period fires the two
// requests and stores the resolved maps. Every subsequent caller with the
// same period gets the cached data synchronously — no duplicate fetches
// across panels or across sub-tab remounts.

import { useEffect, useState } from 'react';
import { getActivationSummary, getDealers } from '../api/client.js';

// { [period]: { aMap, dMap } | Promise<{ aMap, dMap }> }
const _cache = {};

function _buildMaps(acts, dealers) {
  const aMap = {};
  for (const a of Array.isArray(acts) ? acts : []) {
    if (a.dealer_id) aMap[a.dealer_id] = a;
  }
  const dMap = {};
  for (const d of Array.isArray(dealers) ? dealers : []) {
    if (d.dealer_id) dMap[d.dealer_id] = d;
  }
  return { aMap, dMap };
}

export default function useDealerVerification(period) {
  const [activationByDealer, setActivationByDealer] = useState({});
  const [dealerByCode, setDealerByCode] = useState({});
  const [loading, setLoading] = useState(false);

  useEffect(() => {
    if (!period) return;
    let cancelled = false;

    const cached = _cache[period];

    // Already resolved — apply immediately, no loading state needed.
    if (cached && !(cached instanceof Promise)) {
      setActivationByDealer(cached.aMap);
      setDealerByCode(cached.dMap);
      return;
    }

    setLoading(true);

    // First caller for this period: create the promise and cache it so
    // concurrent callers share the same in-flight request.
    if (!cached) {
      _cache[period] = Promise.all([
        getActivationSummary(period).catch(() => []),
        getDealers(period).catch(() => []),
      ]).then(([acts, dealers]) => {
        const maps = _buildMaps(acts, dealers);
        _cache[period] = maps; // replace promise with resolved data
        return maps;
      });
    }

    // All callers (including the first) attach to the same promise.
    _cache[period].then(({ aMap, dMap }) => {
      if (cancelled) return;
      setActivationByDealer(aMap);
      setDealerByCode(dMap);
    }).finally(() => {
      if (!cancelled) setLoading(false);
    });

    return () => {
      cancelled = true;
    };
  }, [period]);

  return { activationByDealer, dealerByCode, loading };
}
