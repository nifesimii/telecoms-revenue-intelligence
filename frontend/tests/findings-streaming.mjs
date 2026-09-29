// Local chunked HTTP fixture: no provider requests. Run with localhost Vite on 5173.
import assert from 'node:assert/strict';
import { createServer } from 'node:http';
import { once } from 'node:events';
const { chromium } = await import(process.env.PLAYWRIGHT_MODULE || 'playwright');
const requests = [];
const chats = [];
const pending = [];
const server = createServer(async (req, res) => {
  res.setHeader('Access-Control-Allow-Origin', '*');
  res.setHeader('Access-Control-Allow-Headers', 'content-type');
  if (req.method === 'OPTIONS') { res.writeHead(204); res.end(); return; }
  let body = '';
  for await (const chunk of req) body += chunk;
  requests.push(JSON.parse(body));
  res.writeHead(200, { 'Content-Type': 'application/x-ndjson', 'Cache-Control': 'no-store' });
  res.flushHeaders();
  const entry = { res, closed: false };
  res.on('close', () => { entry.closed = true; });
  pending.push(entry);
});
server.listen(0, '127.0.0.1');
await once(server, 'listening');
const fixtureURL = `http://127.0.0.1:${server.address().port}/chat/explain`;
const browser = await chromium.launch({ headless: true, channel: 'chrome' });
const page = await browser.newPage({ viewport: { width: 1440, height: 900 } });
const errors = [];
page.on('pageerror', (error) => errors.push(error.message));
const appURL = process.env.APP_URL || 'http://localhost:5173';
const assistant = page.getByRole('region', { name: 'Findings assistant', exact: true });
const input = assistant.getByRole('textbox');
const send = () => assistant.getByRole('button', { name: 'Send question' }).click();
const open = async () => {
  await page.getByRole('button', { name: 'Explain findings', exact: true }).click();
  await page.waitForFunction(() => document.querySelector('textarea')?.value.startsWith('Explain the findings'));
};
const waitUntil = async (condition) => { for (let i = 0; i < 200; i++) { if (condition()) return; await new Promise((resolve) => setTimeout(resolve, 25)); } throw new Error('Fixture condition timed out'); };
const write = (event) => pending.at(-1).res.write(JSON.stringify(event) + '\n');
const complete = (response = 'Completed fixture explanation.') => {
  write({ type: 'complete', response, tools_called: ['get_dealer_full_context'], raw_data: { fixture: { available: true } }, error: null });
  pending.at(-1).res.end();
};
try {
  await page.route('**/chat/explain', (route) => route.continue({ url: fixtureURL }));
  await page.route('**/chat', async (route) => {
    chats.push(route.request().postDataJSON());
    await route.fulfill({ json: { response: 'General fixture answer.', tools_called: [], raw_data: {}, error: null } });
  });
  // Verify the production Overview → Commission wiring before scoped permutations.
  await page.goto(appURL);
  await page.getByRole('button', { name: 'Explain findings', exact: true }).first().click();
  await input.waitFor();
  assert.match(await input.inputValue(), /Explain the findings/);
  assert.equal(requests.length, 0);
  await send();
  await waitUntil(() => requests.length === 1);
  assert.ok(requests[0].dealer_id && requests[0].mon_period && requests[0].finding.module && requests[0].finding.type);
  assert.deepEqual(Object.keys(requests[0]).sort(), ['dealer_id', 'finding', 'mon_period']);
  write({ type: 'text', text: 'First visible fixture text.' });
  await assistant.getByText('First visible fixture text.', { exact: true }).waitFor();
  await page.waitForFunction(() => performance.getEntriesByType('measure').some((e) => e.name.endsWith(':first-visible-text')));
  assert.equal(await assistant.getByRole('button', { name: 'Stop', exact: true }).count(), 1);
  // The delayed terminal event proves the first text was visible before completion.
  await new Promise((resolve) => setTimeout(resolve, 250));
  complete();
  await assistant.getByText('Completed fixture explanation.', { exact: true }).waitFor();
  await page.waitForFunction(() => performance.getEntriesByType('measure').some((e) => e.name.endsWith(':rendered-complete')));
  const timingNames = await page.evaluate(() => performance.getEntriesByType('measure').filter((e) => e.name.startsWith('explanation:')).map((e) => e.name));
  assert.ok(timingNames.every((name) => /^explanation:[0-9a-f-]{36}:(first-visible-text|network-complete|rendered-complete)$/.test(name)));
  const timings = await page.evaluate(() => performance.getEntriesByType('measure').filter((e) => e.name.startsWith('explanation:')).map((e) => ({ phase: e.name.split(':').at(-1), ms: Math.round(e.duration) })));
  assert.ok(timings.find((t) => t.phase === 'rendered-complete').ms > timings.find((t) => t.phase === 'first-visible-text').ms);
  console.log('PASS production opener, explicit Send, progressive text; controlled fixture timing', timings);

  await page.goto(`${appURL}/tests/findings-fixture.html`);
  await open();
  const prefill = await input.inputValue();
  assert.match(prefill, /Explain the findings/);
  await send();
  await waitUntil(() => requests.length === 2);
  assert.deepEqual(requests.at(-1), { dealer_id: '001', mon_period: '202606', finding: { module: 'inventory', type: 'INVENTORY_MISMATCH', product_code: 'P1' } });
  write({ type: 'text', text: 'Pending original thread.' });
  await assistant.getByText('Pending original thread.', { exact: true }).waitFor();
  await page.getByRole('button', { name: 'Change comparison', exact: true }).click();
  await page.getByRole('button', { name: 'Change stream', exact: true }).click();
  assert.equal(await assistant.getByText('Pending original thread.', { exact: true }).count(), 1);
  for (const variant of ['dealer', 'period', 'module', 'type', 'product']) {
    await page.getByLabel('Fixture scope').selectOption(variant);
    await open();
    assert.equal(await assistant.getByText('Pending original thread.', { exact: true }).count(), 0);
    assert.equal(await assistant.getByRole('button', { name: 'Stop', exact: true }).count(), 0);
  }
  // Complete while its original presentation is unmounted.
  complete('Original thread completed while away.');
  await page.waitForFunction(() => performance.getEntriesByType('measure').some((e) => e.name.endsWith(':network-complete')));
  assert.equal(await page.evaluate(() => performance.getEntriesByType('measure').some((e) => e.name.endsWith(':rendered-complete'))), false);

  await page.getByLabel('Fixture scope').selectOption('base');
  await open();
  await assistant.getByText('Original thread completed while away.', { exact: true }).waitFor();
  await assistant.getByText('get_dealer_full_context', { exact: true }).waitFor();
  await input.fill('What evidence is missing?');
  await send();
  await assistant.getByText('General fixture answer.', { exact: true }).waitFor();
  assert.match(chats.at(-1).message, /Exact dealer account code 001/);
  assert.match(chats.at(-1).message, /module inventory, type INVENTORY_MISMATCH.*Exact product code P1/);
  assert.equal(chats.at(-1).mon_period, '202606');
  assert.equal(chats.at(-1).conversation_history.at(-1).content, 'Original thread completed while away.');
  const stored = await page.evaluate(() => Object.keys(localStorage).filter((key) => key.startsWith('fbb.chat.thread.findings.')).map((key) => JSON.parse(localStorage.getItem(key))));
  assert.ok(stored.some((thread) => thread.messages.some((m) => m.raw_data?.fixture?.available && m.tools_called.includes('get_dealer_full_context'))));
  await page.getByRole('button', { name: 'Queue', exact: true }).click(); await open();
  await send(); await waitUntil(() => requests.length === 3);
  complete('Repeated explicit finding explanation.');
  await assistant.getByText('Repeated explicit finding explanation.', { exact: true }).waitFor();
  assert.deepEqual(requests.at(-1), requests.at(-2));
  console.log('PASS repeated explicit findings action uses structured endpoint');
  console.log('PASS thread isolation across five scope dimensions, navigation, follow-up context and completion metadata');

  await assistant.getByRole('button', { name: 'Clear thread' }).click();
  await page.getByRole('button', { name: 'Queue', exact: true }).click(); await open();
  await input.fill('Edited initial question'); await send();
  await assistant.getByText('General fixture answer.', { exact: true }).waitFor();
  assert.equal(requests.length, 3);
  assert.deepEqual(chats.at(-1).conversation_history, []);
  assert.match(chats.at(-1).message, /Edited initial question/);
  await assistant.getByRole('button', { name: 'Clear thread' }).click();
  await page.getByRole('button', { name: 'Queue', exact: true }).click(); await open();
  await send(); await waitUntil(() => requests.length === 4);
  write({ type: 'text', text: 'Partial answer must not enter history.' });
  await assistant.getByText('Partial answer must not enter history.', { exact: true }).waitFor();
  await assistant.getByRole('button', { name: 'Stop', exact: true }).click();
  await assistant.getByText('Stopped · incomplete answer', { exact: true }).waitFor();
  await waitUntil(() => pending.at(-1).closed);
  await assistant.getByRole('button', { name: 'Retry explanation' }).click();
  await waitUntil(() => requests.length === 5);
  assert.deepEqual(requests.at(-1), requests.at(-2));
  write({ type: 'text', text: 'Another incomplete answer.' });
  write({ type: 'error', error: 'deadline', message: 'Fixture request timed out. Please retry.' });
  pending.at(-1).res.end();
  await assistant.getByText('Interrupted · incomplete answer', { exact: true }).waitFor();
  await input.fill('Follow up after failure'); await send();
  await assistant.getByText('General fixture answer.', { exact: true }).waitFor();
  assert.deepEqual(chats.at(-1).conversation_history, []);
  console.log('PASS edited prompt fallback, cancellation/disconnect, exact retry, error and partial-history exclusion');

  await assistant.getByRole('button', { name: 'Clear thread' }).click();
  await page.getByRole('button', { name: 'Queue', exact: true }).click(); await open();
  await send(); await waitUntil(() => requests.length === 6);
  write({ type: 'text', text: 'Interrupted by reload.' });
  await assistant.getByText('Interrupted by reload.', { exact: true }).waitFor();
  await page.reload(); await open();
  await assistant.getByText('Interrupted · incomplete answer', { exact: true }).waitFor();
  await assistant.getByRole('button', { name: 'Retry explanation' }).click();
  await waitUntil(() => requests.length === 7);
  complete('Recovered after reload.');
  await assistant.getByText('Recovered after reload.', { exact: true }).waitFor();
  await page.setViewportSize({ width: 320, height: 844 });
  await page.getByRole('button', { name: 'Queue', exact: true }).click(); await open();
  const rect = await input.boundingBox();
  assert.ok(rect.x >= 0 && rect.x + rect.width <= 320 && rect.y >= 0 && rect.y + rect.height <= 844);
  await page.screenshot({ path: '/tmp/findings-streaming-narrow.png' });
  await page.getByRole('button', { name: 'Inventory opener', exact: true }).click();
  const inventory = page.getByRole('region', { name: 'Inventory assistant', exact: true });
  await inventory.getByRole('button', { name: 'Send question' }).click();
  await inventory.getByText('General fixture answer.', { exact: true }).waitFor();
  assert.equal(requests.length, 7);
  assert.match(chats.at(-1).message, /Inventory investigation.*exact dealer 001.*product P1/);
  assert.deepEqual(errors, []);
  console.log('PASS reload interruption/retry, narrow composer, Inventory behavior and no browser runtime errors');
} finally {
  for (const { res } of pending) res.destroy();
  await browser.close();
  server.closeAllConnections();
  await new Promise((resolve) => server.close(resolve));
}
