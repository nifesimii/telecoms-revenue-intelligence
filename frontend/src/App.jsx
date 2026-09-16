// Top-level shell. Owns:
//   * the view switcher (Overview / Commission / Activation / Inventory / Payment)
//   * the global reporting period selector (shared across all six panels)
//   * the data-mode badge (live Presto vs sample CSVs) driven by /health
//   * a pending-prompt slot so the Overview can launch a templated chat
//
// Period state lives in <PeriodProvider> so switching tabs preserves the
// user's selection — see context/PeriodContext.jsx.

import { useCallback, useEffect, useRef, useState } from 'react';
import CommissionWorkspace from './components/commission/CommissionWorkspace.jsx';
import ActivationIntelligencePanel from './components/activation/ActivationIntelligencePanel.jsx';
import AssuranceStatusPanel from './components/assurance/AssuranceStatusPanel.jsx';
import InventoryIntelligencePanel from './components/inventory/InventoryIntelligencePanel.jsx';
import PaymentIntelligencePanel from './components/payment/PaymentIntelligencePanel.jsx';
import AuditTrailPanel from './components/audit/AuditTrailPanel.jsx';
import FinancialHealthWorkspace from './components/financial/FinancialHealthWorkspace.jsx';
import { PeriodProvider, usePeriod } from './context/PeriodContext.jsx';
import { getHealth } from './api/client.js';
import { formatPeriod } from './lib/format.js';

const VIEWS = [
  { id: 'overview', label: 'Overview' },
  { id: 'commission', label: 'Commission' },
  { id: 'activation', label: 'Activation' },
  { id: 'inventory', label: 'Inventory' },
  { id: 'payment', label: 'Payments' },
  { id: 'financial-health', label: 'Financial Health' },
  { id: 'audit', label: 'Audit Trails' },
];

function DataModeBadge({ financialDemo = false }) {
  const [mode, setMode] = useState(null); // null | 'sample' | 'live' | 'unknown'

  useEffect(() => {
    let cancelled = false;
    getHealth()
      .then((data) => {
        if (cancelled) return;
        setMode(data?.sample_data_mode ? 'sample' : 'live');
      })
      .catch(() => !cancelled && setMode('unknown'));
    return () => {
      cancelled = true;
    };
  }, []);

  const cfg = financialDemo ? { dot: 'bg-amber-500', label: 'Synthetic demonstration', tone: 'text-amber-700' } : {
    checking: { dot: 'bg-gray-400', label: 'Checking data mode…', tone: 'text-gray-600' },
    sample: { dot: 'bg-emerald-500', label: 'Sample data', tone: 'text-gray-500' },
    live: { dot: 'bg-amber-500', label: 'Live Presto', tone: 'text-amber-700' },
    unknown: { dot: 'bg-gray-400', label: 'API unreachable', tone: 'text-red-600' },
  }[mode || 'checking'];

  return (
    <span role="status" className={`inline-flex items-center gap-1.5 whitespace-nowrap text-xs ${cfg.tone} ${financialDemo ? 'print:hidden' : ''}`}>
      <span className={`w-1.5 h-1.5 rounded-full ${cfg.dot}`} />
      {cfg.label}
    </span>
  );
}

function GlobalPeriodSelect() {
  const { periods, period, setPeriod, loading, error } = usePeriod();

  return (
    <label className="flex min-w-0 flex-col gap-1 text-xs text-gray-600 sm:flex-row sm:items-center sm:gap-2">
      <span className="whitespace-nowrap">Reporting period</span>
      <select
        value={period}
        onChange={(e) => setPeriod(e.target.value)}
        disabled={loading || periods.length === 0}
        className="w-28 min-w-0 max-w-full min-h-9 text-sm border border-gray-300 rounded-md px-2 py-1 bg-white disabled:text-gray-500"
      >
        {periods.length === 0 && <option value="">{loading ? 'Loading…' : error ? 'Unavailable' : 'No periods'}</option>}
        {periods.map((p) => (
          <option key={p} value={p}>
            {formatPeriod(p)}
          </option>
        ))}
      </select>
    </label>
  );
}

