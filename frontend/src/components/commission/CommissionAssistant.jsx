import { useEffect, useId, useRef, useState } from 'react';
import useChat from '../../hooks/useChat.js';
import MessageBubble, { LoadingBubble } from '../MessageBubble.jsx';
import { formatPeriod } from '../../lib/format.js';
import { subscriptionContext } from './subscriptionPresentation.js';

export default function CommissionAssistant({ period, comparison, stream, account, inventoryScope, onInventoryScopeClear, subscription, prompt = '', onPromptConsumed }) {
  const questionId = useId();
  const scope = inventoryScope
    ? `inventory.${inventoryScope.period}.${inventoryScope.dealer_id}.${inventoryScope.product_code}`
    : `${period}.${comparison || 'none'}.${stream}.${account?.dealer_id || 'all'}${subscription ? `.${subscription.synthetic ? 'synthetic' : 'live'}` : ''}`;
  const { messages, isLoading, error, sendMessage, clearChat } = useChat({ scope });
  const [input, setInput] = useState('');
  const inputRef = useRef(null);
  const threadRef = useRef(null);
  const context = subscription ? subscriptionContext(subscription, period, account) : inventoryScope
    ? `Inventory investigation for reporting period ${inventoryScope.period}, exact dealer ${inventoryScope.dealer_id} (${inventoryScope.dealer_name}), product ${inventoryScope.product_code} (${inventoryScope.product_name}). Use only this dealer/product scope. Confirm invoice coverage, purchase window and documented Inventory KB explanations; missing evidence does not prove missing purchases or commission owed. ${inventoryScope.scenario_label ? `Synthetic scenario: ${inventoryScope.scenario_label}; fictional purchase evidence is not verified operational evidence.` : ''}`
    : `Reporting period ${period}. ${comparison ? `Comparison period ${comparison}.` : 'No comparison period selected.'} ${account ? `Exact dealer account code ${account.dealer_id} (${account.dealer_name}); do not combine other accounts with the same name.` : 'Portfolio-level investigation.'} ${stream === 'orsc' ? 'Subscription commission review: amounts are recorded subscription revenue, not confirmed commission payable.' : stream === 'payment' ? 'Payment settlement investigation. Use recorded payment and commission evidence; do not infer causes from aggregate differences.' : 'Activation commission.'}`;
  useEffect(() => {
    if (!prompt) return;
    setInput(prompt);
    onPromptConsumed?.();
    inputRef.current?.focus();
  }, [prompt, onPromptConsumed]);
  useEffect(() => {
    if (threadRef.current) threadRef.current.scrollTop = threadRef.current.scrollHeight;
  }, [messages, isLoading]);
  function submit(event) {
    event.preventDefault();
    if (!input.trim() || isLoading) return;
    sendMessage(`${context}\n\n${input.trim()}`, inventoryScope?.period || period);
    setInput('');
  }
  const suggestions = subscription ? (subscription.commission_available ? ['Explain the simulated commission and dealer expectation variance using the supplied device evidence.', 'Which earned commissions are overdue? Keep missing payment evidence unknown.'] : ['Summarise recorded subscription revenue and state which commission evidence is unavailable.']) : inventoryScope ? ['Explain this dealer-product Inventory comparison and identify the evidence still needed.'] : stream === 'payment' ? ['Explain this account’s recorded commission, paid amount and outstanding balance. State what remains unverified.'] : stream === 'orsc'
    ? ['Summarise recorded subscription revenue and zero-amount records.']
    : [comparison ? 'Explain the commission change by denomination between these periods.' : 'Explain the recorded commission breakdown.', 'Investigate zero-commission records using only documented KB causes. State what remains unverified.'];
  return <section className="overview-surface overflow-hidden min-w-0" aria-label={inventoryScope ? 'Inventory assistant' : stream === 'payment' ? 'Payment assistant' : 'Commission assistant'}>
    <div className="p-5 border-b border-gray-200">
      <div className="flex justify-between gap-3 items-center"><h2 className="font-semibold">Ask about these figures</h2>{messages.length > 0 && <button className="text-xs underline" disabled={isLoading} onClick={clearChat}>Clear thread</button>}</div>
      <p className="text-xs text-gray-600 mt-2">{inventoryScope ? `Inventory · Account ${inventoryScope.dealer_id} · Product ${inventoryScope.product_code}` : account ? `Account ${account.dealer_id}` : 'All accounts'} · {formatPeriod(inventoryScope?.period || period)}{!inventoryScope && comparison ? ` vs ${formatPeriod(comparison)}` : ''} · {inventoryScope ? 'Inventory comparison' : stream === 'orsc' ? 'Subscription commission' : stream === 'payment' ? 'Payments' : 'Activation commission'}</p>
      {subscription && <p className="text-xs text-gray-700 mt-3">{subscription.synthetic ? `Synthetic demonstration. ${subscription.policy_label}` : 'Recorded revenue only. Subscription commission is unavailable.'}</p>}
    </div>
    {inventoryScope && <button className="overview-button m-4 mb-0" onClick={onInventoryScopeClear}>Return to Commission assistant</button>}
    <div ref={threadRef} className="p-4 max-h-96 overflow-y-auto commission-conversation" aria-live="polite" aria-busy={isLoading}>
      {!messages.length && <><p className="text-sm text-gray-600 mb-4">Use the records as the starting point. Ask for an explanation when you need more context.</p>
        <div className="space-y-2">{suggestions.map((text) => <button key={text} className="overview-button text-left w-full" onClick={() => { setInput(text); inputRef.current?.focus(); }}>{text}</button>)}</div></>}
      {messages.map((message, i) => <MessageBubble key={i} message={message} />)}
      {isLoading && <><p className="sr-only" role="status">Preparing an evidence-based answer…</p><LoadingBubble /></>}
    </div>
    {error && <p className="mx-4 mb-3 text-sm text-red-800" role="alert">The explanation could not be completed. Your figures remain available. {error}</p>}
    <form className="p-4 border-t border-gray-200" onSubmit={submit}>
      <label className="text-xs font-medium text-gray-600" htmlFor={questionId}>Your question</label>
      <textarea id={questionId} ref={inputRef} className="overview-select w-full mt-2 resize-y" rows={3} value={input} onChange={(e) => setInput(e.target.value)} placeholder="Ask about this account, its commission or the evidence…" disabled={isLoading} />
      <div className="flex flex-wrap justify-between items-center gap-3 mt-3"><p className="text-xs text-gray-500">AI explanation · verify against source evidence</p><button className="overview-button overview-primary" disabled={isLoading || !input.trim()}>{isLoading ? 'Working…' : 'Send question →'}</button></div>
    </form>
  </section>;
}
