// Main layout component.
//
// Header:    "FBB Commission Intelligence" with MTN-yellow accent bar.
// Sidebar (25%): period dropdown + DealerSummaryTable; both refresh when
//                the period selection changes.
// Main (75%):    scrollable message thread, empty-state suggestions,
//                textarea + send button at the bottom.

import { useCallback, useEffect, useRef, useState } from 'react';
import { getPeriods, getDealers } from '../api/client.js';
import useChat from '../hooks/useChat.js';
import MessageBubble, { LoadingBubble } from './MessageBubble.jsx';
import DealerSummaryTable from './DealerSummaryTable.jsx';

const SUGGESTIONS = [
  (period) =>
    `Summarise dealer commissions for ${period || 'the latest period'}`,
  () => 'Which dealers have zero-commission records and why?',
  (period) => `Show me the ORSC summary for ${period || 'the latest period'}`,
  () => "Why did Kashmir Global's commission change this month?",
];

export default function ChatInterface() {
  const {
    messages,
    isLoading,
    error,
    selectedPeriod,
    setSelectedPeriod,
    sendMessage,
    clearChat,
  } = useChat();

  const [periods, setPeriods] = useState([]);
  const [dealers, setDealers] = useState([]);
  const [dealersLoading, setDealersLoading] = useState(false);
  const [inputText, setInputText] = useState('');
  const threadRef = useRef(null);

  // Load periods once on mount; default selectedPeriod to the most recent.
  useEffect(() => {
    let cancelled = false;
    getPeriods()
      .then((data) => {
        if (cancelled) return;
        const ps = data.periods || [];
        setPeriods(ps);
        if (ps.length && !selectedPeriod) setSelectedPeriod(ps[0]);
      })
      .catch(() => {
        /* Silent — period dropdown just stays empty. Error surfaces on /chat too. */
      });
    return () => {
      cancelled = true;
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  // Reload dealers any time the selected period changes.
  useEffect(() => {
    let cancelled = false;
    setDealersLoading(true);
    getDealers(selectedPeriod || null)
      .then((rows) => {
        if (!cancelled) setDealers(Array.isArray(rows) ? rows : []);
      })
      .catch(() => {
        if (!cancelled) setDealers([]);
      })
      .finally(() => {
        if (!cancelled) setDealersLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, [selectedPeriod]);

  // Auto-scroll thread to the bottom whenever messages or loading state change.
  useEffect(() => {
    const el = threadRef.current;
    if (el) el.scrollTop = el.scrollHeight;
  }, [messages, isLoading]);

  const onKeyDown = useCallback(
    (e) => {
      if (e.key === 'Enter' && !e.shiftKey) {
        e.preventDefault();
        if (!isLoading && inputText.trim()) {
          const text = inputText;
          setInputText('');
          sendMessage(text);
        }
      }
    },
    [inputText, isLoading, sendMessage],
  );

  const onSubmit = useCallback(() => {
    if (!isLoading && inputText.trim()) {
      const text = inputText;
      setInputText('');
      sendMessage(text);
    }
  }, [inputText, isLoading, sendMessage]);

  const emptyThread = messages.length === 0;

  return (
    <div className="h-full flex flex-col bg-gray-50 text-gray-800">
      {/* ----- Header ----- */}
      <header className="flex items-center gap-3 px-4 py-3 border-b border-gray-200 bg-white">
        <div className="w-1.5 h-8 bg-mtn-yellow rounded-sm" />
        <h1 className="text-base font-semibold tracking-tight">
          FBB Commission Intelligence
        </h1>
        <div className="ml-auto flex items-center gap-2 text-xs text-gray-500">
          <span className="inline-flex items-center gap-1.5">
            <span className="w-1.5 h-1.5 rounded-full bg-emerald-500" />
            Sample data mode
          </span>
          {messages.length > 0 && (
            <button
              onClick={clearChat}
              className="ml-3 text-gray-500 hover:text-gray-800 hover:underline"
            >
              Clear chat
            </button>
          )}
        </div>
      </header>

      {/* ----- Body: sidebar + thread ----- */}
      <div className="flex-1 flex overflow-hidden">
        {/* Sidebar */}
        <aside className="w-1/4 min-w-[260px] max-w-[360px] border-r border-gray-200 bg-white flex flex-col overflow-hidden">
          <div className="p-3 border-b border-gray-100">
            <label className="block text-[11px] uppercase tracking-wide text-gray-500 mb-1">
              Reporting period
            </label>
            <select
              value={selectedPeriod}
              onChange={(e) => setSelectedPeriod(e.target.value)}
              className="w-full text-sm border border-gray-300 rounded-md px-2 py-1.5 bg-white focus:outline-none focus:ring-2 focus:ring-mtn-yellow focus:border-mtn-yellow"
            >
              {periods.length === 0 && <option value="">—</option>}
              {periods.map((p) => (
                <option key={p} value={p}>
                  {p}
                </option>
              ))}
            </select>
            <p className="mt-2 text-[11px] text-gray-500 leading-snug">
              Chat questions are answered in the context of the period selected
              above.
            </p>
          </div>
          <div className="p-3 border-b border-gray-100">
            <div className="text-[11px] uppercase tracking-wide text-gray-500 mb-1">
              Dealer summary
            </div>
            <div className="text-[11px] text-gray-500">
              {dealers.length} dealers · period {selectedPeriod || '—'}
            </div>
          </div>
          <div className="flex-1 overflow-auto">
            <DealerSummaryTable
              dealers={dealers}
              loading={dealersLoading}
            />
          </div>
        </aside>

        {/* Thread + input */}
        <main className="flex-1 flex flex-col overflow-hidden">
          <div
            ref={threadRef}
            className="flex-1 overflow-y-auto px-6 py-4"
          >
            {emptyThread ? (
              <EmptyState
                period={selectedPeriod}
                onPick={(s) => setInputText(s)}
              />
            ) : (
              <>
                {messages.map((m, i) => (
                  <MessageBubble key={i} message={m} />
                ))}
                {isLoading && <LoadingBubble />}
              </>
            )}
          </div>

          {error && (
            <div className="mx-6 mb-2 text-xs text-red-600 bg-red-50 border border-red-200 rounded-md px-3 py-2">
              {error}
            </div>
          )}

          <div className="border-t border-gray-200 bg-white p-3">
            <div className="flex items-end gap-2">
              <textarea
                rows={2}
                value={inputText}
                onChange={(e) => setInputText(e.target.value)}
                onKeyDown={onKeyDown}
                placeholder="Ask about dealer commissions, variances, zero-commission records…"
                className="flex-1 resize-none text-sm border border-gray-300 rounded-lg px-3 py-2 focus:outline-none focus:ring-2 focus:ring-mtn-yellow focus:border-mtn-yellow"
                disabled={isLoading}
              />
              <button
                onClick={onSubmit}
                disabled={isLoading || !inputText.trim()}
                className="self-stretch px-5 rounded-lg bg-mtn-yellow text-gray-900 text-sm font-semibold hover:brightness-95 disabled:opacity-40 disabled:cursor-not-allowed transition"
              >
                {isLoading ? '…' : 'Send'}
              </button>
            </div>
            <div className="mt-1.5 text-[11px] text-gray-400">
              Enter to send · Shift + Enter for newline
            </div>
          </div>
        </main>
      </div>
    </div>
  );
}

// ---------------------------------------------------------------------------
// Empty-state suggestions
// ---------------------------------------------------------------------------

function EmptyState({ period, onPick }) {
  return (
    <div className="h-full flex flex-col items-center justify-center text-center px-6">
      <div className="w-12 h-12 rounded-full bg-mtn-yellow flex items-center justify-center text-gray-900 font-bold text-lg shadow-sm">
        ₦
      </div>
      <h2 className="mt-4 text-lg font-semibold text-gray-800">
        Ask about trade partner commissions
      </h2>
      <p className="mt-1 text-sm text-gray-500 max-w-md">
        Try one of the suggested questions, or type your own. Period{' '}
        <span className="font-semibold text-gray-700">
          {period || '—'}
        </span>{' '}
        is selected.
      </p>
      <div className="mt-6 grid grid-cols-1 sm:grid-cols-2 gap-3 max-w-2xl w-full">
        {SUGGESTIONS.map((tpl, i) => {
          const text = tpl(period);
          return (
            <button
              key={i}
              onClick={() => onPick(text)}
              className="text-left text-sm text-gray-700 border border-gray-200 rounded-lg px-3 py-2.5 bg-white hover:border-mtn-yellow hover:bg-yellow-50 transition shadow-sm"
            >
              {text}
            </button>
          );
        })}
      </div>
    </div>
  );
}
