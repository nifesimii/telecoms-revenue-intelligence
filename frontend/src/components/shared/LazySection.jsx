import { Component, Suspense } from 'react';

class LoadErrorBoundary extends Component {
  state = { failed: false };
  static getDerivedStateFromError() { return { failed: true }; }
  render() {
    if (this.state.failed) return <div role="alert" className="p-6">{this.props.label} could not load. <button className="underline" onClick={() => window.location.reload()}>Reload to retry</button></div>;
    return this.props.children;
  }
}

// Keep a delayed/failed chunk local to its section. Hidden workspaces must not
// announce a fallback or replace the currently visible workspace.
export default function LazySection({ children, label, active = true }) {
  return <LoadErrorBoundary label={label}>
    <Suspense fallback={active ? <p role="status" className="p-6">Loading {label}…</p> : null}>
      {children}
    </Suspense>
  </LoadErrorBoundary>;
}
