import test from 'node:test';
import assert from 'node:assert/strict';
import { readExplanationStream } from '../src/api/explanationStream.js';
import { explainFinding } from '../src/api/client.js';

const complete = { type: 'complete', response: 'NGN 1,000.00 ✓', tools_called: ['get_dealer_full_context'], raw_data: { evidence: { available: true } }, error: null };
const bytes = new TextEncoder();
function response(text, size = 1) {
  const data = bytes.encode(text);
  return new Response(new ReadableStream({ start(controller) {
    for (let i = 0; i < data.length; i += size) controller.enqueue(data.slice(i, i + size));
    controller.close();
  } }), { headers: { 'Content-Type': 'application/x-ndjson' } });
}
test('decodes split UTF-8 and CRLF, multiple events and final line without newline', async () => {
  const seen = [];
  const result = await readExplanationStream(response('\r\n' + JSON.stringify({ type: 'text', text: '₦ ✓' }) + '\r\n' + JSON.stringify(complete)), { onText: (text) => seen.push(text) });
  assert.deepEqual(seen, ['₦ ✓']);
  assert.deepEqual(result, complete);
});
test('text is delivered before completion arrives', async () => {
  let controller;
  const body = new ReadableStream({ start(value) { controller = value; } });
  const seen = [];
  const pending = readExplanationStream(new Response(body), { onText: (text) => seen.push(text) });
  controller.enqueue(bytes.encode('{"type":"text","text":"First"}\n'));
  await new Promise(setImmediate);
  assert.deepEqual(seen, ['First']);
  controller.enqueue(bytes.encode(JSON.stringify(complete) + '\n'));
  controller.close();
  assert.deepEqual(await pending, complete);
});
test('rejects malformed, unknown, invalid completion and unfinished streams without exposing payloads', async () => {
  for (const body of ['private malformed text\n', '{"type":"other"}\n', '{"type":"complete","response":"partial"}\n', '{"type":"text","text":"partial"}\n', '']) {
    await assert.rejects(readExplanationStream(response(body)), /interrupted|invalid/i);
  }
});
test('terminal server errors preserve sanitized message and code', async () => {
  await assert.rejects(readExplanationStream(response('{"type":"error","error":"deadline","message":"Please retry."}\n')), (error) => error.code === 'deadline' && error.message === 'Please retry.');
});
test('abort cancels a reader waiting for more data', async () => {
  let cancelled = false;
  const controller = new AbortController();
  const pending = readExplanationStream(new Response(new ReadableStream({ cancel() { cancelled = true; } })), { signal: controller.signal });
  controller.abort();
  await assert.rejects(pending, { name: 'AbortError' });
  assert.equal(cancelled, true);
});
test('central client posts only structured scope and retains completion metadata', async (t) => {
  const scope = { dealer_id: '001', mon_period: '202606', finding: { module: 'inventory', type: 'INVENTORY_MISMATCH', product_code: 'P1' } };
  t.mock.method(globalThis, 'fetch', async (url, options) => {
    assert.equal(url, 'http://localhost:8000/chat/explain');
    assert.equal(options.method, 'POST');
    assert.deepEqual(JSON.parse(options.body), scope);
    assert.ok(options.signal);
    return response(JSON.stringify(complete));
  });
  assert.deepEqual(await explainFinding(scope), complete);
});
test('client rejects HTTP and non-NDJSON responses with safe messages', async (t) => {
  for (const result of [new Response('private upstream traceback', { status: 500 }), new Response('<html>proxy</html>')]) {
    t.mock.method(globalThis, 'fetch', async () => result);
    await assert.rejects(explainFinding({}), (error) => !/private|traceback|proxy/.test(error.message));
    t.mock.restoreAll();
  }
});

test('coalesced events and pre-aborted signals do not lose boundaries or deliver text after Stop', async () => {
  const seen = [];
  const body = JSON.stringify({ type: 'text', text: 'one' }) + '\n' + JSON.stringify({ type: 'text', text: 'two' }) + '\n' + JSON.stringify(complete) + '\n';
  assert.deepEqual(await readExplanationStream(response(body, 4096), { onText: (text) => seen.push(text) }), complete);
  assert.deepEqual(seen, ['one', 'two']);
  await assert.rejects(readExplanationStream(response(body), { signal: AbortSignal.abort(), onText: () => assert.fail('Text delivered after abort') }), { name: 'AbortError' });
});
test('central wrapper forwards user cancellation while waiting for headers', async (t) => {
  const controller = new AbortController();
  t.mock.method(globalThis, 'fetch', async (_url, { signal }) => new Promise((_resolve, reject) => {
    signal.addEventListener('abort', () => reject(new DOMException('Aborted', 'AbortError')), { once: true });
  }));
  const pending = explainFinding({}, { signal: controller.signal });
  controller.abort();
  await assert.rejects(pending, { name: 'AbortError' });
});

test('chat status and tool evidence arrive in order without completing the provisional answer', async () => {
  const seen = [];
  const status = { type: 'status', phase: 'tool_complete', tool: 'get_dealer_summary', reset: true,
    tools_called: ['get_dealer_summary'], raw_data: { get_dealer_summary: { source: 'sample' } } };
  const result = await readExplanationStream(response(JSON.stringify(status) + '\n' + JSON.stringify(complete)), {
    onStatus: (event) => seen.push(event),
  });
  assert.deepEqual(seen, [status]);
  assert.deepEqual(result, complete);
});

test('ordinary chat transport uses additive stream endpoint with exact history and period', async (t) => {
  const { streamMessage } = await import('../src/api/client.js');
  const history = [{ role: 'assistant', content: 'Prior complete answer with caveat.' }];
  t.mock.method(globalThis, 'fetch', async (url, options) => {
    assert.equal(url, 'http://localhost:8000/chat/stream');
    assert.deepEqual(JSON.parse(options.body), { message: 'Explain', conversation_history: history, mon_period: '202606' });
    return response(JSON.stringify(complete));
  });
  assert.deepEqual(await streamMessage('Explain', history, '202606'), complete);
});
