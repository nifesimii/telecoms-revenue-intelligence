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

export function PeriodProvider({ children }) {
  const [periods, setPeriods] = useState([]);
  const [period, setPeriod] = useState('');
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
          setPeriod((cur) => cur || ps[0]);
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
