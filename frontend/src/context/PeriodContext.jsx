// App-wide period state.
//
// Fetches /periods once on mount, exposes the list and the currently-selected
// reporting period to every panel. Switching tabs no longer re-defaults the
// period: a finance user picking Oct 2024 in Commission Intelligence will see
// Oct 2024 still selected when they jump to Activation Intelligence.
//
// priorPeriod is the "compare against" value used by variance views; it
// defaults to the second-most-recent period.

import { createContext, useContext, useEffect, useState } from 'react';
import { getPeriods } from '../api/client.js';

const PeriodContext = createContext(null);

// Read ?period=YYYYMM from the URL on mount. Returns null if absent or malformed.
function _readPeriodFromUrl() {
  if (typeof window === 'undefined') return null;
  const p = new URLSearchParams(window.location.search).get('period');
  return p && /^\d{6}$/.test(p) ? p : null;
}

// Push ?period=YYYYMM into the URL without reloading. Uses replaceState so
// period changes don't pile up in browser history.
function _writePeriodToUrl(period) {
  if (typeof window === 'undefined' || !period) return;
  const url = new URL(window.location.href);
  if (url.searchParams.get('period') === period) return;
  url.searchParams.set('period', period);
  window.history.replaceState({}, '', url.toString());
}

export function PeriodProvider({ children }) {
  const [periods, setPeriods] = useState([]);
  // Seed period from URL if present, so the initial render reflects the
  // shared link instead of flickering through the default.
  const [period, setPeriod] = useState(() => _readPeriodFromUrl() || '');
  const [priorPeriod, setPriorPeriod] = useState('');
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);

  useEffect(() => {
    let cancelled = false;
    getPeriods()
      .then((data) => {
        if (cancelled) return;
        const ps = data.periods || [];
        setPeriods(ps);
        if (ps.length) {
          // If URL period is present and valid in this dataset, keep it.
          // Else fall back to the most recent period.
          setPeriod((cur) => (cur && ps.includes(cur) ? cur : ps[0]));
          setPriorPeriod((cur) => cur || ps[1] || ps[0]);
        }
      })
      .catch((e) => {
        if (!cancelled) setError(String(e?.message || e));
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, []);

  // Mirror the current period to the URL so links are shareable.
  useEffect(() => {
    if (period) _writePeriodToUrl(period);
  }, [period]);

  return (
    <PeriodContext.Provider
      value={{
        periods,
        period,
        setPeriod,
        priorPeriod,
        setPriorPeriod,
        loading,
        error,
      }}
    >
      {children}
    </PeriodContext.Provider>
  );
}

export function usePeriod() {
  const ctx = useContext(PeriodContext);
  if (!ctx) throw new Error('usePeriod() must be used inside <PeriodProvider>');
  return ctx;
}
