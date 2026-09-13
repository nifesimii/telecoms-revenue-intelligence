import { useEffect, useId, useRef, useState } from 'react';
import useChat from '../../hooks/useChat.js';
import MessageBubble, { LoadingBubble } from '../MessageBubble.jsx';
import { formatPeriod } from '../../lib/format.js';

export default function CommissionAssistant({ period, comparison, stream, account, prompt = '', onPromptConsumed }) {
  const questionId = useId();
  const scope = `${period}.${comparison || 'none'}.${stream}.${account?.dealer_id || 'all'}`;
  const { messages, isLoading, error, sendMessage, clearChat } = useChat({ scope });
  const [input, setInput] = useState('');
  const inputRef = useRef(null);
  const threadRef = useRef(null);
  const context = `Reporting period ${period}. ${comparison ? `Comparison period ${comparison}.` : 'No comparison period selected.'} ${account ? `Exact dealer account code ${account.dealer_id} (${account.dealer_name}); do not combine other accounts with the same name.` : 'Portfolio-level investigation.'} ${stream === 'orsc' ? 'ORSC subscription revenue, not commission payable.' : stream === 'payment' ? 'Payment settlement investigation. Use recorded payment and commission evidence; do not infer causes from aggregate differences.' : 'Activation commission.'}`;
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
    sendMessage(`${context}\n\n${input.trim()}`, period);
    setInput('');
  }
  const suggestions = stream === 'payment' ? ['Explain this account’s recorded commission, paid amount and outstanding balance. State what remains unverified.'] : stream === 'orsc'
    ? ['Summarise recorded ORSC revenue and zero-amount records.']
    : [comparison ? 'Explain the commission change by denomination between these periods.' : 'Explain the recorded commission breakdown.', 'Investigate zero-commission records using only documented KB causes. State what remains unverified.'];
  return <section className="overview-surface overflow-hidden min-w-0" aria-label={stream === 'payment' ? 'Payment assistant' : 'Commission assistant'}>
    <div className="p-5 border-b border-gray-200">
      <div className="flex justify-between gap-3 items-center"><h2 className="font-semibold">Ask about these figures</h2>{messages.length > 0 && <button className="text-xs underline" disabled={isLoading} onClick={clearChat}>Clear thread</button>}</div>
      <p className="text-xs text-gray-600 mt-2">{account ? `Account ${account.dealer_id}` : 'All accounts'} · {formatPeriod(period)}{comparison ? ` vs ${formatPeriod(comparison)}` : ''} · {stream === 'orsc' ? 'ORSC' : stream === 'payment' ? 'Payments' : 'Activation commission'}</p>
    </div>
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
