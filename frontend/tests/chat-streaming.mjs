// Public Assistant + real chunked loopback HTTP; existing Vite, no provider calls.
import assert from 'node:assert/strict';
import { createServer } from 'node:http';
import { once } from 'node:events';
const { chromium } = await import(process.env.PLAYWRIGHT_MODULE || 'playwright');
const pending = [];
const server = createServer(async (req, res) => {
  res.setHeader('Access-Control-Allow-Origin', '*');
  res.setHeader('Access-Control-Allow-Headers', 'content-type');
  if (req.method === 'OPTIONS') { res.writeHead(204); res.end(); return; }
  let body = '';
  for await (const chunk of req) body += chunk;
  res.writeHead(200, { 'Content-Type': 'application/x-ndjson' });
  res.flushHeaders();
  const entry = { payload: JSON.parse(body), res, closed: false };
  pending.push(entry);
  res.on('close', () => { entry.closed = true; });
});
server.listen(0, '127.0.0.1');
await once(server, 'listening');
const browser = await chromium.launch({ headless: true, channel: 'chrome' });
const page = await browser.newPage({ viewport: { width: 1440, height: 900 } });
page.setDefaultTimeout(8000);
const atlas = page.getByRole('region', { name: 'Atlas', exact: true });
const input = atlas.getByRole('textbox');
const send = () => atlas.getByRole('button', { name: 'Send question' }).click();
const write = (event) => pending.at(-1).res.write(JSON.stringify(event) + '\n');
const evidence = { get_dealer_summary: { rows: [], source: 'sample', caveat: 'Fictional evidence is not operational verification.' } };
const finalText = 'NGN 1,000.00 recorded. Missing settlement evidence does not establish an amount owed.';
const complete = () => { write({ type: 'complete', response: finalText, tools_called: ['get_dealer_summary'], raw_data: evidence, error: null }); pending.at(-1).res.end(); };
const waitCount = async (count) => {
  for (let i = 0; i < 100; i++) {
    if (pending.length === count) return;
    await new Promise((resolve) => setTimeout(resolve, 20));
  }
  assert.equal(pending.length, count);
};
const errors = [];
page.on('pageerror', (error) => errors.push(error.message));
try {
  await page.route('**/chat/stream', (route) => route.continue({ url: `http://127.0.0.1:${server.address().port}/chat/stream` }));
  await page.route('**/chat', (route) => route.abort());
  await page.route('**/chat/explain', (route) => route.abort());
  await page.goto(`${process.env.APP_URL || 'http://localhost:5173'}/tests/findings-fixture.html`);
  const opening = performance.now();
  await page.getByRole('button', { name: 'Inventory opener', exact: true }).click();
  await input.waitFor();
  console.log('Mocked Atlas opening ms:', Math.round(performance.now() - opening));
  assert.equal(pending.length, 0);
  await input.fill('Explain this account.');
  const started = performance.now();
  await send();
  await atlas.getByRole('status').waitFor();
  const rect = await atlas.getByRole('status').boundingBox();
  assert.ok(rect.width > 10 && rect.height > 10, 'waiting status must be visually readable');
  console.log('Mocked immediate waiting ms:', Math.round(performance.now() - started));
  await waitCount(1);
  write({ type: 'status', phase: 'thinking', reset: false });
  write({ type: 'text', text: 'I will check the records.' });
  await atlas.getByText('I will check the records.', { exact: true }).waitFor();
  assert.match(await atlas.getByRole('status').innerText(), /Draft in progress.*not a completed evidence answer/);
  write({ type: 'status', phase: 'tool_start', tool: 'get_dealer_summary', reset: true });
  await atlas.getByText('Checking evidence with get_dealer_summary…', { exact: true }).waitFor();
  assert.equal(await atlas.getByText('I will check the records.', { exact: true }).count(), 0);
  write({ type: 'status', phase: 'tool_complete', tool: 'get_dealer_summary', reset: true,
    tools_called: ['get_dealer_summary'], raw_data: evidence });
  write({ type: 'text', text: finalText });
  await atlas.getByText(finalText, { exact: true }).waitFor();
  await atlas.getByText('get_dealer_summary', { exact: true }).waitFor();
  assert.equal(await atlas.getByRole('button', { name: 'Stop', exact: true }).count(), 1);
  // Completion is withheld: text + provenance are visible while explicitly provisional.
  await page.waitForTimeout(250);
  complete();
  await page.waitForFunction(() => performance.getEntriesByType('measure').some((e) => e.name.endsWith(':rendered-complete')));
  assert.equal(await atlas.getByRole('status').count(), 0);
  console.log('Mocked ordinary stream timings:', await page.evaluate(() => performance.getEntriesByType('measure')
    .filter((e) => e.name.startsWith('explanation:')).map((e) => ({ phase: e.name.split(':').at(-1), ms: Math.round(e.duration) }))));

  await input.fill('Follow up'); await send(); await waitCount(2);
  assert.equal(pending[1].payload.conversation_history.at(-1).content, finalText);
  write({ type: 'text', text: 'Partial to stop.' });
  await atlas.getByText('Partial to stop.', { exact: true }).waitFor();
  await atlas.getByRole('button', { name: 'Stop', exact: true }).click();
  await atlas.getByText('Stopped · incomplete answer', { exact: true }).waitFor();
  await atlas.getByRole('button', { name: 'Retry explanation' }).click(); await waitCount(3);
  assert.deepEqual(pending[2].payload, pending[1].payload);
  assert.ok(pending[1].closed, 'Stop disconnects the transport');
  write({ type: 'text', text: 'Partial interrupted.' });
  pending.at(-1).res.end();
  await atlas.getByText('Interrupted · incomplete answer', { exact: true }).waitFor();
  await input.fill('After interruption'); await send(); await waitCount(4);
  assert.deepEqual(pending[3].payload.conversation_history, pending[1].payload.conversation_history);
  write({ type: 'text', text: 'Pending original account.' });
  await atlas.getByText('Pending original account.', { exact: true }).waitFor();
  await page.getByLabel('Fixture scope').selectOption('dealer');
  await page.getByRole('button', { name: 'Ask Atlas about these findings', exact: true }).click();
  assert.equal(await atlas.getByText('Pending original account.', { exact: true }).count(), 0);
  assert.equal(await atlas.getByRole('button', { name: 'Stop', exact: true }).count(), 0);
  complete();
  await page.getByRole('button', { name: 'Inventory opener', exact: true }).click();
  await atlas.getByText(finalText, { exact: true }).last().waitFor();
  await input.fill('Reload interruption'); await send(); await waitCount(5);
  write({ type: 'text', text: 'Interrupted by reload.' });
  await atlas.getByText('Interrupted by reload.', { exact: true }).waitFor();
  await page.reload();
  await page.getByRole('button', { name: 'Inventory opener', exact: true }).click();
  await atlas.getByText('Interrupted · incomplete answer', { exact: true }).last().waitFor();
  await atlas.getByRole('button', { name: 'Retry explanation' }).click(); await waitCount(6);
  assert.deepEqual(pending[5].payload, pending[4].payload);
  complete();
  await atlas.getByRole('button', { name: 'Send question' }).waitFor();
  await page.setViewportSize({ width: 320, height: 844 });
  await page.getByRole('button', { name: 'Inventory opener', exact: true }).click();
  await page.screenshot({ path: '/tmp/atlas-streaming-narrow.png' });
  assert.deepEqual(errors, []);
  console.log('PASS provisional text/reset, tool provenance, full final answer, Stop/disconnect, exact Retry, EOF, history isolation, navigation and reload');
} finally {
  for (const { res } of pending) res.destroy();
  await browser.close();
  server.closeAllConnections();
  await new Promise((resolve) => server.close(resolve));
}
