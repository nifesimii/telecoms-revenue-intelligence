// Conversations outlive their presentation. Navigation during a request must
// not discard the answer or mix it into another account's thread.
import { useSyncExternalStore } from 'react';
import { sendMessage as apiSendMessage } from '../api/client.js';

const STORAGE_KEY = 'fbb.chat.thread';
const STORAGE_VERSION = 1;
const conversations = new Map();

function conversationFor(key) {
  if (conversations.has(key)) return conversations.get(key);
  let messages = [];
  try {
    const stored = JSON.parse(localStorage.getItem(key) || 'null');
    if (stored?.version === STORAGE_VERSION && Array.isArray(stored.messages)) messages = stored.messages;
  } catch { /* A blocked or malformed store does not prevent investigation. */ }
  const listeners = new Set();
  let state = { messages, isLoading: false, error: null };
  const conversation = {
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

  async function sendMessage(text, monPeriod = null) {
    const trimmed = (text || '').trim();
    const current = conversation.snapshot();
    if (!trimmed || current.isLoading) return;
    const history = current.messages.map(({ role, content }) => ({ role, content }));
    const messages = [...current.messages, { role: 'user', content: trimmed, tools_called: [], raw_data: {}, mon_period: monPeriod }];
    conversation.update({ messages, isLoading: true, error: null });
    try {
      const data = await apiSendMessage(trimmed, history, monPeriod);
      conversation.update({ messages: [...messages, {
        role: 'assistant', content: data.response || '',
        tools_called: Array.isArray(data.tools_called) ? data.tools_called : [],
        raw_data: data.raw_data || {}, mon_period: monPeriod,
      }], isLoading: false, error: data.error || null });
    } catch (err) {
      const error = err?.response?.data?.detail || err?.message || 'Network error contacting the API.';
      conversation.update({ messages: [...messages, {
        role: 'assistant', content: 'The explanation could not be completed. Please retry your question.',
        tools_called: [], raw_data: {}, mon_period: monPeriod,
      }], isLoading: false, error });
    }
  }

  function clearChat() {
    if (!conversation.snapshot().isLoading) conversation.update({ messages: [], error: null });
  }

  return { ...state, sendMessage, clearChat };
}
