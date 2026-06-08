// Top-level routing-free shell: switches between the two intelligence views.
//   Commission Intelligence (Phase 1) — chat + dealer summary sidebar
//   Activation Intelligence (Phase 2) — period selector + 3 data tabs

import { useState } from 'react';
import ChatInterface from './components/ChatInterface.jsx';
import ActivationIntelligencePanel from './components/activation/ActivationIntelligencePanel.jsx';
import AssuranceStatusPanel from './components/assurance/AssuranceStatusPanel.jsx';
import InventoryIntelligencePanel from './components/inventory/InventoryIntelligencePanel.jsx';
import PaymentIntelligencePanel from './components/payment/PaymentIntelligencePanel.jsx';

const VIEWS = [
  { id: 'commission', label: 'Commission Intelligence' },
  { id: 'activation', label: 'Activation Intelligence' },
  { id: 'assurance', label: 'Assurance Status' },
  { id: 'inventory', label: 'Inventory Intelligence' },
  { id: 'payment', label: 'Payment Intelligence' },
];

export default function App() {
  const [view, setView] = useState('commission');

  return (
    <div className="h-full flex flex-col">
      <div className="flex items-center gap-2 px-4 py-2 border-b border-gray-200 bg-white">
        <div className="w-1.5 h-7 bg-mtn-yellow rounded-sm mr-2" />
        <span className="text-sm font-semibold tracking-tight text-gray-800 mr-4">
          FBB Trade Partner Intelligence
        </span>
        <div className="flex items-center gap-1 bg-gray-100 rounded-lg p-1">
          {VIEWS.map((v) => (
            <button
              key={v.id}
              onClick={() => setView(v.id)}
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
      </div>

      <div className="flex-1 overflow-hidden">
        {view === 'commission' && <ChatInterface />}
        {view === 'activation' && <ActivationIntelligencePanel />}
        {view === 'assurance' && <AssuranceStatusPanel />}
        {view === 'inventory' && <InventoryIntelligencePanel />}
        {view === 'payment' && <PaymentIntelligencePanel />}
      </div>
    </div>
  );
}
