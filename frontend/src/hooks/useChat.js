// React hook. Manages chat state and POST /chat calls.
//
// Period context lives in PeriodContext now — sendMessage accepts the period
// at call time rather than holding it as hook-local state.
//
// Chat history persists to localStorage so a page reload doesn't wipe the
// investigation thread (the conversation IS the audit trail for finance).
// Schema-versioned so we can safely evolve the message shape later — a
// version mismatch quietly clears the stored thread instead of crashing.

import { useCallback, useEffect, useRef, useState } from 'react';
import { sendMessage as apiSendMessage } from '../api/client.js';

const STORAGE_KEY = 'fbb.chat.thread';
const STORAGE_VERSION = 1;

function loadStored() {
  try {
    const raw = localStorage.getItem(STORAGE_KEY);
    if (!raw) return [];
    const parsed = JSON.parse(raw);
    if (parsed?.version !== STORAGE_VERSION || !Array.isArray(parsed?.messages)) return [];
    return parsed.messages;
  } catch {
    return [];
  }
}

function saveStored(messages) {
  try {
    localStorage.setItem(
      STORAGE_KEY,
      JSON.stringify({ version: STORAGE_VERSION, messages }),
    );
  } catch {
    // Quota exceeded or storage disabled — drop silently. Chat still works
    // in-memory; we just don't survive a reload.
  }
}

export default function useChat() {
  // Lazy initializer reads from localStorage exactly once.
  const [messages, setMessages] = useState(() => loadStored());
  const [isLoading, setIsLoading] = useState(false);
  const [error, setError] = useState(null);

  // Persist on every change, but skip the very first render (already hydrated).
  const hydrated = useRef(false);
  useEffect(() => {
    if (!hydrated.current) {
      hydrated.current = true;
      return;
    }
    saveStored(messages);
  }, [messages]);

  const sendMessage = useCallback(
    async (text, monPeriod = null) => {
      const trimmed = (text || '').trim();
      if (!trimmed || isLoading) return;

      setError(null);

      const wireHistory = messages.map((m) => ({
        role: m.role,
        content: m.content,
      }));

      const userMsg = {
        role: 'user',
        content: trimmed,
        tools_called: [],
        raw_data: {},
      };
      setMessages((prev) => [...prev, userMsg]);
      setIsLoading(true);

      try {
        const data = await apiSendMessage(trimmed, wireHistory, monPeriod);

        const assistantMsg = {
          role: 'assistant',
          content: data.response || '',
          tools_called: Array.isArray(data.tools_called) ? data.tools_called : [],
          raw_data: data.raw_data || {},
          mon_period: monPeriod || null,
        };
        setMessages((prev) => [...prev, assistantMsg]);

        if (data.error) setError(data.error);
      } catch (err) {
        const message =
          err?.response?.data?.detail ||
          err?.message ||
          'Network error contacting the API.';
        setError(message);
        setMessages((prev) => [
          ...prev,
          {
            role: 'assistant',
            content:
              'I was unable to reach the backend. Please confirm the API is running and try again.',
            tools_called: [],
            raw_data: {},
          },
        ]);
      } finally {
        setIsLoading(false);
      }
    },
    [messages, isLoading],
  );

  const clearChat = useCallback(() => {
    setMessages([]);
    setError(null);
    try {
      localStorage.removeItem(STORAGE_KEY);
    } catch {
      // No-op
    }
  }, []);

  return {
    messages,
    isLoading,
    error,
    sendMessage,
    clearChat,
  };
}
