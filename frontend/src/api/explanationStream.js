// NDJSON records may cross arbitrary network/UTF-8 chunk boundaries.
export async function readExplanationStream(response, { onText = () => {}, signal } = {}) {
  if (!response.body) throw new Error('Explanation stream unavailable. Please retry.');
  const reader = response.body.getReader();
  const decoder = new TextDecoder();
  let buffer = '';
  const abort = () => { reader.cancel().catch(() => {}); };
  signal?.addEventListener('abort', abort, { once: true });
  function checkAbort() {
    if (signal?.aborted) throw new DOMException('Explanation stopped.', 'AbortError');
  }
  function parse(line) {
    if (!line.trim()) return null;
    let event;
    try { event = JSON.parse(line); } catch { throw new Error('Invalid explanation stream. Please retry.'); }
    if (event?.type === 'text' && typeof event.text === 'string') {
      onText(event.text);
      return null;
    }
    if (event?.type === 'complete' && typeof event.response === 'string' &&
        Array.isArray(event.tools_called) && event.tools_called.every((tool) => typeof tool === 'string') &&
        event.raw_data && typeof event.raw_data === 'object' && !Array.isArray(event.raw_data) && event.error === null) return event;
    if (event?.type === 'error' && typeof event.error === 'string' && typeof event.message === 'string') {
      const error = new Error(event.message);
      error.code = event.error;
      throw error;
    }
    throw new Error('Invalid explanation stream. Please retry.');
  }
  try {
    checkAbort();
    while (true) {
      const { done, value } = await reader.read();
      checkAbort();
      buffer += done ? decoder.decode() : decoder.decode(value, { stream: true });
      const lines = buffer.split('\n');
      buffer = lines.pop();
      if (done && buffer) { lines.push(buffer); buffer = ''; }
      for (const line of lines) {
        const complete = parse(line);
        if (complete) return complete;
      }
      if (done) throw new Error('Explanation stream interrupted. Please retry.');
    }
  } finally {
    signal?.removeEventListener('abort', abort);
    await reader.cancel().catch(() => {});
    reader.releaseLock();
  }
}
