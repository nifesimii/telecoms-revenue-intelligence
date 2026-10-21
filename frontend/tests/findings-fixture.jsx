// Public component harness, served by Vite only during local browser regression checks.
import React, { useState } from 'react';
import { createRoot } from 'react-dom/client';
import CommissionAssistant from '../src/components/commission/CommissionAssistant.jsx';
import InvestigationQueue from '../src/components/assurance/InvestigationQueue.jsx';
import '../src/index.css';

function Fixture() {
  const [scope, setScope] = useState(null);
  const [prompt, setPrompt] = useState('');
  const [view, setView] = useState('queue');
  const [variant, setVariant] = useState('base');
  const [comparison, setComparison] = useState('202605');
  const [stream, setStream] = useState('activation');
  const period = variant === 'period' ? '202605' : '202606';
  const finding = { module: variant === 'module' ? 'commission' : 'inventory',
    type: variant === 'type' ? 'ZERO_COMMISSION_ACTIVATION' : 'INVENTORY_MISMATCH',
    product_code: variant === 'product' ? 'P2' : 'P1', description: 'Fixture evidence needs review.' };
  const row = { dealer_id: variant === 'dealer' ? '002' : '001', dealer_name: 'Fixture account',
    lead_finding: finding, finding_count: 1, severity: 'HIGH', amount_outstanding: null,
    modules: ['inventory'], module_findings: {} };
  const ask = (text, nextScope) => { setPrompt(text); setScope(nextScope); setView('assistant'); };
  return <main className="p-5 max-w-4xl mx-auto">
    <nav className="flex gap-3 mb-5 flex-wrap">
      <button onClick={() => setView('queue')}>Queue</button>
      <label>Fixture scope <select aria-label="Fixture scope" value={variant} onChange={(e) => { setVariant(e.target.value); setView('queue'); }}>
        {['base', 'dealer', 'period', 'module', 'type', 'product'].map((v) => <option key={v}>{v}</option>)}
      </select></label>
      <button onClick={() => setComparison(comparison ? '' : '202605')}>Change comparison</button>
      <button onClick={() => setStream(stream === 'activation' ? 'orsc' : 'activation')}>Change stream</button>
      <button onClick={() => ask('Investigate this Inventory comparison.', { period, dealer_id: '001', dealer_name: 'Fixture account', product_code: 'P1', product_name: 'Fixture product' })}>Inventory opener</button>
    </nav>
    {view === 'queue' ? <InvestigationQueue period={period} onAsk={ask} onNavigate={() => {}}
      data={{ items: [row], total: 1, limit: 25, affected_dealers: 1, finding_count: 1, cross_module_dealers: 0 }}
      busy={false} search="" setSearch={() => {}} severity="" setSeverity={() => {}} module="" setModule={() => {}} offset={0} setOffset={() => {}} />
      : <CommissionAssistant key={JSON.stringify(scope)} inventoryScope={scope} period={period} comparison={comparison} stream={stream}
        prompt={prompt} onPromptConsumed={() => setPrompt('')} onInventoryScopeClear={() => setScope(null)} />}
  </main>;
}
createRoot(document.getElementById('root')).render(<Fixture />);
