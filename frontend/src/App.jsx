// Top-level shell. Owns:
//   * the view switcher (Overview / Commission / Activation / Inventory / Payment)
//   * the global reporting period selector (shared across all five panels)
//   * the data-mode badge (live Presto vs sample CSVs) driven by /health
//   * a pending-prompt slot so the Overview can launch a templated chat
//
// Period state lives in <PeriodProvider> so switching tabs preserves the
// user's selection — see context/PeriodContext.jsx.

import { useCallback, useEffect, useState } from 'react';
import ChatInterface from './components/ChatInterface.jsx';
import ActivationIntelligencePanel from './components/activation/ActivationIntelligencePanel.jsx';
import AssuranceStatusPanel from './components/assurance/AssuranceStatusPanel.jsx';
import InventoryIntelligencePanel from './components/inventory/InventoryIntelligencePanel.jsx';
import PaymentIntelligencePanel from './components/payment/PaymentIntelligencePanel.jsx';
import AuditTrailPanel from './components/audit/AuditTrailPanel.jsx';
import { PeriodProvider, usePeriod } from './context/PeriodContext.jsx';
import { getHealth } from './api/client.js';
import { formatPeriod } from './lib/format.js';

const VIEWS = [
  { id: 'overview', label: 'Overview' },
  { id: 'commission', label: 'Commission Intelligence' },
  { id: 'activation', label: 'Activation Intelligence' },
  { id: 'inventory', label: 'Inventory Intelligence' },
  { id: 'payment', label: 'Payment Intelligence' },
  { id: 'audit', label: 'Audit Trails' },
];

function DataModeBadge() {
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

  if (mode === null) return null;

  const cfg = {
    sample: { dot: 'bg-emerald-500', label: 'Sample data', tone: 'text-gray-500' },
    live: { dot: 'bg-amber-500', label: 'Live Presto', tone: 'text-amber-700' },
    unknown: { dot: 'bg-gray-400', label: 'API unreachable', tone: 'text-red-600' },
  }[mode];

  return (
    <span className={`inline-flex items-center gap-1.5 text-xs ${cfg.tone}`}>
      <span className={`w-1.5 h-1.5 rounded-full ${cfg.dot}`} />
      {cfg.label}
    </span>
  );
}

function GlobalPeriodSelect() {
  const { periods, period, setPeriod, loading } = usePeriod();

  return (
    <label className="flex items-center gap-2 text-xs text-gray-600">
      <span className="uppercase tracking-wide text-gray-500">Period</span>
      <select
        value={period}
        onChange={(e) => setPeriod(e.target.value)}
        disabled={loading || periods.length === 0}
        className="text-sm border border-gray-300 rounded-md px-2 py-1 bg-white focus:outline-none focus:ring-2 focus:ring-mtn-yellow focus:border-mtn-yellow disabled:opacity-50"
      >
        {periods.length === 0 && <option value="">—</option>}
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
function _writeViewToUrl(view) {
  if (typeof window === 'undefined') return;
  const url = new URL(window.location.href);
  if (url.searchParams.get('view') === view) return;
  url.searchParams.set('view', view);
  window.history.replaceState({}, '', url.toString());
}

function Shell() {
  const [view, setView] = useState(_readViewFromUrl);
  // Track which panels have been visited. Once mounted, a panel stays in the
  // DOM and is shown/hidden via CSS — preventing re-fetches on every tab switch.
  const [mounted, setMounted] = useState(() => ({ [_readViewFromUrl()]: true }));
  const [pendingPrompt, setPendingPrompt] = useState('');

  const switchView = useCallback((v) => {
    setMounted((m) => (m[v] ? m : { ...m, [v]: true }));
    setView(v);
    _writeViewToUrl(v);
  }, []);

  useEffect(() => {
    _writeViewToUrl(view);
  }, [view]);

  const askClaude = (text) => {
    setPendingPrompt(text);
    switchView('commission');
  };

  // 'h-full' when active, 'hidden' (display:none) when not — sibling panels
  // don't stack because display:none removes them from layout flow entirely.
  const panelClass = (id) => (view === id ? 'h-full' : 'hidden');

  return (
    <div className="h-full flex flex-col">
      <div className="flex items-center gap-3 px-4 py-2 border-b border-gray-200 bg-white">
        <div className="w-1.5 h-7 bg-mtn-yellow rounded-sm mr-1" />
        <span className="text-sm font-semibold tracking-tight text-gray-800 mr-3">
          FBB Trade Partner Intelligence
        </span>
        <div className="flex items-center gap-1 bg-gray-100 rounded-lg p-1">
          {VIEWS.map((v) => (
            <button
              key={v.id}
              onClick={() => switchView(v.id)}
              className={`px-3 py-1.5 text-sm rounded-md transition ${
                view === v.id
                  ? 'bg-white text-gray-900 shadow-sm font-semibold'
                  : 'text-gray-600 hover:text-gray-900'
              }`}
            >
              {v.label}
            </button>
          ))}
        </div>
        <div className="ml-auto flex items-center gap-4">
          <GlobalPeriodSelect />
          <DataModeBadge />
        </div>
      </div>

      <div className="flex-1 overflow-hidden">
        {mounted.overview && (
          <div className={panelClass('overview')}>
            <AssuranceStatusPanel onNavigate={switchView} onAsk={askClaude} />
          </div>
        )}
        {mounted.commission && (
          <div className={panelClass('commission')}>
            <ChatInterface
              pendingPrompt={pendingPrompt}
              onPromptConsumed={() => setPendingPrompt('')}
            />
          </div>
        )}
        {mounted.activation && (
          <div className={panelClass('activation')}>
            <ActivationIntelligencePanel />
          </div>
        )}
        {mounted.inventory && (
          <div className={panelClass('inventory')}>
            <InventoryIntelligencePanel onAsk={askClaude} />
          </div>
        )}
        {mounted.payment && (
          <div className={panelClass('payment')}>
            <PaymentIntelligencePanel onAsk={askClaude} />
          </div>
        )}
        {mounted.audit && (
          <div className={panelClass('audit')}>
            <AuditTrailPanel />
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
