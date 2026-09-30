import { useQuery } from '@tanstack/react-query';
import { useWorkspaceActive } from '../context/WorkspaceActivityContext.jsx';
import { usePeriod } from '../context/PeriodContext.jsx';

// Preserve TanStack's shared bounded cache while disabling hidden observers,
// including focus/reconnect/invalidation reads. Never reuse another month's
// placeholder figures under the current reporting-period label.
export default function useWorkspaceQuery(options) {
  const active = useWorkspaceActive();
  const { period, loading } = usePeriod();
  const { enabled = true, placeholderData, ...rest } = options;
  return useQuery({
    ...rest,
    meta: { ...options.meta, workspacePeriod: period },
    enabled: (query) => !loading && active && (typeof enabled === 'function' ? enabled(query) : enabled),
    placeholderData: typeof placeholderData === 'function'
      ? (previous, query) => query?.meta?.workspacePeriod === period ? placeholderData(previous, query) : undefined
      : placeholderData,
  });
}
