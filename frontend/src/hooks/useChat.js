// Conversations outlive their presentation. Navigation during a request must
// not discard the answer or mix it into another account's thread.
import { useSyncExternalStore } from 'react';
import { streamMessage, explainFinding } from '../api/client.js';
import { startExplanationTiming, measureExplanationTiming } from '../lib/explanationTiming.js';

const STORAGE_KEY = 'fbb.chat.thread';
const STORAGE_VERSION = 1;
const conversations = new Map();

function conversationFor(key) {
  if (conversations.has(key)) return conversations.get(key);
  let messages = [];
  try {
    const stored = JSON.parse(localStorage.getItem(key) || 'null');
    if (stored?.version === STORAGE_VERSION && Array.isArray(stored.messages)) {
      messages = stored.messages.map((message) => message.status === 'streaming'
        ? { ...message, status: 'interrupted', incomplete: true } : message);
    }
  } catch { /* A blocked or malformed store does not prevent investigation. */ }
  const listeners = new Set();
  let state = { messages, isLoading: false, error: messages.at(-1)?.incomplete ? 'Explanation interrupted. Please retry.' : null };
  const conversation = {
    controller: null,
    snapshot: () => state,
    subscribe: (listener) => { listeners.add(listener); return () => listeners.delete(listener); },
    update: (patch) => {
      state = { ...state, ...patch };
      try {
        localStorage.setItem(key, JSON.stringify({ version: STORAGE_VERSION, messages: state.messages }));
      } catch { /* In-memory history still survives workspace navigation. */ }
      listeners.forEach((listener) => listener());
    },
  };
  conversations.set(key, conversation);
  return conversation;
}

export default function useChat({ scope } = {}) {
  const conversation = conversationFor(scope ? `${STORAGE_KEY}.${scope}` : STORAGE_KEY);
  const state = useSyncExternalStore(conversation.subscribe, conversation.snapshot);

  async function sendMessage(text, monPeriod = null, explanation = null, retry = false) {
    const trimmed = (text || '').trim();
    const current = conversation.snapshot();
    if (!trimmed || current.isLoading) return;
    // A retry replaces the failed turn. Incomplete turns never become model history.
    const previous = retry ? current.messages.slice(0, -2) : current.messages;
    const history = previous.filter((message, index) => !message.incomplete &&
      !(message.role === 'user' && previous[index + 1]?.incomplete))
      .map(({ role, content }) => ({ role, content }));
    const request = { text: trimmed, monPeriod, explanation };
    const messages = [...previous, { role: 'user', content: trimmed, tools_called: [], raw_data: {}, mon_period: monPeriod }, {
      role: 'assistant', content: '', tools_called: [], raw_data: {}, mon_period: monPeriod,
      incomplete: true, status: 'streaming', request, phase: 'thinking', timingId: startExplanationTiming(),
    }];
    const controller = new AbortController();
    conversation.controller = controller;
    const updateAnswer = (patch, statePatch = {}) => {
      const currentMessages = conversation.snapshot().messages;
      conversation.update({ messages: [...currentMessages.slice(0, -1), { ...currentMessages.at(-1), ...patch }], ...statePatch });
    };
    conversation.update({ messages, isLoading: true, error: null });
    try {
      const options = { signal: controller.signal, onText: (text) => {
        if (!controller.signal.aborted) updateAnswer({ content: conversation.snapshot().messages.at(-1).content + text });
      }, onStatus: (event) => {
        if (controller.signal.aborted) return;
        updateAnswer({ phase: event.phase, tool: event.tool,
          ...(event.reset ? { content: '' } : {}),
          ...(event.tools_called ? { tools_called: event.tools_called } : {}),
          ...(event.raw_data ? { raw_data: event.raw_data } : {}),
        });
      } };
      const data = explanation
        ? await explainFinding(explanation, options)
        : await streamMessage(trimmed, history, monPeriod, options);
      measureExplanationTiming(messages.at(-1).timingId, 'network-complete');
      if (controller.signal.aborted) throw new DOMException('Explanation stopped.', 'AbortError');
      if (data.error) throw new Error('The explanation could not be completed. Please retry.');
      updateAnswer({ content: data.response || '',
        tools_called: Array.isArray(data.tools_called) ? data.tools_called : [],
        raw_data: data.raw_data || {}, incomplete: false, status: 'complete', request: undefined,
      }, { isLoading: false, error: null });
    } catch (err) {
      const stopped = controller.signal.aborted;
      const error = stopped ? 'Explanation stopped. You can retry.'
        : err?.response?.data?.detail || err?.message || 'Network error contacting the API.';
      updateAnswer({ incomplete: true, status: stopped ? 'stopped' : 'interrupted' }, { isLoading: false, error });
    } finally {
      conversation.controller = null;
    }
  }

  function retryMessage() {
    const last = conversation.snapshot().messages.at(-1);
    if (last?.incomplete && last.request) {
      const { text, monPeriod, explanation } = last.request;
      return sendMessage(text, monPeriod, explanation, true);
    }
  }
  function stopMessage() { conversation.controller?.abort(); }
  function clearChat() {
    if (!conversation.snapshot().isLoading) conversation.update({ messages: [], error: null });
  }

  return { ...state, sendMessage, clearChat, stopMessage, retryMessage,
    canRetry: Boolean(!state.isLoading && state.messages.at(-1)?.incomplete && state.messages.at(-1)?.request) };
}
