import { useCallback, useState } from 'react';
import { getDealerVerification } from '../api/client.js';

const cache = new Map();
const inflight = new Map();

export default function useLazyDealerVerification(period) {
  const [records, setRecords] = useState({});
  const [loading, setLoading] = useState({});
  const load = useCallback(async (dealerId) => {
    if (!period || !dealerId) return null;
    const key = `${period}:${dealerId}`;
    if (cache.has(key)) {
      const value = cache.get(key);
      setRecords((cur) => ({ ...cur, [dealerId]: value }));
      return value;
    }
    setLoading((cur) => ({ ...cur, [dealerId]: true }));
    if (!inflight.has(key)) {
      inflight.set(key, getDealerVerification(dealerId, period)
        .then((value) => { cache.set(key, value); return value; })
        .finally(() => inflight.delete(key)));
    }
    try {
      const value = await inflight.get(key);
      setRecords((cur) => ({ ...cur, [dealerId]: value }));
      return value;
    } finally {
      setLoading((cur) => ({ ...cur, [dealerId]: false }));
    }
  }, [period]);
  return { records, loading, load };
}
