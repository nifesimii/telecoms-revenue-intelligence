// Commission Intelligence view: chat thread + dealer summary sidebar.
// Period is owned by the global <PeriodProvider> — see context/PeriodContext.jsx.

import { useCallback, useEffect, useRef, useState } from 'react';
import { getDealers } from '../api/client.js';
import { usePeriod } from '../context/PeriodContext.jsx';
import { formatPeriod } from '../lib/format.js';
import useChat from '../hooks/useChat.js';
import MessageBubble, { LoadingBubble } from './MessageBubble.jsx';
import DealerSummaryTable from './DealerSummaryTable.jsx';

const SIDEBAR_MIN = 240;
const SIDEBAR_MAX = 720;
const SIDEBAR_DEFAULT = 320;
const SIDEBAR_STORAGE_KEY = 'fbb.commission.sidebarWidth';

const SUGGESTIONS = [
  (label) =>
    `Summarise dealer commissions for ${label || 'the latest period'}`,
  () => 'Which dealers have zero-commission records and why?',
  (label) => `Show me the ORSC summary for ${label || 'the latest period'}`,
  (_label, topDealer) =>
    topDealer
      ? `Why did ${topDealer}'s commission change this month?`
      : "Why did this dealer's commission change this month?",
];

export default function ChatInterface({ pendingPrompt = '', onPromptConsumed } = {}) {
  const { period } = usePeriod();
  const { messages, isLoading, error, sendMessage, clearChat } = useChat();

  const [dealers, setDealers] = useState([]);
  const [dealersLoading, setDealersLoading] = useState(false);
  const [inputText, setInputText] = useState('');
  const threadRef = useRef(null);

  // If the Overview asked us to start with a templated question, prefill the
  // input and let the user hit Send. Don't auto-submit — give them a beat to
  // edit the prompt or change their mind.
  useEffect(() => {
    if (pendingPrompt) {
      setInputText(pendingPrompt);
      onPromptConsumed?.();
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [pendingPrompt]);

  // Sidebar width — drag-resizable, persisted across reloads.
  const [sidebarWidth, setSidebarWidth] = useState(() => {
    const raw = Number(localStorage.getItem(SIDEBAR_STORAGE_KEY));
    return Number.isFinite(raw) && raw >= SIDEBAR_MIN && raw <= SIDEBAR_MAX
      ? raw
      : SIDEBAR_DEFAULT;
  });
  const draggingRef = useRef(false);

  useEffect(() => {
    function onMove(e) {
      if (!draggingRef.current) return;
      const w = Math.min(SIDEBAR_MAX, Math.max(SIDEBAR_MIN, e.clientX));
      setSidebarWidth(w);
    }
    function onUp() {
      if (!draggingRef.current) return;
      draggingRef.current = false;
      document.body.style.cursor = '';
      document.body.style.userSelect = '';
      localStorage.setItem(SIDEBAR_STORAGE_KEY, String(sidebarWidth));
    }
    window.addEventListener('mousemove', onMove);
    window.addEventListener('mouseup', onUp);
    return () => {
      window.removeEventListener('mousemove', onMove);
      window.removeEventListener('mouseup', onUp);
    };
  }, [sidebarWidth]);

  const startDrag = useCallback(() => {
    draggingRef.current = true;
    document.body.style.cursor = 'col-resize';
    document.body.style.userSelect = 'none';
  }, []);

  const resetSidebar = useCallback(() => {
    setSidebarWidth(SIDEBAR_DEFAULT);
    localStorage.setItem(SIDEBAR_STORAGE_KEY, String(SIDEBAR_DEFAULT));
  }, []);

  // Reload dealers any time the selected period changes.
  useEffect(() => {
    let cancelled = false;
    setDealersLoading(true);
    getDealers(period || null)
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
  }, [period]);

  useEffect(() => {
    const el = threadRef.current;
    if (el) el.scrollTop = el.scrollHeight;
  }, [messages, isLoading]);

  const submit = useCallback(
    (text) => {
      const t = (text ?? inputText).trim();
      if (!t || isLoading) return;
      setInputText('');
      sendMessage(t, period || null);
    },
    [inputText, isLoading, sendMessage, period],
  );

  const onKeyDown = useCallback(
    (e) => {
      if (e.key === 'Enter' && !e.shiftKey) {
        e.preventDefault();
        submit();
      }
    },
    [submit],
  );

  const periodLabel = formatPeriod(period);
  const topDealer = dealers[0]?.dealer_name;
  const emptyThread = messages.length === 0;

  return (
    <div className="h-full flex flex-col bg-gray-50 text-gray-800">
      <header className="flex items-center gap-3 px-4 py-2 border-b border-gray-200 bg-white">
        <h1 className="text-sm font-semibold tracking-tight">
          Commission Intelligence
        </h1>
        <span className="text-xs text-gray-500">
          Period <span className="font-semibold text-gray-700">{periodLabel || '—'}</span>
        </span>
        <div className="ml-auto">
          {messages.length > 0 && (
            <button
              onClick={clearChat}
              className="text-xs text-gray-500 hover:text-gray-800 hover:underline"
            >
              Clear chat
            </button>
          )}
        </div>
      </header>

      <div className="flex-1 flex overflow-hidden">
        <aside
          style={{ width: `${sidebarWidth}px` }}
          className="shrink-0 border-r border-gray-200 bg-white flex flex-col overflow-hidden"
        >
          <div className="p-3 border-b border-gray-100 flex items-center justify-between gap-2">
            <div className="min-w-0">
              <div className="text-[11px] uppercase tracking-wide text-gray-500">
                Dealer summary
              </div>
              <div className="text-[11px] text-gray-500 truncate">
                {dealers.length} dealers · {periodLabel || '—'}
              </div>
            </div>
            <button
              onClick={resetSidebar}
              title="Reset sidebar width"
              className="text-[10px] text-gray-400 hover:text-gray-700 uppercase tracking-wide"
            >
              Reset
            </button>
          </div>
          <div className="flex-1 overflow-auto">
            <DealerSummaryTable
              dealers={dealers}
              loading={dealersLoading}
              onDealerClick={(d) =>
                setInputText(
                  `Why did ${d.dealer_name}'s commission change vs last month?`,
                )
              }
            />
          </div>
        </aside>
        {/* Drag handle — 4px hit area, visual hover state, persists width. */}
        <div
          onMouseDown={startDrag}
          onDoubleClick={resetSidebar}
          role="separator"
          aria-orientation="vertical"
          title="Drag to resize · double-click to reset"
          className="w-1 shrink-0 cursor-col-resize bg-gray-200 hover:bg-mtn-yellow transition-colors"
        />

        <main className="flex-1 flex flex-col overflow-hidden">
          <div ref={threadRef} className="flex-1 overflow-y-auto px-6 py-4">
            {emptyThread ? (
              <EmptyState
                periodLabel={periodLabel}
                topDealer={topDealer}
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
                onClick={() => submit()}
                disabled={isLoading || !inputText.trim()}
                className="self-stretch px-5 rounded-lg bg-mtn-yellow text-gray-900 text-sm font-semibold hover:brightness-95 disabled:opacity-40 disabled:cursor-not-allowed transition"
              >
                {isLoading ? '…' : 'Send'}
              </button>
            </div>
            <div className="mt-1.5 text-[11px] text-gray-400">
              Enter to send · Shift + Enter for newline · Click a dealer in the sidebar to template a question
            </div>
          </div>
        </main>
      </div>
    </div>
  );
}

function EmptyState({ periodLabel, topDealer, onPick }) {
  return (
    <div className="h-full flex flex-col items-center justify-center text-center px-6">
      <div className="w-12 h-12 rounded-full bg-mtn-yellow flex items-center justify-center text-gray-900 font-bold text-xs shadow-sm">
        NGN
      </div>
      <h2 className="mt-4 text-lg font-semibold text-gray-800">
        Ask about trade partner commissions
      </h2>
      <p className="mt-1 text-sm text-gray-500 max-w-md">
        Try one of the suggested questions, or type your own. Period{' '}
        <span className="font-semibold text-gray-700">{periodLabel || '—'}</span>{' '}
        is selected.
      </p>
      <div className="mt-6 grid grid-cols-1 sm:grid-cols-2 gap-3 max-w-2xl w-full">
        {SUGGESTIONS.map((tpl, i) => {
          const text = tpl(periodLabel, topDealer);
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
