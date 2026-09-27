import { useQuery, useQueryClient } from '@tanstack/react-query';
import { runAuditModule } from '../../api/client.js';

const RUN_KEY = ['audit-replacement'];

// Keep the operation with the application query client, beyond period and
// navigation remounts. The synchronous cache guard also blocks double clicks.
export default function useAuditReplacement() {
  const queryClient = useQueryClient();
  const { data: replacement } = useQuery({
    queryKey: RUN_KEY, queryFn: () => null, initialData: null,
    enabled: false, gcTime: Infinity,
  });

  async function run(module, period) {
    if (queryClient.getQueryData(RUN_KEY)?.status === 'pending') return;
    const scope = { module, period };
    queryClient.setQueryData(RUN_KEY, { ...scope, status: 'pending' });
    let outcome;
    try {
      const result = await runAuditModule(module, period);
      outcome = { ...scope, status: 'success', result };
    } catch {
      outcome = { ...scope, status: 'unknown' };
    }
    // A failed response may still have replaced evidence on the server.
    await Promise.allSettled(['audit-records', 'audit-evidence', 'audit-breakdown'].map(
      (key) => queryClient.invalidateQueries({ queryKey: [key] }),
    ));
    queryClient.setQueryData(RUN_KEY, outcome);
  }

  return { replacement, run };
}
