// Local diagnostics only: names contain an opaque request ID, never request data.
export function startExplanationTiming() {
  const id = globalThis.crypto?.randomUUID?.();
  if (!id || !globalThis.performance?.mark) return null;
  performance.mark(`explanation:${id}:start`);
  return id;
}

export function measureExplanationTiming(id, phase) {
  if (!id || !globalThis.performance?.measure) return;
  const start = `explanation:${id}:start`;
  const name = `explanation:${id}:${phase}`;
  if (!performance.getEntriesByName(start).length || performance.getEntriesByName(name).length) return;
  performance.measure(name, start);
  if (phase === 'rendered-complete') performance.clearMarks(start);
}
