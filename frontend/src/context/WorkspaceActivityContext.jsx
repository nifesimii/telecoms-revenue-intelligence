import { createContext, useContext, useLayoutEffect, useRef } from 'react';
import { PeriodContext, usePeriod } from './PeriodContext.jsx';

const WorkspaceActivityContext = createContext(true);

// Keep visited workspaces mounted, but only deliver reporting-period changes to
// the visible workspace. A return sees the current global period immediately.
export function WorkspaceActivityBoundary({ active, children }) {
  const current = usePeriod();
  const committed = useRef(current);
  useLayoutEffect(() => {
    if (active) committed.current = current;
  }, [active, current]);
  return <WorkspaceActivityContext.Provider value={active}>
    <PeriodContext.Provider value={active ? current : committed.current}>
      {children}
    </PeriodContext.Provider>
  </WorkspaceActivityContext.Provider>;
}

export function useWorkspaceActive() {
  return useContext(WorkspaceActivityContext);
}
