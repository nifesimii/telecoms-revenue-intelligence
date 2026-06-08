// React hook. Manages chat state and POST /chat calls.
//
// State surface:
//   messages: array of { role, content, tools_called, raw_data }
//   isLoading: bool — true while a /chat round-trip is in flight
//   error:    string | null — set from ChatResponse.error or thrown API errors
//   selectedPeriod: string — current period context, prepended on the backend
//
// Actions:
//   sendMessage(text)        — append user msg, hit /chat, append assistant msg
//   clearChat()              — wipe messages and clear error
//   setSelectedPeriod(value) — store the period selection
//
// Conversation history sent to the API is the lean shape the backend expects:
// [{ role: 'user' | 'assistant', content: string }, ...]

import { useCallback, useState } from 'react';
import { sendMessage as apiSendMessage } from '../api/client.js';

export default function useChat() {
  const [messages, setMessages] = useState([]);
  const [isLoading, setIsLoading] = useState(false);
  const [error, setError] = useState(null);
  const [selectedPeriod, setSelectedPeriod] = useState('');

  const sendMessage = useCallback(
    async (text) => {
      const trimmed = (text || '').trim();
      if (!trimmed || isLoading) return;

      setError(null);

      // Build the wire-shape history from current messages BEFORE appending.
      const wireHistory = messages.map((m) => ({
        role: m.role,
        content: m.content,
      }));

      // Optimistically append the user message so it renders immediately.
      const userMsg = {
        role: 'user',
        content: trimmed,
        tools_called: [],
        raw_data: {},
      };
      setMessages((prev) => [...prev, userMsg]);
      setIsLoading(true);

      try {
        const data = await apiSendMessage(
          trimmed,
          wireHistory,
          selectedPeriod || null,
        );

        const assistantMsg = {
          role: 'assistant',
          content: data.response || '',
          tools_called: Array.isArray(data.tools_called) ? data.tools_called : [],
          raw_data: data.raw_data || {},
        };
        setMessages((prev) => [...prev, assistantMsg]);

        if (data.error) setError(data.error);
      } catch (err) {
        const message =
          err?.response?.data?.detail ||
          err?.message ||
          'Network error contacting the API.';
        setError(message);
        // Surface the failure as an assistant message so the thread still
        // closes the loop visually.
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
    [messages, isLoading, selectedPeriod],
  );

  const clearChat = useCallback(() => {
    setMessages([]);
    setError(null);
  }, []);

  return {
    messages,
    isLoading,
    error,
    selectedPeriod,
    setSelectedPeriod,
    sendMessage,
    clearChat,
  };
}
