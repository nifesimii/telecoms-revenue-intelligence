import { useEffect, useId, useRef, useState } from 'react';
import useChat from '../../hooks/useChat.js';
import MessageBubble, { LoadingBubble } from '../MessageBubble.jsx';
import { measureExplanationTiming } from '../../lib/explanationTiming.js';
import { formatPeriod } from '../../lib/format.js';

export default function CommissionAssistant({ period, comparison, stream, account, inventoryScope, onInventoryScopeClear, prompt = '', onPromptConsumed, composerRequest }) {
  const questionId = useId();
  const findingsScope = inventoryScope?.kind === 'findings' ? inventoryScope : null;
  const scope = findingsScope
    ? `findings.${JSON.stringify([findingsScope.period, findingsScope.dealer_id, findingsScope.finding.module, findingsScope.finding.type, findingsScope.finding.product_code ?? null])}`
    : inventoryScope
    ? `inventory.${inventoryScope.period}.${inventoryScope.dealer_id}.${inventoryScope.product_code}`
    : `${period}.${comparison || 'none'}.${stream}.${account?.dealer_id || 'all'}`;
  const { messages, isLoading, error, sendMessage, clearChat, stopMessage, retryMessage, canRetry } = useChat({ scope });
  const [input, setInput] = useState('');
  const inputRef = useRef(null);
  const initialFindingPrompt = useRef(null);
  const composerRef = useRef(null);
  const threadRef = useRef(null);
  const context = findingsScope
    ? `Findings investigation for reporting period ${findingsScope.period}. Exact dealer account code ${findingsScope.dealer_id} (${findingsScope.dealer_name}); do not combine other accounts with the same name. Finding module ${findingsScope.finding.module}, type ${findingsScope.finding.type}.${findingsScope.finding.product_code ? ` Exact product code ${findingsScope.finding.product_code}.` : ''} Use the evidence and documented rules; distinguish missing evidence from confirmed discrepancies.`
    : inventoryScope
    ? `Inventory investigation for reporting period ${inventoryScope.period}, exact dealer ${inventoryScope.dealer_id} (${inventoryScope.dealer_name}), product ${inventoryScope.product_code} (${inventoryScope.product_name}). Use only this dealer/product scope. Confirm invoice coverage, purchase window and documented Inventory KB explanations; missing evidence does not prove missing purchases or commission owed. ${inventoryScope.scenario_label ? `Synthetic scenario: ${inventoryScope.scenario_label}; fictional purchase evidence is not verified operational evidence.` : ''}`
    : `Reporting period ${period}. ${comparison ? `Comparison period ${comparison}.` : 'No comparison period selected.'} ${account ? `Exact dealer account code ${account.dealer_id} (${account.dealer_name}); do not combine other accounts with the same name.` : 'Portfolio-level investigation.'} ${stream === 'orsc' ? 'Subscription review: subscription revenue is separate from recorded upstream subscription commission, settlement and outstanding amounts. Use get_orsc_summary for available evidence. Do not infer a commission rate or eligibility policy; the actual calculation policy has not been supplied. Missing commission evidence is unavailable, not zero.' : stream === 'payment' ? 'Payment settlement investigation. Use recorded payment and commission evidence; do not infer causes from aggregate differences.' : 'Activation commission.'}`;
  useEffect(() => {
    if (!prompt) return;
    initialFindingPrompt.current = prompt;
    setInput(prompt);
    onPromptConsumed?.();
    composerRef.current?.scrollIntoView({ block: 'center', behavior: 'instant' });
    inputRef.current?.focus({ preventScroll: true });
  }, [prompt, onPromptConsumed]);
  useEffect(() => {
    if (!composerRequest) return;
    // Each opener activation is a new request, including while already mounted.
    // Preserve a question the user has started editing.
    setInput((draft) => draft || composerRequest.prompt);
    composerRef.current?.scrollIntoView({ block: 'center', behavior: 'instant' });
    const focusTarget = inputRef.current?.disabled ? composerRef.current : inputRef.current;
    focusTarget?.focus({ preventScroll: true });
  }, [composerRequest]);
  useEffect(() => {
    if (threadRef.current) threadRef.current.scrollTop = threadRef.current.scrollHeight;
  }, [messages, isLoading]);
  useEffect(() => {
    const answer = messages.at(-1);
    if (!answer?.timingId || !answer.content || typeof requestAnimationFrame !== 'function') return;
    const frame = requestAnimationFrame(() => {
      if (!threadRef.current?.getClientRects().length) return;
      measureExplanationTiming(answer.timingId, 'first-visible-text');
      if (answer.status === 'complete') measureExplanationTiming(answer.timingId, 'rendered-complete');
    });
    return () => cancelAnimationFrame(frame);
  }, [messages]);
  function submit(event) {
    event.preventDefault();
    if (!input.trim() || isLoading) return;
    const explanation = findingsScope && initialFindingPrompt.current !== null && input.trim() === initialFindingPrompt.current.trim()
      ? { dealer_id: findingsScope.dealer_id, mon_period: findingsScope.period, finding: findingsScope.finding } : null;
    initialFindingPrompt.current = null;
    sendMessage(`${context}\n\n${input.trim()}`, inventoryScope?.period || period, explanation);
    setInput('');
  }
  const suggestions = findingsScope ? ['Explain the selected finding and identify the evidence still needed.'] : inventoryScope ? ['Explain this dealer-product Inventory comparison and identify the evidence still needed.'] : stream === 'payment' ? ['Explain this account’s recorded commission, paid amount and outstanding balance. State what remains unverified.'] : stream === 'orsc'
    ? ['Summarise subscription revenue, recorded commission, settlement and outstanding amounts. State any missing evidence.']
    : [comparison ? 'Explain the commission change by denomination between these periods.' : 'Explain the recorded commission breakdown.', 'Investigate zero-commission records using only documented KB causes. State what remains unverified.'];
  return <section className="overview-surface overflow-hidden min-w-0" aria-label={findingsScope ? 'Findings assistant' : inventoryScope ? 'Inventory assistant' : stream === 'payment' ? 'Payment assistant' : 'Commission assistant'}>
    <div className="p-5 border-b border-gray-200">
      <div className="flex justify-between gap-3 items-center"><h2 className="font-semibold">Ask about these figures</h2>{messages.length > 0 && <button className="text-xs underline" disabled={isLoading} onClick={clearChat}>Clear thread</button>}</div>
      <p className="text-xs text-gray-600 mt-2">{findingsScope ? `Findings · Account ${findingsScope.dealer_id}${findingsScope.finding.product_code ? ` · Product ${findingsScope.finding.product_code}` : ''}` : inventoryScope ? `Inventory · Account ${inventoryScope.dealer_id} · Product ${inventoryScope.product_code}` : account ? `Account ${account.dealer_id}` : 'All accounts'} · {formatPeriod(inventoryScope?.period || period)}{!inventoryScope && comparison ? ` vs ${formatPeriod(comparison)}` : ''} · {findingsScope ? `${findingsScope.finding.module} · ${findingsScope.finding.type.replaceAll('_', ' ').toLowerCase()}` : inventoryScope ? 'Inventory comparison' : stream === 'orsc' ? 'Subscriptions' : stream === 'payment' ? 'Payments' : 'Activation commission'}</p>
    </div>
    {inventoryScope && <button className="overview-button m-4 mb-0" onClick={onInventoryScopeClear}>Return to Commission assistant</button>}
    <div ref={threadRef} className="p-4 max-h-96 overflow-y-auto commission-conversation" aria-live="polite" aria-busy={isLoading}>
      {!messages.length && <><p className="text-sm text-gray-600 mb-4">Use the records as the starting point. Ask for an explanation when you need more context.</p>
        <div className="space-y-2">{suggestions.map((text) => <button key={text} className="overview-button text-left w-full" onClick={() => { setInput(text); inputRef.current?.focus(); }}>{text}</button>)}</div></>}
      {messages.map((message, i) => message.status === 'streaming' && !message.content ? null : <MessageBubble key={i} message={message} />)}
      {isLoading && <><p className="sr-only" role="status">Preparing an evidence-based answer…</p>{!messages.at(-1)?.content && <LoadingBubble />}</>}
    </div>
    {error && <p className="mx-4 mb-3 text-sm text-red-800" role="alert">The explanation could not be completed. Your figures remain available. {error}</p>}
    {canRetry && <button className="overview-button mx-4 mb-3" onClick={retryMessage}>Retry explanation</button>}
    <form ref={composerRef} tabIndex={-1} className="p-4 border-t border-gray-200" onSubmit={submit}>
      <label className="text-xs font-medium text-gray-600" htmlFor={questionId}>Your question</label>
      <textarea id={questionId} ref={inputRef} className="overview-select w-full mt-2 resize-y" rows={3} value={input} onChange={(e) => setInput(e.target.value)} placeholder="Ask about this account, its commission or the evidence…" disabled={isLoading} />
      <div className="flex flex-wrap justify-between items-center gap-3 mt-3"><p className="text-xs text-gray-500">AI explanation · verify against source evidence</p><span className="flex gap-2">{isLoading && <button type="button" className="overview-button" onClick={stopMessage}>Stop</button>}<button className="overview-button overview-primary" disabled={isLoading || !input.trim()}>{isLoading ? 'Working…' : 'Send question →'}</button></span></div>
    </form>
  </section>;
}