// Read ?view= from the URL, fall back to the landing view.
function _readViewFromUrl() {
  if (typeof window === 'undefined') return 'overview';
  const v = new URLSearchParams(window.location.search).get('view');
  const valid = VIEWS.some((x) => x.id === v);
  return valid ? v : 'overview';
}

// Push ?view= into the URL without reloading.
function _writeViewToUrl(view, push = false, context) {
  if (typeof window === 'undefined') return;
  const url = new URL(window.location.href);
  if (url.searchParams.get('view') === view && !push && window.history.state?.fbbWorkspace) return;
  url.searchParams.set('view', view);
  window.history[push ? 'pushState' : 'replaceState']({ ...window.history.state,
    fbbWorkspace: { view, context } }, '', url.toString());
}

function Shell() {
  const [view, setView] = useState(_readViewFromUrl);
  // Track which panels have been visited. Once mounted, a panel stays in the
  // DOM and is shown/hidden via CSS — preventing re-fetches on every tab switch.
  const [mounted, setMounted] = useState(() => ({ [_readViewFromUrl()]: true }));
  const [pendingPrompt, setPendingPrompt] = useState('');
  const [navigation, setNavigation] = useState(() => {
    const entry = window.history.state?.fbbWorkspace;
    return entry?.view === _readViewFromUrl() ? { [entry.view]: entry.context } : {};
  });
  const navigationRef = useRef(navigation);
  navigationRef.current = navigation;
  const revision = useRef(window.history.state?.fbbWorkspace?.context?.revision || 0);
  // DOM focus targets remain in memory; history stores only serializable context.
  const auditOrigins = useRef(new Map());
  const activeView = useRef(view);
  activeView.current = view;
  const auditOrigin = useRef(null);

  const switchView = useCallback((v, context) => {
    if (v === activeView.current && !context) return;
    const nextContext = context ? { ...context, revision: ++revision.current } : navigationRef.current[v];
    if (v === 'audit' && context && activeView.current !== 'audit') {
      auditOrigins.current.set(nextContext.revision, { view: activeView.current, focus: document.activeElement });
    }
    if (v === 'audit') auditOrigin.current = auditOrigins.current.get(nextContext?.revision) || null;
    if (context) setNavigation((current) => ({ ...current, [v]: nextContext }));
    setMounted((m) => (m[v] ? m : { ...m, [v]: true }));
    setView(v);
    _writeViewToUrl(v, true, nextContext);
  }, []);

  useEffect(() => {
    _writeViewToUrl(_readViewFromUrl(), false, navigationRef.current[_readViewFromUrl()]);
    const restoreView = () => {
      const next = _readViewFromUrl();
      const entry = window.history.state?.fbbWorkspace;
      const context = entry?.view === next ? entry.context : undefined;
      revision.current = Math.max(revision.current, context?.revision || 0);
      setNavigation((current) => current[next]?.revision === context?.revision
        ? current : { ...current, [next]: context });
      setMounted((current) => ({ ...current, [next]: true }));
      setView(next);
      if (activeView.current === 'audit' && auditOrigin.current?.view === next) {
        const target = auditOrigin.current.focus;
        requestAnimationFrame(() => {
          if (target?.isConnected && target.getClientRects().length) target.focus();
        });
      }
      if (next === 'audit') auditOrigin.current = auditOrigins.current.get(context?.revision) || null;
    };
    window.addEventListener('popstate', restoreView);
    return () => window.removeEventListener('popstate', restoreView);
  }, []);

  const askClaude = (text) => {
    setPendingPrompt(text);
    switchView('commission');
  };

  // 'h-full' when active, 'hidden' (display:none) when not — sibling panels
  // don't stack because display:none removes them from layout flow entirely.
  const panelClass = (id) => (view === id ? 'h-full' : 'hidden');

  return (
    <div className="h-full flex flex-col">
      <header className="app-header shrink-0 border-b border-gray-200 bg-white">
        <div className="mx-auto max-w-7xl px-4 sm:px-6 lg:px-8">
          <div className="flex flex-wrap items-center justify-between gap-x-6 gap-y-3 py-3">
            <div className="flex min-w-0 items-center gap-3">
              <span aria-hidden="true" className="w-1 h-8 bg-mtn-yellow rounded-sm shrink-0" />
              <span className="text-base font-semibold tracking-tight text-gray-900">
                FBB Trade Partner Intelligence
              </span>
            </div>
            <div className="flex w-full min-w-0 items-center justify-between gap-3 sm:w-auto sm:gap-5">
              <GlobalPeriodSelect />
              <div className="shrink-0"><DataModeBadge financialDemo={view === 'financial-health'} /></div>
            </div>
          </div>
          <label className="flex items-center gap-3 pb-3 lg:hidden text-sm text-gray-600">
            Workspace
            <select className="flex-1 min-w-0 min-h-11 border border-gray-300 rounded-md px-3 py-2 bg-white" value={view} onChange={(e) => switchView(e.target.value)}>
              {VIEWS.map((v) => <option key={v.id} value={v.id}>{v.label}</option>)}
            </select>
          </label>
          <nav aria-label="Workspace" className="hidden lg:flex items-center gap-7">
            {VIEWS.map((v) => (
              <button
                key={v.id}
                onClick={() => switchView(v.id)}
                aria-current={view === v.id ? 'page' : undefined}
                className={`min-h-11 border-b-4 py-2 text-sm transition-colors ${
                  view === v.id
                    ? 'border-mtn-yellow text-gray-900 font-bold'
                    : 'border-transparent text-gray-600 hover:text-gray-900 hover:border-gray-300'
                }`}
              >
                {v.label}
              </button>
            ))}
          </nav>
        </div>
      </header>

      <div className="flex-1 overflow-hidden">
        {view === 'financial-health' && <FinancialHealthWorkspace />}
        {mounted.overview && (
          <div className={panelClass('overview')}>
            <AssuranceStatusPanel onNavigate={switchView} onAsk={askClaude} />
          </div>
        )}
        {mounted.commission && (
          <div className={panelClass('commission')}>
            <CommissionWorkspace
              key={navigation.commission?.revision}
              navigation={navigation.commission}
              onNavigate={switchView}
              pendingPrompt={pendingPrompt}
              onPromptConsumed={() => setPendingPrompt('')}
            />
          </div>
        )}
        {mounted.activation && (
          <div className={panelClass('activation')}>
            <ActivationIntelligencePanel key={navigation.activation?.revision} navigation={navigation.activation} onNavigate={switchView} />
          </div>
        )}
        {mounted.inventory && (
          <div className={panelClass('inventory')}>
            <InventoryIntelligencePanel key={navigation.inventory?.revision} navigation={navigation.inventory} onAsk={askClaude} />
          </div>
        )}
        {mounted.payment && (
          <div className={panelClass('payment')}>
            <PaymentIntelligencePanel key={navigation.payment?.revision} navigation={navigation.payment} onNavigate={switchView} onAsk={askClaude} />
          </div>
        )}
        {mounted.audit && (
          <div className={panelClass('audit')}>
            <AuditTrailPanel key={navigation.audit?.revision} navigation={navigation.audit}
              onReturn={auditOrigin.current ? () => {
                const origin = auditOrigin.current;
                switchView(origin.view);
                requestAnimationFrame(() => { if (origin.focus?.isConnected) origin.focus.focus(); });
              } : undefined} />
          </div>
        )}
      </div>
    </div>
  );
}

export default function App() {
  return (
    <PeriodProvider>
      <Shell />
    </PeriodProvider>
  );
}
