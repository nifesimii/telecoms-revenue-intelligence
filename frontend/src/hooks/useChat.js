// React hook. Manages chat state and POST /chat calls.
//
// Period context lives in PeriodContext now — sendMessage accepts the period
// at call time rather than holding it as hook-local state.

import { useCallback, useState } from 'react';
import { sendMessage as apiSendMessage } from '../api/client.js';

export default function useChat() {
  const [messages, setMessages] = useState([]);
  const [isLoading, setIsLoading] = useState(false);
  const [error, setError] = useState(null);

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
  }, []);

  return {
    messages,
    isLoading,
    error,
    sendMessage,
    clearChat,
  };
}
